"""
evaluate.py — Metrics, artifact persistence, and plots for semiconductor demand forecasting.

Evaluation is performed at three levels:
  1. Row-level    — MAE, RMSE, MAPE, R² at the (week × facility × semiconductor) grain
  2. Weekly SUM   — system-level total demand aggregated by week
  3. Weekly MEAN  — series-average demand aggregated by week
  4. Per-series   — MAE/RMSE per (facility_id × semiconductor_id)

All artifacts are saved before any plot is generated.
Non-interactive Agg backend is forced at import time.
"""

import matplotlib
matplotlib.use('Agg')

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)

ARTIFACTS = Path('artifacts/forecasting')
TARGET    = 'customer_orders'

# Colour palette
_BLUE   = '#1f4e79'
_ORANGE = '#ed7d31'
_GRAY   = '#a5a5a5'
_MUTED  = '#c9d9e8'


def _ensure_artifacts() -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS


# ── Scalar helpers ─────────────────────────────────────────────────────────────

def _mae(a, p):
    return float(mean_absolute_error(a, p))


def _rmse(a, p):
    return float(np.sqrt(mean_squared_error(a, p)))


def _mape(a, p):
    """MAPE computed only on non-zero actuals."""
    a, p = np.asarray(a), np.asarray(p)
    mask = a != 0
    if mask.sum() == 0:
        return float('nan')
    return float(mean_absolute_percentage_error(a[mask], p[mask]))


# ── Metric computation ─────────────────────────────────────────────────────────

