# Semiconductor Demand Forecasting

## Overview

This module forecasts weekly customer order volume for semiconductor products across facility–SKU combinations. Forecasts drive the procurement planning layer: predicted demand is exploded through the Bill of Materials (BOM) and fed into the LP optimizer as component net requirements.

The pipeline is built around a **HistGradientBoosting Regressor (HGB)** trained on lag and rolling demand features, price signals, and cyclical time encodings. Two naive baselines (lag-1 and rolling mean-4) establish the performance floor.

---

## Data Structure and Grain

| Attribute | Value |
|---|---|
| Source table | `cleaned_data/finished_goods_demand_table.csv` |
| Modeling grain | `(week, facility_id, semiconductor_id)` — one row per series per week |
| Target | `customer_orders` (raw weekly order volume, not aggregated) |
| Series count | 48 (4 facilities × 12 semiconductor SKUs) |
| Observed history | Weeks 1–145 (~6,959 rows in the raw table; ~6,575 after feature NaN drop) |

Predictions are made at the row level. System-level totals (weekly SUM, series MEAN) are computed post-prediction for interpretability and procurement planning purposes only — the model is never trained on aggregated targets.

**System-level modeling:** A single HGB model is trained jointly on all 48 series. This is not 48 independently deployed per-SKU models. The cross-series feature (`global_mean_lag_1`) explicitly exploits shared demand patterns across series. System-level accuracy metrics therefore reflect the aggregate behavior of one model applied across all series, not the average of 48 separate forecasts.

---

## Feature Engineering (`features.py`)

`build_features(df)` takes the raw demand table and returns a feature-ready modeling dataset. All features are constructed with `shift(1)` before any windowing operation to prevent target leakage.

**Feature categories:**

| Category | Columns |
|---|---|
| Entity (categorical, OHE) | `facility_id`, `semiconductor_id` |
| Price signals | `realized_selling_price`, `list_price`, `discount`, `discount_pct` |
| Promotional signals | `emailer_for_promotion`, `homepage_featured`, `promo_any`, `price_x_promo`, `discount_x_promo` |
| Time / seasonality | `week`, `year`, `month`, `week_sin_52`, `week_cos_52` |
| Per-series lag demand | `lag_1`, `lag_2`, `lag_3`, `lag_4`, `lag_8` |
| Per-series rolling stats | `roll_mean_4`, `roll_std_4`, `roll_mean_8`, `roll_std_8` |
| Cross-series global signal | `global_mean_lag_1` (mean demand across all 48 series at week t−1) |

**Processing steps:**
1. Sort by `[facility_id, semiconductor_id, week]`
2. Compute derived price and promo interaction features
3. Encode cyclical week position with sin/cos at period 52
4. Compute `global_mean_lag_1` — weekly cross-series mean, shifted 1 week
5. Compute per-series lags (lag_1/2/3/4/8) via `groupby.shift()`
6. Compute per-series rolling statistics using `shift(1).rolling(window)`
7. Drop early-history rows with NaN features (approximately the first 8 weeks per series, due to `lag_8` and `roll_mean_8` initialization)

---

## Modeling Approach

### Baseline Models (`run_baseline.py`)

Two naive baselines are evaluated on the same 10-week holdout as HGB:

| Baseline | Prediction rule |
|---|---|
| **Naive lag-1** | `pred[t] = demand[t-1]` for the same series |
| **Rolling mean-4** | `pred[t] = mean(demand[t-4 : t-1])` for the same series |

Both baselines reuse `lag_1` and `roll_mean_4` columns already present in the holdout feature set — no additional computation is needed. HGB performance is reported as percentage lift over each baseline.

### HGB Model (`train.py`)

**Preprocessing pipeline (`build_pipeline`):**
- `OneHotEncoder(handle_unknown='ignore')` applied to `facility_id` and `semiconductor_id`
- Numeric features passed through unchanged (no scaling required for tree-based models)
- All other columns dropped via `remainder='drop'`

**Model:** `HistGradientBoostingRegressor(random_state=42)` wrapped in a scikit-learn `Pipeline`.

**Hyperparameter search space (243 combinations):**

| Parameter | Values searched |
|---|---|
| `learning_rate` | 0.03, 0.05, 0.07 |
| `max_iter` | 150, 200, 300 |
| `max_depth` | 5, 6, 7 |
| `min_samples_leaf` | 30, 50, 70 |
| `l2_regularization` | 0.0, 0.1, 0.3 |

**Validated best parameters:**
`learning_rate=0.05, max_depth=6, max_iter=200, min_samples_leaf=50, l2_regularization=0.1`

---

## Training and Validation (`run_pipeline.py`)

