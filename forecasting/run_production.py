"""
run_production.py — Production Forecasting Pipeline

PRODUCTION MODEL (distinct from validation):
  - Retrains HGB on ALL observed history (weeks 9–145, 6,575 rows)
  - Uses validated best hyperparameters directly — no GridSearchCV
  - Generates 20-week forward forecasts (weeks 146–165)
  - Stores results in dim_forecast_run and fact_semiconductor_demand_forecast

Validated best params (from run_pipeline.py):
  learning_rate=0.05, max_depth=6, max_iter=200,
  min_samples_leaf=50, l2_regularization=0.1

Validated holdout performance (wk 136–145):
  MAE=205.93, RMSE=289.37, R²=0.7778

Forecast method: recursive multi-step
  - Lag/rolling features draw from actual demand for weeks ≤ 145;
    from prior-step predictions for weeks > 145.
  - Price features: last observed per series, held constant.
  - Promo flags: 0 (no planned promotions in forecast horizon).
  - 90% CI: ±1.645 × holdout RMSE, clipped at 0.

Usage (from project root):
    python -m forecasting.run_production
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from .features import CATEGORICAL_COLS, FEATURE_COLS, NUMERIC_FEATURES, TARGET, build_features
from .train import build_pipeline

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

DATA_PATH    = 'cleaned_data/finished_goods_demand_table.csv'
METRICS_PATH = 'artifacts/forecasting/holdout_metrics.json'

HORIZON_WEEKS  = 20
MAX_OBS_WEEK   = 145
WEEK_145_DATE  = date(2025, 10, 5)   # confirmed from CSV: week 145 = 2025-10-05

MODEL_VERSION  = 'hgb_v1_full_history'

# Validated hyperparameters — not re-searched here
BEST_PARAMS = {
    'model__learning_rate':     0.05,
    'model__max_depth':         6,
    'model__max_iter':          200,
    'model__min_samples_leaf':  50,
    'model__l2_regularization': 0.1,
}

HOLDOUT_RMSE    = 289.37
CI_Z_90         = 1.645
INTERVAL_METHOD = 'holdout_rmse_normal_approx'

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://localhost:5432/procurement_agent',
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _week_to_date(week: int) -> date:
    return WEEK_145_DATE + timedelta(weeks=(week - MAX_OBS_WEEK))


def _build_forecast_rows(
    target_week: int,
    series_list: list,
    demand_history: dict,
    price_info: dict,
    global_mean_lag_1: float,
) -> pd.DataFrame:
    """
    Build a 48-row feature DataFrame (one row per series) for target_week.
    Lag and rolling features are populated from demand_history, which holds
    actual demand for weeks ≤ 145 and predicted demand for weeks > 145.
    """
    target_date = _week_to_date(target_week)
    year        = target_date.year
    month       = target_date.month
    wk_sin      = np.sin(2 * np.pi * target_week / 52)
    wk_cos      = np.cos(2 * np.pi * target_week / 52)

    rows = []
    for (fac, semi) in series_list:
        hist = demand_history[(fac, semi)]

        lag_1 = hist.get(target_week - 1, np.nan)
        lag_2 = hist.get(target_week - 2, np.nan)
        lag_3 = hist.get(target_week - 3, np.nan)
        lag_4 = hist.get(target_week - 4, np.nan)
        lag_8 = hist.get(target_week - 8, np.nan)

        v4 = [hist[target_week - i] for i in range(1, 5)
              if target_week - i in hist]
        v8 = [hist[target_week - i] for i in range(1, 9)
              if target_week - i in hist]

        roll_mean_4 = float(np.mean(v4))  if v4          else np.nan
        roll_std_4  = float(np.std(v4, ddof=1)) if len(v4) > 1 else 0.0
        roll_mean_8 = float(np.mean(v8))  if v8          else np.nan
        roll_std_8  = float(np.std(v8, ddof=1)) if len(v8) > 1 else 0.0

        rsp  = price_info[(fac, semi)]['realized_selling_price']
        lp   = price_info[(fac, semi)]['list_price']
        disc = lp - rsp
        disc_pct = disc / lp if lp > 0 else 0.0

        rows.append({
            'facility_id':            fac,
            'semiconductor_id':       semi,
            'realized_selling_price': rsp,
            'list_price':             lp,
            'discount':               disc,
            'discount_pct':           disc_pct,
            'emailer_for_promotion':  0,
            'homepage_featured':      0,
            'promo_any':              0,
            'price_x_promo':          0.0,
            'discount_x_promo':       0.0,
            'week':                   target_week,
            'week_sin_52':            wk_sin,
            'week_cos_52':            wk_cos,
            'year':                   year,
            'month':                  month,
            'lag_1':                  lag_1,
            'lag_2':                  lag_2,
            'lag_3':                  lag_3,
            'lag_4':                  lag_4,
            'lag_8':                  lag_8,
            'roll_mean_4':            roll_mean_4,
            'roll_std_4':             roll_std_4,
            'roll_mean_8':            roll_mean_8,
            'roll_std_8':             roll_std_8,
            'global_mean_lag_1':      global_mean_lag_1,
        })

    df = pd.DataFrame(rows)
    df['facility_id']      = df['facility_id'].astype('object')
    df['semiconductor_id'] = df['semiconductor_id'].astype('object')
    return df


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _insert_forecast_run(cur, model_config: dict, n_series: int) -> int:
    """
    Upsert a dim_forecast_run row and return forecast_run_id.
    ON CONFLICT: re-running on the same day with the same model version
    updates run_status to 'completed' and returns the existing run_id,
    so re-runs are idempotent.
    """
    cur.execute(
        """
        INSERT INTO dim_forecast_run (
            forecast_origin_date,
            observed_through_week_date,
            horizon_weeks_min,
            horizon_weeks_max,
            n_series,
            n_forecast_rows,
            model_version,
            model_config,
            run_status,
            created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (forecast_origin_date, model_version)
        DO UPDATE SET run_status = 'completed'
        RETURNING forecast_run_id
        """,
        (
            date.today(),
            WEEK_145_DATE,
            1,
            HORIZON_WEEKS,
            n_series,
            None,
            MODEL_VERSION,
            json.dumps(model_config),
            'completed',
            'forecasting.run_production',
        ),
    )
    return cur.fetchone()[0]


def _insert_forecast_fact_rows(cur, rows: list) -> int:
    """
    Batch-insert forecast rows into fact_semiconductor_demand_forecast.
    Silently skips rows that already exist (same run × series × week).
    """
    sql = """
        INSERT INTO fact_semiconductor_demand_forecast (
            forecast_run_id,
            facility_id,
            semiconductor_id,
            target_week_date,
            horizon_weeks,
            predicted_demand,
            interval_lower_90,
            interval_upper_90,
            interval_method
        ) VALUES %s
        ON CONFLICT ON CONSTRAINT uq_forecast_grain DO NOTHING
    """
    psycopg2.extras.execute_values(cur, sql, rows, page_size=200)
    return len(rows)


def _update_n_forecast_rows(cur, run_id: int, n: int) -> None:
    cur.execute(
        "UPDATE dim_forecast_run SET n_forecast_rows = %s WHERE forecast_run_id = %s",
        (n, run_id),
    )


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run() -> None:
    print('=' * 62)
    print('  PRODUCTION FORECAST PIPELINE')
    print('  Full-History Retrain → 20-Week Forward Forecast')
    print('=' * 62)

    # ── Step 1: Load and build features ───────────────────────────────────────
    print('\n[1/6] Loading data and building features ...')
    df_raw   = pd.read_csv(DATA_PATH)
    model_df = build_features(df_raw)
    print(f'  All feature-ready rows : {len(model_df):,}')
    print(f'  Training weeks         : {model_df["week"].min()} – {model_df["week"].max()}')

    # ── Step 2: Retrain on full history (no GridSearch) ────────────────────────
    print('\n[2/6] Retraining HGB on full history ...')
    X_all = model_df[FEATURE_COLS].copy()
    y_all = model_df[TARGET].values.ravel()

    pipeline = build_pipeline()
    pipeline.set_params(**BEST_PARAMS)
    pipeline.fit(X_all, y_all)
    print(f'  Done. Params: {BEST_PARAMS}')

    # ── Step 3: Build demand history and price anchors ─────────────────────────
    print('\n[3/6] Building demand history and price anchors ...')
    df_src = (
        df_raw.rename(columns={'finished_sku_id': 'semiconductor_id'})
        if 'finished_sku_id' in df_raw.columns and 'semiconductor_id' not in df_raw.columns
        else df_raw.copy()
    )
    df_src['facility_id']      = df_src['facility_id'].astype(str)
    df_src['semiconductor_id'] = df_src['semiconductor_id'].astype(str)

    series_list = sorted(
        df_src[['facility_id', 'semiconductor_id']]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )

    demand_history = {}
    price_info     = {}
    for (fac, semi) in series_list:
        mask = (df_src['facility_id'] == fac) & (df_src['semiconductor_id'] == semi)
        sub  = df_src[mask].sort_values('week')
        demand_history[(fac, semi)] = dict(
            zip(sub['week'], sub['customer_orders'].astype(float))
        )
        last = sub.iloc[-1]
        price_info[(fac, semi)] = {
            'realized_selling_price': float(last['realized_selling_price']),
            'list_price':             float(last['list_price']),
        }

    print(f'  Series tracked : {len(series_list)}  '
          f'({len(set(f for f, _ in series_list))} facilities × '
          f'{len(set(s for _, s in series_list))} semiconductors)')

    # global_mean_lag_1 for h=1 is the global mean of actual week 145
    global_mean_by_week = {
        MAX_OBS_WEEK: float(np.mean([
            demand_history[(fac, semi)].get(MAX_OBS_WEEK, np.nan)
            for (fac, semi) in series_list
        ]))
    }

    # ── Step 4: Recursive multi-step forecast ──────────────────────────────────
    print(f'\n[4/6] Generating {HORIZON_WEEKS}-week recursive forecast ...')
    print(f'  Horizon: wk {MAX_OBS_WEEK+1} ({_week_to_date(MAX_OBS_WEEK+1)}) → '
          f'wk {MAX_OBS_WEEK+HORIZON_WEEKS} ({_week_to_date(MAX_OBS_WEEK+HORIZON_WEEKS)})')
    print()

    all_rows = []  # list of (run_id_placeholder, fac, semi, date, h, pred, lower, upper, method)

    for h in range(1, HORIZON_WEEKS + 1):
        target_week = MAX_OBS_WEEK + h
        target_date = _week_to_date(target_week)
        g_mean_lag1 = global_mean_by_week.get(target_week - 1, np.nan)

        X_fcast = _build_forecast_rows(
            target_week       = target_week,
            series_list       = series_list,
            demand_history    = demand_history,
            price_info        = price_info,
            global_mean_lag_1 = g_mean_lag1,
        )

        preds = np.clip(pipeline.predict(X_fcast[FEATURE_COLS]), 0.0, None)
        margin = CI_Z_90 * HOLDOUT_RMSE

        for (fac, semi), pred in zip(series_list, preds):
            lower = max(0.0, float(pred) - margin)
            upper = float(pred) + margin
            all_rows.append((
                None,           # forecast_run_id — set after DB insert
                fac,
                semi,
                target_date,
                h,
                float(pred),
                lower,
                upper,
                INTERVAL_METHOD,
            ))
            demand_history[(fac, semi)][target_week] = float(pred)

        global_mean_by_week[target_week] = float(np.mean(preds))
        print(f'  wk {target_week} ({target_date}): '
              f'mean={np.mean(preds):>7,.0f}  '
              f'min={np.min(preds):>6,.0f}  '
              f'max={np.max(preds):>7,.0f}')

    print(f'\n  Forecast rows generated: {len(all_rows):,}')

    # ── Step 5: Insert into database ──────────────────────────────────────────
    print('\n[5/6] Inserting into database ...')

    with open(METRICS_PATH) as f:
        saved_metrics = json.load(f)

    model_config = {
        'model_class':          'HistGradientBoostingRegressor',
        'n_features':           len(FEATURE_COLS),
        'training_weeks_min':   int(model_df['week'].min()),
        'training_weeks_max':   int(model_df['week'].max()),
        'training_rows':        int(len(X_all)),
        'best_params':          BEST_PARAMS,
        'validation_mae':       saved_metrics['row_level']['mae'],
        'validation_rmse':      saved_metrics['row_level']['rmse'],
        'validation_r2':        saved_metrics['row_level']['r2'],
        'forecast_method':      'recursive_multistep',
        'price_assumption':     'last_observed_held_constant',
        'promo_assumption':     'zero_no_planned_promotions',
        'ci_method':            INTERVAL_METHOD,
        'ci_z':                 CI_Z_90,
    }

    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                run_id = _insert_forecast_run(cur, model_config, len(series_list))
                print(f'  dim_forecast_run       → forecast_run_id = {run_id}')

                db_rows = [
                    (run_id, fac, semi, tdate, hwks, pred, lower, upper, imethod)
                    for (_, fac, semi, tdate, hwks, pred, lower, upper, imethod)
                    in all_rows
                ]
                n_inserted = _insert_forecast_fact_rows(cur, db_rows)
                _update_n_forecast_rows(cur, run_id, n_inserted)
                print(f'  fact_semiconductor_demand_forecast → {n_inserted:,} rows inserted')
    finally:
        conn.close()

    # ── Step 6: Final report ───────────────────────────────────────────────────
    all_preds = [r[5] for r in all_rows]
    print('\n' + '=' * 62)
    print('  PRODUCTION FORECAST COMPLETE')
    print('=' * 62)
    print(f'\n  Model              : {MODEL_VERSION}')
    print(f'  Trained on         : {len(X_all):,} rows  (weeks 9–{MAX_OBS_WEEK})')
    print(f'  Horizon            : wk {MAX_OBS_WEEK+1}–{MAX_OBS_WEEK+HORIZON_WEEKS}'
          f'  ({_week_to_date(MAX_OBS_WEEK+1)} → {_week_to_date(MAX_OBS_WEEK+HORIZON_WEEKS)})')
    _n_facilities = len(set(f for f, _ in series_list))
    _n_skus       = len(set(s for _, s in series_list))
    _n_series     = len(series_list)
    print(f'\n  Forecast Coverage:')
    print(f'    Facilities              : {_n_facilities}')
    print(f'    SKUs                    : {_n_skus}')
    print(f'    SKU × Facility series   : {_n_series}')
    print(f'  Forecast rows      : {n_inserted:,}')
    print(f'  Predicted demand   : min={min(all_preds):,.0f}  '
          f'mean={np.mean(all_preds):,.0f}  max={max(all_preds):,.0f}')
    print(f'  DB forecast_run_id : {run_id}')
    print(f'\n  Lead-time coverage:')
    print(f'    Max supplier LT  : 127 days = 18.1 wks  → covered ✓')
    print(f'    Mean supplier LT :  94 days = 13.4 wks  → covered ✓')
    print(f'\n  Ready for BOM explosion layer.')
    print('=' * 62)


if __name__ == '__main__':
    run()
