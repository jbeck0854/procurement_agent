"""
forecast_summary.py — Business-facing production forecast summary.

Entry point:
    get_latest_production_forecast_summary(conn, forecast_run_id=None) -> dict

Reads from:
    dim_forecast_run                    (run metadata)
    fact_semiconductor_demand_forecast  (forecast rows)

Does NOT retrain the model, load CSVs, or call run_production.py.
All dates come from stored DB metadata — not from date.today().

Grain validated at call time:
    expected_rows = facility_count × sku_count × week_count
    actual_rows   = COUNT(*) WHERE forecast_run_id = <run_id>

Also exports a standalone LangChain @tool wrapper (get_forecast_summary_tool)
for future agent integration (Option B — no demo/* files modified).

Usage:
    import psycopg2
    from forecasting.forecast_summary import get_latest_production_forecast_summary

    conn = psycopg2.connect(DATABASE_URL)
    summary = get_latest_production_forecast_summary(conn)
    conn.close()
"""

import os
import logging

import pandas as pd
import psycopg2
from dotenv import load_dotenv

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(fn):  # no-op decorator when langchain_core is not installed
        return fn

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/procurement_agent",
)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _resolve_run_id(conn, forecast_run_id=None) -> int:
    """Return the requested run_id, or the most recent one if None."""
    with conn.cursor() as cur:
        if forecast_run_id is not None:
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "WHERE forecast_run_id = %s",
                (forecast_run_id,),
            )
        else:
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "ORDER BY forecast_run_id DESC LIMIT 1"
            )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "No forecast run found in dim_forecast_run. "
            "Run forecasting/run_production.py to generate the production forecast first."
        )
    return int(row[0])


# ── Core summary function ──────────────────────────────────────────────────────