def compute_row_metrics(y_test: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    Row-level holdout metrics at the (week × facility × semiconductor) grain.
    This is the primary evaluation metric reported for model selection.
    """
    return {
        'mae':  _mae(y_test, y_pred),
        'rmse': _rmse(y_test, y_pred),
        'mape': _mape(y_test, y_pred),
        'r2':   float(r2_score(y_test, y_pred)),
    }


def compute_weekly_agg_metrics(test_df: pd.DataFrame) -> dict:
    """
    Aggregate holdout predictions by week, compute metrics two ways:

    SUM  → system-level total demand (all 48 series summed per week).
           Positive and negative errors partially cancel, so this MAE
           will typically be much smaller than row-level MAE.

    MEAN → average per-series demand per week.
    """
    w_sum  = test_df.groupby('week')[[TARGET, 'pred']].sum()
    w_mean = test_df.groupby('week')[[TARGET, 'pred']].mean()

    return {
        'system_sum_mae':   _mae( w_sum[TARGET],  w_sum['pred']),
        'system_sum_rmse':  _rmse(w_sum[TARGET],  w_sum['pred']),
        'series_mean_mae':  _mae( w_mean[TARGET], w_mean['pred']),
        'series_mean_rmse': _rmse(w_mean[TARGET], w_mean['pred']),
    }


def compute_per_series_metrics(test_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-(facility_id × semiconductor_id) holdout MAE and RMSE.
    Returns a DataFrame sorted by MAE descending (worst series first).
    """
    records = []
    for (fac, semi), grp in test_df.groupby(['facility_id', 'semiconductor_id']):
        a = grp[TARGET].values
        p = grp['pred'].values
        records.append({
            'facility_id':      str(fac),
            'semiconductor_id': str(semi),
            'mae':              _mae(a, p),
            'rmse':             _rmse(a, p),
            'n':                len(grp),
        })
    return (
        pd.DataFrame(records)
        .sort_values('mae', ascending=False)
        .reset_index(drop=True)
    )


# ── Artifact persistence ───────────────────────────────────────────────────────

def save_artifacts(
    test_df:     pd.DataFrame,
    cv_results:  dict,
    best_params: dict,
    best_cv_mae: float,
    row_metrics: dict,
    agg_metrics: dict,
    per_series:  pd.DataFrame,
    last_train_week: int,
    first_holdout_week: int,
) -> None:
    """
    Write all evaluation outputs to disk before any plots are generated.

    Saved files:
      holdout_predictions.csv       — week, facility, semiconductor, actual, pred
      per_series_holdout_metrics.csv — per-series MAE/RMSE
      cv_summary.csv                 — GridSearchCV results table
      holdout_metrics.json           — key numeric summary
      model_selection_summary.txt   — human-readable report
      validation_window_explanation.txt
    """
    out = _ensure_artifacts()

    # 1. holdout_predictions.csv
    save_cols = ['week', 'facility_id', 'semiconductor_id', TARGET, 'pred']
    test_df[save_cols].to_csv(out / 'holdout_predictions.csv', index=False)

    # 2. per_series_holdout_metrics.csv
    per_series.to_csv(out / 'per_series_holdout_metrics.csv', index=False)

    # 3. cv_summary.csv
    cv_df = pd.DataFrame(cv_results)
    cv_df['mean_test_mae'] = -cv_df['mean_test_score']
    cv_df['std_test_mae']  =  cv_df['std_test_score']
    param_cols = [c for c in cv_df.columns if c.startswith('param_')]
    keep = param_cols + ['mean_test_mae', 'std_test_mae', 'rank_test_score']
    cv_df[keep].sort_values('rank_test_score').to_csv(out / 'cv_summary.csv', index=False)

    # 4. holdout_metrics.json
    worst5 = (
        per_series.head(5)[['facility_id', 'semiconductor_id', 'mae']]
        .round(2).to_dict('records')
    )
    metrics_json = {
        'target':              TARGET,
        'modeling_grain':      '(week, facility_id, semiconductor_id)',
        'best_cv_params':      best_params,
        'best_cv_mae':         round(best_cv_mae, 2),
        'holdout_week_range': {'first': first_holdout_week, 'last': last_train_week + 10},
        'row_level': {k: round(v, 4) for k, v in row_metrics.items()},
        'weekly_aggregate':    {k: round(v, 2) for k, v in agg_metrics.items()},
        'per_series': {
            'mae_mean':   round(float(per_series['mae'].mean()),   2),
            'mae_median': round(float(per_series['mae'].median()), 2),
            'mae_std':    round(float(per_series['mae'].std()),    2),
            'worst_5':    worst5,
        },
    }
    (out / 'holdout_metrics.json').write_text(json.dumps(metrics_json, indent=2))

    # 5. model_selection_summary.txt
    worst5_str = (
        per_series.head(5)[['facility_id', 'semiconductor_id', 'mae', 'rmse']]
        .round(2).to_string(index=False)
    )
    lines = [
        'MODEL SELECTION SUMMARY',
        '=' * 58,
        f'  Target                 : {TARGET}',
        f'  Modeling grain         : (week, facility_id, semiconductor_id)',
        f'  Best CV params         : {best_params}',
        f'  Best CV MAE            : {best_cv_mae:>10,.2f}',
        '',
        'HOLDOUT EVALUATION',
        '-' * 46,
        f'  Row-level MAE          : {row_metrics["mae"]:>10,.2f}',
        f'  Row-level RMSE         : {row_metrics["rmse"]:>10,.2f}',
        f'  Row-level MAPE         : {row_metrics["mape"] * 100:>10.2f}%',
        f'  Row-level R²           : {row_metrics["r2"]:>10.4f}',
        '',
        'WEEKLY AGGREGATE METRICS',
        '-' * 46,
        f'  System SUM  MAE        : {agg_metrics["system_sum_mae"]:>10,.2f}',
        f'  System SUM  RMSE       : {agg_metrics["system_sum_rmse"]:>10,.2f}',
        f'  Series MEAN MAE        : {agg_metrics["series_mean_mae"]:>10,.2f}',
        f'  Series MEAN RMSE       : {agg_metrics["series_mean_rmse"]:>10,.2f}',
        '',
        'INTERPRETATION',
        '-' * 46,
        '  Row-level MAE = granular prediction error per (series, week).',
        '  System SUM MAE can be much smaller because positive and negative',
        '  errors across the 48 series partially cancel at the weekly total.',
        '  Series MEAN MAE (groupby week → .mean()) enables cross-model benchmarking.',
        '',
        'PER-SERIES HOLDOUT MAE',
        '-' * 46,
        f'  Mean   : {per_series["mae"].mean():,.2f}',
        f'  Median : {per_series["mae"].median():,.2f}',
        f'  Std    : {per_series["mae"].std():,.2f}',
        '',
        'WORST 5 SERIES BY MAE',
        '-' * 46,
        worst5_str,
    ]
    (out / 'model_selection_summary.txt').write_text('\n'.join(lines))

    # 6. validation_window_explanation.txt
    expl_lines = [
        'VALIDATION WINDOW EXPLANATION',
        '=' * 62,
        '',
        'DESIGN PHILOSOPHY',
        '-' * 46,
        '  The holdout is defined as the LAST 10 WEEKS of the feature-ready',
        '  dataset (model_df), after lag/rolling feature engineering and NaN',
        '  dropping.',
        '',
        f'  Last training week  : {last_train_week}',
        f'  First holdout week  : {first_holdout_week}',
        f'  Holdout span        : 10 weeks',
        '',
        'WHY LAST 10 WEEKS (NOT FIXED ORIGIN)?',
        '-' * 46,
        '    This design:',
        '    - Evaluates the model on the most recent demand patterns',
        '    - Keeps train/holdout boundary clean with no row overlap',
        '',
        'FEATURE-READY WEEK RANGE',
        '-' * 46,
        '  The first ~8 weeks of each series are dropped by dropna() because',
        '  lag_8 and roll_mean_8 (using shift(1).rolling(8)) require 9 weeks',
        '  of history to produce a non-NaN value. This is expected.',
        '',
        'LEAKAGE PREVENTION',
        '-' * 46,
        '  All lag and rolling features use shift(1) before any windowing,',
        '  ensuring the current week\'s demand is never included in its own',
        '  feature computation. global_mean_lag_1 is the global mean at week',
        '  t-1, observable at prediction time for week t.',
    ]
    (out / 'validation_window_explanation.txt').write_text('\n'.join(expl_lines))

    print(f'  Artifacts saved → {out}/')


# ── Plots ──────────────────────────────────────────────────────────────────────

def plot_cv_summary(cv_results: dict, best_index: int) -> None:
    """
    Bar chart of holdout MAE per CV fold for the best parameter configuration.
    """
    n_splits  = sum(1 for k in cv_results if k.startswith('split') and '_test_score' in k)
    fold_maes = [-cv_results[f'split{i}_test_score'][best_index] for i in range(n_splits)]
    mean_mae  = float(np.mean(fold_maes))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        [f'Fold {i + 1}' for i in range(n_splits)],
        fold_maes,
        color=_BLUE, edgecolor='white', alpha=0.85,
    )
    ax.axhline(mean_mae, color=_ORANGE, lw=1.8, ls='--',
               label=f'Mean MAE = {mean_mae:,.0f}')
    ax.set_xlabel('CV Fold')
    ax.set_ylabel('MAE (original units)')
    ax.set_title('CV MAE per Fold — Best Parameter Configuration')
    ax.legend()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    plt.tight_layout()
    out = _ensure_artifacts() / 'cv_fold_mae.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out.name}')