**Holdout split strategy:**
The last 10 feature-ready weeks are held out as a fixed test set. The remaining weeks form the training set. This ensures evaluation reflects the most recent demand patterns and maintains strict temporal ordering.

```
Train:   weeks  9 – 135   (~5,760 rows, ~126 unique weeks)
Holdout: weeks 136 – 145  (10 weeks × 48 series = 480 rows)
```

**Cross-validation:** Week-based `TimeSeriesSplit` with 5 folds (`make_week_time_splits`). CV is applied only within the training set. Each fold maps week indices to row indices so that no series within a fold crosses its temporal boundary. Scoring: `neg_mean_absolute_error`.

**GridSearchCV:** 243 configurations × 5 folds = 1,215 model fits. `n_jobs=-1`. Best estimator is refit on the full training set.

**Evaluation levels:**

| Level | Description |
|---|---|
| Row-level | MAE, RMSE, MAPE, R² at `(week × facility × semiconductor)` grain — primary metric for model selection |
| Weekly SUM | System-level total demand aggregated by week; errors partially cancel across 48 series |
| Weekly MEAN | Series-average demand per week; enables cross-model benchmarking |
| Per-series | MAE and RMSE for every `(facility_id × semiconductor_id)` pair; identifies hard-to-forecast SKUs |

**Validated holdout performance (weeks 136–145):**

| Metric | Value |
|---|---|
| Row-level MAE | 205.93 |
| Row-level RMSE | 289.37 |
| Row-level R² | 0.7778 |

---

## Forecast Generation Pipeline (`run_production.py`)

### Production Retrain

The production model retrains HGB on **all observed history** (weeks 9–145, ~6,575 rows) using the validated best hyperparameters directly — no GridSearchCV is re-run. This maximizes training data for the forward horizon.

### Recursive Multi-Step Forecast

The model generates **20 weeks of forward forecasts** (weeks 146–165) using a recursive rollout:

- For horizon step h=1: lag and rolling features are computed from actual demand (weeks ≤ 145)
- For h > 1: prior-step predictions backfill the demand history used to construct lag/rolling features
- Price features: last observed realized price per series, held constant across the horizon
- Promotional flags: set to 0 (no planned promotions in the forecast horizon)
- All predictions are clipped at 0

**Confidence intervals:** 90% CI computed as `±1.645 × holdout_RMSE` (= ±476.0 units), clipped at zero for the lower bound. Method: `holdout_rmse_normal_approx`.

**Lead-time coverage:**
The 20-week horizon covers the maximum observed supplier lead time (127 days = 18.1 weeks), ensuring all procurement decisions within the LP optimizer have forecast support.

### Database Write

Results are written to two PostgreSQL tables:

| Table | Contents |
|---|---|
| `dim_forecast_run` | One row per execution: `forecast_origin_date`, `observed_through_week_date` (the last actual demand week used in training — marks the boundary between history and forecast), `horizon_weeks_min/max`, `model_version`, `model_config` (hyperparameters as JSONB), `n_series`, `n_forecast_rows`, `run_status`. Upsert on `(forecast_origin_date, model_version)` — re-runs are idempotent. |
| `fact_semiconductor_demand_forecast` | One row per `(forecast_run_id, facility_id, semiconductor_id, target_week_date)`: `predicted_demand`, `interval_lower_90`, `interval_upper_90`, `horizon_weeks`. Inserts skip duplicate rows via `ON CONFLICT DO NOTHING`. |

**Downstream consumption:** Rows in `fact_semiconductor_demand_forecast` are the starting point for the full procurement planning pipeline. The BOM explosion layer joins this table to `dim_bom` via `vw_component_requirement_detail` to translate finished-good SKU demand into component-level gross requirements. Those component requirements are then aggregated into `vw_component_requirement_lp`, which the LP optimizer queries — together with the decision-point inventory snapshot and safety stock policy — to compute the horizon-level net procurement requirement per facility and component.

---

## Output Artifacts

Running `run_pipeline.py` saves all of the following to `artifacts/forecasting/` **before** any plots are generated:

