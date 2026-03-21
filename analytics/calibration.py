import math
from typing import Sequence

import pandas as pd


GLOBAL_TIER_LABELS = ["Preferred", "Acceptable", "Avoid"]


def _stable_sort_group(group: pd.DataFrame) -> pd.DataFrame:
    """
    Stable ascending sort by risk_adjusted_cost, with supplier_id as tiebreaker
    when available.
    """
    group = group.copy()

    sort_cols = ["risk_adjusted_cost"]
    ascending = [True]

    if "supplier_id" in group.columns:
        sort_cols.append("supplier_id")
        ascending.append(True)

    return group.sort_values(sort_cols, ascending=ascending).reset_index(drop=False)


def _assign_global_tiers(group: pd.DataFrame) -> pd.DataFrame:
    """
    Assign global tiers within a product universe.

    Rules:
    - 1 supplier  -> Preferred
    - 2 suppliers -> best Preferred, worst Avoid
    - 3+ suppliers -> top / middle / bottom thirds
    """
    ranked = _stable_sort_group(group)
    n = len(ranked)

    if n == 1:
        ranked["decision_tier_global"] = "Preferred"

    elif n == 2:
        ranked["decision_tier_global"] = ["Preferred", "Avoid"]

    else:
        preferred_count = math.ceil(n / 3)
        avoid_count = math.ceil(n / 3)
        acceptable_count = n - preferred_count - avoid_count

        tiers = (
            ["Preferred"] * preferred_count
            + ["Acceptable"] * acceptable_count
            + ["Avoid"] * avoid_count
        )

        ranked["decision_tier_global"] = tiers[:n]

    ranked = ranked.set_index("index").sort_index()
    return ranked


def _assign_local_comparison_tiers(
    group: pd.DataFrame,
    local_supplier_ids: Sequence[str] | None,
) -> pd.DataFrame:
    """
    Assign local comparison tiers only within the selected comparison set.

    Rules:
    - None / empty / 1 selected supplier -> None
    - 2 selected suppliers -> Better of Compared Set / Worse of Compared Set
    - 3+ selected suppliers -> Best / Middle / Worst of Compared Set
    """
    out = group.copy()
    out["decision_tier_local"] = None

    if not local_supplier_ids:
        return out

    local_ids = set(local_supplier_ids)
    local = out[out["supplier_id"].isin(local_ids)].copy()

    if local.empty or len(local) <= 1:
        return out

    ranked = _stable_sort_group(local)
    n = len(ranked)

    if n == 2:
        ranked["decision_tier_local"] = [
            "Better of Compared Set",
            "Worse of Compared Set",
        ]
    else:
        labels = ["Middle of Compared Set"] * n
        labels[0] = "Best of Compared Set"
        labels[-1] = "Worst of Compared Set"
        ranked["decision_tier_local"] = labels

    out.loc[ranked["index"], "decision_tier_local"] = ranked["decision_tier_local"].values
    return out


def calibrate_decision_tiers(
    df: pd.DataFrame,
    local_supplier_ids: Sequence[str] | None = None,
) -> pd.DataFrame:
    """
    Assign:
    1. decision_tier_global -> relative to the full supplier universe for a product
    2. decision_tier_local  -> relative only to the currently compared supplier set

    Lower risk_adjusted_cost = better.

    Notes
    -----
    - Global tier is the main business-facing label.
    - Local tier is optional comparison context.
    - Uses an explicit per-product loop to avoid fragile chained groupby/apply
      behavior across pandas versions.
    """
    df = df.copy()

    required_cols = ["product", "risk_adjusted_cost", "supplier_id"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for calibration: {missing}")

    parts: list[pd.DataFrame] = []

    for product_value, group in df.groupby("product", sort=False):
        g = group.copy()

        g = _assign_global_tiers(g)
        g = _assign_local_comparison_tiers(g, local_supplier_ids)

        if "product" not in g.columns:
            g["product"] = product_value

        parts.append(g)

    if not parts:
        out = df.copy()
        out["decision_tier_global"] = None
        out["decision_tier_local"] = None
        return out

    out = pd.concat(parts, axis=0).sort_index()
    return out