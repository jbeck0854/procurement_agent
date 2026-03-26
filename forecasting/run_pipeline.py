"""
run_pipeline.py — Semiconductor Demand Forecasting Pipeline
===========================================================

Target      : customer_orders
Grain       : (week, facility_id, semiconductor_id) — row level, not aggregated
Aggregation : weekly SUM and MEAN computed post-prediction for interpretability only

Steps:
  1.  Load data + sanity checks
  2.  Feature engineering  (build_features)
  3.  Holdout split        (last 10 feature-ready weeks)
  4.  Define X / y
  5.  Week-based TimeSeriesSplit CV (n_splits=5)
  6.  GridSearchCV         (HistGradientBoostingRegressor, 243 configs)
  7.  Holdout evaluation   (row-level, weekly SUM, weekly MEAN, per-series)
  8.  Save all artifacts   (BEFORE any plots)
  9.  Generate plots       (6 figures)

Usage (from project root):
    python -m forecasting.run_pipeline
"""

import matplotlib
matplotlib.use('Agg')

import numpy as np
import pandas as pd

from .features import (
    CATEGORICAL_COLS,
    FEATURE_COLS,
    NUMERIC_FEATURES,
    TARGET,
    build_features,
    sanity_check,
)
from .train import PARAM_GRID, make_week_time_splits, run_grid_search
from .evaluate import (
    compute_per_series_metrics,
    compute_row_metrics,
    compute_weekly_agg_metrics,
    plot_cv_summary,
    plot_full_history_and_holdout,
    plot_holdout_zoom,
    plot_permutation_importance,
    plot_residuals,
    plot_worst_5_series,
    save_artifacts,
)

DATA_PATH = 'cleaned_data/finished_goods_demand_table.csv'