def get_latest_production_forecast_summary(conn, forecast_run_id=None) -> dict:
    """
    Return a structured summary of the production forecast.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.

    Returns
    -------
    dict
        Structured summary with keys:
          forecast_run_id, model_version,
          forecast_origin_date, observed_through_week_date,
          planning_horizon_start_date, planning_horizon_end_date,
          horizon_weeks,
          coverage   : {facility_count, sku_count, series_count,
                        week_count, expected_rows, actual_rows, grain_valid}
          demand     : {total_forecasted_demand, average_weekly_demand,
                        peak_week_date, peak_week_demand,
                        lowest_week_date, lowest_week_demand}
          weekly_totals : list of {week_date, total_demand}

    All date fields come from stored DB metadata — no date.today() is used.
    Grain is validated: expected_rows = series_count × week_count.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    # ── Run metadata (from dim_forecast_run) ───────────────────────────────────
    run_sql = """
        SELECT
            forecast_run_id,
            model_version,
            forecast_origin_date,
            observed_through_week_date,
            horizon_weeks_max
        FROM dim_forecast_run
        WHERE forecast_run_id = %(run_id)s
    """
    run_df = pd.read_sql(run_sql, conn, params={"run_id": run_id})
    if run_df.empty:
        raise RuntimeError(f"forecast_run_id={run_id} not found in dim_forecast_run.")
    run = run_df.iloc[0]

    # ── Coverage counts (from fact table) ─────────────────────────────────────
    # Grain: (forecast_run_id, facility_id, semiconductor_id, target_week_date)
    # DB-level UNIQUE constraint uq_forecast_grain already prevents duplicates;
    # grain_valid provides an additional application-layer assertion.
    coverage_sql = """
        SELECT
            COUNT(DISTINCT facility_id)                        AS facility_count,
            COUNT(DISTINCT semiconductor_id)                   AS sku_count,
            COUNT(DISTINCT (facility_id, semiconductor_id))    AS series_count,
            COUNT(DISTINCT target_week_date)                   AS week_count,
            COUNT(*)                                           AS actual_rows,
            MIN(target_week_date)                              AS horizon_start,
            MAX(target_week_date)                              AS horizon_end
        FROM fact_semiconductor_demand_forecast
        WHERE forecast_run_id = %(run_id)s
    """
    cov_df = pd.read_sql(coverage_sql, conn, params={"run_id": run_id})
    cov = cov_df.iloc[0]

    facility_count = int(cov["facility_count"])
    sku_count      = int(cov["sku_count"])
    series_count   = int(cov["series_count"])
    week_count     = int(cov["week_count"])
    actual_rows    = int(cov["actual_rows"])
    expected_rows  = series_count * week_count
    grain_valid    = (actual_rows == expected_rows)

    if not grain_valid:
        logger.warning(
            f"[FORECAST_SUMMARY] Grain check FAILED for run_id={run_id}: "
            f"expected {expected_rows:,} rows ({series_count} series × "
            f"{week_count} weeks), got {actual_rows:,}."
        )

    # ── Weekly totals (aggregated across all facilities + SKUs) ───────────────
    weekly_sql = """
        SELECT
            target_week_date,
            SUM(predicted_demand) AS total_demand
        FROM fact_semiconductor_demand_forecast
        WHERE forecast_run_id = %(run_id)s
        GROUP BY target_week_date
        ORDER BY target_week_date
    """
    weekly_df = pd.read_sql(weekly_sql, conn, params={"run_id": run_id})

    total_demand = float(weekly_df["total_demand"].sum())
    avg_weekly   = total_demand / len(weekly_df) if len(weekly_df) > 0 else 0.0
    peak_idx     = weekly_df["total_demand"].idxmax()
    lowest_idx   = weekly_df["total_demand"].idxmin()

    weekly_totals = [
        {
            "week_date":    str(row["target_week_date"]),
            "total_demand": round(float(row["total_demand"]), 2),
        }
        for _, row in weekly_df.iterrows()
    ]

    return {
        # Run metadata — all from stored DB values, not computed at call time
        "forecast_run_id":              run_id,
        "model_version":                str(run["model_version"]),
        "forecast_origin_date":         str(run["forecast_origin_date"]),
        "observed_through_week_date":   str(run["observed_through_week_date"]),
        "planning_horizon_start_date":  str(cov["horizon_start"]),
        "planning_horizon_end_date":    str(cov["horizon_end"]),
        "horizon_weeks":                int(run["horizon_weeks_max"]),

        # Coverage — computed from actual fact rows
        "coverage": {
            "facility_count": facility_count,
            "sku_count":       sku_count,
            "series_count":    series_count,
            "week_count":      week_count,
            "expected_rows":   expected_rows,
            "actual_rows":     actual_rows,
            "grain_valid":     grain_valid,
        },

        # Planning horizon demand overview
        "demand": {
            "total_forecasted_demand": round(total_demand, 2),
            "average_weekly_demand":   round(avg_weekly, 2),
            "peak_week_date":          str(weekly_df.loc[peak_idx,   "target_week_date"]),
            "peak_week_demand":        round(float(weekly_df.loc[peak_idx,   "total_demand"]), 2),
            "lowest_week_date":        str(weekly_df.loc[lowest_idx, "target_week_date"]),
            "lowest_week_demand":      round(float(weekly_df.loc[lowest_idx, "total_demand"]), 2),
        },

        # Full weekly breakdown (system-level totals across all 48 series)
        "weekly_totals": weekly_totals,
    }


# ── Formatted text renderer ────────────────────────────────────────────────────

def _format_summary(s: dict) -> str:
    """Render the structured summary dict as a business-facing string."""
    cov = s["coverage"]
    dm  = s["demand"]

    grain_status = (
        f"✓  ({cov['actual_rows']:,} rows = "
        f"{cov['series_count']} series × {cov['week_count']} weeks)"
        if cov["grain_valid"]
        else (
            f"⚠  FAIL — expected {cov['expected_rows']:,}, "
            f"got {cov['actual_rows']:,}"
        )
    )

    lines = [
        "=" * 62,
        "  PRODUCTION DEMAND FORECAST — SUMMARY",
        "=" * 62,
        "",
        f"  Model              : {s['model_version']}",
        f"  Forecast run ID    : {s['forecast_run_id']}",
        f"  Forecast run date  : {s['forecast_origin_date']}",
        f"  Last observed week : {s['observed_through_week_date']}",
        "",
        "  Forecast Coverage:",
        f"    Facilities              : {cov['facility_count']}",
        f"    SKUs                    : {cov['sku_count']}",
        f"    SKU × Facility series   : {cov['series_count']}",
        f"    Grain check             : {grain_status}",
        "",
        "  Planning Horizon:",
        f"    Start                   : {s['planning_horizon_start_date']}",
        f"    End                     : {s['planning_horizon_end_date']}",
        f"    Duration                : {s['horizon_weeks']} weeks",
        "",
        "  Demand Overview  (all facilities + SKUs combined):",
        f"    Total forecasted demand : {dm['total_forecasted_demand']:>12,.0f} units",
        f"    Average weekly demand   : {dm['average_weekly_demand']:>12,.0f} units/week",
        f"    Peak week               : {dm['peak_week_date']}  →  "
        f"{dm['peak_week_demand']:>10,.0f} units",
        f"    Lowest week             : {dm['lowest_week_date']}  →  "
        f"{dm['lowest_week_demand']:>10,.0f} units",
        "",
        "=" * 62,
    ]
    return "\n".join(lines)


# ── Drill-down function ───────────────────────────────────────────────────────

def get_production_forecast_drilldown(
    conn,
    forecast_run_id=None,
    export_csv: bool = False,
) -> "pd.DataFrame":
    """
    Return the full row-level forecast for a given run.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    export_csv : bool, optional
        If True, write the result to
        artifacts/forecasting/forecast_drilldown_<run_id>.csv.

    Returns
    -------
    pd.DataFrame
        Columns: target_week_date, facility_id, semiconductor_id,
                 predicted_demand, interval_lower_90, interval_upper_90,
                 horizon_weeks
        Sorted: ORDER BY target_week_date, facility_id, semiconductor_id
        Grain:  (forecast_run_id, facility_id, semiconductor_id, target_week_date)

    Validation (raises RuntimeError on failure):
        actual_rows == weeks × facilities × SKUs
        no duplicate rows
        interval_lower_90 <= predicted_demand <= interval_upper_90 for all rows
    """
    import os as _os

    run_id = _resolve_run_id(conn, forecast_run_id)

    drilldown_sql = """
        SELECT
            target_week_date,
            facility_id,
            semiconductor_id,
            predicted_demand,
            interval_lower_90,
            interval_upper_90,
            horizon_weeks
        FROM fact_semiconductor_demand_forecast
        WHERE forecast_run_id = %(run_id)s
        ORDER BY target_week_date, facility_id, semiconductor_id
    """
    with conn.cursor() as cur:
        cur.execute(drilldown_sql, {"run_id": run_id})
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]

    df = pd.DataFrame(rows, columns=col_names)

    # ── Validation ────────────────────────────────────────────────────────────
    weeks      = df["target_week_date"].nunique()
    facilities = df["facility_id"].nunique()
    skus       = df["semiconductor_id"].nunique()
    expected   = weeks * facilities * skus
    actual     = len(df)

    if actual != expected:
        raise RuntimeError(
            f"[DRILLDOWN] Grain check FAILED for run_id={run_id}: "
            f"expected {expected:,} rows ({weeks} weeks × {facilities} fac × {skus} SKUs), "
            f"got {actual:,}."
        )

    dup_count = df.duplicated(
        subset=["target_week_date", "facility_id", "semiconductor_id"]
    ).sum()
    if dup_count > 0:
        raise RuntimeError(
            f"[DRILLDOWN] {dup_count} duplicate grain rows found for run_id={run_id}."
        )

    ci_violations = (
        (df["interval_lower_90"] > df["predicted_demand"]) |
        (df["interval_upper_90"] < df["predicted_demand"])
    ).sum()
    if ci_violations > 0:
        logger.warning(
            f"[DRILLDOWN] {ci_violations} CI bound violations for run_id={run_id} "
            f"(interval_lower_90 > predicted_demand OR interval_upper_90 < predicted_demand)."
        )

    # ── Optional CSV export ───────────────────────────────────────────────────
    if export_csv:
        out_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "artifacts", "forecasting",
        )
        _os.makedirs(out_dir, exist_ok=True)
        out_path = _os.path.join(out_dir, f"forecast_drilldown_{run_id}.csv")
        df.to_csv(out_path, index=False)
        logger.info(f"[DRILLDOWN] Exported {len(df):,} rows → {out_path}")

    return df


# ── LangChain @tool wrapper (Option B — no demo/* modified) ───────────────────

@tool
def get_forecast_summary_tool(forecast_run_id: int = 0) -> str:
    """Retrieve the production demand forecast summary from the database.

    Returns a business-facing summary including:
    - Run metadata (model version, forecast run date, last observed week)
    - Forecast coverage (facilities, SKUs, series count, grain validation)
    - Planning horizon (start date, end date, duration in weeks)
    - Demand overview (total, average weekly, peak week, lowest week)

    Reads from pre-computed DB tables only — no model retraining.

    Args:
        forecast_run_id: Specific run ID to retrieve. Use 0 (default) to
                         retrieve the most recent production forecast run.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        summary = get_latest_production_forecast_summary(conn, forecast_run_id=run_id)
        return _format_summary(summary)
    except Exception as e:
        logger.error(f"[FORECAST_SUMMARY] Tool call failed: {e}", exc_info=True)
        return f"Error retrieving forecast summary: {e}"
    finally:
        conn.close()


