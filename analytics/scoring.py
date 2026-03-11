from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .calibration import calibrate_decision_tiers

# ================================
# Helper utilities
# These functions perform small, focused tasks used repeatedly
# throughout the scoring pipeline. They are kept separate to 
# make the main scoring logic easier to read and debug.
# ================================

# Columns that are optional for explainability only.
# Missing them should never block scoring.


def _require_columns(df: pd.DataFrame, cols: list[str]) -> None: 
    # () -> None is a type hint indicating this function does not return anything meaningful
    # This function expects df to be a pandas DataFrame and cols to be a list of strings representing column names.
    # It checks if all the specified columns are present in the DataFrame, and if not, it raises a ValueError with a message listing the missing columns.
    """
    Ensure the input DataFrame contains all required columns.
    If any are missing, fail early with a clear error message."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for scoring: {missing}")


def _clip_series(s: pd.Series, q_low: float, q_high: float) -> pd.Series:
    """
    Clip the values of a pandas Series to the specified quantile range.
    Values below the lower quantile are set to the lower quantile,
    and values above the upper quantile are set to the upper quantile.
    """
    if s.dropna().empty:
        # return original seriesif all values are NaN (to avoid errors in quantile calculation)
        return s
    lo = s.quantile(q_low) 
    # findings the q_low-th quantile value in the series, 
    # which will be used as the lower bound for clipping.
    hi = s.quantile(q_high)
    return s.clip(lower=lo, upper=hi)


def _minmax(s: pd.Series, eps: float = 1e-9) -> pd.Series:
    """
    Normalizes a numeric series to the 0-1 range.
    eps prevents division by zero when all values are identical.
    """
    s_nonnull = pd.to_numeric(s, errors="coerce").astype(float)
    # Convert the input series to numeric, coercing errors (e.g., strings) to NaN, and then to float type. 
    # This ensures that the series is in a suitable format for min-max normalization.
    mn = s_nonnull.min()
    mx = s_nonnull.max()
    return (s_nonnull - mn) / ((mx - mn) + eps)


def _normalize(
    df: pd.DataFrame,
    col: str, # the name of the column to normalize e.g., "lead_time_mean"
    scope_cols: list[str] | None, # columns that define the scope of normalization (e.g., ["product"] for by-product normalization)
    method: str,
    eps: float,
    clip_enabled: bool,
    q_low: float,
    q_high: float,
) -> pd.Series:
    """
    Normalize a column either globally or within groups (e.g., by product) using the specified method (e.g., min-max).
    Normalization rules come directly from the metric contract YAML, allowing for flexible configuration without code changes.

    This is used so suppliers can be compared fairly within the same product category (or across full dataset if contract modified)
    """

    def _norm_series(s: pd.Series) -> pd.Series:
        """
        Normalize one pandas Series.
        This helper is reused for both global and group normalization depending on the scope defined in the contract.
        """
        s = pd.to_numeric(s, errors="coerce").astype(float) # ensure the series is numeric and of float type for accurate normalization calculations. Non-numeric values will be converted to NaN.

        if clip_enabled:
            s = _clip_series(s, q_low, q_high) # if clipping is enabled in the contract, we apply quantile-based clipping to the series before normalization. This helps to mitigate the influence of outliers on the normalization process by capping values at specified lower and upper quantiles.
        
        if method == "minmax":
            return _minmax(s, eps) # if the normalization method specified in the contract is "minmax", we apply min-max normalization to the series using the _minmax helper function. This scales the values to a 0-1 range based on the minimum and maximum values in the series, with an epsilon added to prevent division by zero when all values are identical.
        
        raise ValueError(f"Unsupported normalization method: {method}") # if the method specified in the contract is not recognized, we raise a ValueError to indicate that the normalization method is unsupported. This ensures that any misconfiguration in the contract is caught early with a clear error message.
    
    # If scope_cols is defined (e.g., ["product"]), we perform normalization within each group defined by those columns. Otherwise, we normalize across the entire dataset.
    if scope_cols:
        return df.groupby(scope_cols)[col].transform(_norm_series) # if scope_cols is provided, we group the DataFrame by those columns and apply the _norm_series function to the specified column within each group. The transform method ensures that the normalized values are aligned with the original DataFrame's index, allowing us to return a Series of normalized values that corresponds to each row in the original DataFrame.
    
    # Otherwise, we normalize the entire column without grouping.
    return _norm_series(df[col]) # if scope_cols is not provided, we simply apply the _norm_series function to the entire specified column of the DataFrame, resulting in a Series of normalized values for that column across all rows.


def _bulk_price(
    baseline_price: pd.Series,
    bulk_discount: pd.Series,
    bulk_units: pd.Series,
    Q: int,
) -> pd.Series:
    """
    Compute the effective unit price after applying bulk discounts.
    If the order quantity Q meets the supplier's bulk threshold, apply the discount; otherwise,
    use the baseline price.
    """
    apply_discount = Q >= pd.to_numeric(bulk_units, errors="coerce").astype(float)
    base = pd.to_numeric(baseline_price, errors="coerce").astype(float)
    disc = pd.to_numeric(bulk_discount, errors="coerce").astype(float)
    return pd.Series(
        np.where(apply_discount, base * (1.0 - disc), base),
        index=baseline_price.index,
        dtype=float,
    )





# ================================
# Contract loader
# Wraps the YAML file so the scorer can read configuration
# cleanly and consistently.
# ================================

@dataclass(frozen=True, slots=True) # frozen=True makes the dataclass immutable after creation, which is good for configuration objects that should not change. slots=True stored attributes in a fixed structure which optimizes memory usage by preventing the creation of __dict__ for each instance, which can be beneficial when creating many instances or when immutability is desired.
# @dataclass is a decorator that automatically generates special methods like __init__() and __repr__() for the class, based on the defined fields. This makes it easier to create classes that are primarily used to store data, such as configuration objects.
class MetricContract:
    raw: dict[str, Any] 
    # MetricContract has a single field raw, which is a dictionary that can contain any keys and values. This dictionary will hold the entire contents of the YAML contract, allowing the class to provide structured access to specific parts of the configuration through properties.

    @property # @property is a decorator that allows you to define a method that can be called/accessed like an attribute. This is useful for providing read-only access to certain parts of the raw configuration while still allowing for any necessary processing or validation when accessing those parts.
    def required_columns(self) -> list[str]: # after the method definition, you can access this as contract.required_columns instead of contract.required_columns() to get the list of required columns from the contract.
        return self.raw["data_requirements"]["required_columns"] # This property accesses the raw dictionary to retrieve the list of required columns specified under the data_requirements section of the YAML contract. It assumes that the YAML structure includes a data_requirements key with a nested required_columns key that contains a list of column names.
    
    @property
    def optional_columns(self) -> list[str]:
        return self.raw['data_requirements'].get('optional_columns', []) # This property retrieves the list of optional columns from the raw dictionary. It uses the get method to safely access the optional_columns key, providing an empty list as a default value if the key is not present in the YAML contract. This allows for flexibility in the contract definition, where optional columns can be omitted without causing errors when accessing this property.

    @property
    def null_policy(self) -> dict[str, Any]: # describes structure of the null_policy dictionary and what to expect as a return. keys are strings and values can be of any type (e.g., values could be lists, strings, dictionaries, etc)
        return self.raw["data_requirements"]["null_policy"]

    @property
    def tariff_policy(self) -> dict[str, Any]:
        return self.raw["data_requirements"].get("tariff_policy", {}) # return the value for the tariff_policy key (its dictionary), if the key doesn't exist, return {}

    @property
    def normalization(self) -> dict[str, Any]: 
        # describes the expected structure of the normalization configuration in the YAML contract. It indicates that when you access the normalization property, you will get a dictionary that contains the normalization settings defined in the contract. The keys and values of this dictionary can be of any type, depending on how the normalization is configured in the YAML file.
        return self.raw["normalization"]

    @property
    def constraints(self) -> dict[str, Any]:
        return self.raw.get("constraints", {})

    @property
    def metrics(self) -> dict[str, Any]:
        return self.raw.get("metrics", {})

    @property
    def ranking(self) -> dict[str, Any]:
        return self.raw.get("ranking", {})

    @property
    def explainability(self) -> dict[str, Any]:
        return self.raw.get("explainability", {})

    @property
    def assumptions(self) -> dict[str, Any]:
        return self.raw.get("assumptions", {})

    @property
    def version(self) -> str | None:
        return self.raw.get("version")


def load_contract(path: str) -> MetricContract:
    """
    Load the metric contract YAML file from disk.
    The contract defines all scoring rules and ensures the 
    scoring engine stays fully configuration-driven.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError("metric_contract.yaml must parse to a dictionary at the root.")
    return MetricContract(raw=raw)