| File | Description |
|---|---|
| `holdout_predictions.csv` | Row-level predictions for all 480 holdout rows (week × facility × semiconductor): actual and predicted. Audit trail and basis for all reported holdout metrics. |
| `per_series_holdout_metrics.csv` | Per-series MAE and RMSE sorted worst-first. Surfaces which SKU–facility pairs carry the most forecast uncertainty — input for procurement buffer decisions. |
| `cv_summary.csv` | Full GridSearchCV results (all 243 configs ranked by mean CV MAE). Validates that the selected hyperparameters were chosen systematically, not cherry-picked. |
| `holdout_metrics.json` | Machine-readable performance summary (row-level, weekly aggregate, per-series statistics). Read by agent helpers to answer "how accurate is the forecast?" questions. |
| `model_selection_summary.txt` | Plain-language evaluation report for stakeholders. Primary explainability document — summarizes model performance, validation design, and baseline comparisons in one place. |
| `validation_window_explanation.txt` | Documents holdout design and leakage prevention strategy. Supports audit and reproducibility claims. |
| `cv_fold_mae.png` | MAE per CV fold for the best configuration. Confirms model performance is stable across time periods — not just good on the last fold. |
| `system_full_history_holdout.png` | Full 145-week training history with holdout overlay (system-level SUM). Shows whether the model tracks real demand trends; primary evidence that the model learned meaningful patterns. |
| `system_holdout_actual_vs_predicted.png` | Holdout zoom: weekly SUM and weekly MEAN panels. Primary validation chart for stakeholder presentations — shows the model tracks actual weekly totals across the 10-week test window. |
| `residuals_summary.png` | Residual distribution histogram and residuals-vs-predicted scatter. A centered distribution with no trend confirms the model is not systematically over- or under-predicting. |
| `worst_5_series_holdout.png` | Small-multiple panels for the 5 highest-MAE series. Focuses procurement planners' attention on the highest-uncertainty SKUs where buffer stock or supplier flexibility matters most. |
| `permutation_importance.png` | Top 15 features by permutation importance on the holdout set. Validates that lag demand and rolling mean dominate as expected and confirms that the cross-series signal (`global_mean_lag_1`) adds value. |
| `baseline_system_comparison.png` | System-level SUM — Actual vs HGB vs Naive lag-1 vs Rolling mean-4. Quantifies HGB lift over naive baselines; primary justification for using ML over simple heuristics. |
| `baseline_example_series.png` | Single representative series (closest to median HGB MAE) — all three models. Shows HGB outperforms naive at the individual SKU level, not just in system-level aggregates. |

---

## Design Principles

**No target leakage.** All lag and rolling features use `shift(1)` before any windowing. `global_mean_lag_1` is the global mean at week t−1, which is observable when predicting week t.

**Week-aware CV.** TimeSeriesSplit operates on unique weeks, not individual rows. This prevents the model from seeing future rows of other series during validation, which standard row-level shuffled CV would allow.

**Artifacts before plots.** Numeric outputs are written to disk before any matplotlib figure is generated. A plotting failure cannot corrupt the model evaluation record.

**Idempotent DB writes.** Both `dim_forecast_run` (upsert) and `fact_semiconductor_demand_forecast` (`ON CONFLICT DO NOTHING`) are safe to re-run without duplicating data.

**Separation of validation and production.** `run_pipeline.py` performs holdout evaluation on a withheld test set. `run_production.py` retrains on all data and generates forward forecasts. The production model is never evaluated on data it trained on.

---

## Usage

```bash
# Run validation pipeline (GridSearchCV + holdout evaluation + plots)
python -m forecasting.run_pipeline

# Run baseline comparison (requires holdout_predictions.csv from above)
python -m forecasting.run_baseline

# Run production forecast (retrain on full history + write to DB)
python -m forecasting.run_production
```

All commands must be run from the project root.

## Agent-facing forecast retrieval and explainability helpers

The forecasting layer now includes business-facing helpers for agent-side retrieval and explainability.

These helpers do **not** retrain the model and do **not** change forecast generation logic. They read from already-stored production forecast outputs and artifacts. This makes them safe for demo use and faster for conversational retrieval.

### Helper categories

#### 1) Forecast summary
Returns a clean planning-window summary of the latest production forecast, including:
- planning horizon
- total forecasted demand
- facility / SKU coverage
- weekly totals
- forecast metadata

#### 2) Forecast drill-down
Returns week × facility × semiconductor detail for the production forecast, including:
- predicted demand
- lower / upper confidence bounds
- horizon week

This is used when the user wants to inspect:
- which SKUs are needed at which facilities
- where demand is concentrated
- how the forecast behaves across the horizon

#### 3) Forecast model assessment / explainability
Returns business-facing summaries and artifacts for:
- validation / training performance
- feature importance
- baseline comparison

This allows the agent to answer questions like:
- “How was the model trained and validated?”
- “What features drove the forecast most?”
- “How does the model compare to baseline approaches?”

### Why this matters

The forecasting layer now supports two distinct user needs:

1. **Operational planning**
   - What demand are we expecting?
   - Where is that demand located?
   - How uncertain is it?

2. **Model understanding**
   - Why should we trust the forecast?
   - What drives the prediction?
   - How much better is the model than simple baselines?

This separation helps the system feel like a real decision-support workflow rather than a single static output.
