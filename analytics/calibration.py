import pandas as pd

def calibrate_decision_tiers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert risk_adjusted_cost value scores into procurement decision tiers
    within each product category using within-group percentile ranks.

    Lower risk_adjusted_cost should correspond to better decision tiers (e.g. "Preferred"), while higher risk_adjusted_cost should correspond to worse tiers (e.g. "Avoid"). This calibration allows users to easily interpret the scores in terms of actionable procurement decisions, rather than just raw cost values.

    NOTE: This script is called directly by scoring.py
    """
    df = df.copy()

    # Rank suppliers within each product group
    # pct=True returns percentile rank from 0 to 1, which we then bin into decision tiers
    df['decision_percentile'] = (
        df.groupby("product")['risk_adjusted_cost'].rank(method="average",
                                                         pct=True,
                                                         ascending=True))

    # Map percentile ranks to business-facing decision tiers
    df["decision_tier"] = pd.cut(
        df["decision_percentile"],
        bins=[0, 0.33, 0.66, 1.0],
        labels=["Preferred", "Acceptable", "Avoid"],
        include_lowest=True
    ).astype(object)

    df = df.drop(columns=["decision_percentile"])

    return df