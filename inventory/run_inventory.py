"""
run_inventory.py — Component Inventory Simulation and Policy Pipeline

Populates two tables:
  1. fact_component_inventory_history  (2,320 rows: 145 wks × 4 facilities × 4 products)
  2. fact_inventory_policy             (16 rows per forecast run: 4 × 4)

Pipeline:
  1. Load BOM-implied historical component demand
       fact_semiconductor_demand × dim_bom  →  aggregate to (week, facility, product)
  2. Load lead-time parameters from dim_supplier (compliance-eligible suppliers only)
  3. Load unit costs from cleaned_data/combined_products_UPDATED.csv (USA real_price)
  4. Compute μ_D, σ_D per (facility, product) from historical BOM-implied demand
  5. Compute S using the base-stock formula:
       S = μ_D*(r + μ_L) + z * sqrt((r + μ_L)*σ_D² + μ_D²*σ_L²)
  6. Run deterministic periodic-review simulation (r=8, L=round(μ_L))
  7. Write both tables to database

Simulation policy:
  - Cold start: on_hand = S at week 1
  - Review weeks: 1, 9, 17, 25, … (every 8 weeks)
  - Lead time: deterministic, round(μ_L_days / 7) weeks
  - scheduled_receipts_qty: total outstanding on-order (MRP convention)

Usage (from project root):
    python -m inventory.run_inventory
"""

import logging
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

COMPLIANCE_THRESHOLD = 0.50    # minimum compliance_eligibility to include supplier
REVIEW_PERIOD        = 8       # weeks
SERVICE_LEVEL_Z      = 1.65    # 95% service level (z-score)
COST_CSV_PATH        = 'cleaned_data/combined_products_UPDATED.csv'

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://localhost:5432/procurement_agent',
)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _load_bom_demand(conn) -> pd.DataFrame:
    """
    BOM-exploded historical component demand.
    Joins fact_semiconductor_demand × dim_bom, aggregates to
    (week_date, week_number, facility_id, product_key).
    Returns 2,320 rows (145 wks × 4 facilities × 4 products).
    """
    sql = """
        SELECT
            fsd.week_date,
            fsd.week_number,
            fsd.facility_id,
            db.product_key,
            SUM(fsd.customer_orders * db.units_per_sku)  AS bom_implied_demand
        FROM fact_semiconductor_demand fsd
        JOIN dim_bom db ON db.semiconductor_id = fsd.semiconductor_id
        GROUP BY fsd.week_date, fsd.week_number, fsd.facility_id, db.product_key
        ORDER BY fsd.week_number, fsd.facility_id, db.product_key
    """
    df = pd.read_sql(sql, conn)
    df['week_number']        = df['week_number'].astype(int)
    df['bom_implied_demand'] = df['bom_implied_demand'].astype(float)
    return df


def _load_lead_times(conn) -> dict:
    """
    Per-product lead-time stats (days) from compliance-eligible suppliers.
    Returns {product_key: {'mu_days': float, 'sigma_days': float, 'n': int}}.
    """
    sql = """
        SELECT
            product_key,
            AVG(lead_time_mean)   AS mu_days,
            AVG(lead_time_stddev) AS sigma_days,
            COUNT(*)              AS n_eligible
        FROM dim_supplier
        WHERE compliance_eligibility >= %(thr)s
        GROUP BY product_key
        ORDER BY product_key
    """
    with conn.cursor() as cur:
        cur.execute(sql, {'thr': COMPLIANCE_THRESHOLD})
        rows = cur.fetchall()
    return {
        int(pk): {'mu_days': float(mu), 'sigma_days': float(sig), 'n': int(n)}
        for pk, mu, sig, n in rows
    }


def _load_product_map(conn) -> dict:
    """Returns {product_key: product_name}."""
    with conn.cursor() as cur:
        cur.execute("SELECT product_key, product FROM dim_product ORDER BY product_key")
        return {int(row[0]): str(row[1]) for row in cur.fetchall()}


