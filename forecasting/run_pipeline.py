"""
run_pipeline.py — Demand Forecasting Pipeline Orchestration
===========================================================

Executes the full pipeline in sequence:

  Step 1  Cross-validation (raw vs log) → select target transformation
  Step 2  Holdout evaluation (fixed origin = week 132, target weeks 133–144)
  Step 3  Naive benchmark comparison
  Step 4  Variant selection (aggregate system-level MAE, >5% threshold)
  Step 5  Diagnostic plots
  Step 6  Deployment model training (full data, selected variant)
  Step 7  12-week forward forecast (weeks 146–157)
  Step 8  Save all artifacts

Usage (from project root):
    python -m forecasting.run_pipeline
"""

from pathlib import Path

import numpy as np
import pandas as pd

from .features import FEATURE_COLS, build_inference_features
from .train import (
    HORIZONS,
    HOLDOUT_ORIGIN,
    naive_benchmark_holdout,
    run_cv,
    run_holdout,
    train_deployment_models,
)
from .evaluate import (
    holdout_aggregate,
    plot_cv_mae_by_horizon,
    plot_feature_importance,
    plot_forward_forecasts,
    plot_residuals,
    plot_series_sample,
    plot_system_actual_vs_predicted,
    print_cv_summary,
    print_holdout_summary,
)

DATA_PATH = Path("cleaned_data/finished_goods_demand_table.csv")
ARTIFACTS = Path("artifacts/forecasting")

LOG_IMPROVEMENT_THRESHOLD = 0.05   # adopt log if MAE improvement > 5%


# ── Variant selection ─────────────────────────────────────────────────────────

def _select_variant(
    holdout_raw: pd.DataFrame, holdout_log: pd.DataFrame
) -> str:
    """
    Compare system-level aggregate MAE for raw vs log variants.
    Adopt log only if it improves aggregate MAE by more than the threshold.
    """
    agg_raw = holdout_aggregate(holdout_raw)
    agg_log = holdout_aggregate(holdout_log)
    mae_raw = float(agg_raw["mae_system"].iloc[0])
    mae_log = float(agg_log["mae_system"].iloc[0])
    improvement = (mae_raw - mae_log) / mae_raw

    print(f"\n  System MAE — raw: {mae_raw:,.1f}  |  log: {mae_log:,.1f}  "
          f"|  improvement: {improvement*100:.1f}%")

    if improvement > LOG_IMPROVEMENT_THRESHOLD:
        print(f"  → Log transform adopted (>{LOG_IMPROVEMENT_THRESHOLD*100:.0f}% improvement)")
        return "log"
    else:
        print(f"  → Raw target retained (improvement below {LOG_IMPROVEMENT_THRESHOLD*100:.0f}% threshold)")
        return "raw"


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run() -> None:
    print("=" * 62)
    print("  DEMAND FORECASTING PIPELINE")
    print("=" * 62)

    # ── Load ──────────────────────────────────────────────────────────
    df = pd.read_csv(DATA_PATH)
    print(f"\n  Loaded {len(df):,} rows  |  "
          f"{df['facility_id'].nunique()} facilities  |  "
          f"{df['semiconductor_id'].nunique()} semiconductors  |  "
          f"weeks {df['week'].min()}–{df['week'].max()}")

    # ── Step 1: Cross-validation ───────────────────────────────────────
    print("\n── Step 1: Cross-Validation ──────────────────────────────────")
    print("  Running raw variant …")
    cv_raw = run_cv(df, use_log=False)
    print("  Running log variant …")
    cv_log = run_cv(df, use_log=True)
    cv_all = pd.concat([cv_raw, cv_log], ignore_index=True)
    print_cv_summary(cv_all)
    plot_cv_mae_by_horizon(cv_all)

    # ── Step 2: Holdout evaluation ─────────────────────────────────────
    print("\n── Step 2: Holdout Evaluation (origin = week 132) ───────────")
    print("  Running raw variant …")
    holdout_raw   = run_holdout(df, use_log=False)
    print("  Running log variant …")
    holdout_log   = run_holdout(df, use_log=True)

    # ── Step 3: Naive benchmark ────────────────────────────────────────
    print("\n── Step 3: Naive Benchmark ───────────────────────────────────")
    holdout_naive = naive_benchmark_holdout(df)

    holdout_all = pd.concat([holdout_raw, holdout_log, holdout_naive], ignore_index=True)
    print_holdout_summary(holdout_all)

    # ── Step 4: Variant selection ──────────────────────────────────────
    print("\n── Step 4: Variant Selection ─────────────────────────────────")
    best_variant  = _select_variant(holdout_raw, holdout_log)
    use_log       = best_variant == "log"
    holdout_best  = holdout_raw if best_variant == "raw" else holdout_log

    # ── Step 5: Diagnostic plots ───────────────────────────────────────
    print("\n── Step 5: Diagnostic Plots ──────────────────────────────────")
    plot_system_actual_vs_predicted(holdout_all, variant=best_variant)
    plot_system_actual_vs_predicted(holdout_all, variant="naive_roll4")
    plot_series_sample(holdout_best, df, variant=best_variant, n_series=6)
    plot_residuals(holdout_best, variant=best_variant)

    # ── Step 6: Deployment models ──────────────────────────────────────
    print("\n── Step 6: Deployment Models (full data) ─────────────────────")
    deployment_models = train_deployment_models(df, use_log=use_log)
    for h in [1, 4, 12]:
        plot_feature_importance(deployment_models, FEATURE_COLS, horizon=h)

    # ── Step 7: Forward forecast (weeks 146–157) ───────────────────────
    print("\n── Step 7: Forward Forecast (weeks 146–157) ──────────────────")
    X_inf    = build_inference_features(df, origin_week=df["week"].max())
    fac_ids  = X_inf["facility_id"].astype(str).values
    semi_ids = X_inf["semiconductor_id"].astype(str).values

    forecast_records = []
    for h in HORIZONS:
        preds = deployment_models[h].predict(X_inf[FEATURE_COLS])
        if use_log:
            preds = np.expm1(preds)
        preds = np.clip(preds, 0, None)

        for i, (fac, semi) in enumerate(zip(fac_ids, semi_ids)):
            forecast_records.append({
                "facility_id":      fac,
                "semiconductor_id": semi,
                "horizon":          h,
                "target_week":      df["week"].max() + h,
                "predicted":        float(preds[i]),
                "variant":          best_variant,
            })

    forecast_df = pd.DataFrame(forecast_records)
    plot_forward_forecasts(forecast_df, df, n_series=6)

    # ── Step 8: Save artifacts ─────────────────────────────────────────
    print("\n── Step 8: Saving Artifacts ──────────────────────────────────")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    forecast_df.to_csv(ARTIFACTS / "forward_forecasts_w146_w157.csv",  index=False)
    holdout_all.to_csv(ARTIFACTS / "holdout_predictions.csv",          index=False)
    cv_all.to_csv(     ARTIFACTS / "cv_metrics.csv",                   index=False)

    # Per-series and aggregate summary tables
    from .evaluate import holdout_per_series, holdout_aggregate
    holdout_per_series(holdout_all).to_csv(
        ARTIFACTS / "holdout_per_series_metrics.csv", index=False
    )
    holdout_aggregate(holdout_all).to_csv(
        ARTIFACTS / "holdout_aggregate_metrics.csv", index=False
    )

    print(f"\n  All artifacts saved to: {ARTIFACTS}/")
    print(f"  Selected variant      : {best_variant}")
    print("\n" + "=" * 62)
    print("  PIPELINE COMPLETE")
    print("=" * 62)


if __name__ == "__main__":
    run()