def run() -> None:
    print('=' * 62)
    print('  SEMICONDUCTOR DEMAND FORECASTING PIPELINE')
    print('=' * 62)

    # ── Step 1: Load + sanity checks ──────────────────────────────────────────
    print('\n[1/9] Loading data ...')
    df_raw = pd.read_csv(DATA_PATH)
    print(f'  Loaded: {len(df_raw):,} rows from {DATA_PATH}')
    sanity_check(df_raw)

    # ── Step 2: Feature engineering ───────────────────────────────────────────
    print('[2/9] Building features ...')
    model_df = build_features(df_raw)
    print(f'  Feature-ready dataset: {len(model_df):,} rows')
    print(f'  Feature-ready weeks  : {model_df["week"].min()} – {model_df["week"].max()}')

    # ── Step 3: Holdout split (last 10 feature-ready weeks) ───────────────────
    print('\n[3/9] Holdout split ...')
    all_weeks     = sorted(model_df['week'].unique())
    holdout_weeks = all_weeks[-10:]
    train_weeks   = all_weeks[:-10]

    train_df = (
        model_df[model_df['week'].isin(train_weeks)]
        .sort_values(['week', 'facility_id', 'semiconductor_id'])
        .reset_index(drop=True)
    )
    test_df = (
        model_df[model_df['week'].isin(holdout_weeks)]
        .sort_values(['week', 'facility_id', 'semiconductor_id'])
        .reset_index(drop=True)
    )

    last_train_week     = int(train_df['week'].max())
    first_holdout_week  = int(test_df['week'].min())

    print(f'  Train  : weeks {train_df["week"].min()} – {last_train_week}'
          f'  ({len(train_df):,} rows, {len(train_weeks)} unique weeks)')
    print(f'  Holdout: weeks {first_holdout_week} – {test_df["week"].max()}'
          f'  ({len(test_df):,} rows, 10 unique weeks)')

    # ── Step 4: Features / target ─────────────────────────────────────────────
    print('\n[4/9] Defining features and target ...')
    print(f'  Categorical features : {CATEGORICAL_COLS}')
    print(f'  Numeric features     : {len(NUMERIC_FEATURES)} columns')
    print(f'  Total feature cols   : {len(FEATURE_COLS)}')
    print(f'  Target               : {TARGET}')

    X_train = train_df[FEATURE_COLS].copy()
    y_train = train_df[TARGET].values.ravel()
    X_test  = test_df[FEATURE_COLS].copy()
    y_test  = test_df[TARGET].values.ravel()

    print(f'  X_train: {X_train.shape}   X_test: {X_test.shape}')

    # ── Step 5: Week-based CV ─────────────────────────────────────────────────
    print('\n[5/9] Building week-based TimeSeriesSplit (n_splits=5) ...')
    cv_splits = make_week_time_splits(train_df, n_splits=5)
    print(f'  {len(cv_splits)} CV folds created')
    for i, (tr_idx, va_idx) in enumerate(cv_splits, 1):
        tr_wks = sorted(train_df.loc[tr_idx, 'week'].unique())
        va_wks = sorted(train_df.loc[va_idx, 'week'].unique())
        print(f'    Fold {i}: train wks {tr_wks[0]}–{tr_wks[-1]}'
              f'  |  val wks {va_wks[0]}–{va_wks[-1]}')

    # ── Step 6: GridSearchCV ──────────────────────────────────────────────────
    print(f'\n[6/9] GridSearchCV ({len(PARAM_GRID)} param axes, '
          f'{len(cv_splits)} folds) ...')
    grid = run_grid_search(X_train, y_train, cv_splits)

    print(f'\n  Best params : {grid.best_params_}')
    print(f'  Best CV MAE : {-grid.best_score_:,.2f}')

    # ── Step 7: Holdout evaluation ────────────────────────────────────────────
    print('\n[7/9] Holdout evaluation ...')
    y_pred = np.clip(grid.best_estimator_.predict(X_test), 0, None)

    test_df          = test_df.copy()
    test_df['pred']  = y_pred

    row_metrics = compute_row_metrics(y_test, y_pred)
    agg_metrics = compute_weekly_agg_metrics(test_df)
    per_series  = compute_per_series_metrics(test_df)

    print(f'\n  Row-level MAE          : {row_metrics["mae"]:>10,.2f}')
    print(f'  Row-level RMSE         : {row_metrics["rmse"]:>10,.2f}')
    print(f'  Row-level MAPE         : {row_metrics["mape"] * 100:>10.2f}%')
    print(f'  Row-level R²           : {row_metrics["r2"]:>10.4f}')
    print(f'\n  System SUM  MAE        : {agg_metrics["system_sum_mae"]:>10,.2f}')
    print(f'  Series MEAN MAE        : {agg_metrics["series_mean_mae"]:>10,.2f}')
    print(f'\n  Per-series MAE         : mean={per_series["mae"].mean():,.2f}'
          f'   median={per_series["mae"].median():,.2f}')
    print(f'\n  Worst 5 series by MAE:')
    print(per_series.head(5)[['facility_id', 'semiconductor_id', 'mae', 'rmse']]
          .round(2).to_string(index=False))

    # ── Step 8: Save artifacts (BEFORE plots) ─────────────────────────────────
    print('\n[8/9] Saving artifacts ...')
    save_artifacts(
        test_df=test_df,
        cv_results=grid.cv_results_,
        best_params=grid.best_params_,
        best_cv_mae=-grid.best_score_,
        row_metrics=row_metrics,
        agg_metrics=agg_metrics,
        per_series=per_series,
        last_train_week=last_train_week,
        first_holdout_week=first_holdout_week,
    )

    # ── Step 9: Plots ─────────────────────────────────────────────────────────
    print('\n[9/9] Generating plots ...')
    plot_cv_summary(grid.cv_results_, grid.best_index_)
    plot_full_history_and_holdout(df_raw, test_df, last_train_week)
    plot_holdout_zoom(test_df)
    plot_residuals(test_df)
    plot_worst_5_series(test_df, df_raw, per_series, last_train_week)
    plot_permutation_importance(grid.best_estimator_, X_test, y_test)

    # ── Final report ──────────────────────────────────────────────────────────
    print('\n' + '=' * 62)
    print('  PIPELINE COMPLETE')
    print('=' * 62)
    print(f'\n  Artifacts → artifacts/forecasting/')
    print(f'\n  Best CV MAE         : {-grid.best_score_:>10,.2f}')
    print(f'  Holdout MAE  (row)  : {row_metrics["mae"]:>10,.2f}')
    print(f'  Holdout RMSE (row)  : {row_metrics["rmse"]:>10,.2f}')
    print(f'  Holdout R²          : {row_metrics["r2"]:>10.4f}')
    print(f'  System SUM  MAE     : {agg_metrics["system_sum_mae"]:>10,.2f}')
    print(f'  Series MEAN MAE     : {agg_metrics["series_mean_mae"]:>10,.2f}')
    print(f'  Per-series MAE mean : {per_series["mae"].mean():>10,.2f}')
    print(f'  Per-series MAE med  : {per_series["mae"].median():>10,.2f}')
    print(f'\n  Worst 5 series:')
    print(per_series.head(5)[['facility_id', 'semiconductor_id', 'mae']]
          .round(2).to_string(index=False))
    print('=' * 62)


if __name__ == '__main__':
    run()
