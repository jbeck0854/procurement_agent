"""
features.py — Feature engineering for semiconductor demand forecasting.

Modeling grain: one row per (week, facility_id, semiconductor_id).
Target: customer_orders (raw, not aggregated).

Excluded from features: date, year_month (non-numeric strings), customer_orders (target).
"""

import numpy as np
import pandas as pd

# ── Column definitions ─────────────────────────────────────────────────────────

CATEGORICAL_COLS = ['facility_id', 'semiconductor_id']

NUMERIC_FEATURES = [
    # ── Price signals ──────────────────────────────────────────────────────
    'realized_selling_price',
    'list_price',
    'discount',
    'discount_pct',
    # ── Promotional signals ────────────────────────────────────────────────
    'emailer_for_promotion',
    'homepage_featured',
    'promo_any',
    'price_x_promo',
    'discount_x_promo',
    # ── Time / seasonality ─────────────────────────────────────────────────
    'week',
    'week_sin_52',
    'week_cos_52',
    'year',
    'month',
    # ── Lag demand (per series) ────────────────────────────────────────────
    'lag_1',
    'lag_2',
    'lag_3',
    'lag_4',
    'lag_8',
    # ── Rolling demand statistics (per series, no current-week leakage) ───
    'roll_mean_4',
    'roll_std_4',
    'roll_mean_8',
    'roll_std_8',
    # ── Global demand signal ───────────────────────────────────────────────
    'global_mean_lag_1',
]

FEATURE_COLS = CATEGORICAL_COLS + NUMERIC_FEATURES
TARGET = 'customer_orders'


# ── Sanity checks ──────────────────────────────────────────────────────────────

def sanity_check(df: pd.DataFrame) -> None:
    """Print data integrity and distribution diagnostics before modeling."""
    print('── Data Sanity Check ────────────────────────────────────────')
    print(f'  Shape          : {df.shape}')
    print(f'  Weeks          : {df["week"].min()} – {df["week"].max()}'
          f'  ({df["week"].nunique()} unique)')
    print(f'  Facilities     : {df["facility_id"].nunique()}')
    print(f'  Semiconductors : {df["semiconductor_id"].nunique()}')
    print(f'  Series (F×S)   : {df.groupby(["facility_id", "semiconductor_id"]).ngroups}')

    n_dupes = df.duplicated(subset=['week', 'facility_id', 'semiconductor_id']).sum()
    dupe_status = '✓ None' if n_dupes == 0 else f'⚠  {n_dupes} duplicates found'
    print(f'  Duplicates (week×F×S): {dupe_status}')

    print(f'\n  customer_orders distribution:')
    desc = df['customer_orders'].describe()
    for k, v in desc.items():
        print(f'    {k:<8}: {v:>12,.2f}')
    skew    = df['customer_orders'].skew()
    pct_zero = (df['customer_orders'] == 0).mean() * 100
    print(f'    skewness : {skew:.3f}')
    print(f'    % zero   : {pct_zero:.1f}%')

    print(f'\n  Per-series observation counts:')
    obs = df.groupby(['facility_id', 'semiconductor_id']).size()
    print(f'    Min    : {obs.min()}')
    print(f'    Median : {obs.median():.0f}')
    print(f'    Max    : {obs.max()}')
    low = obs[obs < 20]
    if low.empty:
        print('    Low-history series (< 20 obs): none')
    else:
        print(f'  ⚠  Low-history series (< 20 obs):')
        print(low.to_string())
    print()


# ── Feature engineering ────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the feature-ready modeling dataset from the raw demand table.

    Steps:
      1. Sort by [facility_id, semiconductor_id, week]
      2. Cast entity columns to object dtype for sklearn compatibility
      3. Compute derived price / promo / cyclical features
      4. Compute global_mean_lag_1 — weekly cross-series mean, lagged 1 week
      5. Compute per-series lag features: lag_1, lag_2, lag_3, lag_4, lag_8
      6. Compute per-series rolling features with shift(1) to prevent leakage:
         roll_mean_4, roll_std_4, roll_mean_8, roll_std_8
      7. Drop rows with NaN in any feature or target column
         (early-history rows — expected and acceptable)

    Returns the feature-ready model_df.
    Excluded from the returned dataset: no columns are dropped, but only
    FEATURE_COLS + TARGET are used downstream for modeling.
    """
    df = df.copy()
    df = df.sort_values(
        ['facility_id', 'semiconductor_id', 'week']
    ).reset_index(drop=True)

    # Cast entity columns to object for consistent sklearn handling
    df['facility_id']      = df['facility_id'].astype('object')
    df['semiconductor_id'] = df['semiconductor_id'].astype('object')

    # ── Price / promo features ─────────────────────────────────────────────────
    df['discount'] = df['list_price'] - df['realized_selling_price']

    df['discount_pct'] = np.where(
        df['list_price'] > 0,
        (df['list_price'] - df['realized_selling_price']) / df['list_price'],
        0.0,
    )

    df['promo_any'] = (
        df['emailer_for_promotion'] | df['homepage_featured']
    ).astype(int)

    df['price_x_promo']    = df['realized_selling_price'] * df['promo_any']
    df['discount_x_promo'] = df['discount']               * df['promo_any']

    # ── Cyclical week features ─────────────────────────────────────────────────
    df['week_sin_52'] = np.sin(2 * np.pi * df['week'] / 52)
    df['week_cos_52'] = np.cos(2 * np.pi * df['week'] / 52)

    # ── Global demand lag ──────────────────────────────────────────────────────
    # Mean customer_orders across ALL series in week t, lagged by 1 week.
    # At prediction time for week t, the global mean of week t-1 is observable.
    global_weekly = (
        df.groupby('week')['customer_orders']
        .mean()
        .reset_index()
        .rename(columns={'customer_orders': '_gmean'})
    )
    global_weekly['global_mean_lag_1'] = global_weekly['_gmean'].shift(1)
    df = df.merge(
        global_weekly[['week', 'global_mean_lag_1']], on='week', how='left'
    )

    # ── Per-series lag features ────────────────────────────────────────────────
    grp = df.groupby(['facility_id', 'semiconductor_id'], sort=False)['customer_orders']

    for lag in [1, 2, 3, 4, 8]:
        df[f'lag_{lag}'] = grp.shift(lag)

    # ── Per-series rolling features ────────────────────────────────────────────
    # shift(1) before rolling ensures current week is excluded from every window
    for window in [4, 8]:
        df[f'roll_mean_{window}'] = grp.transform(
            lambda x: x.shift(1).rolling(window).mean()
        )
        df[f'roll_std_{window}'] = grp.transform(
            lambda x: x.shift(1).rolling(window).std()
        )

    # ── Drop NaN rows (early-history rows per series) ──────────────────────────
    n_before  = len(df)
    model_df  = df.dropna(subset=FEATURE_COLS + [TARGET]).copy()
    n_after   = len(model_df)
    n_dropped = n_before - n_after
    print(f'  Rows before dropna : {n_before:,}')
    print(f'  Rows after  dropna : {n_after:,}  ({n_dropped:,} early-history NaN rows dropped)')

    return model_df.reset_index(drop=True)
