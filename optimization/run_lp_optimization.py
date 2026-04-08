"""
run_lp_optimization.py — Supplier Allocation LP

Allocates procurement volume across eligible suppliers for a selected
component to minimize risk-adjusted cost while satisfying demand,
budget, compliance, and diversification constraints.

Solver: PuLP + CBC (open-source, bundled with PuLP).
Gurobi can be swapped in by replacing pulp.LpProblem / pulp.lpSum
with gurobipy equivalents if a license is available.

Pipeline:
  1. Load net procurement requirement  →  vw_procurement_requirement
  2. Score eligible suppliers           →  vw_supplier_complete_profile
                                            + analytics.scoring.SupplierScorer
  3. Build LP                           →  PuLP model
  4. Solve
  5. Post-process                       →  facility split, MOQ flags, diagnostics
  6. Return structured LPResult

Usage (from project root):
    from optimization.run_lp_optimization import run, LPParams
    result = run(LPParams(product='transistors', lambda_risk=0.5))
    print(result['formula_description'])
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
import pulp
from dotenv import load_dotenv

# ── Path setup so analytics module is importable from project root ─────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analytics.scoring import SupplierScorer, load_contract  # noqa: E402

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

DATABASE_URL         = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/procurement_agent')
METRIC_CONTRACT_PATH = _PROJECT_ROOT / 'analytics' / 'metric_contract.yaml'

URGENCY_LEAD_TIME_WEIGHT = 0.25     # multiplicative weight applied to lead_time_mean_norm
                                     # (0–1, already scored) when urgency=True.
                                     # slowest supplier in the pool pays a 25% cost premium;
                                     # fastest supplier pays no urgency premium.
                                     # same structural form as lambda_risk.


def _qty_int(x: float) -> int:
    """Round-half-up to nearest integer (fractional part ≥ 0.5 → ceil)."""
    return int(x + 0.5)


# ── Parameter container ────────────────────────────────────────────────────────

@dataclass
class LPParams:
    """
    All user-facing parameters for one LP run.

    product             : component to procure ('transistors', 'microprocessors',
                          'integrated_circuit_components', 'power_devices')
    facility_id         : if set, restrict demand to this facility only;
                          default None = all facilities with net_req > 0
    budget_cap          : optional USD budget cap for this product / run;
                          None = unconstrained
    compliance_threshold: minimum compliance_eligibility to include a supplier;
                          default 0.50 (contract default)
    lambda_risk         : risk-aversion weight 0–1 in objective;
                          0 = pure cost, 1 = pure risk
    max_supplier_share  : maximum fraction of total requirement any single
                          supplier may receive; 1.0 = no cap
    service_level_target: multiplier on net_requirement to size total
                          procurement demand floor; 1.0 = exactly meet policy
                          requirement (95% SL already baked in); 1.05 = +5% buffer
    order_quantity      : units passed to SupplierScorer for bulk-discount
                          calculation; default 5000
    urgency             : if True, add a normalised lead-time cost premium
                          (λ_urgency × lead_time_mean_norm) to each supplier's
                          objective coefficient; 0=fastest supplier, no premium;
                          1=slowest supplier, URGENCY_LEAD_TIME_WEIGHT premium
    exclude_supplier_ids: optional list of supplier IDs to forcibly exclude
                          (supports disruption / what-if scenarios)
    forecast_run_id     : forecast run to source demand from; None = most recent
                          run in dim_forecast_run (resolved at query time)
    diversification_mode: controls supplier/country diversification constraint;
                          "none"                → no diversification constraint
                          "supplier_share_only" → apply max_supplier_share cap only
                          "country_diversified" → select exactly 3 suppliers, each from
                                                  a different country, each allocated
                                                  roughly one-third of volume (30–35%);
                                                  requires ≥ 3 countries in eligible pool
    """
    product:               str
    facility_id:           Optional[str]   = None
    budget_cap:            Optional[float] = None
    compliance_threshold:  float           = 0.50
    lambda_risk:           float           = 0.50
    max_supplier_share:    float           = 1.00
    service_level_target:  float           = 1.00
    order_quantity:        int             = 5_000
    urgency:               bool            = False
    exclude_supplier_ids:  list            = field(default_factory=list)
    forecast_run_id:       Optional[int]   = None
    diversification_mode:  str             = "none"


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _resolve_forecast_run_id(conn, forecast_run_id: Optional[int]) -> int:
    """Return the requested run_id, or the most recent one if None."""
    with conn.cursor() as cur:
        if forecast_run_id is not None:
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "WHERE forecast_run_id = %s",
                (forecast_run_id,),
            )
        else:
            cur.execute(
                "SELECT MAX(forecast_run_id) FROM dim_forecast_run"
            )
        row = cur.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(
            "No forecast run found in dim_forecast_run. "
            "Run forecasting/run_production.py first."
        )
    return int(row[0])


def _load_requirement(conn, params: LPParams, forecast_run_id: int) -> tuple[float, pd.DataFrame]:
    """
    Compute horizon-level net procurement requirement for the selected product.

    The inventory offset (on_hand, scheduled_receipts, backorder, safety_stock)
    is applied ONCE against the total gross demand for the planning horizon,
    per facility.  This is the correct formulation for a single-run LP that
    covers the full forecast window.

    Previous behaviour summed per-week max(0, gross_T + K) values, which
    applied the inventory offset N times (once per triggered week) and produced
    a demand floor 40–1000× below the correct horizon procurement need.

    Formula (per facility):
        facility_net_req = max(0,
            SUM(gross_requirement over all forecast weeks)
            + backorder_qty
            + safety_stock_qty
            - on_hand_qty
            - scheduled_receipts_qty
        )

    Returns
    -------
    D : float
        Total net requirement summed across included facilities.
    facility_df : pd.DataFrame
        One row per facility with columns [facility_id, net_req, share_pct].
    """
    sql = """
        SELECT
            lp.facility_id,
            dp.product,
            GREATEST(0,
                SUM(lp.total_component_requirement)
                + MAX(dp_snap.backorder_qty)
                + MAX(pol.safety_stock_qty)
                - MAX(dp_snap.on_hand_qty)
                - MAX(dp_snap.scheduled_receipts_qty)
            ) AS facility_net_req
        FROM vw_component_requirement_lp lp
        JOIN dim_product dp
            ON  dp.product_key = lp.product_key
        JOIN (
            SELECT facility_id,
                   product_key,
                   on_hand_qty,
                   scheduled_receipts_qty,
                   backorder_qty
            FROM   fact_component_inventory_history
            WHERE  week_date = (
                       SELECT MAX(week_date)
                       FROM   fact_component_inventory_history
                   )
        ) dp_snap
            ON  dp_snap.facility_id = lp.facility_id
            AND dp_snap.product_key = lp.product_key
        JOIN fact_inventory_policy pol
            ON  pol.forecast_run_id = lp.forecast_run_id
            AND pol.facility_id     = lp.facility_id
            AND pol.product_key     = lp.product_key
        WHERE dp.product          = %(product)s
          AND lp.forecast_run_id  = %(forecast_run_id)s
          {facility_filter}
        GROUP BY lp.facility_id, dp.product
        HAVING GREATEST(0,
            SUM(lp.total_component_requirement)
            + MAX(dp_snap.backorder_qty)
            + MAX(pol.safety_stock_qty)
            - MAX(dp_snap.on_hand_qty)
            - MAX(dp_snap.scheduled_receipts_qty)
        ) > 0
        ORDER BY lp.facility_id
    """.format(
        facility_filter="AND lp.facility_id = %(facility_id)s"
        if params.facility_id else ""
    )
    qparams = {'product': params.product, 'forecast_run_id': forecast_run_id}
    if params.facility_id:
        qparams['facility_id'] = params.facility_id

    df = pd.read_sql(sql, conn, params=qparams)

    if df.empty:
        return 0.0, df

    D = float(df['facility_net_req'].sum())
    df['share_pct'] = (df['facility_net_req'] / D * 100).round(2)
    return D, df


def _load_scored_suppliers(conn, params: LPParams) -> tuple[pd.DataFrame, list]:
    """
    Query vw_supplier_complete_profile for the selected product, run
    SupplierScorer, and return a DataFrame of eligible suppliers with
    cost and risk coefficients needed by the LP.

    Returns
    -------
    eligible_df : pd.DataFrame
        Columns include supplier_id, landed_unit_cost, risk_penalty_norm,
        compliance_eligibility, lead_time_mean, bulk_units, decision_tier_global,
        top_risk_drivers, etc.
    excluded : list[dict]
        Suppliers removed by compliance gate or explicit exclusion list,
        with reason.
    """
    sql = "SELECT * FROM vw_supplier_complete_profile WHERE product = %(product)s"
    df = pd.read_sql(sql, conn, params={'product': params.product})

    if df.empty:
        return pd.DataFrame(), []

    contract = load_contract(str(METRIC_CONTRACT_PATH))
    scorer   = SupplierScorer(contract)
    result   = scorer.score(
        df,
        Q                    = params.order_quantity,
        lambda_risk          = params.lambda_risk,
        compliance_threshold = params.compliance_threshold,
    )

    excluded = []

    # Suppliers dropped by compliance gate
    if not result.dropped_rows.empty:
        for _, row in result.dropped_rows.iterrows():
            excluded.append({
                'supplier_id':            row.get('supplier_id', ''),
                'country_code':           row.get('country_code', ''),
                'compliance_eligibility': float(row.get('compliance_eligibility', 0)),
                'exclusion_reason':       row.get('drop_reason', 'compliance_gate'),
            })

    eligible = result.ranked.copy()

    # Normalise risk_penalty to 0-1 for use as LP objective coefficient.
    # The scorer returns risk_penalty on a 0-100 scale; divide by 100.
    eligible['risk_penalty_norm'] = (
        eligible['risk_penalty'].astype(float) / 100.0
    ).clip(0.0, 1.0)

    # Apply explicit exclusion list (disruption / what-if)
    if params.exclude_supplier_ids:
        forced_out = eligible[
            eligible['supplier_id'].isin(params.exclude_supplier_ids)
        ].copy()
        for _, row in forced_out.iterrows():
            excluded.append({
                'supplier_id':            row['supplier_id'],
                'country_code':           row.get('country_code', ''),
                'compliance_eligibility': float(row.get('compliance_eligibility', 0)),
                'exclusion_reason':       'excluded_by_user_scenario',
            })
        eligible = eligible[
            ~eligible['supplier_id'].isin(params.exclude_supplier_ids)
        ].copy()

    return eligible, excluded


# ── Lead-time feasibility note ────────────────────────────────────────────────

def _build_lead_time_feasibility_note(
    conn,
    params:         LPParams,
    resolved_run_id: int,
    eligible_df:    pd.DataFrame,
    allocation_rows: list,
) -> tuple:
    """
    Return (note_str, urgency_feasibility) tuple.

    note_str: 0–2 sentence execution-risk note appended to executive summary.
    urgency_feasibility: dict with per-week feasibility data, or None if no shortfall.

    Fires only when the earliest triggered procurement week occurs before the
    selected suppliers can realistically deliver, based on lead_time_mean (days).
    Lead time is converted to weeks using round(lead_time_mean / 7.0), consistent
    with the simulation convention in run_inventory.py.

    Case A: faster alternatives exist in the eligible pool for the earliest week.
    Case B: no eligible supplier can cover the earliest week → spot-sourcing note.
    Suppressed: LP infeasible, no allocation rows, no triggered weeks, no gap.

    urgency_feasibility keys:
      earliest_shortfall_week  — first triggered week before selected suppliers can deliver
      gap_weeks                — all triggered weeks before min selected lead time
      coverable_weeks          — gap weeks where ≥1 eligible supplier can deliver on time
      uncoverable_weeks        — gap weeks where NO eligible supplier can deliver on time
      fast_suppliers           — eligible pool suppliers that can cover ≥1 gap week
    """
    if not allocation_rows:
        return "", None

    # Step 1: Earliest triggered procurement week for this product / run.
    facility_filter = "AND r.facility_id = %(facility_id)s" if params.facility_id else ""
    qparams = {'run_id': resolved_run_id, 'product': params.product}
    if params.facility_id:
        qparams['facility_id'] = params.facility_id

    sql_min = f"""
        SELECT MIN(r.horizon_week)
        FROM   vw_procurement_requirement r
        JOIN   dim_product dp ON dp.product_key = r.product_key
        WHERE  r.forecast_run_id = %(run_id)s
          AND  dp.product        = %(product)s
          AND  r.net_requirement > 0
          {facility_filter}
    """
    with conn.cursor() as cur:
        cur.execute(sql_min, qparams)
        row = cur.fetchone()

    if row is None or row[0] is None:
        return "", None  # no triggered weeks → no note

    earliest_week = int(row[0])

    # Step 2: Minimum lead time (weeks) across selected suppliers.
    selected_ids = {r['supplier_id'] for r in allocation_rows}
    selected_df  = eligible_df[eligible_df['supplier_id'].isin(selected_ids)]

    if selected_df.empty or 'lead_time_mean' not in selected_df.columns:
        return "", None

    min_selected_lead_weeks = int(round(float(selected_df['lead_time_mean'].min()) / 7.0))
    min_selected_lead_weeks = max(1, min_selected_lead_weeks)

    # Step 3: Gap check — if selected suppliers can already cover in time, no note.
    if earliest_week >= min_selected_lead_weeks:
        return "", None

    # Step 4: Compute lead weeks for all eligible suppliers.
    eligible_df = eligible_df.copy()
    eligible_df['_lead_weeks'] = eligible_df['lead_time_mean'].apply(
        lambda x: max(1, int(round(float(x) / 7.0)))
    )

    # Step 5: Query ALL triggered weeks in the gap (not just earliest).
    sql_all = f"""
        SELECT DISTINCT r.horizon_week
        FROM   vw_procurement_requirement r
        JOIN   dim_product dp ON dp.product_key = r.product_key
        WHERE  r.forecast_run_id = %(run_id)s
          AND  dp.product        = %(product)s
          AND  r.net_requirement > 0
          {facility_filter}
        ORDER BY r.horizon_week
    """
    with conn.cursor() as cur:
        cur.execute(sql_all, qparams)
        all_triggered = [int(r[0]) for r in cur.fetchall()]

    # Gap weeks = triggered weeks before selected suppliers can first deliver.
    gap_trigger_weeks = [w for w in all_triggered if w < min_selected_lead_weeks]
    if not gap_trigger_weeks:
        gap_trigger_weeks = [earliest_week]

    # Step 6: Per-week feasibility — which gap weeks can ≥1 eligible supplier cover?
    coverable_weeks   = []
    uncoverable_weeks = []
    for w in gap_trigger_weeks:
        if not eligible_df[eligible_df['_lead_weeks'] <= w].empty:
            coverable_weeks.append(w)
        else:
            uncoverable_weeks.append(w)

    # Fast suppliers: eligible pool members that can cover ≥1 gap week, top 3.
    max_gap_week = max(gap_trigger_weeks)
    fast_sups_df = (
        eligible_df[eligible_df['_lead_weeks'] <= max_gap_week]
        .sort_values('lead_time_mean')
        .head(3)
    )
    fast_suppliers = [
        {
            'supplier_id':     str(r['supplier_id']),
            'lead_time_weeks': int(r['_lead_weeks']),
            'lead_time_days':  int(round(float(r['lead_time_mean']))),
        }
        for _, r in fast_sups_df.iterrows()
    ]

    urgency_feasibility = {
        'earliest_shortfall_week': earliest_week,
        'gap_weeks':               gap_trigger_weeks,
        'coverable_weeks':         coverable_weeks,
        'uncoverable_weeks':       uncoverable_weeks,
        'fast_suppliers':          fast_suppliers,
    }

    # Step 7: Build exec-summary note string (preserves existing Case A / Case B text).
    can_cover_earliest = eligible_df[eligible_df['_lead_weeks'] <= earliest_week]
    if not can_cover_earliest.empty:
        # Case A: faster alternatives exist for the earliest week.
        top3  = can_cover_earliest.sort_values('lead_time_mean').head(3)
        names = [
            f"{i + 1}) {r['supplier_id']} ({int(round(float(r['lead_time_mean'])))} d)"
            for i, (_, r) in enumerate(top3.iterrows())
        ]
        note_str = (
            f" Early shortfall begins Week {earliest_week}, before selected supplier"
            f" lead times can cover it."
            f" Faster alternative(s) in pool: {', '.join(names)}."
        )
    else:
        # Case B: no eligible supplier can cover the earliest week.
        note_str = (
            f" Early shortfall begins Week {earliest_week}, before current supplier"
            f" lead times can cover it."
            f" Recommend emergency domestic / spot sourcing for immediate coverage;"
            f" planned orders will support later weeks."
        )

    return note_str, urgency_feasibility


# ── LP core ────────────────────────────────────────────────────────────────────

def _build_and_solve(
    D:           float,
    eligible_df: pd.DataFrame,
    params:      LPParams,
) -> dict:
    """
    Build and solve the LP using PuLP + CBC.

    Objective (minimize):
        Σ_j  c_j * (1 + λ_risk * r_j + λ_urgency * lt_norm_j)  *  x_j

    where:
        c_j          = landed_unit_cost (per unit, USD)
        r_j          = risk_penalty_norm (0–1)
        lt_norm_j    = lead_time_mean_norm (0–1, 0=fastest in pool, 1=slowest)
        λ_urgency    = URGENCY_LEAD_TIME_WEIGHT (0.25) if urgency else 0

    Constraints:
        C1  Σ x_j  ≥  sl * D                         (demand fulfillment)
        C2  Σ c_j * x_j  ≤  B                        (budget, optional)
        C3  x_j  ≤  α * sl * D    for all j          (max share per supplier)
        C4a Σ_j y_j  =  3                                 (country_diversified: exactly 3)
        C4b Σ_{j ∈ country_c} y_j  ≤  1  for each c   (one supplier per country)
        C4c 0.30*D  ≤  x_j  ≤  0.35*D  for selected j (30–35% share each; x_j=0 if unselected)
            y_j ∈ {0,1}
        C5  x_j  ≥  0                                 (non-negativity, default)

    Returns raw solve result dict.
    """
    demand_floor = params.service_level_target * D

    suppliers   = list(eligible_df['supplier_id'])
    cost        = dict(zip(eligible_df['supplier_id'],
                           eligible_df['landed_unit_cost'].astype(float)))
    risk_norm   = dict(zip(eligible_df['supplier_id'],
                           eligible_df['risk_penalty_norm'].astype(float)))
    # Normalise lead_time_mean to [0,1] within the eligible pool:
    #   0 = fastest supplier, 1 = slowest.
    # Computed here (not from scorer output) so the range reflects the
    # compliance-filtered pool, which is what the LP objective should penalise against.
    _lt_vals = eligible_df['lead_time_mean'].astype(float)
    _lt_min, _lt_max = _lt_vals.min(), _lt_vals.max()
    if _lt_max > _lt_min:
        _lt_norm_series = (_lt_vals - _lt_min) / (_lt_max - _lt_min)
    else:
        _lt_norm_series = _lt_vals * 0.0   # all equal — urgency has no effect
    lead_time_norm = dict(zip(eligible_df['supplier_id'], _lt_norm_series))

    lam   = float(params.lambda_risk)
    alpha = float(params.max_supplier_share)
    urg   = params.urgency
    lam_u = URGENCY_LEAD_TIME_WEIGHT if urg else 0.0

    # Effective cost coefficient per supplier:
    #   c_j × (1 + λ_risk × r_j + λ_urgency × lt_norm_j)
    obj_coeff = {
        j: cost[j] * (1 + lam * risk_norm[j] + lam_u * lead_time_norm[j])
        for j in suppliers
    }

    model = pulp.LpProblem('SupplierAllocation', pulp.LpMinimize)

    x = pulp.LpVariable.dicts('x', suppliers, lowBound=0)

    # Objective
    model += pulp.lpSum(obj_coeff[j] * x[j] for j in suppliers), 'risk_adjusted_cost'

    # C1: demand fulfillment
    c1 = pulp.lpSum(x[j] for j in suppliers) >= demand_floor
    model += c1, 'demand_fulfillment'

    # C2: budget (optional)
    if params.budget_cap is not None:
        c2 = pulp.lpSum(cost[j] * x[j] for j in suppliers) <= params.budget_cap
        model += c2, 'budget_cap'

    # C3 / diversification — modes are mutually exclusive
    country_map: dict = dict(zip(eligible_df['supplier_id'],
                                 eligible_df['country_code'].astype(str)))
    country_groups: dict = {}
    for j in suppliers:
        country_groups.setdefault(country_map.get(j, 'UNK'), []).append(j)

    country_diversity_applied:    bool       = False
    country_diversity_skip_reason: str | None = None
    y_vars:                       dict       = {}   # MIP binary selection variables
    country_share_lo:             float      = 0.0
    country_share_hi:             float      = 0.0

    if params.diversification_mode == "country_diversified":
        n_ctry = len(country_groups)
        n_sup  = len(suppliers)
        if n_ctry >= 3 and n_sup >= 3:
            # MIP: binary variable y_j = 1 if supplier j is selected
            y_vars = pulp.LpVariable.dicts('y', suppliers, cat='Binary')
            # Exactly 3 suppliers selected
            model += pulp.lpSum(y_vars[j] for j in suppliers) == 3, 'cd_exactly_3'
            # At most 1 supplier per country
            for ctry, grp in country_groups.items():
                model += pulp.lpSum(y_vars[j] for j in grp) <= 1, f'cd_one_per_{ctry}'
            # Per-supplier share bounds (tied to demand_floor): 30–35% when selected, 0 otherwise
            country_share_lo = 0.30 * demand_floor
            country_share_hi = 0.35 * demand_floor
            for j in suppliers:
                model += x[j] >= country_share_lo * y_vars[j], f'cd_lo_{j}'
                model += x[j] <= country_share_hi * y_vars[j], f'cd_hi_{j}'
            country_diversity_applied = True
        else:
            if n_ctry < 3:
                country_diversity_skip_reason = (
                    f"only {n_ctry} "
                    f"{'country' if n_ctry == 1 else 'countries'} "
                    f"in eligible pool — need ≥ 3; applying share-cap fallback"
                )
            else:
                country_diversity_skip_reason = (
                    f"only {n_sup} eligible supplier(s) — need ≥ 3 "
                    f"across ≥ 3 countries; applying share-cap fallback"
                )
            # MIP diversification is infeasible for this pool.
            # Fall back to a 50% per-supplier share cap so the LP must use
            # at least 2 suppliers, partially honouring the diversification intent.
            _fallback_share = min(alpha, 0.50) if alpha < 1.0 else 0.50
            for j in suppliers:
                model += x[j] <= _fallback_share * demand_floor, f'max_share_{j}'
    else:
        # "none" or "supplier_share_only": apply simple per-supplier share cap if set
        if alpha < 1.0:
            for j in suppliers:
                model += x[j] <= alpha * demand_floor, f'max_share_{j}'

    # Solve (suppress CBC console output)
    solver = pulp.PULP_CBC_CMD(msg=0)
    model.solve(solver)

    status = pulp.LpStatus[model.status]

    allocation = {}
    if status == 'Optimal':
        allocation = {j: max(0.0, x[j].varValue or 0.0) for j in suppliers}

    # Constraint diagnostics
    budget_binding      = False
    demand_binding      = False
    share_binding_count = 0
    country_n_selected: int        = 0
    country_n_distinct: int        = 0
    country_share_rule_sat: bool | None = None

    if status == 'Optimal':
        total_alloc = sum(allocation.values())
        total_cost  = sum(cost[j] * allocation[j] for j in suppliers)

        demand_binding = abs(total_alloc - demand_floor) < 1.0

        if params.budget_cap is not None:
            budget_binding = abs(total_cost - params.budget_cap) / max(params.budget_cap, 1) < 0.01

        if params.diversification_mode != "country_diversified" and alpha < 1.0:
            for j in suppliers:
                if abs(allocation[j] - alpha * demand_floor) < 1.0:
                    share_binding_count += 1

        if country_diversity_applied and y_vars:
            sel = [j for j in suppliers if (y_vars[j].varValue or 0) > 0.5]
            country_n_selected = len(sel)
            country_n_distinct = len({country_map.get(j, 'UNK') for j in sel})
            if total_alloc > 0 and sel:
                shares = [allocation[j] / total_alloc for j in sel]
                # Allow slight rounding tolerance (±2pp)
                country_share_rule_sat = all(0.28 <= s <= 0.37 for s in shares)
            else:
                country_share_rule_sat = False

    return {
        'status':                        status,
        'allocation':                    allocation,
        'obj_coeff':                     obj_coeff,
        'demand_floor':                  demand_floor,
        'demand_binding':                demand_binding,
        'budget_binding':                budget_binding,
        'share_binding_count':           share_binding_count,
        'country_diversity_applied':     country_diversity_applied,
        'country_diversity_skip_reason': country_diversity_skip_reason,
        'country_n_selected':            country_n_selected,
        'country_n_distinct':            country_n_distinct,
        'country_share_lo':              country_share_lo,
        'country_share_hi':              country_share_hi,
        'country_share_rule_sat':        country_share_rule_sat,
        'country_map':                   country_map,
    }


# ── Baseline comparison helper ─────────────────────────────────────────────────

def _run_baseline(D: float, eligible_df: pd.DataFrame, params: LPParams) -> dict:
    """
    Compute the cheapest-feasible baseline plan for session-summary comparison.

    Fixes: λ=0, diversification_mode='none', max_supplier_share=1.0, urgency=False.
    Inherits: product, compliance_threshold, service_level_target, order_quantity.
    Same compliance-filtered supplier pool as the main run.

    Returns a compact dict used by the session summary baseline comparison section.
    Returns {} if the eligible pool is empty or the baseline solve is infeasible.

    NOT shown in standard LP run output (_print_result).
    Only surfaced in the final session summary or on explicit comparison request.
    """
    if eligible_df.empty:
        return {}

    # Minimal params — pure cost, no extra constraints
    baseline_lp = LPParams(
        product              = params.product,
        compliance_threshold = params.compliance_threshold,
        lambda_risk          = 0.0,
        max_supplier_share   = 1.0,
        service_level_target = params.service_level_target,
        diversification_mode = 'none',
        urgency              = False,
        order_quantity       = params.order_quantity,
    )
    solve = _build_and_solve(D, eligible_df, baseline_lp)

    if solve['status'] != 'Optimal':
        return {}

    alloc = {j: q for j, q in solve['allocation'].items() if q >= 0.01}
    if not alloc:
        return {}

    total_alloc = sum(alloc.values())
    cost_map    = dict(zip(eligible_df['supplier_id'],
                           eligible_df['landed_unit_cost'].astype(float)))
    total_cost  = sum(cost_map.get(j, 0.0) * q for j, q in alloc.items())

    lead_sup   = max(alloc, key=lambda j: alloc[j])
    lead_share = alloc[lead_sup] / total_alloc * 100 if total_alloc > 0 else 0.0

    ctry_map  = dict(zip(eligible_df['supplier_id'],
                         eligible_df['country_code'].astype(str)))
    countries = {ctry_map.get(j, 'UNK') for j in alloc}

    return {
        'baseline_total_cost':          round(total_cost, 2),
        'baseline_selected_suppliers':  sorted(alloc.keys()),
        'baseline_lead_supplier_share': round(lead_share, 1),
        'baseline_country_count':       len(countries),
    }


# ── Post-processing ─────────────────────────────────────────────────────────────

def _facility_split(
    allocation:   dict,
    facility_df:  pd.DataFrame,
    D:            float,
) -> list:
    """
    Proportionally split each supplier's total allocation across facilities
    based on each facility's share of net_requirement.
    Returns list of {facility_id, net_req, share_pct, allocated_qty}.
    """
    rows = []
    for _, frow in facility_df.iterrows():
        facility_share = float(frow['facility_net_req']) / D if D > 0 else 0.0
        total_alloc    = sum(allocation.values())
        rows.append({
            'facility_id':    frow['facility_id'],
            'net_req':        _qty_int(float(frow['facility_net_req'])),
            'share_pct':      round(float(frow['share_pct']), 2),
            'allocated_qty':  _qty_int(total_alloc * facility_share),
        })
    return rows


def _moq_flag(supplier_id: str, allocated_qty: float, eligible_df: pd.DataFrame) -> dict:
    """
    Return MOQ / bulk-discount status for a selected supplier.
    """
    row = eligible_df[eligible_df['supplier_id'] == supplier_id].iloc[0]
    moq = int(row.get('bulk_units', 0))
    met = allocated_qty >= moq if moq > 0 else True
    return {
        'bulk_units_threshold':  moq,
        'moq_met':               met,
        'bulk_discount_active':  met,
        'moq_note': (
            'MOQ met — bulk pricing applies'
            if met else
            f'Allocated {_qty_int(allocated_qty):,} units, below MOQ of {moq:,} — '
            f'bulk discount not realized'
        ),
    }


def _build_formula_description(D: float, params: LPParams,
                                n_eligible: int, n_total: int,
                                solve_result: dict,
                                n_avoid_excluded: int = 0) -> str:
    """
    Return a structured, business-readable description of the LP that was solved.
    Shows the objective function, active constraints, and parameter interpretation.
    """
    lam    = params.lambda_risk
    sl_pct = int(params.service_level_target * 100)
    floor    = solve_result["demand_floor"]
    product  = params.product.replace('_', ' ')

    lam_u    = URGENCY_LEAD_TIME_WEIGHT if params.urgency else 0.0
    urg_term = f' + {lam_u:.2f} × lt_norm_j' if params.urgency else ''

    # ── Layer 1: Plain-English ─────────────────────────────────────────────────
    if lam == 0.0:
        tradeoff = 'no risk penalty — optimises on landed cost only'
    elif lam == 1.0:
        tradeoff = 'maximum risk penalty — cost still present but risk dominates'
    elif lam < 0.5:
        tradeoff = 'mild risk penalty — cost is the primary driver'
    elif lam > 0.5:
        tradeoff = 'stronger risk penalty — higher-risk suppliers are more heavily penalised'
    else:
        tradeoff = 'moderate risk penalty — balances landed cost with supplier risk'

    lines = [
        f'Goal: select the lowest-cost, lowest-risk supplier mix for {product}',
        f'      that satisfies all active business rules below.',
        '',
        f'Risk/cost tradeoff:  λ_risk = {lam:.2f}  →  {tradeoff}',
        f'  A higher λ_risk shifts volume toward lower-risk suppliers even at higher cost.',
        f'  A lower λ_risk prioritises unit cost over risk profile.',
    ]
    if params.urgency:
        lines += [
            f'  Urgency mode active  (λ_urgency = {lam_u:.2f}):',
            '    Slow-lead-time suppliers carry a cost premium proportional to their',
            '    normalised lead time within the eligible pool.',
            f'    Slowest supplier  → effective cost ×{1 + lam_u:.2f}  (+{lam_u*100:.0f}% premium)',
            '    Fastest supplier  → no urgency premium  (lead_time_mean_norm = 0)',
            '    Same mechanism as λ_risk — a dial, not a hard cutoff.',
        ]

    # Business rules
    lines += ['', 'Active business rules:']

    # Demand rule
    lines.append(
        f'  Demand rule       : procure at least {floor:,.0f} units'
        + (
            f'  (={sl_pct}% × {D:,.0f} net requirement)'
            if params.service_level_target != 1.0
            else f'  (= net requirement of {D:,.0f} units; safety stock already included)'
        )
    )

    # Budget rule
    if params.budget_cap:
        lines.append(
            f'  Budget rule       : total spend ≤ ${params.budget_cap:,.0f} USD  [active]'
        )
    else:
        lines.append('  Budget rule       : no cap set  [inactive]')

    # Diversification rule — labeled by mode
    div_mode = params.diversification_mode
    if div_mode == "country_diversified":
        if solve_result.get('country_diversity_applied'):
            lines.append('  Diversification   : country-diversified  [active]')
            lines.append('                      exactly 3 suppliers selected')
            lines.append('                      all from different countries')
            lines.append('                      each allocated roughly one-third of volume (30–35%)')
        else:
            reason = solve_result.get('country_diversity_skip_reason', 'insufficient data')
            lines.append('  Diversification   : country-diversified requested — constraint skipped')
            lines.append(f'                      ({reason})')
    elif div_mode == "supplier_share_only" or params.max_supplier_share < 1.0:
        pct     = int(params.max_supplier_share * 100)
        min_sup = int(-(-1 // params.max_supplier_share))
        lines.append(
            f'  Diversification   : supplier share cap  [active]'
        )
        lines.append(
            f'                      no supplier may exceed {pct}% of volume'
            f'  → at least {min_sup} suppliers required'
        )
    else:
        lines.append('  Diversification   : none  [inactive]')

    # Compliance rule
    lines.append(
        f'  Compliance gate   : suppliers with eligibility < {params.compliance_threshold:.0%} excluded'
        f'  →  {n_eligible} of {n_total} {product} suppliers eligible'
    )
    if n_avoid_excluded > 0:
        n_in_lp = n_eligible - n_avoid_excluded
        lines.append(
            f'  Avoid-tier filter : {n_avoid_excluded} Avoid-tier supplier(s) excluded from LP'
            f'  →  {n_in_lp} non-Avoid supplier(s) used  [active]'
        )

    # Facility scope
    if params.facility_id:
        lines.append(f'  Facility scope    : {params.facility_id} only')
        lines.append(
            f'                      demand reflects that facility\'s net requirement only;'
            f' allocation satisfies {params.facility_id} independently'
        )
    else:
        lines.append('  Facility scope    : all facilities with net_requirement > 0')
        lines.append(
            '                      demand is summed across all triggered facilities;'
            ' supplier allocation then split proportionally by facility share'
        )

    if params.exclude_supplier_ids:
        lines.append(
            f'  Scenario exclusion: {len(params.exclude_supplier_ids)} supplier(s) '
            f'forced out  ({", ".join(params.exclude_supplier_ids)})'
        )

    # ── Layer 2: Formula / Technical ──────────────────────────────────────────
    lines += [
        '',
        'Objective function:',
        f'  minimize  Σ_j  c_j × (1 + {lam:.2f} × r_j{urg_term})  ×  x_j',
        '',
        '  c_j      landed unit cost (USD/unit)',
        '  r_j      risk penalty, normalised 0–1',
        '  x_j      units allocated to supplier j  (continuous, ≥ 0)',
    ]
    if params.urgency:
        lines += [
            f'  lt_norm_j  lead_time_mean_norm (0–1, scored within eligible pool)',
            f'             0 = fastest supplier in pool;  1 = slowest',
            f'             λ_urgency = {lam_u:.2f}  →  slowest supplier carries a '
            f'{lam_u*100:.0f}% cost premium',
        ]

    lines += [
        '',
        'Constraints:',
        f'  C1  Σ x_j  ≥  {floor:,.0f}                        [demand rule]',
    ]
    if params.budget_cap:
        lines.append(
            f'  C2  Σ c_j × x_j  ≤  {params.budget_cap:,.0f}                [budget rule]'
        )
    else:
        lines.append('  C2  —                                          [budget rule inactive]')

    if div_mode == "country_diversified" and solve_result.get('country_diversity_applied'):
        lo = _qty_int(0.30 * floor)
        hi = _qty_int(0.35 * floor)
        lines += [
            '  C3a Σ_j y_j = 3                               [exactly 3 suppliers]',
            '  C3b Σ_{j ∈ country_c} y_j ≤ 1  ∀ c          [one supplier per country]',
            f'  C3c {lo:,} ≤ x_j ≤ {hi:,}  for selected j  [30–35% share each]',
            '       y_j ∈ {0,1}',
        ]
    elif params.max_supplier_share < 1.0:
        pct = int(params.max_supplier_share * 100)
        lines.append(
            f'  C3  x_j  ≤  {pct}% × {floor:,.0f}  for all j      [supplier share rule]'
        )
    else:
        lines.append('  C3  —                                          [diversification inactive]')

    return '\n'.join(lines)


# ── Main pipeline ───────────────────────────────────────────────────────────────

def run(params: LPParams) -> dict:
    """
    Run the full LP optimization pipeline.

    Parameters
    ----------
    params : LPParams
        User-controlled parameters for this run.

    Returns
    -------
    dict
        Fully structured LPResult with allocation, cost summary,
        excluded suppliers, constraint diagnostics, and formula description.
    """
    conn = _get_conn()
    try:
        # ── Step 0: Resolve forecast run ──────────────────────────────────────
        resolved_run_id = _resolve_forecast_run_id(conn, params.forecast_run_id)

        # ── Step 1: Net procurement requirement ───────────────────────────────
        D, facility_df = _load_requirement(conn, params, resolved_run_id)

        if D <= 0:
            return {
                'params_recap':           vars(params),
                'lp_status':             'Skipped',
                'reason':                (
                    f'No positive net_requirement found for product '
                    f'"{params.product}"'
                    + (f' at facility {params.facility_id}' if params.facility_id else '')
                    + '. No procurement action required.'
                ),
                'requirement':           {'total_net_requirement': 0},
                'allocation':            [],
                'cost_summary':          {},
                'excluded_suppliers':    [],
                'constraint_diagnostics': {},
                'formula_description':   '',
            }

        # ── Step 2: Score suppliers ────────────────────────────────────────────
        eligible_df, excluded = _load_scored_suppliers(conn, params)

        n_total    = len(eligible_df) + len(excluded)
        n_eligible = len(eligible_df)

        if n_eligible == 0:
            return {
                'params_recap':          vars(params),
                'lp_status':            'Infeasible',
                'reason':               (
                    f'No eligible suppliers for "{params.product}" after '
                    f'compliance threshold {params.compliance_threshold:.0%}.'
                ),
                'requirement':          {
                    'total_net_requirement': round(D, 2),
                    'adjusted_requirement':  round(D * params.service_level_target, 2),
                    'n_facilities_included': len(facility_df),
                },
                'allocation':           [],
                'cost_summary':         {},
                'excluded_suppliers':   excluded,
                'constraint_diagnostics': {'lp_status': 'Infeasible'},
                'formula_description':  '',
            }

        # ── Pre-check A: Compliance unlock note (Fix P3) ──────────────────────
        # Detect when a compliance threshold below the contract default (0.50)
        # did not actually add any new suppliers to the eligible pool.
        compliance_unlocked_note: str | None = None
        _CONTRACT_COMPLIANCE_DEFAULT = 0.50
        if params.compliance_threshold < _CONTRACT_COMPLIANCE_DEFAULT:
            _newly_in_pool = int(
                (eligible_df['compliance_eligibility'].astype(float)
                 < _CONTRACT_COMPLIANCE_DEFAULT).sum()
            )
            if _newly_in_pool == 0:
                compliance_unlocked_note = (
                    f"Compliance threshold was lowered to "
                    f"{params.compliance_threshold:.0%} but no additional suppliers "
                    f"entered the eligible pool — no suppliers found with a compliance "
                    f"score between {params.compliance_threshold:.0%} and "
                    f"{_CONTRACT_COMPLIANCE_DEFAULT:.0%}. "
                    f"Allocation is unchanged from the higher threshold."
                )

        # ── Pre-check B: Compliance exclusion callout (Fix P4) ────────────────
        # Surface a note when compliance filtering excluded any suppliers.
        n_excluded_compliance = sum(
            1 for e in excluded if 'compliance' in e.get('exclusion_reason', '')
        )
        compliance_exclusion_note: str | None = (
            f"{n_excluded_compliance} supplier(s) excluded by the "
            f"{params.compliance_threshold:.0%} compliance threshold. "
            f"Lowering the threshold may unlock additional options."
        ) if n_excluded_compliance > 0 else None

        # ── Pre-check C: Avoid-tier filter (Fix P1) ───────────────────────────
        # If non-Avoid suppliers can satisfy demand on their own, restrict the LP
        # to that subset.  If they cannot, fall back to the full eligible pool
        # and set a visible warning so the user knows an Avoid supplier was used.
        avoid_tier_warning: str | None = None
        lp_eligible_df = eligible_df          # pool the LP will actually use

        if 'decision_tier_global' in eligible_df.columns:
            _non_avoid_df = eligible_df[
                eligible_df['decision_tier_global'] != 'Avoid'
            ].copy()
            _n_avoid = len(eligible_df) - len(_non_avoid_df)

            if _n_avoid > 0 and len(_non_avoid_df) > 0:
                # Some suppliers are Avoid.  Test whether non-Avoid pool suffices.
                _probe = _build_and_solve(D, _non_avoid_df, params)
                if _probe['status'] == 'Optimal':
                    # Non-Avoid pool is sufficient — use restricted pool.
                    lp_eligible_df = _non_avoid_df
                else:
                    # Non-Avoid alone cannot satisfy demand — use full pool + warn.
                    avoid_tier_warning = (
                        f"Avoid-tier supplier(s) included: non-Avoid suppliers "
                        f"alone cannot satisfy the full procurement requirement of "
                        f"{_qty_int(D):,} units. Selection extended to Avoid-tier "
                        f"suppliers due to constraint limitations."
                    )
            elif _n_avoid > 0 and len(_non_avoid_df) == 0:
                # All eligible suppliers are Avoid-tier.
                avoid_tier_warning = (
                    "All eligible suppliers are classified as Avoid-tier. "
                    "This indicates limited supplier availability after compliance "
                    "filtering."
                )
        else:
            _n_avoid = 0

        n_avoid_excluded = len(eligible_df) - len(lp_eligible_df)

        # ── Step 3: Solve LP ───────────────────────────────────────────────────
        solve = _build_and_solve(D, lp_eligible_df, params)

        # ── Step 4: Build allocation rows ──────────────────────────────────────
        allocation_rows = []
        if solve['status'] == 'Optimal':
            total_alloc = sum(solve['allocation'].values())
            for j, qty in solve['allocation'].items():
                if qty < 0.01:
                    continue
                row   = lp_eligible_df[lp_eligible_df['supplier_id'] == j].iloc[0]
                c_j   = float(row['landed_unit_cost'])
                r_j   = float(row['risk_penalty_norm'])
                moq   = _moq_flag(j, qty, lp_eligible_df)

                top_drivers = row.get('top_risk_drivers', [])
                if isinstance(top_drivers, str):
                    import ast
                    try:
                        top_drivers = ast.literal_eval(top_drivers)
                    except Exception:
                        top_drivers = [top_drivers]

                allocation_rows.append({
                    'supplier_id':             j,
                    'country_code':            str(row.get('country_code', '')).strip(),
                    'decision_tier':           str(row.get('decision_tier_global', 'N/A')),
                    'allocated_qty':           _qty_int(qty),
                    'share_pct':               round(qty / total_alloc * 100, 2) if total_alloc > 0 else 0.0,
                    'landed_unit_cost':        round(c_j, 5),
                    'risk_penalty_norm':       round(r_j, 4),
                    'total_cost':              round(c_j * qty, 2),
                    'risk_adjusted_cost_total':round(solve['obj_coeff'][j] * qty, 2),
                    'top_risk_drivers':        top_drivers,
                    **moq,
                })

            # Sort by allocated quantity descending for readability
            allocation_rows.sort(key=lambda r: r['allocated_qty'], reverse=True)

        # Zero-allocation suppliers → flagged as excluded with reason
        for j in solve['allocation']:
            if solve['allocation'][j] < 0.01:
                row = lp_eligible_df[lp_eligible_df['supplier_id'] == j].iloc[0]
                excluded.append({
                    'supplier_id':            j,
                    'country_code':           str(row.get('country_code', '')).strip(),
                    'compliance_eligibility': float(row.get('compliance_eligibility', 0)),
                    'exclusion_reason':       'zero_allocation',
                })

        # ── Step 5: Cost summary ───────────────────────────────────────────────
        # total_alloc_raw: continuous LP values used for demand_satisfied check
        total_alloc_raw = sum(v for v in solve['allocation'].values() if v >= 0.01)
        total_cost = sum(r['total_cost'] for r in allocation_rows)
        total_rac  = sum(r['risk_adjusted_cost_total'] for r in allocation_rows)
        total_alloc_qty = sum(r['allocated_qty'] for r in allocation_rows)  # sum of ints

        if total_alloc_qty > 0:
            avg_cost = total_cost / total_alloc_qty
            avg_risk = sum(r['risk_penalty_norm'] * r['allocated_qty']
                           for r in allocation_rows) / total_alloc_qty
        else:
            avg_cost = avg_risk = 0.0

        budget_util   = None
        budget_remain = None
        if params.budget_cap:
            budget_util   = round(total_cost / params.budget_cap * 100, 1)
            budget_remain = round(params.budget_cap - total_cost, 2)

        cost_summary = {
            'total_cost_usd':          round(total_cost, 2),
            'total_risk_adjusted_cost':round(total_rac, 2),
            'avg_landed_unit_cost':    round(avg_cost, 5),
            'avg_risk_penalty_norm':   round(avg_risk, 4),
            'budget_utilization_pct':  budget_util,
            'budget_remaining_usd':    budget_remain,
        }

        # ── Step 6: Facility split ─────────────────────────────────────────────
        facility_breakdown = _facility_split(solve['allocation'], facility_df, D)

        # Countries selected — derived from allocation rows
        countries_selected = sorted({r['country_code'] for r in allocation_rows
                                      if r['country_code']})

        # ── Step 7: Constraint diagnostics ────────────────────────────────────
        constraint_diagnostics = {
            'lp_status':                    solve['status'],
            'demand_constraint_binding':    solve['demand_binding'],
            'budget_constraint_binding':    solve['budget_binding'] if params.budget_cap else None,
            'n_share_constraints_binding':  solve['share_binding_count'],
            'total_allocated':              total_alloc_qty,
            'demand_floor':                 _qty_int(solve['demand_floor']),
            'demand_satisfied':             total_alloc_raw >= solve['demand_floor'] - 1.0,
            'infeasibility_reason':         None if solve['status'] == 'Optimal' else
                                            'Check budget vs. demand floor feasibility.',
            'diversification_mode':         params.diversification_mode,
            'countries_selected':           countries_selected,
            'country_diversity_applied':    solve['country_diversity_applied'],
            'country_diversity_skip_reason': solve.get('country_diversity_skip_reason'),
            'country_n_selected':           solve.get('country_n_selected', 0),
            'country_n_distinct':           solve.get('country_n_distinct', 0),
            'country_share_lo':             solve.get('country_share_lo', 0.0),
            'country_share_hi':             solve.get('country_share_hi', 0.0),
            'country_share_rule_satisfied': solve.get('country_share_rule_sat'),
        }

        # ── Step 8: Baseline comparison (silent — not printed; for session summary) ─
        baseline = _run_baseline(D, eligible_df, params)

        # ── Step 9: Formula description ────────────────────────────────────────
        formula_desc = _build_formula_description(
            D, params, n_eligible, n_total, solve,
            n_avoid_excluded=n_avoid_excluded,
        )

        # Add Avoid-excluded suppliers to excluded list for transparency.
        if n_avoid_excluded > 0:
            _avoid_ids_in_lp = set(lp_eligible_df['supplier_id'])
            for _, _avoid_row in eligible_df.iterrows():
                if _avoid_row['supplier_id'] not in _avoid_ids_in_lp:
                    excluded.append({
                        'supplier_id':            _avoid_row['supplier_id'],
                        'country_code':           str(_avoid_row.get('country_code', '')).strip(),
                        'compliance_eligibility': float(_avoid_row.get('compliance_eligibility', 0)),
                        'exclusion_reason':       'avoid_tier_filter',
                    })

        # ── Step 10: Executive summary (business-readable one-paragraph string) ──
        n_lp_eligible = len(lp_eligible_df)
        if solve['status'] == 'Optimal' and allocation_rows:
            n_excl_comp = sum(
                1 for e in excluded if 'compliance' in e.get('exclusion_reason', '')
            )
            top_sup = allocation_rows[0]
            exec_summary = (
                f"Procure {_qty_int(solve['demand_floor']):,} units of "
                f"{params.product.replace('_', ' ')} "
                f"({int(params.service_level_target * 100)}% service-level target). "
                f"{len(allocation_rows)} of {n_lp_eligible} eligible supplier(s) selected. "
                f"Lead supplier: {top_sup['supplier_id']} "
                f"({top_sup['share_pct']:.0f}% of volume, "
                f"${top_sup['landed_unit_cost']:.4f}/unit). "
                f"Total procurement cost: ${cost_summary['total_cost_usd']:,.2f}."
            )
            if params.urgency:
                exec_summary += (
                    f" Urgency mode active (λ_urgency = {URGENCY_LEAD_TIME_WEIGHT:.2f}): "
                    "slow suppliers carry a lead-time cost premium; "
                    "the allocation favours faster suppliers."
                )
            if n_excl_comp > 0:
                exec_summary += (
                    f" {n_excl_comp} supplier(s) excluded by compliance "
                    f"threshold ({params.compliance_threshold:.0%})."
                )
            # Prepend Avoid warning so it appears before the main summary.
            if avoid_tier_warning:
                exec_summary = f"[AVOID-TIER ALERT] {avoid_tier_warning}  " + exec_summary
            # ── Lead-time feasibility note (appended last; does not alter LP result) ──
            _lt_note, _urgency_feas = _build_lead_time_feasibility_note(
                conn, params, resolved_run_id, lp_eligible_df, allocation_rows
            )
            exec_summary += _lt_note
        else:
            exec_summary = (
                f"No feasible procurement plan for "
                f"{params.product.replace('_', ' ')}. "
                + constraint_diagnostics.get(
                    'infeasibility_reason', 'Infeasible.'
                )
            )
            _urgency_feas = None

        return {
            'params_recap': {
                'product':               params.product,
                'facility_id':           params.facility_id,
                'budget_cap':            params.budget_cap,
                'compliance_threshold':  params.compliance_threshold,
                'lambda_risk':           params.lambda_risk,
                'max_supplier_share':    params.max_supplier_share,
                'service_level_target':  params.service_level_target,
                'order_quantity':        params.order_quantity,
                'urgency':               params.urgency,
                'exclude_supplier_ids':   params.exclude_supplier_ids,
                'forecast_run_id':        resolved_run_id,
                'diversification_mode':   params.diversification_mode,
            },
            'requirement': {
                'total_net_requirement':  _qty_int(D),
                'adjusted_requirement':   _qty_int(solve['demand_floor']),
                'n_facilities_included':  len(facility_df),
                'n_weeks_with_positive_req': None,   # available if needed; omitted for brevity
                'facility_breakdown':     facility_breakdown,
            },
            'supplier_pool': {
                'n_total_for_product':       n_total,
                'n_eligible_post_compliance':n_eligible,
                'n_excluded_compliance':     sum(
                    1 for e in excluded if 'compliance' in e.get('exclusion_reason','')
                ),
                'n_avoid_excluded_from_lp':  n_avoid_excluded,
                'n_in_lp':                   n_lp_eligible,
                'n_selected_by_lp':          len(allocation_rows),
                'compliance_threshold_applied': params.compliance_threshold,
            },
            'allocation':               allocation_rows,
            'cost_summary':             cost_summary,
            'excluded_suppliers':       excluded,
            'constraint_diagnostics':   constraint_diagnostics,
            'formula_description':      formula_desc,
            'executive_summary':        exec_summary,
            'baseline':                 baseline,
            # ── Semantic alerts (rendered prominently by demo layer) ───────────
            'avoid_tier_warning':       avoid_tier_warning,
            'compliance_unlocked_note': compliance_unlocked_note,
            'compliance_exclusion_note':compliance_exclusion_note,
            'diversification_fallback_note': (
                f"Country-diversified constraint could not be fully satisfied "
                f"({solve.get('country_diversity_skip_reason', '')}). "
                f"A 50% per-supplier share cap was applied as fallback to partially "
                f"enforce diversification intent."
            ) if (
                params.diversification_mode == 'country_diversified'
                and not solve.get('country_diversity_applied')
                and solve.get('country_diversity_skip_reason')
            ) else None,
            # ── Per-week lead-time feasibility (used by demo urgency bullets) ──────
            'urgency_feasibility': _urgency_feas,
        }

    finally:
        conn.close()


# ── CLI convenience runner ─────────────────────────────────────────────────────

def _print_result(result: dict) -> None:
    """Pretty-print a result dict for validation / demo preview."""

    print('\n' + '=' * 70)
    print('  SUPPLIER ALLOCATION — LP OPTIMIZATION RESULT')
    print('=' * 70)

    exec_summary = result.get('executive_summary', '')
    if exec_summary:
        print(f'\n── Executive Summary ────────────────────────────────────────────────')
        for line in exec_summary.split('. '):
            line = line.strip()
            if line:
                print(f'  {line}{"." if not line.endswith(".") else ""}')
        print(f'{"─" * 70}')

    status = result.get('constraint_diagnostics', {}).get('lp_status') or result.get('lp_status')
    print(f'\n  Solver status : {status}')

    if status not in ('Optimal',):
        print(f'  Reason        : {result.get("reason", "")}')
        return

    req = result['requirement']
    print(f'\n── Procurement Requirement ──────────────────────────────────────────')
    print(f'  Net requirement   : {req["total_net_requirement"]:>12,} units')
    print(f'  Adjusted target   : {req["adjusted_requirement"]:>12,} units')
    print(f'  Facilities        : {req["n_facilities_included"]}')
    for fb in req['facility_breakdown']:
        print(f'    {fb["facility_id"]:<14}  {fb["net_req"]:>10,} units  '
              f'({fb["share_pct"]:.1f}%)  allocated → {fb["allocated_qty"]:,}')

    sp = result['supplier_pool']
    print(f'\n── Supplier Pool ────────────────────────────────────────────────────')
    print(f'  Total suppliers   : {sp["n_total_for_product"]}')
    print(f'  Eligible          : {sp["n_eligible_post_compliance"]} '
          f'(compliance ≥ {sp["compliance_threshold_applied"]:.0%})')
    print(f'  Selected by LP    : {sp["n_selected_by_lp"]}')

    print(f'\n── Allocation ───────────────────────────────────────────────────────')
    hdr = f'  {"Supplier":<16} {"Country":>7} {"Tier":<12} {"Qty":>10} '  \
          f'{"Share%":>7} {"Unit$":>8} {"TotalCost":>12} {"MOQ?":>6}'
    print(hdr)
    print('  ' + '-' * 80)
    for r in result['allocation']:
        moq_flag = '✓' if r['moq_met'] else '!'
        print(
            f'  {r["supplier_id"]:<16} {r["country_code"]:>7} '
            f'{r["decision_tier"]:<12} {r["allocated_qty"]:>10,} '
            f'{r["share_pct"]:>7.1f}% {r["landed_unit_cost"]:>8.4f} '
            f'{r["total_cost"]:>12,.2f}  {moq_flag}'
        )
        if r.get('top_risk_drivers'):
            drivers = r['top_risk_drivers']
            if isinstance(drivers, (list, tuple)):
                print(f'    Risk drivers: {", ".join(str(d) for d in drivers)}')

    cs = result['cost_summary']
    print(f'\n── Cost Summary ─────────────────────────────────────────────────────')
    print(f'  Total cost (USD)          : ${cs["total_cost_usd"]:>14,.2f}')
    print(f'  Risk-adjusted total       : ${cs["total_risk_adjusted_cost"]:>14,.2f}')
    print(f'  Avg landed unit cost      : ${cs["avg_landed_unit_cost"]:>14.5f}')
    print(f'  Avg risk penalty (norm)   :  {cs["avg_risk_penalty_norm"]:>14.4f}')
    if cs['budget_utilization_pct'] is not None:
        print(f'  Budget utilization        :  {cs["budget_utilization_pct"]:>13.1f}%')
        print(f'  Budget remaining (USD)    : ${cs["budget_remaining_usd"]:>14,.2f}')

    cd = result['constraint_diagnostics']
    print(f'\n── Constraint Diagnostics ───────────────────────────────────────────')
    print(f'  Demand constraint binding : {cd["demand_constraint_binding"]}')
    if cd['budget_constraint_binding'] is not None:
        print(f'  Budget constraint binding : {cd["budget_constraint_binding"]}')
    print(f'  Share constraints binding : {cd["n_share_constraints_binding"]}')
    print(f'  Total allocated           : {cd["total_allocated"]:>10,}  '
          f'(floor = {cd["demand_floor"]:,})')
    print(f'  Demand satisfied          : {cd["demand_satisfied"]}')

    # Diversification diagnostics
    div_mode = cd.get('diversification_mode', 'none')
    countries = cd.get('countries_selected', [])
    print(f'  Diversification mode      : {div_mode}')
    if countries:
        print(f'  Countries selected        : {", ".join(countries)}'
              f'  ({len(countries)} {"country" if len(countries) == 1 else "countries"})')
    if div_mode == 'country_diversified':
        if cd.get('country_diversity_applied'):
            n_sel  = cd.get('country_n_selected', 0)
            n_dis  = cd.get('country_n_distinct', 0)
            sh_ok  = cd.get('country_share_rule_satisfied')
            lo_qty = _qty_int(cd.get('country_share_lo', 0))
            hi_qty = _qty_int(cd.get('country_share_hi', 0))
            print(f'  Suppliers selected (MIP)  : {n_sel}  (required: 3)')
            print(f'  Distinct countries        : {n_dis}  (required: 3)')
            print(f'  Share rule (30–35%)       : '
                  f'{"satisfied" if sh_ok else "NOT satisfied"}  '
                  f'[{lo_qty:,}–{hi_qty:,} units per supplier]')
        else:
            reason = cd.get('country_diversity_skip_reason', 'insufficient data')
            print(f'  Country diversity         : SKIPPED — {reason}')

    if result['excluded_suppliers']:
        comp_excluded = [e for e in result['excluded_suppliers']
                         if 'compliance' in e.get('exclusion_reason', '')]
        zero_alloc    = [e for e in result['excluded_suppliers']
                         if e.get('exclusion_reason') == 'zero_allocation']
        print(f'\n── Excluded Suppliers ───────────────────────────────────────────────')
        if comp_excluded:
            print(f'  Compliance-excluded  : {len(comp_excluded)} suppliers')
        if zero_alloc:
            print(f'  Zero-allocation (LP) : {len(zero_alloc)} suppliers '
                  f'(eligible but not selected)')

    print(f'\n── LP Problem Definition ────────────────────────────────────────────')
    for line in result['formula_description'].split('\n'):
        print(f'  {line}')

    print('\n' + '=' * 70)


if __name__ == '__main__':
    # ── Scenario 1: no diversification ────────────────────────────────────────
    params = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.50,
        compliance_threshold = 0.50,
        max_supplier_share   = 1.00,
        service_level_target = 1.00,
        order_quantity       = 5_000,
        diversification_mode = 'none',
    )
    result = run(params)
    _print_result(result)

    # ── Scenario 2: supplier share cap (max 40% per supplier) ─────────────────
    print('\n\n' + '─' * 70)
    print('  SCENARIO 2: Supplier share cap  (max 40% per supplier)')
    print('─' * 70)
    params2 = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.75,
        compliance_threshold = 0.50,
        max_supplier_share   = 0.40,
        budget_cap           = 5_000,
        service_level_target = 1.00,
        order_quantity       = 5_000,
        diversification_mode = 'supplier_share_only',
    )
    result2 = run(params2)
    _print_result(result2)

    # ── Scenario 3: country-diversified MIP (3 suppliers, 3 countries, ~1/3) ──
    print('\n\n' + '─' * 70)
    print('  SCENARIO 3: Country-diversified (3 suppliers, 3 countries, ~1/3 each)')
    print('─' * 70)
    params3 = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.50,
        compliance_threshold = 0.50,
        max_supplier_share   = 1.00,
        service_level_target = 1.00,
        order_quantity       = 5_000,
        diversification_mode = 'country_diversified',
    )
    result3 = run(params3)
    _print_result(result3)

    # ── Scenario 4: urgency mode (normalised lead-time cost premium) ───────────
    print('\n\n' + '─' * 70)
    print('  SCENARIO 4a: Baseline — no urgency')
    print('─' * 70)
    params4a = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.50,
        compliance_threshold = 0.50,
        max_supplier_share   = 0.40,
        service_level_target = 1.00,
        order_quantity       = 5_000,
        diversification_mode = 'supplier_share_only',
        urgency              = False,
    )
    result4a = run(params4a)
    _print_result(result4a)

    print('\n\n' + '─' * 70)
    print('  SCENARIO 4b: Urgency mode ON (same params, urgency=True)')
    print('─' * 70)
    params4b = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.50,
        compliance_threshold = 0.50,
        max_supplier_share   = 0.40,
        service_level_target = 1.00,
        order_quantity       = 5_000,
        diversification_mode = 'supplier_share_only',
        urgency              = True,
    )
    result4b = run(params4b)
    _print_result(result4b)
