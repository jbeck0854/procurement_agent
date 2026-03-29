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
import psycopg2.extras
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

URGENCY_LEAD_TIME_PENALTY = 0.002   # $ per day of lead-time mean added to unit cost
                                     # scales slow suppliers' effective cost upward


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
                          default 0.60 (contract default)
    lambda_risk         : risk-aversion weight 0–1 in objective;
                          0 = pure cost, 1 = pure risk
    max_supplier_share  : maximum fraction of total requirement any single
                          supplier may receive; 1.0 = no cap
    service_level_target: multiplier on net_requirement to size total
                          procurement demand floor; 1.0 = exactly meet policy
                          requirement (95% SL already baked in); 1.05 = +5% buffer
    order_quantity      : units passed to SupplierScorer for bulk-discount
                          calculation; default 5000
    urgency             : if True, penalise slow suppliers via lead-time term
                          in objective coefficient (no hard cut-off)
    exclude_supplier_ids: optional list of supplier IDs to forcibly exclude
                          (supports disruption / what-if scenarios)
    """
    product:               str
    facility_id:           Optional[str]   = None
    budget_cap:            Optional[float] = None
    compliance_threshold:  float           = 0.60
    lambda_risk:           float           = 0.50
    max_supplier_share:    float           = 1.00
    service_level_target:  float           = 1.00
    order_quantity:        int             = 5_000
    urgency:               bool            = False
    exclude_supplier_ids:  list            = field(default_factory=list)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _load_requirement(conn, params: LPParams) -> tuple[float, pd.DataFrame]:
    """
    Query vw_procurement_requirement for the selected product (and optionally
    facility), keeping only rows with net_requirement > 0.

    Returns
    -------
    D : float
        Total net requirement (sum across included facility × week rows).
    facility_df : pd.DataFrame
        One row per facility with columns [facility_id, net_req, share_pct].
    """
    sql = """
        SELECT pr.facility_id,
               dp.product,
               SUM(pr.net_requirement) AS facility_net_req
        FROM vw_procurement_requirement pr
        JOIN dim_product dp ON dp.product_key = pr.product_key
        WHERE dp.product        = %(product)s
          AND pr.net_requirement > 0
          {facility_filter}
        GROUP BY pr.facility_id, dp.product
        ORDER BY pr.facility_id
    """.format(
        facility_filter="AND pr.facility_id = %(facility_id)s"
        if params.facility_id else ""
    )
    qparams = {'product': params.product}
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


# ── LP core ────────────────────────────────────────────────────────────────────

def _build_and_solve(
    D:           float,
    eligible_df: pd.DataFrame,
    params:      LPParams,
) -> dict:
    """
    Build and solve the LP using PuLP + CBC.

    Objective (minimize):
        Σ_j  c_j * (1 + λ * r_j + urgency_j)  *  x_j

    where:
        c_j          = landed_unit_cost (per unit, USD)
        r_j          = risk_penalty_norm (0–1)
        urgency_j    = URGENCY_LEAD_TIME_PENALTY * lead_time_mean_j  if urgency else 0

    Constraints:
        C1  Σ x_j  ≥  sl * D                         (demand fulfillment)
        C2  Σ c_j * x_j  ≤  B                        (budget, optional)
        C3  x_j  ≤  α * sl * D    for all j          (max share per supplier)
        C4  x_j  ≥  0                                 (non-negativity, default)

    Returns raw solve result dict.
    """
    demand_floor = params.service_level_target * D

    suppliers   = list(eligible_df['supplier_id'])
    cost        = dict(zip(eligible_df['supplier_id'],
                           eligible_df['landed_unit_cost'].astype(float)))
    risk_norm   = dict(zip(eligible_df['supplier_id'],
                           eligible_df['risk_penalty_norm'].astype(float)))
    lead_time   = dict(zip(eligible_df['supplier_id'],
                           eligible_df['lead_time_mean'].astype(float)))

    lam   = float(params.lambda_risk)
    alpha = float(params.max_supplier_share)
    urg   = params.urgency

    # Effective cost coefficient per supplier
    obj_coeff = {
        j: cost[j] * (1 + lam * risk_norm[j])
           + (URGENCY_LEAD_TIME_PENALTY * lead_time[j] if urg else 0.0)
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

    # C3: max supplier share
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
    budget_binding = False
    demand_binding = False
    share_binding_count = 0

    if status == 'Optimal':
        total_alloc = sum(allocation.values())
        total_cost  = sum(cost[j] * allocation[j] for j in suppliers)

        demand_binding = abs(total_alloc - demand_floor) < 1.0

        if params.budget_cap is not None:
            budget_binding = abs(total_cost - params.budget_cap) / max(params.budget_cap, 1) < 0.01

        if alpha < 1.0:
            for j in suppliers:
                if abs(allocation[j] - alpha * demand_floor) < 1.0:
                    share_binding_count += 1

    return {
        'status':               status,
        'allocation':           allocation,
        'obj_coeff':            obj_coeff,
        'demand_floor':         demand_floor,
        'demand_binding':       demand_binding,
        'budget_binding':       budget_binding,
        'share_binding_count':  share_binding_count,
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
            'net_req':        round(float(frow['facility_net_req']), 2),
            'share_pct':      round(float(frow['share_pct']), 2),
            'allocated_qty':  round(total_alloc * facility_share, 2),
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
            f'Allocated {int(allocated_qty):,} units, below MOQ of {moq:,} — '
            f'bulk discount not realized'
        ),
    }


def _build_formula_description(D: float, params: LPParams,
                                n_eligible: int, n_total: int,
                                solve_result: dict) -> str:
    """
    Return a clean, business-readable description of the LP that was solved.
    """
    lam_pct  = int(params.lambda_risk * 100)
    sl_pct   = int(params.service_level_target * 100)
    demand   = f'{solve_result["demand_floor"]:,.0f}'
    product  = params.product.replace('_', ' ')

    parts = [
        f'Minimize total procurement spend for {product}, '
        f'weighted {100 - lam_pct}% cost / {lam_pct}% risk.',
        '',
        f'Procurement target: {demand} units '
        f'({sl_pct}% of net requirement = {D:,.0f} units; '
        f'safety stock coverage already included).',
    ]

    if params.budget_cap:
        parts.append(f'Budget cap: ${params.budget_cap:,.0f} USD.')

    if params.max_supplier_share < 1.0:
        pct = int(params.max_supplier_share * 100)
        min_sup = -(-1 // params.max_supplier_share)  # ceiling division
        parts.append(
            f'Diversification: no single supplier may receive more than '
            f'{pct}% of volume (requires at least {int(min_sup)} suppliers).'
        )

    if params.urgency:
        parts.append(
            'Urgency mode: slow-lead-time suppliers carry an additional '
            'cost penalty in the objective.'
        )

    if params.exclude_supplier_ids:
        parts.append(
            f'Scenario exclusions: {len(params.exclude_supplier_ids)} supplier(s) '
            f'forced out ({", ".join(params.exclude_supplier_ids)}).'
        )

    parts.append(
        f'Supplier pool: {n_eligible} of {n_total} {product} suppliers '
        f'eligible after compliance threshold ≥ {params.compliance_threshold:.0%}.'
    )

    if params.facility_id:
        parts.append(f'Facility filter: {params.facility_id} only.')
    else:
        parts.append('Facility scope: all facilities with positive net requirement.')

    return '\n'.join(parts)


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
        # ── Step 1: Net procurement requirement ───────────────────────────────
        D, facility_df = _load_requirement(conn, params)

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
                'requirement':           {'total_net_requirement': 0.0},
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

        # ── Step 3: Solve LP ───────────────────────────────────────────────────
        solve = _build_and_solve(D, eligible_df, params)

        # ── Step 4: Build allocation rows ──────────────────────────────────────
        allocation_rows = []
        if solve['status'] == 'Optimal':
            total_alloc = sum(solve['allocation'].values())
            for j, qty in solve['allocation'].items():
                if qty < 0.01:
                    continue
                row   = eligible_df[eligible_df['supplier_id'] == j].iloc[0]
                c_j   = float(row['landed_unit_cost'])
                r_j   = float(row['risk_penalty_norm'])
                moq   = _moq_flag(j, qty, eligible_df)

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
                    'allocated_qty':           round(qty, 2),
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
                row = eligible_df[eligible_df['supplier_id'] == j].iloc[0]
                excluded.append({
                    'supplier_id':            j,
                    'country_code':           str(row.get('country_code', '')).strip(),
                    'compliance_eligibility': float(row.get('compliance_eligibility', 0)),
                    'exclusion_reason':       'zero_allocation',
                })

        # ── Step 5: Cost summary ───────────────────────────────────────────────
        total_cost = sum(r['total_cost'] for r in allocation_rows)
        total_rac  = sum(r['risk_adjusted_cost_total'] for r in allocation_rows)
        total_alloc_qty = sum(r['allocated_qty'] for r in allocation_rows)

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

        # ── Step 7: Constraint diagnostics ────────────────────────────────────
        constraint_diagnostics = {
            'lp_status':                  solve['status'],
            'demand_constraint_binding':  solve['demand_binding'],
            'budget_constraint_binding':  solve['budget_binding'] if params.budget_cap else None,
            'n_share_constraints_binding':solve['share_binding_count'],
            'total_allocated':            round(total_alloc_qty, 2),
            'demand_floor':               round(solve['demand_floor'], 2),
            'demand_satisfied':           total_alloc_qty >= solve['demand_floor'] - 1.0,
            'infeasibility_reason':       None if solve['status'] == 'Optimal' else
                                          'Check budget vs. demand floor feasibility.',
        }

        # ── Step 8: Formula description ────────────────────────────────────────
        formula_desc = _build_formula_description(
            D, params, n_eligible, n_total, solve
        )

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
                'exclude_supplier_ids':  params.exclude_supplier_ids,
            },
            'requirement': {
                'total_net_requirement':  round(D, 2),
                'adjusted_requirement':   round(solve['demand_floor'], 2),
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
                'n_selected_by_lp':          len(allocation_rows),
                'compliance_threshold_applied': params.compliance_threshold,
            },
            'allocation':             allocation_rows,
            'cost_summary':           cost_summary,
            'excluded_suppliers':     excluded,
            'constraint_diagnostics': constraint_diagnostics,
            'formula_description':    formula_desc,
        }

    finally:
        conn.close()


# ── CLI convenience runner ─────────────────────────────────────────────────────

def _print_result(result: dict) -> None:
    """Pretty-print a result dict for validation / demo preview."""

    print('\n' + '=' * 70)
    print('  SUPPLIER ALLOCATION — LP OPTIMIZATION RESULT')
    print('=' * 70)

    status = result.get('constraint_diagnostics', {}).get('lp_status') or result.get('lp_status')
    print(f'\n  Solver status : {status}')

    if status not in ('Optimal',):
        print(f'  Reason        : {result.get("reason", "")}')
        return

    req = result['requirement']
    print(f'\n── Procurement Requirement ──────────────────────────────────────────')
    print(f'  Net requirement   : {req["total_net_requirement"]:>12,.2f} units')
    print(f'  Adjusted target   : {req["adjusted_requirement"]:>12,.2f} units')
    print(f'  Facilities        : {req["n_facilities_included"]}')
    for fb in req['facility_breakdown']:
        print(f'    {fb["facility_id"]:<14}  {fb["net_req"]:>10,.2f} units  '
              f'({fb["share_pct"]:.1f}%)  allocated → {fb["allocated_qty"]:,.2f}')

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
            f'{r["decision_tier"]:<12} {r["allocated_qty"]:>10,.1f} '
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
    print(f'  Total allocated           : {cd["total_allocated"]:>10,.2f}  '
          f'(floor = {cd["demand_floor"]:,.2f})')
    print(f'  Demand satisfied          : {cd["demand_satisfied"]}')

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

    print(f'\n── Formula Description ──────────────────────────────────────────────')
    for line in result['formula_description'].split('\n'):
        print(f'  {line}')

    print('\n' + '=' * 70)


if __name__ == '__main__':
    # ── Validation run — transistors, default params ───────────────────────────
    params = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.50,
        compliance_threshold = 0.60,
        max_supplier_share   = 1.00,
        service_level_target = 1.00,
        order_quantity       = 5_000,
    )
    result = run(params)
    _print_result(result)

    # ── Second validation — with budget + diversification ─────────────────────
    print('\n\n' + '─' * 70)
    print('  SCENARIO 2: Budget cap + diversification (max 40% per supplier)')
    print('─' * 70)
    params2 = LPParams(
        product              = 'transistors',
        lambda_risk          = 0.75,
        compliance_threshold = 0.60,
        max_supplier_share   = 0.40,
        budget_cap           = 5_000,
        service_level_target = 1.00,
        order_quantity       = 5_000,
    )
    result2 = run(params2)
    _print_result(result2)