def plot_full_history_and_holdout(
    df_raw: pd.DataFrame,
    test_df: pd.DataFrame,
    last_train_week: int,
) -> None:
    """
    Full system-level demand history (all training weeks from raw data)
    plus holdout actual vs predicted (SUM across all series per week).

    Uses df_raw for the training history so the earliest weeks (pre-feature
    engineering) are included — gives the most complete historical context.
    Holdout boundary is clearly marked.
    """
    # Training history: sum all series per week from the raw dataset
    train_hist = (
        df_raw[df_raw['week'] <= last_train_week]
        .groupby('week')[TARGET].sum()
        .reset_index()
    )
    # Holdout: sum actual and predicted per week
    ho = (
        test_df.groupby('week')[[TARGET, 'pred']].sum().reset_index()
    )

    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(train_hist['week'], train_hist[TARGET],
            color=_MUTED, lw=1.5, label='Training history (actual)')
    ax.plot(ho['week'], ho[TARGET],
            color=_BLUE, lw=2.5, label='Holdout actual')
    ax.plot(ho['week'], ho['pred'],
            color=_ORANGE, lw=2, ls='--', marker='o', ms=5, label='Holdout predicted')
    ax.axvline(last_train_week + 0.5, color=_GRAY, ls='--', lw=1.5,
               label=f'Holdout boundary (wk {last_train_week} → {last_train_week + 1})')
    ax.set_xlabel('Week')
    ax.set_ylabel('Total Customer Orders (sum of all series)')
    ax.set_title('System-Level Demand: Full Training History + Holdout Evaluation')
    ax.legend(fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    plt.tight_layout()
    out = _ensure_artifacts() / 'system_full_history_holdout.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out.name}')


