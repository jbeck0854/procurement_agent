"""
run_baseline.py — Baseline model evaluation for semiconductor demand forecasting.

Evaluates two naive baselines against the same 10-week holdout used by the HGB model:
  1. Naive lag-1    : prediction = demand at t-1 (same series)
  2. Rolling mean-4 : prediction = 4-week rolling mean ending at t-1 (same series)

Both feature columns (lag_1, roll_mean_4) are produced by build_features() and
already present in the holdout slice of model_df — no additional computation needed.

HGB predictions are loaded from the saved artifact (holdout_predictions.csv);
GridSearchCV is NOT re-run.

Usage (from project root):
    python -m forecasting.run_baseline

Output:
    artifacts/forecasting/baseline_system_comparison.png
    artifacts/forecasting/baseline_example_series.png
"""

import matplotlib
matplotlib.use('Agg')

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from .features import TARGET, build_features
from .evaluate import (
    compute_baselines,
    plot_baseline_system_comparison,
    plot_baseline_example_series,
    _mae,
)

DATA_PATH      = 'cleaned_data/finished_goods_demand_table.csv'
HGB_PREDS_PATH = 'artifacts/forecasting/holdout_predictions.csv'
METRICS_PATH   = 'artifacts/forecasting/holdout_metrics.json'


def run() -> None:
    print('=' * 62)
    print('  BASELINE EVALUATION (Naive Lag-1 + Rolling Mean-4)')
    print('=' * 62)

    # ── Step 1: Load raw data and build features ───────────────────────────────
    print('\n[1/4] Loading data and building features ...')
    df_raw   = pd.read_csv(DATA_PATH)
    model_df = build_features(df_raw)

    # ── Step 2: Reconstruct holdout split (identical to run_pipeline.py) ───────
    print('\n[2/4] Reconstructing holdout split ...')
    all_weeks     = sorted(model_df['week'].unique())
    holdout_weeks = all_weeks[-10:]

    test_df = (
        model_df[model_df['week'].isin(holdout_weeks)]
        .sort_values(['week', 'facility_id', 'semiconductor_id'])
        .reset_index(drop=True)
    )
    print(f'  Holdout weeks : {test_df["week"].min()} – {test_df["week"].max()}'
          f'  ({len(test_df):,} rows)')

    # Merge HGB predictions from the saved artifact
    hgb_preds = pd.read_csv(HGB_PREDS_PATH)
    hgb_preds['facility_id']      = hgb_preds['facility_id'].astype(str)
    hgb_preds['semiconductor_id'] = hgb_preds['semiconductor_id'].astype(str)
    test_df['facility_id']        = test_df['facility_id'].astype(str)
    test_df['semiconductor_id']   = test_df['semiconductor_id'].astype(str)

    test_df = test_df.merge(
        hgb_preds[['week', 'facility_id', 'semiconductor_id', 'pred']],
        on=['week', 'facility_id', 'semiconductor_id'],
        how='left',
    )
    n_missing = test_df['pred'].isna().sum()
    assert n_missing == 0, (
        f'{n_missing} holdout rows have no HGB prediction — '
        'check that holdout_predictions.csv is up to date.'
    )
    print(f'  Merged {len(hgb_preds):,} HGB predictions  (0 missing)')

    # Load HGB holdout MAE from the saved metrics JSON
    with open(METRICS_PATH) as f:
        saved_metrics = json.load(f)
    hgb_mae = saved_metrics['row_level']['mae']

    # ── Step 3: Compute baselines ──────────────────────────────────────────────
    print('\n[3/4] Computing baseline MAEs ...')
    baseline = compute_baselines(test_df)
    naive_mae   = baseline['naive_mae']
    rolling_mae = baseline['rolling_mae']

    print(f'\n  ┌─────────────────────────────────────┐')
    print(f'  │  MODEL           ROW-LEVEL MAE      │')
    print(f'  ├─────────────────────────────────────┤')
    print(f'  │  HGB             {hgb_mae:>10,.2f}       │')
    print(f'  │  Naive lag-1     {naive_mae:>10,.2f}       │')
    print(f'  │  Rolling mean-4  {rolling_mae:>10,.2f}       │')
    print(f'  └─────────────────────────────────────┘')
    print(f'\n  HGB lift vs Naive  : {(1 - hgb_mae / naive_mae) * 100:+.1f}%')
    print(f'  HGB lift vs Rolling: {(1 - hgb_mae / rolling_mae) * 100:+.1f}%')

    # ── Step 4: Identify representative series (closest to median HGB MAE) ────
    #           and compute per-series baseline MAEs for that series
    series_records = []
    for (fac, semi), grp in test_df.groupby(['facility_id', 'semiconductor_id']):
        actual = grp[TARGET].values
        series_records.append({
            'facility_id':      str(fac),
            'semiconductor_id': str(semi),
            'hgb_mae':          _mae(actual, grp['pred'].values),
            'naive_mae':        _mae(actual, grp['lag_1'].values),
            'rolling_mae':      _mae(actual, grp['roll_mean_4'].values),
        })
    series_df   = pd.DataFrame(series_records)
    median_hgb  = series_df['hgb_mae'].median()
    sel_idx     = (series_df['hgb_mae'] - median_hgb).abs().idxmin()
    sel         = series_df.loc[sel_idx]

    print(f'\n  Representative series (median HGB MAE ≈ {median_hgb:,.0f}):')
    print(f'    {sel["facility_id"]} × {sel["semiconductor_id"]}')
    print(f'    HGB MAE    = {sel["hgb_mae"]:,.2f}')
    print(f'    Naive MAE  = {sel["naive_mae"]:,.2f}')
    print(f'    Rolling MAE= {sel["rolling_mae"]:,.2f}')

    # ── Step 5: Generate plots ─────────────────────────────────────────────────
    print('\n[4/4] Generating plots ...')
    plot_baseline_system_comparison(test_df, hgb_mae, naive_mae, rolling_mae)
    plot_baseline_example_series(
        test_df            = test_df,
        facility_id        = sel['facility_id'],
        semiconductor_id   = sel['semiconductor_id'],
        hgb_mae_series     = sel['hgb_mae'],
        naive_mae_series   = sel['naive_mae'],
        rolling_mae_series = sel['rolling_mae'],
        series_label       = 'median MAE series',
    )

    print('\n' + '=' * 62)
    print('  BASELINE EVALUATION COMPLETE')
    print('=' * 62)
    print(f'\n  HGB    row-level MAE : {hgb_mae:>10,.2f}')
    print(f'  Naive  row-level MAE : {naive_mae:>10,.2f}')
    print(f'  Rolling row-level MAE: {rolling_mae:>10,.2f}')
    print(f'\n  Plots saved → artifacts/forecasting/')
    print(f'    baseline_system_comparison.png')
    print(f'    baseline_example_series.png')
    print('=' * 62)


if __name__ == '__main__':
    run()