# ===============================
# Core scoring engine
# This class performs the full scoring workflow:
# - validate input
# - apply contract rules (null policy, compliance gate)
# - compute metrics (base and composite)
# - normalize values as needed
# - build composite scores from components using contract-defined weights
# - rank suppliers
# - return explainability fields as configured in the contract
# ===============================

@dataclass(slots=True)
class ScoreResult:
    ranked: pd.DataFrame # The ranked DataFrame contains the final scored and ranked supplier data, including any fields specified for explainability in the contract. This is the main output of the scoring process that will be used for decision-making.
    dropped_rows: pd.DataFrame # The dropped_rows DataFrame contains all rows that were excluded from scoring due to the null policy or compliance gate. Also provides reason (e.g., missing unit_cost). This serves as an audit trail for transparency and debugging. It indicates exactly which suppliers were dropped and why.
    warnings: list[str] 

# example: result = ScoreResult(ranked=ranked_df, dropped_rows=dropped_df, warnings=wraning_list)
# Reults accessed using e.g., result.ranked, result.dropped_rows, result.warnings

class SupplierScorer:
    def __init__(self, contract: MetricContract):
        self.c = contract

    def _required_non_optional(self) -> list[str]:
        """
        Return required columns excluding optional columns defined in the contract
        This ensures missing explainability columns do not block scoring, while still enforcing all other required fields are present."""
        optional = set(self.c.optional_columns)
        return [c for c in self.c.required_columns if c not in optional]

    def _norm_cfg(self) -> tuple[list[str] | None, str, float, bool, float, float]:
        """
        Read normalization configuration setting from the contract.
        These settings control how all normalized metrics behave.
        """
        norm_cfg = self.c.normalization
        scope = norm_cfg.get("scope", "by_product")
        scope_cols = ["product"] if scope == "by_product" else None
        method = norm_cfg.get("method", "minmax")
        eps = float(norm_cfg.get("epsilon", 1e-9))
        clip_cfg = norm_cfg.get("clip", {})
        clip_enabled = bool(clip_cfg.get("enabled", True))
        q_low = float(clip_cfg.get("lower_quantile", 0.01))
        q_high = float(clip_cfg.get("upper_quantile", 0.99))
        return scope_cols, method, eps, clip_enabled, q_low, q_high

    def _tariff_cfg(self) -> tuple[bool, str, float]:
        """
        Read tariff settings from the contract.
        Determines whether tariffs are applied and how missing values behave.
        """
        enabled = bool(self.c.assumptions.get("tariff", {}).get("enabled", False))
        rate_field = self.c.tariff_policy.get("rate_field", "mfn_text_rate_pct")
        default_pct = float(self.c.tariff_policy.get("missing_rate_default_pct", 0.0))
        return enabled, rate_field, default_pct

    def _metric(self, name: str) -> dict[str, Any]:
        """
        Retrieve a metric definition from the contract.
        If missing, fail early with a clear error.
        """
        m = self.c.metrics.get(name)
        if not isinstance(m, dict):
            raise ValueError(f"Contract missing metrics.{name}")
        return m

    def score(
        self,
        df: pd.DataFrame,
        Q: int = 5000, # default order quantity for bulk discount calculation; can be overridden at runtime
        lambda_risk: float | None = None,
        top_k: int | None = None,
    ) -> ScoreResult:
        """
        Main scoring function.
        Applies the full contract-driven scoring pipeline to the input DataFrame and returns ranked results, dropped rows for audit, and any warnings.
        """
        warnings: list[str] = [] # This list will collect any warnings generated during the scoring process, such as rows dropped due to null values or compliance gate failures. These warnings can be returned as part of the ScoreResult to provide transparency about any data issues or exclusions that occurred during scoring.
        # also tells the user that the variable (warnings) will be a list of strings

        # ------------------------------------------
        # contract version sanity check
        # ------------------------------------------
        if self.c.version and self.c.version != "1.0":
            warnings.append(f"Metric contract version mismatch: {self.c.version} (expected 1.0).")

        # ------------------------------------------
        # Validate schema (do NOT require explainability-only columns)
        # ------------------------------------------
        _require_columns(df, self._required_non_optional())

        # -----------------------------------------
        # Null policy (from YAML) + audit reason
        # -----------------------------------------
        # Rows missing critical fields are removed before scoring.
        null_policy = self.c.null_policy
        if null_policy.get("strategy") != "drop_row":
            raise ValueError(f"Unsupported null policy strategy: {null_policy.get('strategy')}")

        cols = null_policy.get("columns", [])
        dropped = df[df[cols].isna().any(axis=1)].copy()
        kept = df.drop(index=dropped.index).copy()

        if not dropped.empty:
            dropped["drop_reason"] = "null_policy_drop_row"
            warnings.append(f"Dropped {len(dropped)} rows due to nulls in null_policy columns: {cols}")

        df = kept

        # -----------------------------------------
        # Compliance gate (from YAML) + audit reason
        # -----------------------------------------
        # Removes suppliers that fail minimum compliance threshold requirements.
        gate = self.c.constraints.get("compliance_gate", {})
        if gate.get("enabled", False):  # if true, apply the compliance gate filter; if false or missing, skip this step and mark all as eligible
            field = gate["field"]
            thresh = float(gate["threshold"])
            eligible_mask = pd.to_numeric(df[field], errors="coerce").astype(float) >= thresh
            df["is_eligible"] = eligible_mask

            ineligible = df[~eligible_mask].copy()
            if not ineligible.empty: # if there are any rows that do not meet the compliance gate threshold, block is executed 
                ineligible["drop_reason"] = "gate:compliance_gate"
                warnings.append(f"Excluded {len(ineligible)} rows due to compliance (governance + customs) gate < {thresh}).")

            df = df[eligible_mask].copy() # filter the DataFrame to only include rows that meet the compliance gate threshold, and create a copy of this filtered DataFrame for further processing. This step effectively removes any suppliers that do not meet the specified compliance requirements from the scoring process.
        else:
            df["is_eligible"] = True # if compliance gate is not enabled in the contract, we mark all rows as eligible by settings is_eligible to True for all rows.
            ineligible = df.iloc[0:0].copy() # create an empty ineleginle DataFrame so the code doesn't break.

        if df.empty: # if there are no rows left after applying the null policy and compliance gate filters, we create an empty ranked DataFrame with the expected columns and return it along with any dropped rows and warnings. This ensures that the function can still return a valid ScoreResult even when there are no eligible suppliers to score.
            out = pd.DataFrame(columns=["supplier_id", "product", "risk_penalty", "risk_adjusted_cost"])
            dropped_all = pd.concat([dropped, ineligible], axis=0) if (not dropped.empty or not ineligible.empty) else pd.DataFrame()
            return ScoreResult(ranked=out, dropped_rows=dropped_all, warnings=warnings)

        # -----------------------------------------
        # Compute base/derived metrics YAML (same formulas as defined in the contract, but now contract-aligned)
        # -----------------------------------------
        # lead_time_cv
        df["lead_time_cv"] = pd.to_numeric(df["lead_time_stddev"], errors="coerce").astype(float) / (
            pd.to_numeric(df["lead_time_mean"], errors="coerce").astype(float) + 1e-9
        )

        # raw risks
        df["risk_disruption"] = pd.to_numeric(df["disruption_probability"], errors="coerce").astype(float)
        df["risk_quality"] = pd.to_numeric(df["probability_of_defect"], errors="coerce").astype(float)
        df["risk_cost_instability"] = pd.to_numeric(df["price_volatility"], errors="coerce").astype(float)

        # risk_logistics = 1 - logistics_reliability (inverse of reliability)
        df["risk_logistics"] = 1.0 - pd.to_numeric(df["logistics_reliability"], errors="coerce").astype(float)

        # ----------------------------------------
        # Normalization settings as defined in the YAML contract
        # ----------------------------------------
        scope_cols, method, eps, clip_enabled, q_low, q_high = self._norm_cfg()
        
        # ---- Lead-time Composite metrics (from YAML) ----
        # risk_leadtime composite (from YAML components)
        # components:
        #   - lead_time_mean weight .70 normalize true
        #   - lead_time_cv   weight .30 normalize true
        df["lead_time_mean_norm"] = _normalize(df, "lead_time_mean", scope_cols, method, eps, clip_enabled, q_low, q_high)
        df["lead_time_cv_norm"] = _normalize(df, "lead_time_cv", scope_cols, method, eps, clip_enabled, q_low, q_high)
        df["risk_leadtime"] = 0.70 * df["lead_time_mean_norm"] + 0.30 * df["lead_time_cv_norm"]

        # --------------------------------------------
        # effective_unit_price (bulk discount logic defined in YAML)
        # --------------------------------------------
        df["effective_unit_price"] = _bulk_price(df["baseline_price"], df["bulk_discount"], df["bulk_units"], Q) # Q will hold how many units purchased

        # landed_unit_cost (tariff enabled cost logic aka rate defaults from tariff_policy)
        tariff_enabled, rate_field, missing_default = self._tariff_cfg()
        if tariff_enabled:
            # if field missing, treat as default for demo stability
            if rate_field in df.columns:
                df["tariff_rate"] = pd.to_numeric(df[rate_field], errors="coerce").fillna(missing_default).astype(float)
            else:
                df["tariff_rate"] = missing_default
            df["landed_unit_cost"] = pd.to_numeric(df["effective_unit_price"], errors="coerce").astype(float) * (1.0 + df["tariff_rate"])
        else:
            df["tariff_rate"] = 0.0
            df["landed_unit_cost"] = pd.to_numeric(df["effective_unit_price"], errors="coerce").astype(float)
        
        # ---------------------------------------------
        # Normalize components used in composites (driven by YAML flags)
        # ---------------------------------------------
        df["risk_quality_norm"] = _normalize(df, "risk_quality", scope_cols, method, eps, clip_enabled, q_low, q_high)
        df["landed_unit_cost_norm"] = _normalize(df, "landed_unit_cost", scope_cols, method, eps, clip_enabled, q_low, q_high)

        # ---------------------------------------------
        # risk_penalty from YAML metrics.risk_penalty.components
        # ---------------------------------------------
        risk_penalty_def = self._metric("risk_penalty")
        comps = risk_penalty_def.get("components", []) # becomes list  of 5 dictionaries, each with metric, weight, and normalize keys based on the YAML contract definition for risk_penalty
        if not comps:
            raise ValueError("metrics.risk_penalty.components missing/empty in contract")

        risk_penalty_0_1 = pd.Series(0.0, index=df.index, dtype=float) # initialize an empty Series to hold the cumulative risk penalty, starting at 0 for all suppliers. This Series will be updated iteratively as we add each component's contribution to the overall risk penalty.
        for comp in comps: # iterate over each component defined in the risk_penalty composite metric in the YAML contract. Each component specifies a metric to include, its weight in the overall score, and whether it should be normalized. This loop will calculate the contribution of each component to the final risk_penalty based on these specifications.
            m = comp["metric"]
            w = float(comp["weight"])
            norm = bool(comp.get("normalize", False))

            if m not in df.columns:
                raise ValueError(f"risk_penalty component metric missing: {m}") # if SQL view forgot to include a required metric, scorer fails ealy with a clear error.

            s = pd.to_numeric(df[m], errors="coerce").astype(float) # extract the metric column specified by the component, convert it to numeric (coercing errors to NaN), and ensure it's of float type for accurate calculations. This prepares the metric data for normalization and weighting as part of the risk score calculation.

            if norm:
                tmp = df[["product"]].copy() if scope_cols else pd.DataFrame(index=df.index) # if normalization is scoped by product, we create a temporary DataFrame that includes the product column to use as the grouping key for normalization. If there is no scope (i.e., global normalization), we create an empty DataFrame with the same index as df to pass to the normalization function.
                tmp["_tmp"] = s # we add the metric series s to the temporary DataFrame under the column name "_tmp". This allows us to pass this DataFrame to the _normalize function, which expects a DataFrame input. The _normalize function will then normalize the "_tmp" column according to the specified scope and method.
                s = _normalize(tmp, "_tmp", scope_cols, method, eps, clip_enabled, q_low, q_high)

            risk_penalty_0_1 = risk_penalty_0_1 + w * s # we update the cumulative risk penalty by adding the weighted contribution of the current component. The metric value s (normalized if specified) is multiplied by its weight w and added to the existing risk_penalty_0_1 Series. This process is repeated for each component, resulting in a final risk_penalty_0_1 that represents the combined risk penalty based on all specified components and their weights.

        df["risk_penalty"] = (100.0 * risk_penalty_0_1).clip(lower=0.0, upper=100.0) # after calculating the cumulative risk penalty as a value between 0 and 1, we scale it to a 0-100 range by multiplying by 100. We then apply clipping to ensure that the final risk_penalty values do not exceed the bounds of 0 and 100, which provides a more interpretable risk penalty for decision-makers.
        df["risk_penalty_norm"] = _normalize(df, "risk_penalty", scope_cols, method, eps, clip_enabled, q_low, q_high) # we also create a normalized version of the risk_penalty within product groups, which can be used in composite metrics that require normalized inputs. This ensures consistency in how the risk_penalty is incorporated into other calculations, such as the risk_adjusted_cost, based on the normalization settings defined in the contract.

        # ---------------------------------------------
        # risk_adjusted_cost from YAML metrics.risk_adjusted_cost.components (+ __LAMBDA_RISK__)
        # ---------------------------------------------
        rac_def = self._metric("risk_adjusted_cost")
        rac_comps = rac_def.get("components", [])
        if not rac_comps:
            raise ValueError("metrics.risk_adjusted_cost.components missing/empty in contract")

        # default lambda from YAML if not provided
        if lambda_risk is None:
            lambda_risk = float(rac_def.get("params", {}).get("lambda_risk", 0.50))
        lam = float(lambda_risk)

        total = pd.Series(0.0, index=df.index, dtype=float)

        for comp in rac_comps: # iterate over each component defined in the risk_adjusted_cost composite metric in the YAML contract. Each component specifies a metric to include, its weight (which can be a fixed value or the special placeholder __LAMBDA_RISK__), and whether it should be normalized. This loop will calculate the contribution of each component to the final risk_adjusted_cost based on these specifications.
            m = comp["metric"]
            w_raw = comp["weight"]
            norm = bool(comp.get("normalize", False))

            w = lam if (isinstance(w_raw, str) and w_raw == "__LAMBDA_RISK__") else float(w_raw)
            # w is determined by checking if the weight specified in the component is the special string "__LAMBDA_RISK__". If it is, we use the value of lam (which is set to lambda_risk, either from the function argument or the contract default). If the weight is not the special placeholder, we convert it to a float and use that as the weight. This allows for dynamic weighting of the risk component in the risk_adjusted_cost calculation based on a runtime parameter, while still supporting fixed weights for other components.

            if m not in df.columns:
                raise ValueError(f"risk_adjusted_cost component metric missing: {m}")

            s = pd.to_numeric(df[m], errors="coerce").astype(float)

            if norm:
                tmp = df[["product"]].copy() if scope_cols else pd.DataFrame(index=df.index) # series of product groups/labels for normalization scope if by_product, otherwise empty DataFrame with same index as df
                tmp["_tmp"] = s # add the metric series s to the temporary DataFrame under the column name "_tmp" for normalization
                s = _normalize(tmp, "_tmp", scope_cols, method, eps, clip_enabled, q_low, q_high)

            total = total + w * s # we update the cumulative risk-adjusted cost by adding the weighted contribution of the current component. The metric value s (normalized if specified) is multiplied by its weight w and added to the existing total Series. This process is repeated for each component, resulting in a final total that represents the combined risk-adjusted cost based on all specified components and their weights.

        df["risk_adjusted_cost"] = total

        # call the calibrate_decision_tiers function from calibration.py
        df = calibrate_decision_tiers(df)


        # ---------------------------------------------
        # Ranking logic (already contract-driven)
        # Sort suppliers using the contract-defined primary metric
        # and tie-breakers, and return the top K results as specified at runtime or by default in the contract.
        # ---------------------------------------------
        rank_cfg = self.c.ranking
        if not rank_cfg.get("enabled", True):
            warnings.append("Ranking disabled in contract; returning unranked results.")
            ranked = df.copy()
        else:
            if top_k is None:
                top_k = int(rank_cfg.get("top_k_default", 5))

            primary_metric = rank_cfg.get("primary_metric", "risk_adjusted_cost")
            primary_ascending = bool(rank_cfg.get("ascending", True))

            sort_cols: list[str] = [primary_metric]
            ascending: list[bool] = [primary_ascending]

            for tb in rank_cfg.get("tie_breakers", []):
                sort_cols.append(tb["metric"])
                ascending.append(bool(tb.get("ascending", True)))

            # deterministic final tie-break
            if "supplier_id" in df.columns and "supplier_id" not in sort_cols:
                sort_cols.append("supplier_id")
                ascending.append(True)

            ranked = df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True).head(top_k).copy()

        # ---------------------------------------------
        # Explainability (contract-driven)
        # ---------------------------------------------
        exp_cfg = self.c.explainability
        if exp_cfg.get("enabled", False):

            # -----------------------------------------
            # 1. RAC-level explainability (top_drivers)
            # -----------------------------------------
            if exp_cfg.get("driver_method") in ("largest_weighted_components", "both"):
                top_n = int(exp_cfg.get("driver_count", 3))
                primary = rank_cfg.get("primary_metric", "risk_adjusted_cost")

                if primary == "risk_adjusted_cost":
                    contrib = pd.DataFrame(index=ranked.index)

                    for comp in rac_comps:
                        m = comp["metric"]
                        w_raw = comp["weight"]
                        norm = bool(comp.get("normalize", False))
                        w = lam if (isinstance(w_raw, str) and w_raw == "__LAMBDA_RISK__") else float(w_raw)

                        s = pd.to_numeric(ranked[m], errors="coerce").astype(float)
                        if norm:
                            tmp = ranked[["product"]].copy() if scope_cols else pd.DataFrame(index=ranked.index)
                            tmp["_tmp"] = s
                            s = _normalize(tmp, "_tmp", scope_cols, method, eps, clip_enabled, q_low, q_high)

                        contrib[m] = w * s

                    ranked["top_adjusted_cost_drivers"] = contrib.apply(
                        lambda row: row.sort_values(ascending=False).head(top_n).index.tolist(),
                        axis=1
                    )

            # -----------------------------------------
            # 2. Nested explainability (top_risk_drivers)
            # -----------------------------------------
            if exp_cfg.get("driver_method") in ("nested_components", "both"):
                top_n = int(exp_cfg.get("driver_count", 3))
                primary = rank_cfg.get("primary_metric", "risk_adjusted_cost")

                comps = self._metric(primary)["components"]

                expanded = []
                for comp in comps:
                    metric_name = comp["metric"]
                    metric_def = self._metric(metric_name)

                    if metric_def.get("type") == "composite":
                        for sub in metric_def["components"]:
                            expanded.append(sub)
                    else:
                        expanded.append(comp)

                contrib_nested = pd.DataFrame(index=ranked.index)

                for comp in expanded:
                    m = comp["metric"]
                    w_raw = comp["weight"]
                    norm = bool(comp.get("normalize", False))
                    w = lam if (isinstance(w_raw, str) and w_raw == "__LAMBDA_RISK__") else float(w_raw)

                    s = pd.to_numeric(ranked[m], errors="coerce").astype(float)
                    if norm:
                        tmp = ranked[["product"]].copy() if scope_cols else pd.DataFrame(index=ranked.index)
                        tmp["_tmp"] = s
                        s = _normalize(tmp, "_tmp", scope_cols, method, eps, clip_enabled, q_low, q_high)

                    contrib_nested[m] = w * s

                ranked["top_risk_drivers"] = contrib_nested.apply(
                    lambda row: row.sort_values(ascending=False).head(top_n).index.tolist(),
                    axis=1
                )

            # --------------------------------------


            # ------------------------------
            # Return fields exactly as YAML says (raw + derived), with YAML labels
            # ------------------------------
            ret = exp_cfg.get("return_fields", {}) # raw and derived as keys, list of fields to return as values
            out_cols: list[str] = [] # initialize an empty list to hold the column names that will be included in the final output DataFrame based on the explainability configuration defined in the YAML contract. This list will be populated with the original column names from the ranked DataFrame that correspond to the fields specified in the explainability return_fields section of the contract.
            rename: dict[str, str] = {} # initialize an empty dictionary to hold the mapping of original column names to their corresponding labels as specified in the YAML contract. This will be used to rename the columns in the final output DataFrame according to the explainability configuration defined in the contract.

            for section in ("raw", "derived"): # iterate over the "raw" and "derived" sections of the explainability return_fields configuration in the YAML contract. Each section contains a list of fields that should be included in the output for explainability purposes. This loop allows us to process both raw input fields and derived metric fields as specified in the contract.
                for item in ret.get(section, []):
                    # item is {src: Label} e.g., {supplier_id: "Supplier ID"}
                    if isinstance(item, dict):
                        for src, label in item.items():
                            if src in ranked.columns: # only include the column if it exists in the ranked DataFrame (e.g., if SQL view included it, or if it's a derived metric we calculated); this prevents errors if the contract asks for explainability fields that aren't present
                                out_cols.append(src)
                                rename[src] = str(label) 

            # remove duplices while preserving order (e.g., if same field included in raw and derived, which can happen if a metric is both an input and a component of a composite, like landed_unit_cost)
            out_cols = list(dict.fromkeys(out_cols))

            ranked_out = ranked[out_cols].rename(columns=rename) if out_cols else ranked.copy() # selects columns list in out_cols and renames them using the new labels

            #if "top_drivers" in ranked.columns:
            #    ranked_out["TopDrivers"] = ranked["top_drivers"].astype(object).values

            ranked = ranked_out

        # -----------------------------------------------
        # Collect dropped rows (audit)
        # -----------------------------------------------
        dropped_rows = pd.concat([dropped, ineligible], axis=0) if (not dropped.empty or not ineligible.empty) else pd.DataFrame()
        # merges rows dropped due to null policy and compliance gate into a single DataFrame for audit purposes. If there are no dropped rows from either reason, it creates an empty DataFrame instead.

        return ScoreResult(ranked=ranked, dropped_rows=dropped_rows, warnings=warnings)


if __name__ == "__main__": # only run this block if the script is executed directly (e.g., python scoring.py), not when imported as a module.
    contract = load_contract("analytics/metric_contract.yaml") # loads YAML contract
    scorer = SupplierScorer(contract) # instantiates scorer with the contract

    # df should come from SQL view vw_supplier_complete_profile
    # df = pd.read_csv("debug_join_output.csv") <-- developer convenience for tester scorer without connecting to SL, load a CSV dump of the expected SQL view.
    # result = scorer.score(df, Q=6000, lambda_risk=0.6, top_k=5) <-- example usage to run the scorer, override A and lambda etc
    # print(result.warnings)
    # print(result.ranked.head())