def plot_holdout_zoom(test_df: pd.DataFrame) -> None:
    """
    Holdout weeks only — system-level actual vs predicted.
    Two panels:
      Left  — weekly SUM (system total, matches procurement planning view)
      Right — weekly MEAN (series average)
    """
    ho_sum  = test_df.groupby('week')[[TARGET, 'pred']].sum().reset_index()
    ho_mean = test_df.groupby('week')[[TARGET, 'pred']].mean().reset_index()
    weeks   = ho_sum['week'].tolist()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    for ax, ho, title, ylabel in [
        (axes[0], ho_sum,  'System Total (SUM)',        'Total Orders (all series)'),
        (axes[1], ho_mean, 'Series Average (MEAN)',     'Avg Orders per Series'),
    ]:
        ax.plot(weeks, ho[TARGET], color=_BLUE,   lw=2.5, label='Actual')
        ax.plot(weeks, ho['pred'], color=_ORANGE, lw=2, ls='--',
                marker='o', ms=4, label='Predicted')
        ax.set_title(f'Holdout — {title}')
        ax.set_xlabel('Week')
        ax.set_ylabel(ylabel)
        ax.set_xticks(weeks)
        ax.tick_params(axis='x', rotation=45)
        ax.legend(fontsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    plt.suptitle('System-Level Holdout: Actual vs Predicted', fontsize=11)
    plt.tight_layout()
    out = _ensure_artifacts() / 'system_holdout_actual_vs_predicted.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out.name}')


def plot_residuals(test_df: pd.DataFrame) -> None:
    """
    Two-panel residual diagnostic:
      Left  — histogram of (actual − predicted)
      Right — residuals vs predicted scatter
    """
    residuals = test_df[TARGET].values - test_df['pred'].values

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    axes[0].hist(residuals, bins=40, color=_BLUE, edgecolor='white', alpha=0.85)
    axes[0].axvline(0, color='red', lw=1.5, ls='--')
    axes[0].set_title('Residual Distribution')
    axes[0].set_xlabel('Actual − Predicted')
    axes[0].set_ylabel('Count')
    axes[0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    axes[1].scatter(test_df['pred'].values, residuals,
                    alpha=0.25, s=8, color=_BLUE)
    axes[1].axhline(0, color='red', lw=1.5, ls='--')
    axes[1].set_title('Residuals vs Predicted')
    axes[1].set_xlabel('Predicted')
    axes[1].set_ylabel('Residual')
    axes[1].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    plt.suptitle('Residual Analysis — Holdout Set', fontsize=11)
    plt.tight_layout()
    out = _ensure_artifacts() / 'residuals_summary.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out.name}')


