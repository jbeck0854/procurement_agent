"""
features.py — Feature engineering for the demand forecasting pipeline.

Design rules (enforced throughout):
  - All features are computed strictly at time t (the forecast origin).
  - Feature set is identical across all forecast horizons.
  - Only the target changes per horizon (demand at t+h).
  - No future promotional signals; only lagged promotions are included.
  - Categorical encoding uses fixed categories so train and inference are aligned.
"""

import numpy as np
import pandas as pd

# Fixed category lists — must match the data exactly
FACILITY_CATS = ["FACILITY_1", "FACILITY_2", "FACILITY_3", "FACILITY_4"]
SEMI_CATS     = [f"SEMICONDUCTOR_{i}" for i in range(1, 13)]

FEATURE_COLS = [
    # Lag demand (at t-k, all strictly before t)
    "lag_1", "lag_2", "lag_4", "lag_8", "lag_12",
    # Rolling demand statistics (window ends at t-1)
    "roll_mean_4", "roll_std_4", "roll_mean_8",
    # Lagged promotional flags (known past activity only)
    "promo_email_lag1", "promo_home_lag1",
    # Price discount signal at t
    "price_ratio",
    # Trend proxy (sequential week index 1–145)
    "week",
    # Seasonality proxies
    "week_of_year", "quarter",
    # Series identity (encoded as categorical)
    "facility_id", "semiconductor_id",
]

CAT_COLS = ["facility_id", "semiconductor_id"]

# Lags that must be non-null for a row to be valid training data
_REQUIRED_LAGS = ["lag_1", "lag_2", "lag_4", "lag_8", "lag_12"]


def _add_series_features(g: pd.DataFrame) -> pd.DataFrame:
    """
    Compute feature columns for a single (facility × semiconductor) series.

    g must be sorted by week ascending before calling.
    All features are computed at time t; no future information is used.
    Returns a copy of g with feature columns appended.
    """
    g = g.copy()
    s = g["customer_orders"]

    # --- Lag features ---------------------------------------------------
    # lag_k = demand observed k weeks before the current origin t
    g["lag_1"]  = s.shift(1)
    g["lag_2"]  = s.shift(2)
    g["lag_4"]  = s.shift(4)
    g["lag_8"]  = s.shift(8)
    g["lag_12"] = s.shift(12)

    # --- Rolling statistics ---------------------------------------------
    # shift(1) ensures the current week t is excluded from every window
    s_lagged = s.shift(1)
    g["roll_mean_4"] = s_lagged.rolling(4).mean()   # avg of [t-4 … t-1]
    g["roll_std_4"]  = s_lagged.rolling(4).std()    # std  of [t-4 … t-1]
    g["roll_mean_8"] = s_lagged.rolling(8).mean()   # avg of [t-8 … t-1]

    # --- Promotional signals (lagged only) ------------------------------
    # Only past promotions are observable at t; forward promotions are excluded
    g["promo_email_lag1"] = g["emailer_for_promotion"].shift(1)
    g["promo_home_lag1"]  = g["homepage_featured"].shift(1)

    # --- Price discount signal ------------------------------------------
    # Ratio < 1 indicates discounting; ratio = 1 means listed at list price
    g["price_ratio"] = g["realized_selling_price"] / g["list_price"].replace(0, np.nan)

    # --- Calendar / seasonality features --------------------------------
    dates = pd.to_datetime(g["date"])
    g["week_of_year"] = dates.dt.isocalendar().week.astype(int)
    g["quarter"]      = dates.dt.quarter
    # "week" column (1–145) is already in g and acts as a trend proxy

    return g


def build_dataset(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    Build the full feature + target dataset for a given forecast horizon h.

    For each (facility × semiconductor) series at each time t:
      - X(t): feature vector computed from history up to and including t
      - y(t): customer_orders at t + horizon  ← target shifts per horizon

    Rows missing any required lag or the target are dropped.
    Categorical columns use fixed categories for consistent encoding.

    Returns a flat DataFrame with columns FEATURE_COLS + ["target", "week",
    "facility_id", "semiconductor_id"] (and other pass-through columns).
    """
    records = []
    for _, g in df.groupby(["facility_id", "semiconductor_id"], sort=False):
        g = g.sort_values("week").reset_index(drop=True)
        g = _add_series_features(g)
        g["target"] = g["customer_orders"].shift(-horizon)
        records.append(g)

    full = pd.concat(records, ignore_index=True)
    full = full.dropna(subset=_REQUIRED_LAGS + ["target"]).reset_index(drop=True)

    # Consistent categorical encoding across train / validation / inference
    full["facility_id"]      = pd.Categorical(full["facility_id"],      categories=FACILITY_CATS)
    full["semiconductor_id"] = pd.Categorical(full["semiconductor_id"], categories=SEMI_CATS)

    return full


def build_inference_features(df: pd.DataFrame, origin_week: int) -> pd.DataFrame:
    """
    Build one feature row per (facility × semiconductor) series at a fixed
    origin week. Used for holdout evaluation and forward forecasting.

    Returns a DataFrame aligned to FEATURE_COLS with categorical encoding applied.
    Row order matches groupby sort order (facility_id, semiconductor_id).
    """
    records = []
    for _, g in df.groupby(["facility_id", "semiconductor_id"], sort=True):
        g = g.sort_values("week").reset_index(drop=True)
        g = _add_series_features(g)
        row = g[g["week"] == origin_week]
        if row.empty:
            continue
        records.append(row.iloc[[0]])

    result = pd.concat(records, ignore_index=True)
    result["facility_id"]      = pd.Categorical(result["facility_id"],      categories=FACILITY_CATS)
    result["semiconductor_id"] = pd.Categorical(result["semiconductor_id"], categories=SEMI_CATS)

    return result
