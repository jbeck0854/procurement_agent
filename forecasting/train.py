"""
train.py — Model training, cross-validation, and holdout evaluation.

Leakage prevention (strictly enforced):
  For each horizon h, a training row at origin t is included only when its
  TARGET (at t+h) falls within the training window.  This ensures no holdout
  demand value ever appears as a training label.

  Train mask:  (week + h) <= train_ceiling
  where train_ceiling is fold["train_end"] for CV or HOLDOUT_TRAIN_END for holdout.

Holdout evaluation uses a FIXED origin (week 132), generating predictions for
target weeks 133–144 across h=1…12.  This is the most realistic deployment
scenario: as of week 132, forecast the next 12 weeks.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .features import build_dataset, build_inference_features, FEATURE_COLS

# ── Constants ─────────────────────────────────────────────────────────────────

HORIZONS = list(range(1, 13))   # h = 1 … 12

# Expanding-window CV folds (origin-week boundaries)
CV_FOLDS = [
    {"train_end":  96, "val_start":  97, "val_end": 108},
    {"train_end": 108, "val_start": 109, "val_end": 120},
    {"train_end": 120, "val_start": 121, "val_end": 132},
]

HOLDOUT_TRAIN_END  = 132   # last origin week in training for holdout
HOLDOUT_ORIGIN     = 132   # fixed inference origin for holdout evaluation
HOLDOUT_TEST_START = 133   # first target week in the holdout window
HOLDOUT_TEST_END   = 144   # last  target week in the holdout window


# ── Model factory ─────────────────────────────────────────────────────────────

def _make_model() -> HistGradientBoostingRegressor:
    """Single model spec used throughout the pipeline."""
    return HistGradientBoostingRegressor(
        max_iter=500,
        learning_rate=0.05,
        max_depth=5,
        min_samples_leaf=20,
        l2_regularization=0.1,
        categorical_features="from_dtype",   # reads pd.Categorical columns
        random_state=42,
    )


# ── Metric helpers ────────────────────────────────────────────────────────────

def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae  = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    nonzero = y_true != 0
    mape = float(np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero]))) \
           if nonzero.any() else np.nan
    return {"mae": mae, "rmse": rmse, "mape": mape}


# ── Cross-validation ──────────────────────────────────────────────────────────

def run_cv(df: pd.DataFrame, use_log: bool = False) -> pd.DataFrame:
    """
    Rolling expanding-window cross-validation.

    3 folds × 12 horizons.  Train mask for each (fold, horizon) pair:
        (week + h) <= fold["train_end"]   ← no target leakage into validation

    Returns a DataFrame with one row per (variant × fold × horizon).
    """
    records = []
    variant = "log" if use_log else "raw"

    for h in HORIZONS:
        ds    = build_dataset(df, h)
        weeks = ds["week"].values
        X     = ds[FEATURE_COLS]
        y_raw = ds["target"].values
        y_fit = np.log1p(y_raw) if use_log else y_raw

        for fold in CV_FOLDS:
            # Strict: target must land within the training window
            tr = (weeks + h) <= fold["train_end"]
            va = (weeks >= fold["val_start"]) & (weeks <= fold["val_end"])

            if tr.sum() == 0 or va.sum() == 0:
                continue

            m = _make_model()
            m.fit(X[tr], y_fit[tr])

            preds = m.predict(X[va])
            if use_log:
                preds = np.expm1(preds)
            preds = np.clip(preds, 0, None)

            metrics = _metrics(y_raw[va], preds)
            records.append({
                "variant": variant,
                "horizon": h,
                "fold":    f"[{fold['val_start']}–{fold['val_end']}]",
                **metrics,
            })

    return pd.DataFrame(records)


# ── Holdout evaluation ────────────────────────────────────────────────────────

def run_holdout(df: pd.DataFrame, use_log: bool = False) -> pd.DataFrame:
    """
    Fixed-origin holdout evaluation.

    For each horizon h:
      - Train on all rows where (origin + h) < HOLDOUT_TEST_START
        (guarantees no holdout demand values appear as training labels)
      - Predict from origin week 132 → target week = 132 + h

    Returns one row per (facility × semiconductor × horizon).
    Actuals come directly from the source data for target weeks 133–144.
    """
    variant = "log" if use_log else "raw"

    # Feature rows at the fixed inference origin (computed once, reused per h)
    X_inf = build_inference_features(df, origin_week=HOLDOUT_ORIGIN)
    fac_ids  = X_inf["facility_id"].astype(str).values
    semi_ids = X_inf["semiconductor_id"].astype(str).values

    # Actual demand lookup for target weeks 133–144
    actuals: dict[tuple, dict] = {}
    for (fac, semi), g in df.groupby(["facility_id", "semiconductor_id"], sort=False):
        g = g.sort_values("week").set_index("week")
        actuals[(fac, semi)] = g["customer_orders"].to_dict()

    records = []
    for h in HORIZONS:
        target_week = HOLDOUT_ORIGIN + h   # 133 … 144

        ds    = build_dataset(df, h)
        weeks = ds["week"].values
        X_all = ds[FEATURE_COLS]
        y_raw = ds["target"].values
        y_fit = np.log1p(y_raw) if use_log else y_raw

        # Strict leakage prevention: target must NOT touch the holdout window
        tr = (weeks + h) < HOLDOUT_TEST_START   # equivalent to weeks <= 132 - h

        m = _make_model()
        m.fit(X_all[tr], y_fit[tr])

        preds = m.predict(X_inf[FEATURE_COLS])
        if use_log:
            preds = np.expm1(preds)
        preds = np.clip(preds, 0, None)

        for i, (fac, semi) in enumerate(zip(fac_ids, semi_ids)):
            actual = actuals.get((fac, semi), {}).get(target_week, np.nan)
            records.append({
                "variant":          variant,
                "facility_id":      fac,
                "semiconductor_id": semi,
                "horizon":          h,
                "target_week":      target_week,
                "actual":           actual,
                "predicted":        float(preds[i]),
            })

    return pd.DataFrame(records)


# ── Naive benchmark ───────────────────────────────────────────────────────────

def naive_benchmark_holdout(df: pd.DataFrame) -> pd.DataFrame:
    """
    4-week rolling mean benchmark evaluated at the same fixed-origin holdout.

    Prediction for every horizon h = 1…12 is the rolling mean of the last 4
    observed weeks at the origin (week 132).  This is a constant-flat forecast
    — the strongest naive baseline for short procurement horizons.
    """
    actuals: dict[tuple, dict] = {}
    for (fac, semi), g in df.groupby(["facility_id", "semiconductor_id"], sort=False):
        actuals[(fac, semi)] = g.sort_values("week").set_index("week")["customer_orders"].to_dict()

    records = []
    for (fac, semi), g in df.groupby(["facility_id", "semiconductor_id"], sort=False):
        g      = g.sort_values("week")
        last4  = g[g["week"] <= HOLDOUT_ORIGIN]["customer_orders"].tail(4)
        bench  = max(0.0, float(last4.mean()))

        for h in HORIZONS:
            target_week = HOLDOUT_ORIGIN + h
            actual      = actuals.get((fac, semi), {}).get(target_week, np.nan)
            records.append({
                "variant":          "naive_roll4",
                "facility_id":      fac,
                "semiconductor_id": semi,
                "horizon":          h,
                "target_week":      target_week,
                "actual":           actual,
                "predicted":        bench,
            })

    return pd.DataFrame(records)


# ── Deployment models (full data) ─────────────────────────────────────────────

def train_deployment_models(df: pd.DataFrame, use_log: bool = False) -> dict:
    """
    Train one HistGBT model per horizon on ALL available data.

    Train mask per horizon: (week + h) <= 145
    (ensures targets don't exceed the last observed week)

    Returns {h: fitted model} for h = 1 … 12.
    Used for generating the 12-week forward forecast from origin week 145.
    """
    models = {}
    for h in HORIZONS:
        ds    = build_dataset(df, h)
        weeks = ds["week"].values
        tr    = (weeks + h) <= df["week"].max()   # targets must be observed
        X     = ds[FEATURE_COLS][tr]
        y     = ds["target"].values[tr]
        if use_log:
            y = np.log1p(y)
        m = _make_model()
        m.fit(X, y)
        models[h] = m
        print(f"  Trained deployment model h={h:2d}  ({tr.sum():,} rows)")
    return models