def plot_worst_5_series(
    test_df: pd.DataFrame,
    df_raw: pd.DataFrame,
    per_series: pd.DataFrame,
    last_train_week: int,
    n_history_weeks: int = 24,
) -> None:
    """
    Small-multiple figure for the 5 worst series by holdout MAE.

    Each panel shows:
      - Last n_history_weeks of training history (muted, from df_raw)
      - Holdout actual (blue)
      - Holdout predicted (orange dashed)
      - Holdout boundary vertical line

    Layout: 2-column × 3-row grid (last slot hidden).
    """
    worst5 = per_series.head(5).reset_index(drop=True)
    n      = len(worst5)
    ncols, nrows = 2, 3

    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 4 * nrows))
    axes_flat = axes.flatten()
    for ax in axes_flat[n:]:
        ax.set_visible(False)

    for idx, row in worst5.iterrows():
        ax   = axes_flat[idx]
        fac  = str(row['facility_id'])
        semi = str(row['semiconductor_id'])

        # Recent training history from raw data (pre-feature-engineering)
        hist = (
            df_raw[
                (df_raw['facility_id'].astype(str) == fac)
                & (df_raw['semiconductor_id'].astype(str) == semi)
                & (df_raw['week'] <= last_train_week)
            ]
            .sort_values('week')
            .tail(n_history_weeks)
        )

        # Holdout window for this series
        ho = (
            test_df[
                (test_df['facility_id'].astype(str) == fac)
                & (test_df['semiconductor_id'].astype(str) == semi)
            ]
            .sort_values('week')
        )

        ax.plot(hist['week'], hist[TARGET],
                color=_MUTED, lw=1.5, label='Training history')
        ax.plot(ho['week'], ho[TARGET],
                color=_BLUE, lw=2, label='Actual')
        ax.plot(ho['week'], ho['pred'],
                color=_ORANGE, lw=2, ls='--', marker='o', ms=3, label='Predicted')
        ax.axvline(last_train_week + 0.5, color=_GRAY, ls=':', lw=1.2)
        ax.set_title(f'{fac} × {semi}   MAE = {row["mae"]:,.0f}', fontsize=9)
        ax.legend(fontsize=7, loc='upper left')
        ax.set_ylabel('Orders')
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    plt.suptitle('Worst 5 Series by Holdout MAE', fontsize=11, y=1.01)
    plt.tight_layout()
    out = _ensure_artifacts() / 'worst_5_series_holdout.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out.name}')


def plot_permutation_importance(pipeline, X_test: pd.DataFrame, y_test: np.ndarray) -> None:
    """
    Permutation importance on the holdout set (top 15 features).

    Operates on the full fitted pipeline with original (pre-OHE) X_test
    columns — importance is assigned per original feature, not per OHE dummy.

    Positive importance_mean = permuting that feature hurts MAE (important).
    Negative importance_mean = permuting slightly helps (near-zero / noise).
    """
    perm = permutation_importance(
        pipeline,
        X_test,
        y_test,
        scoring='neg_mean_absolute_error',
        n_repeats=5,
        random_state=42,
        n_jobs=-1,
    )

    imp_df = (
        pd.DataFrame({
            'feature':         X_test.columns.tolist(),
            'importance_mean': perm.importances_mean,
            'importance_std':  perm.importances_std,
        })
        .sort_values('importance_mean', ascending=False)
        .head(15)
        .reset_index(drop=True)
    )

    # Plot highest-importance at top (reverse for horizontal bars)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = [_BLUE if v >= 0 else _GRAY for v in imp_df['importance_mean']]
    ax.barh(
        imp_df['feature'][::-1],
        imp_df['importance_mean'][::-1],
        xerr=imp_df['importance_std'][::-1],
        color=colors[::-1],
        edgecolor='white',
        alpha=0.85,
        capsize=3,
    )
    ax.axvline(0, color='black', lw=0.8, ls='-')
    ax.set_xlabel('Mean decrease in MAE when feature is permuted\n(higher = more important)')
    ax.set_title('Permutation Feature Importance — Top 15  (Holdout Set)')
    plt.tight_layout()
    out = _ensure_artifacts() / 'permutation_importance.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print(f'  Saved: {out.name}')