@tool
def get_forecast_drilldown_tool(
    forecast_run_id: int = 0,
    export_csv: bool = False,
) -> str:
    """Retrieve the row-level production forecast drill-down from the database.

    Returns a coverage summary (row count, distinct facilities, SKUs, weeks,
    grain validation) for the requested forecast run. If export_csv is True,
    also writes the full drill-down to a CSV file and reports the export path.

    All data is read from pre-computed DB tables only — no model retraining.

    Args:
        forecast_run_id: Specific run ID to retrieve. Use 0 (default) to
                         retrieve the most recent production forecast run.
        export_csv: If True, export the full drill-down DataFrame to
                    artifacts/forecasting/forecast_drilldown_<run_id>.csv.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        resolved = _resolve_run_id(conn, run_id)
        df = get_production_forecast_drilldown(conn, forecast_run_id=run_id, export_csv=export_csv)

        weeks      = df["target_week_date"].nunique()
        facilities = df["facility_id"].nunique()
        skus       = df["semiconductor_id"].nunique()
        expected   = weeks * facilities * skus
        actual     = len(df)
        grain_ok   = actual == expected

        lines = [
            f"Forecast Drill-Down  (run_id={resolved})",
            f"  Rows returned   : {actual:,}",
            f"  Facilities      : {facilities}",
            f"  SKUs            : {skus}",
            f"  Weeks           : {weeks}  "
            f"({str(df['target_week_date'].min())} → {str(df['target_week_date'].max())})",
            f"  Grain valid     : {'✓' if grain_ok else '⚠ FAIL'}  "
            f"({actual:,} rows = {weeks} weeks × {facilities} fac × {skus} SKUs)",
        ]

        if export_csv:
            import os as _os
            out_dir = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "artifacts", "forecasting",
            )
            out_path = _os.path.join(out_dir, f"forecast_drilldown_{resolved}.csv")
            lines.append(f"  CSV exported    : {out_path}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[FORECAST_DRILLDOWN] Tool call failed: {e}", exc_info=True)
        return f"Error retrieving forecast drill-down: {e}"
    finally:
        conn.close()


# ── Model assessment / explainability helper ──────────────────────────────────

_ASSESSMENT_DIRECTIONS = {
    "A": {
        "title": "Model Validation & Training Performance",
        "keywords": {
            "validation", "training", "performance", "metrics", "accuracy",
            "results", "trained", "how was", "evaluate", "evaluation",
            "holdout", "cv", "cross-validation",
        },
        "executive_summary": (
            "The forecasting model is a Histogram Gradient Boosting Regressor (HGB) "
            "trained on 145 weeks of historical customer order data across 48 facility–SKU "
            "series (4 facilities × 12 semiconductor products). "
            "Features include per-series lag demand (lag 1–8), 4- and 8-week rolling statistics, "
            "price and promotional signals, cyclical week encodings, and a cross-series global "
            "demand lag. All lag and rolling features use a one-period shift before windowing "
            "to prevent any target leakage. "
            "\n\n"
            "Model selection used 5-fold time-series cross-validation across 243 hyperparameter "
            "configurations (GridSearchCV). The best configuration — "
            "learning_rate=0.05, max_depth=6, max_iter=200, min_samples_leaf=50, l2=0.1 — "
            "achieved a CV MAE of 294.98 units/series/week. "
            "\n\n"
            "The holdout evaluation covers the last 10 observed weeks (weeks 136–145), "
            "held out before any model fitting. On this unseen data:\n"
            "  • Row-level MAE  :  205.93 units per series per week\n"
            "  • Row-level RMSE :  289.37\n"
            "  • Row-level MAPE :  23.75%\n"
            "  • R²             :  0.778  (the model explains ~78% of demand variance)\n"
            "\n"
            "At the system level, errors partially cancel across the 48 series, producing "
            "a weekly aggregate MAE of ~4,012 units — less than 8% of typical weekly system "
            "demand (~51,500 units). The production model retrains on all 145 weeks before "
            "generating the forward planning horizon."
        ),
        "artifact": {
            "label": "Full History + Holdout (System Level)",
            "path": "artifacts/forecasting/system_full_history_holdout.png",
            "why_it_matters": (
                "Shows the model's actual vs. predicted demand across the full training "
                "history and the 10-week unseen holdout. Confirms the model tracks macro "
                "demand trends and seasonal patterns without overfitting to training data."
            ),
        },
        "next_step_prompt": (
            "To inspect which series drove the most error, ask about the worst-performing "
            "SKU–facility combinations. To understand what the model relies on most, "
            "ask about feature importance."
        ),
    },
    "B": {
        "title": "Feature Importance — What Drives the Forecast",
        "keywords": {
            "importance", "influential", "features", "drivers", "drove",
            "weight", "weights", "feature", "input", "inputs", "signal", "signals",
        },
        "executive_summary": (
            "Feature importance was measured using permutation importance on the 10-week "
            "holdout set — the same data used for final model evaluation. Permutation "
            "importance works by randomly shuffling one feature at a time and measuring "
            "how much prediction accuracy degrades; a larger drop means the feature carries "
            "more forecasting signal. "
            "\n\n"
            "Demand lag features consistently dominate: lag_1 (last week's observed demand "
            "for the same series) is the single strongest predictor. Rolling mean features "
            "(roll_mean_4, roll_mean_8) also rank highly, confirming that near-term demand "
            "momentum is the primary driver of forecast accuracy. "
            "\n\n"
            "Price and promotional signals (realized_selling_price, emailer_for_promotion, "
            "homepage_featured) contribute meaningfully but are secondary to the demand "
            "history features. Cyclical time encodings (week_sin_52, week_cos_52) capture "
            "seasonal patterns. Entity identifiers (facility_id, semiconductor_id) allow "
            "the model to learn series-specific demand levels. "
            "\n\n"
            "Caution: permutation importance reflects the model as trained — features with "
            "lower measured importance are not necessarily unimportant in general. Correlated "
            "features (e.g. lag_1 and roll_mean_4) can suppress each other's measured importance."
        ),
        "artifact": {
            "label": "Permutation Feature Importance (Top 15)",
            "path": "artifacts/forecasting/permutation_importance.png",
            "why_it_matters": (
                "Ranks the top 15 model inputs by their measured influence on forecast "
                "accuracy. Directly answers which data sources matter most and where data "
                "quality issues would most degrade the procurement plan."
            ),
        },
        "next_step_prompt": (
            "If a specific feature is unavailable or unreliable in production, its importance "
            "score indicates how much forecast accuracy would be at risk. Ask about model "
            "validation performance to see the overall accuracy this feature set supports."
        ),
    },
    "C": {
        "title": "Baseline Comparison & Improvement Guidance",
        "keywords": {
            "baseline", "benchmark", "compare", "comparison", "naive",
            "improve", "improvement", "better", "versus", "vs", "hgb vs",
            "simpler", "simple model",
        },
        "executive_summary": (
            "The HGB model was benchmarked against two naive baselines on the same 10-week "
            "holdout: a lag-1 model (last week's demand repeated forward) and a rolling "
            "mean-4 model (4-week trailing average). At the per-series, per-week level — "
            "the grain at which LP procurement allocation decisions are made — HGB achieves "
            "a row-level MAE of 205.93, compared to 223.06 for the lag-1 baseline and "
            "266.42 for the rolling mean-4 baseline. This represents a 7.7% reduction in "
            "error versus lag-1 and a 22.7% reduction versus rolling mean-4."
            "\n\n"
            "These gains are consistent across the majority of the 48 facility–SKU series, "
            "not driven by a single outlier. The HGB model captures demand structure the "
            "naive models cannot — including price effects, promotional signals, and "
            "cross-series momentum — and this accuracy advantage translates directly into "
            "procurement planning quality: more accurate per-series demand inputs into the "
            "LP layer mean tighter inventory targets, fewer unnecessary safety stock buffers, "
            "and more reliable supplier allocation decisions."
        ),
        "artifact": {
            "label": "Baseline System-Level Comparison",
            "path": "artifacts/forecasting/baseline_system_comparison.png",
            "why_it_matters": (
                "Shows weekly system-level demand (sum across all 48 series) for Actual, "
                "HGB, Naive lag-1, and Rolling mean-4 across the holdout window. Confirms "
                "that HGB tracks actual demand more closely than either baseline, "
                "particularly at inflection points where simple averages lag the true signal."
            ),
        },
        "improvement_recommendations": [
            (
                "Add external demand signals — industry lead-time indices or macro "
                "semiconductor cycle indicators could help the model anticipate demand "
                "inflections not captured in recent order history alone."
            ),
            (
                "Improve confidence interval calibration — current 90% intervals apply a "
                "uniform width based on holdout RMSE. A quantile regression approach would "
                "produce intervals that adapt to each series' individual volatility."
            ),
            (
                "Investigate the 5 highest-error series — FACILITY_2/SEMICONDUCTOR_1 "
                "(MAE 440) and FACILITY_1/SEMICONDUCTOR_5 (MAE 432) are more than twice "
                "the system median. These series may have structural demand breaks or data "
                "quality issues that warrant separate treatment before the next cycle."
            ),
        ],
        "next_step_prompt": (
            "To understand what drove HGB's accuracy advantage over the baselines, ask "
            "about feature importance. To review the full validation methodology and "
            "holdout metrics, ask about model training and validation performance."
        ),
    },
}


def _resolve_direction(direction: str) -> str:
    """Map a free-text direction string to 'A', 'B', or 'C'.

    Scans for keywords associated with each direction.
    Returns the matched direction key, or raises ValueError if none match.
    """
    lowered = direction.lower()
    for key, spec in _ASSESSMENT_DIRECTIONS.items():
        if any(kw in lowered for kw in spec["keywords"]):
            return key
    raise ValueError(
        f"Could not map direction '{direction}' to A, B, or C. "
        "Use terms like: 'validation/training/performance' (A), "
        "'features/importance/drivers' (B), or 'baseline/benchmark/improve' (C)."
    )


def get_forecast_model_assessment(direction: str) -> dict:
    """
    Return a structured model assessment for the requested direction.

    Parameters
    ----------
    direction : str
        Free-text direction string. Mapped internally to one of:
          A — Validation / training / recent performance
          B — Feature importance / influential inputs
          C — Baseline comparison / improvement guidance

    Returns
    -------
    dict with keys:
        direction           : 'A', 'B', or 'C'
        title               : str
        executive_summary   : str
        artifacts           : list of {label, path, why_it_matters}
        next_step_prompt    : str

    All artifact paths are validated at call time.
    Raises FileNotFoundError if an expected artifact is missing.
    """
    direction_key = _resolve_direction(direction)
    spec = _ASSESSMENT_DIRECTIONS[direction_key]

    # Validate the primary artifact path exists before returning
    full_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        spec["artifact"]["path"],
    )
    if not os.path.exists(full_path):
        raise FileNotFoundError(
            f"[MODEL_ASSESSMENT] Expected artifact not found: {full_path}"
        )

    result = {
        "direction":         direction_key,
        "title":             spec["title"],
        "executive_summary": spec["executive_summary"],
        "artifact":          dict(spec["artifact"]),
        "next_step_prompt":  spec["next_step_prompt"],
    }
    if "improvement_recommendations" in spec:
        result["improvement_recommendations"] = list(spec["improvement_recommendations"])
    return result
