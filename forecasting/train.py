"""
train.py — Pipeline, CV splits, and grid search for semiconductor demand forecasting:
  - Week-based TimeSeriesSplit CV (not random row CV)
  - ColumnTransformer: OHE for categoricals, passthrough for numerics
  - HistGradientBoostingRegressor inside a Pipeline
  - GridSearchCV scored on neg_mean_absolute_error
"""

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .features import CATEGORICAL_COLS, NUMERIC_FEATURES

# ── Tuning grid ────────────────────────────────

PARAM_GRID = {
    'model__learning_rate':    [0.03, 0.05, 0.07],
    'model__max_iter':         [150, 200, 300],
    'model__max_depth':        [5, 6, 7],
    'model__min_samples_leaf': [30, 50, 70],
    'model__l2_regularization':[0.0, 0.1, 0.3],
}
# 3 × 3 × 3 × 3 × 3 = 243 combinations × 5 folds = 1,215 fits
# Local search neighborhood around prior winner:
#   learning_rate=0.05, max_depth=6, max_iter=200,
#   min_samples_leaf=50, l2_regularization=0.1


# ── Week-based time-series CV ──────────────────────────────────────────────────

def make_week_time_splits(train_df: pd.DataFrame, n_splits: int = 5) -> list:
    """
    Build week-aware time-series cross-validation splits:
      1. Derive unique train weeks in chronological order
      2. Apply TimeSeriesSplit to the ordered unique weeks
      3. Map each fold's train/val week sets back to row indices in train_df

    train_df must be reset_index()'d so that .index gives 0-based integer
    positions (required for sklearn's GridSearchCV cv= parameter).

    Returns a list of (train_indices, val_indices) numpy arrays.
    """
    unique_weeks = sorted(train_df['week'].unique())
    tscv   = TimeSeriesSplit(n_splits=n_splits)
    splits = []

    for train_week_idx, val_week_idx in tscv.split(unique_weeks):
        train_weeks = [unique_weeks[i] for i in train_week_idx]
        val_weeks   = [unique_weeks[i] for i in val_week_idx]

        train_idx = train_df.loc[train_df['week'].isin(train_weeks)].index.to_numpy()
        val_idx   = train_df.loc[train_df['week'].isin(val_weeks)].index.to_numpy()

        splits.append((train_idx, val_idx))

    return splits


# ── Pipeline ───────────────────────────────────────────────────────────────────

def build_pipeline() -> Pipeline:
    """
    Preprocessing + model pipeline.

    Preprocessor (ColumnTransformer):
      - OneHotEncoder(handle_unknown='ignore') for CATEGORICAL_COLS
        → facility_id (4 values) and semiconductor_id (12 values)
      - passthrough for NUMERIC_FEATURES (25 columns)
      - remainder='drop' (excludes date, year_month, customer_orders, etc.)

    Model: HistGradientBoostingRegressor(random_state=42)
      - No numeric scaling needed (tree-based model; scale of features
        does not influence split decisions)
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False),
             CATEGORICAL_COLS),
            ('num', 'passthrough', NUMERIC_FEATURES),
        ],
        remainder='drop',
    )

    return Pipeline(steps=[
        ('pre',   preprocessor),
        ('model', HistGradientBoostingRegressor(random_state=42)),
    ])


# ── Grid search ────────────────────────────────────────────────────────────────

def run_grid_search(
    X_train: pd.DataFrame,
    y_train,
    cv_splits: list,
) -> GridSearchCV:
    """
    Fit GridSearchCV with week-based CV splits.

    Scoring: neg_mean_absolute_error.
    n_jobs=-1 uses all available cores.
    Returns the fitted GridSearchCV (best_estimator_ is the refit full pipeline).
    """
    grid = GridSearchCV(
        estimator=build_pipeline(),
        param_grid=PARAM_GRID,
        cv=cv_splits,
        scoring='neg_mean_absolute_error',
        n_jobs=-1,
        verbose=1,
        refit=True,
    )
    grid.fit(X_train, y_train)
    return grid