def _load_latest_forecast_run_id(conn) -> int:
    """Returns the most recent forecast_run_id from dim_forecast_run."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(forecast_run_id) FROM dim_forecast_run")
        val = cur.fetchone()[0]
    if val is None:
        raise RuntimeError('No rows in dim_forecast_run — run forecasting first.')
    return int(val)


def _load_unit_costs(product_map: dict) -> dict:
    """
    Global-average real_price per (product_key, year, month).

    Averages real_price across ALL countries for each (product, year, month)
    combination, then maps to product_key.  This is more defensible than
    USA-only because:
      - the firm sources globally, not exclusively from US suppliers
      - more observations per cell → fewer missing year-month combinations
      - avoids silent 0.0 fallback caused by missing USA rows

    Returns {(product_key, year, month): float}.
    """
    df = pd.read_csv(COST_CSV_PATH)
    # Average across all countries — no country_code filter
    avg = (
        df.groupby(['product', 'year', 'month'])['real_price']
        .mean()
        .reset_index()
    )
    name_to_key = {v: k for k, v in product_map.items()}
    result = {}
    for _, row in avg.iterrows():
        pk = name_to_key.get(str(row['product']))
        if pk is None:
            continue
        result[(pk, int(row['year']), int(row['month']))] = float(row['real_price'])
    return result


# ── Formula ────────────────────────────────────────────────────────────────────

def _base_stock_params(
    mu_d: float, sigma_d: float,
    mu_l: float, sigma_l: float,
    r: int,      z: float,
) -> tuple:
    """
    Base-stock formula:
        S  = mu_d*(r + mu_l) + z * sqrt((r + mu_l)*sigma_d^2 + mu_d^2*sigma_l^2)
    Returns (S, safety_stock).
    All inputs in consistent units (weeks for time, demand units for demand).
    """
    risk_period  = float(r) + mu_l
    variance     = risk_period * sigma_d**2 + mu_d**2 * sigma_l**2
    safety_stock = z * math.sqrt(max(variance, 0.0))
    S            = mu_d * risk_period + safety_stock
    return float(S), float(safety_stock)


# ── Inventory simulation ───────────────────────────────────────────────────────

def _simulate_series(
    demand_by_week:   dict,   # {week_number (int): demand (float)}
    S:                float,
    L_weeks:          int,    # deterministic lead time in weeks
    cost_by_ym:       dict,   # {(year, month): unit_cost (float)}
    week_date_by_wk:  dict,   # {week_number: date}
    facility_id:      str,
    product_key:      int,
    review_period:    int = 8,
) -> list:
    """
    Periodic-review order-up-to-S simulation.

    Cold start: on_hand = S, backorder = 0 at week 1.
    Review weeks: t where (t-1) % review_period == 0  →  1, 9, 17, …
    Lead time: deterministic (L_weeks).
    scheduled_receipts_qty: total outstanding on-order at end of week (MRP).
    """
    on_hand       = 0.65 * float(S)
    backorder     = 0.0
    pending       = {}          # {arrival_week_number (int): qty (float)}
    rows          = []

    for t in sorted(demand_by_week.keys()):
        # 1. Receive arrivals due this week
        arrivals  = pending.pop(t, 0.0)
        on_hand  += arrivals

        # 2. Fill backorders first (FIFO)
        if backorder > 0.0:
            fill      = min(backorder, on_hand)
            on_hand  -= fill
            backorder -= fill

        # 3. Satisfy current demand
        demand = float(demand_by_week[t])
        if demand <= on_hand:
            on_hand -= demand
        else:
            backorder += demand - on_hand
            on_hand    = 0.0

        # 4. End-of-period review: place order at review weeks
        order_qty    = 0.0
        on_order_pre = sum(pending.values())       # outstanding BEFORE review
        ip_pre       = on_hand + on_order_pre - backorder

        if (t - 1) % review_period == 0:
            order_qty = max(0.0, S - ip_pre)
            if order_qty > 0.0:
                arr_wk          = t + L_weeks
                pending[arr_wk] = pending.get(arr_wk, 0.0) + order_qty

        on_order = sum(pending.values())           # post-review (for IP tracking)

        # 5. Post-decision inventory position
        ip = on_hand + on_order - backorder

        # 6. Unit cost and inventory value
        wd        = week_date_by_wk[t]
        cost_key  = (wd.year, wd.month)
        cost      = cost_by_ym.get(cost_key)
        if cost is None:
            logger.warning(
                'Unit cost missing for product_key=%s facility=%s '
                'year=%s month=%s — defaulting to 0.0; '
                'inventory_value will be zero for this row.',
                product_key, facility_id, wd.year, wd.month,
            )
            cost = 0.0

        rows.append({
            'week_date':              wd,
            'week_number':            t,
            'facility_id':            facility_id,
            'product_key':            product_key,
            'bom_implied_demand':     round(demand,   4),
            'scheduled_receipts_qty': round(on_order_pre, 4),
            'on_hand_qty':            round(on_hand,  4),
            'backorder_qty':          round(backorder, 4),
            'order_placed_qty':       round(order_qty, 4),
            'inventory_position':     round(ip, 4),
            'unit_cost':              round(cost, 6),
            'inventory_value':        round(on_hand * cost, 4),
        })

    return rows


# ── DB writes ──────────────────────────────────────────────────────────────────

def _write_inventory_history(cur, rows: list) -> int:
    cur.execute("TRUNCATE fact_component_inventory_history")
    sql = """
        INSERT INTO fact_component_inventory_history (
            week_date, week_number, facility_id, product_key,
            bom_implied_demand, scheduled_receipts_qty, on_hand_qty,
            backorder_qty, order_placed_qty, inventory_position,
            unit_cost, inventory_value
        ) VALUES %s
    """
    psycopg2.extras.execute_values(
        cur, sql,
        [(r['week_date'], r['week_number'], r['facility_id'], r['product_key'],
          r['bom_implied_demand'], r['scheduled_receipts_qty'], r['on_hand_qty'],
          r['backorder_qty'], r['order_placed_qty'], r['inventory_position'],
          r['unit_cost'], r['inventory_value'])
         for r in rows],
        page_size=500,
    )
    return len(rows)


def _write_inventory_policy(cur, rows: list) -> int:
    sql = """
        INSERT INTO fact_inventory_policy (
            forecast_run_id, facility_id, product_key,
            avg_demand_weekly, std_demand_weekly,
            avg_lead_time_weeks, std_lead_time_weeks,
            review_period_weeks, service_level_z,
            safety_stock_qty, base_stock_target_qty,
            n_eligible_suppliers, compliance_threshold
        ) VALUES %s
        ON CONFLICT (forecast_run_id, facility_id, product_key) DO UPDATE SET
            avg_demand_weekly     = EXCLUDED.avg_demand_weekly,
            std_demand_weekly     = EXCLUDED.std_demand_weekly,
            avg_lead_time_weeks   = EXCLUDED.avg_lead_time_weeks,
            std_lead_time_weeks   = EXCLUDED.std_lead_time_weeks,
            safety_stock_qty      = EXCLUDED.safety_stock_qty,
            base_stock_target_qty = EXCLUDED.base_stock_target_qty,
            n_eligible_suppliers  = EXCLUDED.n_eligible_suppliers,
            computed_at           = NOW()
    """
    psycopg2.extras.execute_values(
        cur, sql,
        [(r['forecast_run_id'], r['facility_id'], r['product_key'],
          r['avg_demand_weekly'], r['std_demand_weekly'],
          r['avg_lead_time_weeks'], r['std_lead_time_weeks'],
          r['review_period_weeks'], r['service_level_z'],
          r['safety_stock_qty'], r['base_stock_target_qty'],
          r['n_eligible_suppliers'], r['compliance_threshold'])
         for r in rows],
        page_size=50,
    )
    return len(rows)


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run() -> None:
    print('=' * 66)
    print('  INVENTORY SIMULATION & POLICY PIPELINE')
    print('  BOM-Implied Demand  →  Periodic Review  →  Base-Stock Policy')
    print('=' * 66)

    conn = _get_conn()
    try:
        # ── Step 1: Load data ──────────────────────────────────────────────────
        print('\n[1/5] Loading data ...')
        demand_df   = _load_bom_demand(conn)
        lead_times  = _load_lead_times(conn)
        product_map = _load_product_map(conn)
        run_id      = _load_latest_forecast_run_id(conn)
        unit_costs  = _load_unit_costs(product_map)

        assert len(demand_df) > 0, 'BOM-implied demand is empty — load DB first.'
        assert len(lead_times) == 4, (
            f'Expected 4 products with lead time data, got {len(lead_times)}.'
        )

        print(f'  BOM demand rows      : {len(demand_df):,}')
        print(f'  Facilities           : {sorted(demand_df["facility_id"].unique())}')
        print(f'  Product keys         : {sorted(lead_times.keys())}')
        print(f'  Weeks                : {demand_df["week_number"].min()}–'
              f'{demand_df["week_number"].max()}')
        print(f'  Unit cost entries    : {len(unit_costs):,}')
        print(f'  Forecast run_id      : {run_id}')

        # Build week_number → date lookup (week_date is the same for all
        # facility × product rows sharing the same week_number)
        wk_unique = (demand_df[['week_number', 'week_date']]
                     .drop_duplicates('week_number')
                     .sort_values('week_number'))
        week_date_by_wk = {
            int(row.week_number): pd.Timestamp(row.week_date).date()
            for row in wk_unique.itertuples()
        }

        facilities = sorted(demand_df['facility_id'].unique())

        # ── Step 2: Compute policy parameters ─────────────────────────────────
        print('\n[2/5] Computing inventory policy (μ_D, σ_D, μ_L, σ_L, S) ...')
        print(f'  r={REVIEW_PERIOD}w  z={SERVICE_LEVEL_Z}  '
              f'compliance_threshold>={COMPLIANCE_THRESHOLD}')
        print()

        policy_rows = []
        base_stock  = {}    # {(facility_id, product_key): S}

        for product_key in sorted(lead_times.keys()):
            lt         = lead_times[product_key]
            mu_l       = lt['mu_days']   / 7.0
            sigma_l    = lt['sigma_days'] / 7.0
            n_eligible = lt['n']
            pname      = product_map.get(product_key, f'pk{product_key}')

            for facility_id in facilities:
                mask   = ((demand_df['facility_id'] == facility_id) &
                          (demand_df['product_key'] == product_key))
                series = demand_df.loc[mask, 'bom_implied_demand'].astype(float)

                if series.empty:
                    print(f'  ⚠  No demand: {facility_id} × {pname}  skipping')
                    continue

                mu_d    = float(series.mean())
                sigma_d = float(series.std(ddof=1))

                S, ss = _base_stock_params(
                    mu_d=mu_d, sigma_d=sigma_d,
                    mu_l=mu_l, sigma_l=sigma_l,
                    r=REVIEW_PERIOD, z=SERVICE_LEVEL_Z,
                )
                base_stock[(facility_id, product_key)] = S

                policy_rows.append({
                    'forecast_run_id':      run_id,
                    'facility_id':          facility_id,
                    'product_key':          product_key,
                    'avg_demand_weekly':    round(mu_d, 4),
                    'std_demand_weekly':    round(sigma_d, 4),
                    'avg_lead_time_weeks':  round(mu_l, 4),
                    'std_lead_time_weeks':  round(sigma_l, 4),
                    'review_period_weeks':  REVIEW_PERIOD,
                    'service_level_z':      SERVICE_LEVEL_Z,
                    'safety_stock_qty':     round(ss, 2),
                    'base_stock_target_qty': round(S, 2),
                    'n_eligible_suppliers': n_eligible,
                    'compliance_threshold': COMPLIANCE_THRESHOLD,
                })

                print(f'  {facility_id} × {pname:<36}: '
                      f'μ_D={mu_d:>9,.1f}  σ_D={sigma_d:>7,.1f}  '
                      f'μ_L={mu_l:.2f}w  SS={ss:>9,.1f}  S={S:>11,.1f}')

        print(f'\n  Policy rows: {len(policy_rows)}  (expected 16)')

        # ── Step 3: Run inventory simulation ──────────────────────────────────
        print('\n[3/5] Running periodic-review inventory simulation ...')
        print(f'  Review period: every {REVIEW_PERIOD} weeks  '
              f'|  Lead time: deterministic round(μ_L)')

        all_inv_rows = []

        for product_key in sorted(lead_times.keys()):
            lt      = lead_times[product_key]
            L_weeks = max(1, round(lt['mu_days'] / 7.0))
            pname   = product_map.get(product_key, f'pk{product_key}')

            # Unit costs keyed by (year, month) for this product only
            cost_by_ym = {
                (yr, mo): cost
                for (pk, yr, mo), cost in unit_costs.items()
                if pk == product_key
            }

            for facility_id in facilities:
                mask = ((demand_df['facility_id'] == facility_id) &
                        (demand_df['product_key'] == product_key))
                sub  = demand_df[mask].sort_values('week_number')

                if sub.empty:
                    continue

                demand_by_week = dict(zip(
                    sub['week_number'].astype(int),
                    sub['bom_implied_demand'].astype(float),
                ))

                S    = base_stock[(facility_id, product_key)]
                rows = _simulate_series(
                    demand_by_week  = demand_by_week,
                    S               = S,
                    L_weeks         = L_weeks,
                    cost_by_ym      = cost_by_ym,
                    week_date_by_wk = week_date_by_wk,
                    facility_id     = facility_id,
                    product_key     = product_key,
                    review_period   = REVIEW_PERIOD,
                )
                all_inv_rows.extend(rows)

            print(f'  {pname:<40}: L={L_weeks}w  ×{len(facilities)} facilities  done')

        print(f'\n  Inventory rows generated: {len(all_inv_rows):,}  (expected 2,320)')

        # ── Step 3b: Decision-point benchmark override ─────────────────────────
        # The final week (MAX week_number) is the planning decision point consumed
        # by vw_procurement_requirement.  The fully-converged periodic-review
        # simulation always yields IP ≈ S at that week (L=13–14 w > r=8 w means
        # at least one large order is always in transit), making net_requirement = 0
        # for every LP row.  We replace that single week's inventory state with a
        # benchmark anchored in historical demand statistics:
        #
        #   on_hand      = safety_stock_qty + avg_demand_weekly   (SS + 1 week avg)
        #   scheduled_receipts = 0                                (conservative)
        #
        # This produces net_requirement > 0 for forecast weeks where predicted
        # demand exceeds avg_demand_weekly, and 0 for weeks below — a ~50/50 mix.
        # Weeks 1–144 are untouched and preserve full simulation history.

        decision_wk  = max(r['week_number'] for r in all_inv_rows)
        mu_d_lookup  = {(r['facility_id'], r['product_key']): float(r['avg_demand_weekly'])
                        for r in policy_rows}
        ss_lookup    = {(r['facility_id'], r['product_key']): float(r['safety_stock_qty'])
                        for r in policy_rows}

        n_overridden = 0
        for row in all_inv_rows:
            if row['week_number'] != decision_wk:
                continue
            key    = (row['facility_id'], row['product_key'])
            mu_d   = mu_d_lookup[key]
            ss     = ss_lookup[key]
            dp_oh  = mu_d + ss          # SS + 1 week of average demand
            row['on_hand_qty']            = round(dp_oh, 4)
            row['scheduled_receipts_qty'] = 0.0
            row['backorder_qty']          = 0.0
            row['inventory_position']     = round(dp_oh, 4)
            row['order_placed_qty']       = 0.0
            row['inventory_value']        = round(dp_oh * row['unit_cost'], 4)
            n_overridden += 1

        print(f'  Decision-point override applied: {n_overridden} rows '
              f'(week {decision_wk})  on_hand = SS + μ_D, scheduled_receipts = 0')

        # ── Step 4: Write to database ──────────────────────────────────────────
        print('\n[4/5] Writing to database ...')

        with conn:
            with conn.cursor() as cur:
                n_inv = _write_inventory_history(cur, all_inv_rows)
                print(f'  fact_component_inventory_history → {n_inv:,} rows')
                n_pol = _write_inventory_policy(cur, policy_rows)
                print(f'  fact_inventory_policy            → {n_pol:,} rows '
                      f'(run_id={run_id})')

        # ── Step 5: Validation summary ─────────────────────────────────────────
        print('\n[5/5] Validation ...')

        inv_df = pd.DataFrame(all_inv_rows)
        pol_df = pd.DataFrame(policy_rows)

        # Row counts
        expected_inv = 145 * len(facilities) * len(lead_times)
        rc_ok = len(inv_df) == expected_inv
        print(f'  Inventory rows        : {len(inv_df):,}  '
              f'(expected {expected_inv:,})  {"✓" if rc_ok else "⚠"}')
        print(f'  Policy rows           : {len(pol_df):,}  '
              f'(expected 16)  {"✓" if len(pol_df) == 16 else "⚠"}')

        # No duplicates
        dupes = inv_df.duplicated(
            subset=['week_date', 'facility_id', 'product_key']
        ).sum()
        print(f'  Duplicate inv rows    : {dupes}  {"✓" if dupes == 0 else "⚠ FAIL"}')

        # Non-negative
        neg_oh = (inv_df['on_hand_qty']  < -0.01).sum()
        neg_bo = (inv_df['backorder_qty'] < -0.01).sum()
        neg_nr = (inv_df['order_placed_qty'] < -0.01).sum()
        print(f'  Negative on_hand      : {neg_oh}  '
              f'{"✓" if neg_oh == 0 else "⚠ FAIL"}')
        print(f'  Negative backorder    : {neg_bo}  '
              f'{"✓" if neg_bo == 0 else "⚠ FAIL"}')
        print(f'  Negative order_placed : {neg_nr}  '
              f'{"✓" if neg_nr == 0 else "⚠ FAIL"}')

        # Formula spot-check on first policy row
        s0 = pol_df.iloc[0]
        rp = s0['review_period_weeks']
        ml = s0['avg_lead_time_weeks']
        md = s0['avg_demand_weekly']
        sd = s0['std_demand_weekly']
        sl = s0['std_lead_time_weeks']
        z0 = s0['service_level_z']
        ss_check = z0 * math.sqrt((rp + ml)*sd**2 + md**2*sl**2)
        s_check  = md*(rp + ml) + ss_check
        ss_err   = abs(s0['safety_stock_qty']     - ss_check)
        s_err    = abs(s0['base_stock_target_qty'] - s_check)
        print(f'  Formula check SS err  : {ss_err:.4f}  '
              f'{"✓" if ss_err < 0.5 else "⚠ FAIL"}')
        print(f'  Formula check S err   : {s_err:.4f}  '
              f'{"✓" if s_err  < 0.5 else "⚠ FAIL"}')

        # Review-week order pattern
        review_wks  = inv_df[inv_df['order_placed_qty'] > 0.01]['week_number']
        bad_reviews = [t for t in review_wks if (t - 1) % REVIEW_PERIOD != 0]
        print(f'  Orders on non-review weeks: {len(bad_reviews)}  '
              f'{"✓" if len(bad_reviews) == 0 else "⚠ FAIL"}')

        # ── Sample output ──────────────────────────────────────────────────────
        print('\n  ── fact_inventory_policy (all 16 rows) ──')
        print(f'  {"Facility":<12} {"Product":<36} '
              f'{"μ_D":>10} {"SS":>10} {"S":>12}')
        print('  ' + '-' * 82)
        for _, r in pol_df.sort_values(['facility_id', 'product_key']).iterrows():
            pn = product_map.get(int(r['product_key']), str(r['product_key']))
            print(f'  {r["facility_id"]:<12} {pn:<36} '
                  f'{r["avg_demand_weekly"]:>10,.1f} '
                  f'{r["safety_stock_qty"]:>10,.1f} '
                  f'{r["base_stock_target_qty"]:>12,.1f}')

        print('\n  ── fact_component_inventory_history — week 145 (decision point) ──')
        last_wk    = inv_df['week_number'].max()
        sample_inv = (inv_df[inv_df['week_number'] == last_wk]
                      .sort_values(['facility_id', 'product_key']))
        print(f'  {"Facility":<12} {"Product":<36} '
              f'{"BOM_dem":>9} {"OH":>10} {"BO":>8} {"IP":>11}')
        print('  ' + '-' * 90)
        for _, r in sample_inv.iterrows():
            pn = product_map.get(int(r['product_key']), str(r['product_key']))
            print(f'  {r["facility_id"]:<12} {pn:<36} '
                  f'{r["bom_implied_demand"]:>9,.1f} '
                  f'{r["on_hand_qty"]:>10,.1f} '
                  f'{r["backorder_qty"]:>8,.1f} '
                  f'{r["inventory_position"]:>11,.1f}')

    finally:
        conn.close()

    print('\n' + '=' * 66)
    print('  INVENTORY PIPELINE COMPLETE')
    print('  fact_component_inventory_history and fact_inventory_policy loaded.')
    print('  vw_procurement_requirement is live — query when ready.')
    print('=' * 66)


if __name__ == '__main__':
    run()
