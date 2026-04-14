"""
procurement_summary.py — Business-facing BOM / inventory planning layer summaries.

Tool hierarchy for agent use
─────────────────────────────────────────────────────────────────────────────────

PRIMARY — start here
    get_procurement_recommendation_tool(forecast_run_id=0)
        One-screen answer to "do we need to buy anything?"
        Shows LP net requirement per component with 🔴/🟢 action status.

SECONDARY — explainability
    get_aggregated_procurement_need_tool(forecast_run_id=0,
                                         product='', facility_id='')
        Horizon-level LP demand floor per facility × component.
        This is the quantity the LP optimizer actually allocates across suppliers.

    get_triggered_procurement_rows_tool(forecast_run_id=0,
                                        product='', facility_id='')
        The specific weeks and facilities where procurement is triggered
        (net_requirement > 0). Use to explain WHERE and WHEN buying happens.

DIAGNOSTIC / DEEP-DIVE — use only when deeper detail is needed
    get_procurement_status_summary_tool(forecast_run_id=0)
        Full week-by-week inventory trigger signal for all components.

    get_procurement_planning_summary_tool(forecast_run_id=0)
        Gross BOM demand + weekly trigger signal in one combined output.

    get_component_requirements_summary_tool(forecast_run_id=0)
        Full-horizon gross BOM demand before any inventory offset.

    get_bom_translation_tool(semiconductor_id, forecast_run_id=0,
                             facility_id='', target_week_date='')
        BOM recipe (Mode A) or forecast-row explosion (Mode B).

─────────────────────────────────────────────────────────────────────────────────

Entry points (independently callable):
    format_procurement_recommendation(conn, forecast_run_id=None)     -> str
    format_component_requirements(conn, forecast_run_id=None)         -> str
    format_procurement_status(conn, forecast_run_id=None)             -> str
    format_aggregated_procurement_need(conn, forecast_run_id=None,    -> str
                                       product=None, facility_id=None)
    format_bom_translation(conn, semiconductor_id,                    -> str
                           forecast_run_id=None,
                           facility_id=None,
                           target_week_date=None)

Reads from:
    vw_component_requirement_lp          (BOM-exploded full-horizon demand)
    vw_component_requirement_detail      (per-SKU per-week BOM explosion detail)
    vw_procurement_requirement           (inventory-adjusted net requirement)
    fact_component_inventory_history     (decision-point on-hand / inventory state)
    fact_inventory_policy                (safety stock and policy parameters)
    dim_forecast_run                     (run metadata)
    dim_product                          (product name lookup)
    dim_bom                              (BOM recipe: SKU → component mappings)

Does NOT modify any computational logic, formulas, or DB tables.
All values are read from pre-computed tables and views.

Usage:
    import psycopg2
    from inventory.procurement_summary import (
        get_procurement_recommendation_tool,
        get_aggregated_procurement_need_tool,
    )

    # Primary entry point — "do we need to buy anything?"
    print(get_procurement_recommendation_tool())

    # Horizon-level LP demand floor with facility detail
    print(get_aggregated_procurement_need_tool())

    conn = psycopg2.connect(DATABASE_URL)
    from inventory.procurement_summary import format_procurement_status
    print(format_procurement_status(conn))
    conn.close()
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(fn):  # no-op decorator when langchain_core is not installed
        return fn

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/procurement_agent",
)

_W = 70  # output width in characters


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _resolve_run_id(conn, forecast_run_id=None) -> int:
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
                "SELECT forecast_run_id FROM dim_forecast_run "
                "ORDER BY forecast_run_id DESC LIMIT 1"
            )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "No forecast run found in dim_forecast_run. "
            "Run forecasting/run_production.py first."
        )
    return int(row[0])


def _rule(label: str = "", width: int = _W) -> str:
    """Return a labelled horizontal rule."""
    if label:
        return f"  ── {label} " + "─" * max(0, width - len(label) - 6)
    return "  " + "─" * (width - 2)


# ── Component Requirements ────────────────────────────────────────────────────

def format_component_requirements(conn, forecast_run_id=None) -> str:
    """
    Return a business-facing summary of full-horizon BOM-exploded component demand.

    Shows gross component requirement across ALL facilities and ALL forecast weeks.
    No inventory offsets applied — this is raw demand before policy adjustment.
    See format_procurement_status() for the inventory-adjusted buy signal.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    with conn.cursor() as cur:
        # Planning window and scope
        cur.execute(
            """
            SELECT
                MIN(target_week_date)        AS start_date,
                MAX(target_week_date)        AS end_date,
                COUNT(DISTINCT target_week_date) AS n_weeks,
                COUNT(DISTINCT facility_id)  AS n_facilities,
                COUNT(DISTINCT product_key)  AS n_components
            FROM vw_component_requirement_lp
            WHERE forecast_run_id = %s
            """,
            (run_id,),
        )
        r = cur.fetchone()
        start_date, end_date, n_weeks, n_facilities, n_components = r

        # Per-component totals (all rows, no filter)
        cur.execute(
            """
            SELECT p.product, SUM(lp.total_component_requirement) AS total_gross
            FROM vw_component_requirement_lp lp
            JOIN dim_product p ON p.product_key = lp.product_key
            WHERE lp.forecast_run_id = %s
            GROUP BY p.product
            ORDER BY total_gross DESC
            """,
            (run_id,),
        )
        comp_rows = cur.fetchall()

    total_gross = sum(float(r[1]) for r in comp_rows)

    lines = [
        "═" * _W,
        "  COMPONENT REQUIREMENTS — Full-Horizon BOM-Exploded Demand",
        "═" * _W,
        "",
        "  This output shows the total volume of each procurement component",
        "  required to fulfill the finished-goods forecast, after translating",
        "  finished-good SKU demand through the Bill of Materials (BOM).",
        "",
        "  These figures are BEFORE any inventory position or policy adjustment.",
        "  They represent the demand the planning horizon places on the supply",
        "  chain in raw component terms.",
        "",
        "  To see the actual procurement buy signal (net of inventory), refer",
        "  to the Procurement Status output.",
        "",
        _rule("Planning Window"),
        f"  Forecast start     : {start_date}",
        f"  Forecast end       : {end_date}",
        f"  Horizon weeks      : {n_weeks}",
        f"  Forecast run ID    : {run_id}",
        "",
        _rule("Aggregation Scope"),
        f"  Facilities         : {n_facilities}  (all facilities included)",
        f"  Component types    : {n_components}",
        f"  Totals below       : summed across all {n_facilities} facilities"
        f" × {n_weeks} forecast weeks",
        "",
        _rule("Full-Horizon Gross Requirement by Component"),
        f"  {'Component':<40} {'Units Required':>14}",
        _rule(),
    ]

    for product, gross in comp_rows:
        lines.append(f"  {product:<40} {float(gross):>14,.0f}")

    lines += [
        _rule(),
        f"  {'TOTAL':<40} {total_gross:>14,.0f}",
        "",
        _rule("How This Is Computed"),
        "  For each forecast row:",
        "    gross_component_requirement = predicted_demand × units_per_sku",
        "  Summed across: all finished-good SKUs → all facilities → all forecast weeks",
        "",
        _rule("Metric Definition"),
        "  Gross component requirement",
        "    The BOM-implied volume of each procurement component required to",
        "    fulfill the finished-goods demand forecast. A single finished-good",
        "    SKU may require several units of a component per unit produced.",
        "    This total does NOT reflect whether inventory is already available.",
        "",
        "═" * _W,
    ]

    return "\n".join(lines)


# ── Procurement Status ────────────────────────────────────────────────────────

def format_procurement_status(conn, forecast_run_id=None) -> str:
    """
    Return a business-facing week-by-week inventory-adjusted procurement signal.

    Shows where and when procurement is triggered across the planning horizon,
    after applying inventory position and safety stock policy to BOM-exploded
    component demand on a per-week basis.

    This is a WEEKLY inventory trigger signal — NOT the LP demand floor.
    The LP applies the inventory offset once at the horizon level, not per
    forecast week.  See format_aggregated_procurement_need() for the
    horizon-level quantity the optimizer actually allocates across suppliers.

    The 'Gross Req' column in the summary table reflects only the weeks where
    procurement is triggered (net_requirement > 0). Most weeks have gross
    demand but net requirement = 0 because the existing inventory position
    plus the safety stock buffer is sufficient.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    with conn.cursor() as cur:
        # Decision-point date
        cur.execute(
            "SELECT MAX(week_date) FROM fact_component_inventory_history"
        )
        decision_date = cur.fetchone()[0]

        # Planning window
        cur.execute(
            """
            SELECT MIN(target_week_date), MAX(target_week_date)
            FROM vw_procurement_requirement
            WHERE forecast_run_id = %s
            """,
            (run_id,),
        )
        horizon_start, horizon_end = cur.fetchone()

        # Full-horizon gross total (for comparison with Component Requirements)
        cur.execute(
            """
            SELECT SUM(gross_requirement)
            FROM vw_procurement_requirement
            WHERE forecast_run_id = %s
            """,
            (run_id,),
        )
        full_horizon_gross = float(cur.fetchone()[0])

        # Per-component aggregates over triggered rows (net_requirement > 0).
        #
        # on_hand and SS are decision-point constants (same value for every
        # forecast week within a facility × product series).  Their sums here
        # represent the aggregate starting inventory and policy buffer across
        # facilities and triggered weeks — useful context, not a formula identity.
        #
        # With stateful depletion, net_requirement = gross - remaining_inventory,
        # so the column totals do not maintain the old formula identity.
        cur.execute(
            """
            SELECT
                p.product,
                SUM(CASE WHEN r.net_requirement > 0
                         THEN r.gross_requirement   ELSE 0 END)          AS trig_gross,
                SUM(CASE WHEN r.net_requirement > 0
                         THEN r.on_hand_qty         ELSE 0 END)          AS trig_on_hand,
                SUM(CASE WHEN r.net_requirement > 0
                         THEN r.scheduled_receipts_qty ELSE 0 END)       AS trig_sched,
                SUM(CASE WHEN r.net_requirement > 0
                         THEN r.backorder_qty       ELSE 0 END)          AS trig_backorder,
                SUM(CASE WHEN r.net_requirement > 0
                         THEN r.safety_stock_qty    ELSE 0 END)          AS trig_ss,
                SUM(r.net_requirement)                                    AS net_req,
                SUM(CASE WHEN r.net_requirement > 0 THEN 1 ELSE 0 END)  AS trig_rows,
                COUNT(*)                                                  AS total_rows
            FROM vw_procurement_requirement r
            JOIN dim_product p ON p.product_key = r.product_key
            WHERE r.forecast_run_id = %s
            GROUP BY p.product
            ORDER BY net_req DESC
            """,
            (run_id,),
        )
        comp_rows = cur.fetchall()

    # Totals
    t_gross    = sum(float(r[1]) for r in comp_rows)
    t_on_hand  = sum(float(r[2]) for r in comp_rows)
    t_sched    = sum(float(r[3]) for r in comp_rows)
    t_backorder= sum(float(r[4]) for r in comp_rows)
    t_ss       = sum(float(r[5]) for r in comp_rows)
    t_net      = sum(float(r[6]) for r in comp_rows)

    # Box sizing
    box_inner = _W - 4
    net_line  = f"  NET PROCUREMENT REQUIREMENT  →  {t_net:,.0f} units"
    sub_line  = "  (all components · all facilities · full planning horizon)"

    lines = [
        "═" * _W,
        "  PROCUREMENT STATUS — Inventory-Adjusted Buy Signal",
        "═" * _W,
        "",
        "  This output applies current inventory position and safety stock",
        "  policy to the BOM-exploded component demand on a week-by-week",
        "  basis. It shows WHERE and WHEN procurement is triggered across",
        "  the planning horizon.",
        "",
        "  NOTE: This is a weekly inventory signal, not the LP demand floor.",
        "  The LP applies the inventory offset once at the horizon level.",
        "  See the Aggregated Procurement Need output for the quantity the",
        "  optimizer actually allocates across suppliers.",
        "",
        "  on_hand_qty and safety_stock_qty appear constant per series in this",
        "  output — both are decision-point values fixed at the start of the",
        "  horizon. Net requirement is computed via stateful rolling depletion:",
        "  each week's gross demand reduces the available inventory carried",
        "  forward, so procurement triggers only once the starting stock above",
        "  the safety stock floor is exhausted across cumulative weeks.",
        "",
        _rule("How This Differs from Component Requirements"),
        f"  Full-horizon gross demand     : {full_horizon_gross:>12,.0f} units",
        "    (sum across all facilities × all forecast weeks)",
        f"  Procurement-triggered gross   : {t_gross:>12,.0f} units",
        "    (sum over weeks where on-hand + policy coverage is insufficient)",
        f"  Net procurement requirement   : {t_net:>12,.0f} units",
        "    (after subtracting on-hand inventory and adding safety stock buffer)",
        "",
        "  Most weeks have gross demand but net requirement = 0 because the",
        "  existing inventory position, combined with the safety stock buffer,",
        "  is sufficient to cover that week's component need without additional",
        "  procurement.",
        "",
        _rule("Decision Point"),
        f"  Inventory state date   : {decision_date}  (last observed week)",
        f"  Planning horizon start : {horizon_start}",
        f"  Planning horizon end   : {horizon_end}",
        f"  Forecast run ID        : {run_id}",
        "",
        _rule("How Weekly Net Requirement Is Computed"),
        "  Step 1 — Available above SS floor (computed once per facility × component):",
        "    available_above_ss = max(0, on_hand + SR − BO − safety_stock)",
        "    This is the inventory that demand is allowed to consume.",
        "    Safety stock is reserved here as an untouchable floor.",
        "",
        "  Step 2 — Remaining usable inventory at the start of each week:",
        "    remaining_N = max(0, available_above_ss − cumulative_gross_{weeks 1..N−1})",
        "    Decreases each week as prior demand depletes the usable pool.",
        "    When remaining_N = 0: the SS floor has been reached.",
        "",
        "  Step 3 — This week's net procurement requirement:",
        "    net_requirement_N = max(0, gross_N − remaining_N)",
        "    Procurement is triggered when gross demand exceeds remaining inventory.",
        "",
        "  WHY safety_stock is NOT added in Step 3:",
        "    SS was already pre-deducted in Step 1. Adding it again per week",
        "    would inflate requirements by SS × (number of triggered weeks).",
        "    SS is a one-time reserve, not a weekly replenishment target.",
        "    Proof: SUM(net_req) = SUM(gross) − available_above_ss = LP demand floor.",
        "",
        _rule("Metric Definitions"),
        "  gross_requirement        [+]",
        "    BOM-translated forecast demand for the planning horizon.",
        "    In this table: sum over weeks where procurement is triggered.",
        "    Full-horizon total is shown in Component Requirements.",
        "",
        "  backorder_qty            [+]",
        "    Unfilled demand carried over at the decision point.",
        "    Currently 0 — set to zero at the planning decision point by design.",
        "",
        "  safety_stock_qty  [SS Floor — context only in this table]",
        "    Policy-required buffer stock per facility × component.",
        "    Periodic-review base-stock formula, z = 1.65 (95% service level).",
        "    Role in the formula: pre-deducted once in available_above_ss.",
        "    NOT added per week in net_requirement — see formula section above.",
        "    Shown here as context: summed over triggered rows to indicate total",
        "    SS reserves held across the facilities where procurement activated.",
        "",
        "  on_hand_qty  [Starting OH — context only in this table]",
        "    Inventory on hand at the decision point (SS + μ_D per facility).",
        "    Fixed — the same for every forecast week in a series.",
        "    Role in the formula: used to derive available_above_ss.",
        "    Shown here as context: summed over triggered rows to indicate total",
        "    starting stock held across the facilities where procurement activated.",
        "",
        "  scheduled_receipts_qty   [-]",
        "    Quantity already on order at the decision point.",
        "    Currently 0 — set to zero at the planning decision point by design.",
        "",
        "  net_requirement",
        "    Weekly procurement trigger after stateful rolling depletion.",
        "    Positive only in weeks where this week's gross demand exceeds the",
        "    inventory remaining after all prior weeks have consumed from the",
        "    starting stock above the safety stock floor.",
        "    When on_hand >= SS at the decision point, SUM(weekly net_req) equals",
        "    the LP horizon-level demand floor exactly.",
        "    See the Aggregated Procurement Need output for the LP demand floor.",
        "",
        _rule("Procurement Signal by Component"),
        "  Triggered rows only (net_requirement > 0). Starting OH and SS Floor",
        "  are decision-point constants shown for context, not formula inputs.",
        "",
        (
            f"  {'Component':<36}"
            f" {'Gross Req':>13}"
            f" {'Starting OH':>11}"
            f" {'Sched Rec':>13}"
            f" {'Backorder':>13}"
            f" {'SS Floor':>14}"
            f" {'Net Req':>8}"
        ),
        _rule(),
    ]

    for r in comp_rows:
        product     = r[0]
        trig_gross  = float(r[1])
        trig_oh     = float(r[2])
        trig_sched  = float(r[3])
        trig_bo     = float(r[4])
        trig_ss     = float(r[5])
        net_req     = float(r[6])
        lines.append(
            f"  {product:<36}"
            f" {trig_gross:>13,.0f}"
            f" {trig_oh:>11,.0f}"
            f" {trig_sched:>13,.0f}"
            f" {trig_bo:>13,.0f}"
            f" {trig_ss:>14,.0f}"
            f" {net_req:>8,.0f}"
        )

    lines += [
        _rule(),
        (
            f"  {'TOTAL':<36}"
            f" {t_gross:>13,.0f}"
            f" {t_on_hand:>11,.0f}"
            f" {t_sched:>13,.0f}"
            f" {t_backorder:>13,.0f}"
            f" {t_ss:>14,.0f}"
            f" {t_net:>8,.0f}"
        ),
        "",
        "  ┌" + "─" * box_inner + "┐",
        f"  │{net_line:<{box_inner}}│",
        f"  │{sub_line:<{box_inner}}│",
        "  └" + "─" * box_inner + "┘",
        "",
        "  Note: backorder_qty and scheduled_receipts_qty are currently zero",
        "  at the decision point by design. They appear in the formula and",
        "  table so that future planning runs with non-zero values render",
        "  correctly without layout changes.",
        "",
        "═" * _W,
    ]

    return "\n".join(lines)


# ── Procurement Requirement Drill-Down ───────────────────────────────────────

def get_procurement_requirement_drilldown(
    conn,
    forecast_run_id=None,
    product: str = None,
    facility_id: str = None,
) -> str:
    """
    Return a week-by-week drill-down of the procurement requirement at the
    grain: target_week_date × facility_id × component.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    product : str, optional
        Component name to filter on (e.g. 'transistors').
        Case-insensitive prefix match against dim_product.product.
        Required — if omitted, returns a guidance message.
    facility_id : str, optional
        Facility identifier to filter on (e.g. 'FAC_A').
        If omitted, all facilities are returned for the given component.

    Modes
    -----
    product only         → all facilities × all forecast weeks for that component
    product + facility   → one facility × all forecast weeks for that component
    neither              → guidance message (no DB query issued)
    """
    if product is None:
        return "\n".join([
            "═" * _W,
            "  PROCUREMENT REQUIREMENT DRILL-DOWN — Usage",
            "═" * _W,
            "",
            "  This helper requires at least a component name.",
            "",
            "  Modes:",
            "    product only          → all facilities × all forecast weeks",
            "    product + facility_id → one facility   × all forecast weeks",
            "",
            "  Example calls:",
            "    get_procurement_requirement_drilldown(conn, product='transistors')",
            "    get_procurement_requirement_drilldown(",
            "        conn, product='transistors', facility_id='FAC_A')",
            "",
            "  Available components (from dim_product):",
            "    integrated_circuit_components · transistors",
            "    power_devices · microprocessors",
            "═" * _W,
        ])

    run_id = _resolve_run_id(conn, forecast_run_id)

    with conn.cursor() as cur:
        # Resolve product name — case-insensitive exact match first, then prefix
        cur.execute(
            "SELECT product_key, product FROM dim_product "
            "WHERE LOWER(product) = LOWER(%s)",
            (product,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "SELECT product_key, product FROM dim_product "
                "WHERE LOWER(product) LIKE LOWER(%s) LIMIT 1",
                (f"{product}%",),
            )
            row = cur.fetchone()
        if row is None:
            return (
                f"Component '{product}' not found in dim_product. "
                "Check spelling or use the exact product name."
            )
        product_key, product_name = row

        # Build query — optionally filter by facility_id
        if facility_id is not None:
            cur.execute(
                """
                SELECT
                    r.target_week_date,
                    r.facility_id,
                    p.product                   AS component,
                    r.horizon_week,
                    r.gross_requirement,
                    r.on_hand_qty,
                    r.scheduled_receipts_qty,
                    r.backorder_qty,
                    r.safety_stock_qty,
                    r.remaining_inventory,
                    r.net_requirement
                FROM vw_procurement_requirement r
                JOIN dim_product p ON p.product_key = r.product_key
                WHERE r.forecast_run_id = %s
                  AND r.product_key     = %s
                  AND r.facility_id     = %s
                ORDER BY r.target_week_date
                """,
                (run_id, product_key, facility_id),
            )
        else:
            cur.execute(
                """
                SELECT
                    r.target_week_date,
                    r.facility_id,
                    p.product                   AS component,
                    r.horizon_week,
                    r.gross_requirement,
                    r.on_hand_qty,
                    r.scheduled_receipts_qty,
                    r.backorder_qty,
                    r.safety_stock_qty,
                    r.remaining_inventory,
                    r.net_requirement
                FROM vw_procurement_requirement r
                JOIN dim_product p ON p.product_key = r.product_key
                WHERE r.forecast_run_id = %s
                  AND r.product_key     = %s
                ORDER BY r.facility_id, r.target_week_date
                """,
                (run_id, product_key),
            )
        rows = cur.fetchall()

    if not rows:
        scope = f"facility '{facility_id}'" if facility_id else "any facility"
        return (
            f"No rows found for component='{product_name}', {scope}, "
            f"forecast_run_id={run_id}."
        )

    # Scope label for header
    if facility_id is not None:
        scope_label = f"{product_name}  ·  {facility_id}"
        mode_note   = "Single facility — all forecast weeks"
    else:
        n_fac = len({r[1] for r in rows})
        scope_label = f"{product_name}  ·  all {n_fac} facilities"
        mode_note   = "All facilities — all forecast weeks"

    # Column totals (horizon_week at [3]; remaining at [9] — not additive)
    tot_gross  = sum(float(r[4]) for r in rows)
    tot_oh     = sum(float(r[5]) for r in rows)
    tot_sched  = sum(float(r[6]) for r in rows)
    tot_bo     = sum(float(r[7]) for r in rows)
    tot_ss     = sum(float(r[8]) for r in rows)
    tot_net    = sum(float(r[10]) for r in rows)

    lines = [
        "═" * _W,
        "  PROCUREMENT REQUIREMENT DRILL-DOWN",
        f"  {scope_label}",
        "═" * _W,
        "",
        f"  Mode           : {mode_note}",
        f"  Forecast run   : {run_id}",
        f"  Rows returned  : {len(rows)}",
        "",
        _rule("Column Guide"),
        "  Horizon Wk    — week 1 = first forecast week, 20 = last",
        "  Week Date     — calendar date of the forecast week",
        "  Gross Req     — BOM-translated forecast demand for this week",
        "  Starting OH   — on_hand at the decision point [FIXED per series]",
        "  SS Floor      — safety stock threshold [FIXED per series]",
        "  Remaining     — usable inventory above SS floor at START of this week",
        "                  = max(0, (Starting OH + SR − BO − SS Floor)",
        "                           − cumulative gross from prior weeks)",
        "                  decreases each week as gross demand is consumed",
        "  Net Req       — max(0, Gross Req − Remaining)",
        "                  procurement needed this week",
        "                  0 while Remaining covers gross demand; positive once",
        "                  the usable pool is exhausted",
        "",
        "  WHY SS is not re-added per week:",
        "    SS was already pre-deducted when computing Starting OH − SS = usable pool.",
        "    Adding SS again in the net_requirement formula would double-count it.",
        "    Proof: SUM(Net Req, all weeks) = SUM(Gross) − usable = LP demand floor.",
        "",
        _rule("Source"),
        "  vw_procurement_requirement  (grain: forecast_run_id × week × facility × product)",
        "  net_requirement_N = max(0, gross_N − remaining_inventory_N)",
        "  remaining_N       = max(0, available_above_ss − cumulative_gross_prior)",
        "  available_above_ss = max(0, on_hand + SR − BO − safety_stock)  [once per series]",
        "",
        _rule("Detail"),
        (
            f"  {'Wk':>3}"
            f"  {'Week Date':<12}"
            f" {'Facility':<10}"
            f" {'Gross Req':>10}"
            f" {'Starting OH':>11}"
            f" {'Sched Rec':>10}"
            f" {'Backorder':>10}"
            f" {'SS Floor':>9}"
            f" {'Remaining':>10}"
            f" {'Net Req':>8}"
        ),
        _rule(),
    ]

    for r in rows:
        week_date, fac, _, hw, gross, oh, sched, bo, ss, remaining, net = r
        lines.append(
            f"  {int(hw):>3}"
            f"  {str(week_date):<12}"
            f" {fac:<10}"
            f" {float(gross):>10,.0f}"
            f" {float(oh):>11,.0f}"
            f" {float(sched):>10,.0f}"
            f" {float(bo):>10,.0f}"
            f" {float(ss):>9,.0f}"
            f" {float(remaining):>10,.0f}"
            f" {float(net):>8,.0f}"
        )

    lines += [
        _rule(),
        (
            f"  {'':>3}"
            f"  {'TOTAL':<23}"
            f" {tot_gross:>10,.0f}"
            f" {tot_oh:>11,.0f}"
            f" {tot_sched:>10,.0f}"
            f" {tot_bo:>10,.0f}"
            f" {tot_ss:>9,.0f}"
            f" {'—':>10}"
            f" {tot_net:>8,.0f}"
        ),
        "  (Remaining not summed — represents per-week inventory state, not additive)",
        "",
        "═" * _W,
    ]

    return "\n".join(lines)


# ── Triggered Procurement Rows ────────────────────────────────────────────────

def get_triggered_procurement_rows(
    conn,
    forecast_run_id=None,
    product: str = None,
    facility_id: str = None,
) -> str:
    """
    Return all rows where net_requirement > 0 — the weeks and facilities
    where procurement is actually triggered.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    product : str, optional
        Filter to one component (case-insensitive exact then prefix match).
        If omitted, all components are returned.
    facility_id : str, optional
        Filter to one facility. Only applied when product is also supplied.
        If product is omitted, facility_id is ignored.

    Modes
    -----
    no filters           → all triggered rows, all components, all facilities
    product only         → triggered rows for that component, all facilities
    product + facility   → triggered rows for that component, that facility
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    # Resolve optional product filter
    product_key = None
    product_name = None
    if product is not None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT product_key, product FROM dim_product "
                "WHERE LOWER(product) = LOWER(%s)",
                (product,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT product_key, product FROM dim_product "
                    "WHERE LOWER(product) LIKE LOWER(%s) LIMIT 1",
                    (f"{product}%",),
                )
                row = cur.fetchone()
        if row is None:
            return (
                f"Component '{product}' not found in dim_product. "
                "Check spelling or use the exact product name."
            )
        product_key, product_name = row

    # Build WHERE clauses dynamically
    conditions = ["r.forecast_run_id = %s", "r.net_requirement > 0"]
    params = [run_id]

    if product_key is not None:
        conditions.append("r.product_key = %s")
        params.append(product_key)
        if facility_id is not None:
            conditions.append("r.facility_id = %s")
            params.append(facility_id)

    where = " AND ".join(conditions)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                r.target_week_date,
                r.facility_id,
                p.product                   AS component,
                r.horizon_week,
                r.gross_requirement,
                r.on_hand_qty,
                r.scheduled_receipts_qty,
                r.backorder_qty,
                r.safety_stock_qty,
                r.remaining_inventory,
                r.net_requirement
            FROM vw_procurement_requirement r
            JOIN dim_product p ON p.product_key = r.product_key
            WHERE {where}
            ORDER BY p.product, r.facility_id, r.target_week_date
            """,
            params,
        )
        rows = cur.fetchall()

    if not rows:
        return (
            f"No triggered procurement rows found for "
            f"forecast_run_id={run_id}"
            + (f", component='{product_name}'" if product_name else "")
            + (f", facility='{facility_id}'" if facility_id and product_name else "")
            + "."
        )

    # Scope label
    if product_name and facility_id:
        scope_label = f"{product_name}  ·  {facility_id}"
        mode_note   = "Single component · single facility"
    elif product_name:
        n_fac = len({r[1] for r in rows})
        scope_label = f"{product_name}  ·  {n_fac} facilit{'y' if n_fac == 1 else 'ies'}"
        mode_note   = "Single component · all facilities"
    else:
        n_comp = len({r[2] for r in rows})
        n_fac  = len({r[1] for r in rows})
        scope_label = f"all {n_comp} components  ·  all {n_fac} facilities"
        mode_note   = "All components · all facilities"

    # Totals: horizon_week at [3], gross at [4], on_hand at [5], ss at [8], net at [10]
    tot_gross = sum(float(r[4]) for r in rows)
    tot_oh    = sum(float(r[5]) for r in rows)
    tot_ss    = sum(float(r[8]) for r in rows)
    tot_net   = sum(float(r[10]) for r in rows)

    lines = [
        "═" * _W,
        "  TRIGGERED PROCUREMENT ROWS  (net_requirement > 0 only)",
        f"  {scope_label}",
        "═" * _W,
        "",
        f"  Mode           : {mode_note}",
        f"  Forecast run   : {run_id}",
        f"  Triggered rows : {len(rows)}",
        "",
        _rule("What This Shows"),
        "  Only weeks where this week's gross demand exceeds the remaining",
        "  usable inventory (above SS floor) after prior weeks consumed stock.",
        "  Rows where net_requirement = 0 are excluded.",
        "",
        "  Column guide:",
        "    Wk #        — horizon week number (1 = first forecast week)",
        "    Gross Req   — BOM-translated demand for this week",
        "    Starting OH — on_hand at decision point [FIXED per series]",
        "    SS Floor    — safety stock threshold [FIXED per series; pre-deducted",
        "                  from Starting OH to derive the usable pool]",
        "    Remaining   — usable inventory above SS floor at START of this week",
        "    Net Req     — max(0, Gross Req − Remaining)",
        "",
        _rule("Source"),
        "  vw_procurement_requirement  WHERE net_requirement > 0",
        "  net_requirement_N = max(0, gross_N − remaining_inventory_N)",
        "  remaining_N       = max(0, available_above_ss − cumulative_gross_prior)",
        "  available_above_ss = max(0, Starting OH + SR − BO − SS Floor)  [once per series]",
        "",
        _rule("Triggered Detail"),
        (
            f"  {'Wk':>3}"
            f"  {'Component':<32}"
            f" {'Week Date':<12}"
            f" {'Facility':<10}"
            f" {'Gross Req':>10}"
            f" {'Starting OH':>11}"
            f" {'SS Floor':>9}"
            f" {'Remaining':>10}"
            f" {'Net Req':>8}"
        ),
        _rule(),
    ]

    for r in rows:
        week_date, fac, comp, hw, gross, oh, _, _, ss, remaining, net = r
        lines.append(
            f"  {int(hw):>3}"
            f"  {comp:<32}"
            f" {str(week_date):<12}"
            f" {fac:<10}"
            f" {float(gross):>10,.0f}"
            f" {float(oh):>11,.0f}"
            f" {float(ss):>9,.0f}"
            f" {float(remaining):>10,.0f}"
            f" {float(net):>8,.0f}"
        )

    lines += [
        _rule(),
        (
            f"  {'':>3}"
            f"  {'TOTAL':<55}"
            f" {tot_gross:>10,.0f}"
            f" {tot_oh:>11,.0f}"
            f" {tot_ss:>9,.0f}"
            f" {'—':>10}"
            f" {tot_net:>8,.0f}"
        ),
        "",
        "  Note: Sched Rec and Backorder omitted (zero by design at decision point).",
        "  Remaining not summed — represents per-week inventory state, not additive.",
        "",
        "═" * _W,
    ]

    return "\n".join(lines)


# ── Aggregated Procurement Need (Horizon-Level LP Demand) ────────────────────

def format_aggregated_procurement_need(
    conn,
    forecast_run_id=None,
    product: str = None,
    facility_id: str = None,
) -> str:
    """
    Return the horizon-level aggregated procurement need used by the LP optimizer.

    This is the quantity the optimizer actually allocates across suppliers:
    total gross component demand for the planning horizon minus the inventory
    offset applied ONCE per facility (not per forecast week).

    Formula (per facility × component):
        horizon_net_req = max(0,
            SUM(gross_requirement over all forecast weeks)
            + backorder_qty
            + safety_stock_qty
            - on_hand_qty
            - scheduled_receipts_qty
        )

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    product : str, optional
        Filter to one component (case-insensitive exact then prefix match).
        If None, returns all components.
    facility_id : str, optional
        Filter to one facility. If None, returns all facilities.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    # Resolve optional product filter
    product_key = None
    product_name_resolved = None
    if product is not None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT product_key, product FROM dim_product "
                "WHERE LOWER(product) = LOWER(%s)",
                (product,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT product_key, product FROM dim_product "
                    "WHERE LOWER(product) LIKE LOWER(%s) LIMIT 1",
                    (f"{product}%",),
                )
                row = cur.fetchone()
        if row is None:
            return (
                f"Component '{product}' not found. "
                "Check spelling or use the exact product name."
            )
        product_key, product_name_resolved = row

    # Build dynamic filters
    filters = ["lp.forecast_run_id = %(forecast_run_id)s"]
    qparams = {"forecast_run_id": run_id}
    if product_key is not None:
        filters.append("lp.product_key = %(product_key)s")
        qparams["product_key"] = product_key
    if facility_id is not None:
        filters.append("lp.facility_id = %(facility_id)s")
        qparams["facility_id"] = facility_id

    where_clause = " AND ".join(filters)

    sql = f"""
        SELECT
            lp.facility_id,
            dp.product,
            SUM(lp.total_component_requirement)        AS gross_total,
            MAX(dp_snap.on_hand_qty)                   AS on_hand_qty,
            MAX(dp_snap.scheduled_receipts_qty)        AS scheduled_receipts_qty,
            MAX(dp_snap.backorder_qty)                 AS backorder_qty,
            MAX(pol.safety_stock_qty)                  AS safety_stock_qty,
            GREATEST(0,
                SUM(lp.total_component_requirement)
                + MAX(dp_snap.backorder_qty)
                + MAX(pol.safety_stock_qty)
                - MAX(dp_snap.on_hand_qty)
                - MAX(dp_snap.scheduled_receipts_qty)
            ) AS horizon_net_req
        FROM vw_component_requirement_lp lp
        JOIN dim_product dp ON dp.product_key = lp.product_key
        JOIN (
            SELECT facility_id, product_key,
                   on_hand_qty, scheduled_receipts_qty, backorder_qty
            FROM fact_component_inventory_history
            WHERE week_date = (
                SELECT MAX(week_date) FROM fact_component_inventory_history
            )
        ) dp_snap
            ON  dp_snap.facility_id = lp.facility_id
            AND dp_snap.product_key = lp.product_key
        JOIN fact_inventory_policy pol
            ON  pol.forecast_run_id = lp.forecast_run_id
            AND pol.facility_id     = lp.facility_id
            AND pol.product_key     = lp.product_key
        WHERE {where_clause}
        GROUP BY lp.facility_id, dp.product
        ORDER BY dp.product, lp.facility_id
    """

    with conn.cursor() as cur:
        # Planning window
        cur.execute(
            """
            SELECT MIN(target_week_date), MAX(target_week_date),
                   COUNT(DISTINCT target_week_date)
            FROM vw_component_requirement_lp
            WHERE forecast_run_id = %(forecast_run_id)s
            """,
            qparams,
        )
        horizon_start, horizon_end, n_weeks = cur.fetchone()

        # Decision-point date
        cur.execute("SELECT MAX(week_date) FROM fact_component_inventory_history")
        decision_date = cur.fetchone()[0]

        cur.execute(sql, qparams)
        rows = cur.fetchall()

    if not rows:
        scope = (
            f"component='{product_name_resolved or product}'"
            if product else "all components"
        )
        return (
            f"No aggregated procurement need found for {scope}, "
            f"forecast_run_id={run_id}."
        )

    # ── Aggregate by product ─────────────────────────────────────────────────
    # rows: facility_id, product, gross_total, on_hand, sched, backorder, ss, horizon_net_req

    # product-level summary
    from collections import defaultdict
    prod_gross   = defaultdict(float)
    prod_on_hand = defaultdict(float)
    prod_ss      = defaultdict(float)
    prod_net     = defaultdict(float)
    fac_rows     = []  # kept for facility breakdown

    for fac, prod, gross, oh, sched, bo, ss, net in rows:
        prod_gross[prod]   += float(gross)
        prod_on_hand[prod] += float(oh)
        prod_ss[prod]      += float(ss)
        prod_net[prod]     += float(net)
        fac_rows.append((fac, prod, float(gross), float(oh), float(ss), float(net)))

    products_ordered = sorted(prod_net.keys(), key=lambda p: -prod_net[p])
    total_gross = sum(prod_gross.values())
    total_net   = sum(prod_net.values())
    n_facilities = len({r[0] for r in rows})
    n_products   = len(prod_net)

    scope_header = (
        product_name_resolved if product_name_resolved
        else f"all {n_products} component{'s' if n_products != 1 else ''}"
    )
    if facility_id:
        scope_header += f"  ·  {facility_id}"

    box_inner = _W - 4
    net_line  = f"  HORIZON-LEVEL LP DEMAND FLOOR  →  {total_net:,.0f} units"
    sub_line  = f"  ({scope_header}  ·  {n_facilities} facilit{'y' if n_facilities == 1 else 'ies'}  ·  full planning horizon)"

    lines = [
        "═" * _W,
        "  AGGREGATED PROCUREMENT NEED — Horizon-Level LP Demand Floor",
        f"  {scope_header}",
        "═" * _W,
        "",
        "  This output shows the quantity the LP optimizer actually allocates",
        "  across suppliers. The inventory offset (on-hand stock, safety stock,",
        "  scheduled receipts) is applied ONCE against the total horizon demand,",
        "  per facility — not once per forecast week.",
        "",
        "  ┌" + "─" * box_inner + "┐",
        f"  │{net_line:<{box_inner}}│",
        f"  │{sub_line:<{box_inner}}│",
        "  └" + "─" * box_inner + "┘",
        "",
        _rule("Planning Window"),
        f"  Inventory state date : {decision_date}  (last observed week)",
        f"  Horizon start        : {horizon_start}",
        f"  Horizon end          : {horizon_end}",
        f"  Horizon weeks        : {n_weeks}",
        f"  Forecast run ID      : {run_id}",
        "",
        _rule("Horizon-Level Formula (per facility × component)"),
        "  horizon_net_req = max( 0,",
        "      SUM(gross_requirement across all forecast weeks)",
        "    + backorder_qty            [current backlog at decision point]",
        "    + safety_stock_qty         [policy buffer, 95% service level]",
        "    - on_hand_qty              [inventory at decision point]",
        "    - scheduled_receipts_qty   [on-order at decision point]",
        "  )",
        "",
        "  The inventory state values (on_hand, safety_stock, etc.) are",
        "  point-in-time constants — applied once against the full horizon.",
        "",
        _rule("Aggregated Procurement Need by Component"),
        f"  {'Component':<36} {'Gross Demand':>13} {'On Hand [-]':>11}"
        f" {'Safety Stk [+]':>14} {'LP Net Req':>10}",
        _rule(),
    ]

    for prod in products_ordered:
        lines.append(
            f"  {prod:<36}"
            f" {prod_gross[prod]:>13,.0f}"
            f" {prod_on_hand[prod]:>11,.0f}"
            f" {prod_ss[prod]:>14,.0f}"
            f" {prod_net[prod]:>10,.0f}"
        )

    lines += [
        _rule(),
        f"  {'TOTAL':<36}"
        f" {total_gross:>13,.0f}"
        f" {sum(prod_on_hand.values()):>11,.0f}"
        f" {sum(prod_ss.values()):>14,.0f}"
        f" {total_net:>10,.0f}",
        "",
    ]

    # ── Optional facility breakdown ──────────────────────────────────────────
    if n_facilities > 1 or facility_id:
        lines += [
            _rule("Facility Breakdown"),
            f"  {'Component':<36} {'Facility':<12} {'Gross Demand':>13} {'LP Net Req':>10}",
            _rule(),
        ]
        current_prod = None
        for fac, prod, gross, oh, ss, net in sorted(fac_rows, key=lambda r: (r[1], r[0])):
            if prod != current_prod:
                if current_prod is not None:
                    lines.append("")
                current_prod = prod
            lines.append(
                f"  {prod:<36} {fac:<12} {gross:>13,.0f} {net:>10,.0f}"
            )
        lines.append("")

    lines += [
        _rule("How This Differs from Other Procurement Outputs"),
        "  Component Requirements  — full-horizon GROSS BOM demand; no inventory",
        "                            offset applied. Largest number.",
        "",
        "  Procurement Status      — week-by-week inventory trigger signal;",
        "                            shows WHERE and WHEN procurement activates.",
        "                            Sums per-week net values (each ≥ 0).",
        "                            NOT the LP demand floor.",
        "",
        "  Triggered Rows          — subset of weekly rows where net > 0;",
        "                            useful for drill-down, not for LP sizing.",
        "",
        "  Aggregated Procurement  — THIS OUTPUT. Inventory offset applied",
        "  Need (LP demand floor)    once per horizon. The quantity the LP",
        "                            allocates across suppliers. Correct for",
        "                            comparing against LP allocation output.",
        "",
        "═" * _W,
    ]

    return "\n".join(lines)


# ── Procurement Recommendation (concise agent-facing summary) ────────────────

def format_procurement_recommendation(conn, forecast_run_id=None) -> str:
    """
    Return a concise, actionable procurement recommendation for the current
    planning cycle.

    Combines aggregated procurement need (LP demand floor) with a triggered-week
    count to produce a one-screen answer suitable for a conversational agent
    response to questions like "Do we need to procure anything?" or
    "What do we need to buy this cycle?"

    This does NOT replace get_aggregated_procurement_need_tool() for detailed
    LP demand or get_triggered_procurement_rows_tool() for week-by-week
    explainability. It is the concise entry point.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    with conn.cursor() as cur:
        # Planning window
        cur.execute(
            """
            SELECT MIN(target_week_date), MAX(target_week_date),
                   COUNT(DISTINCT target_week_date)
            FROM vw_component_requirement_lp
            WHERE forecast_run_id = %s
            """,
            (run_id,),
        )
        horizon_start, horizon_end, n_horizon_weeks = cur.fetchone()

        # Decision date
        cur.execute("SELECT MAX(week_date) FROM fact_component_inventory_history")
        decision_date = cur.fetchone()[0]

        # Aggregated net requirement per product (LP demand floor)
        cur.execute(
            """
            SELECT
                dp.product,
                GREATEST(0,
                    SUM(lp.total_component_requirement)
                    + MAX(dp_snap.backorder_qty)
                    + MAX(pol.safety_stock_qty)
                    - MAX(dp_snap.on_hand_qty)
                    - MAX(dp_snap.scheduled_receipts_qty)
                ) AS horizon_net_req
            FROM vw_component_requirement_lp lp
            JOIN dim_product dp ON dp.product_key = lp.product_key
            JOIN (
                SELECT facility_id, product_key,
                       on_hand_qty, scheduled_receipts_qty, backorder_qty
                FROM fact_component_inventory_history
                WHERE week_date = (
                    SELECT MAX(week_date) FROM fact_component_inventory_history
                )
            ) dp_snap
                ON  dp_snap.facility_id = lp.facility_id
                AND dp_snap.product_key = lp.product_key
            JOIN fact_inventory_policy pol
                ON  pol.forecast_run_id = lp.forecast_run_id
                AND pol.facility_id     = lp.facility_id
                AND pol.product_key     = lp.product_key
            WHERE lp.forecast_run_id = %s
            GROUP BY dp.product
            ORDER BY horizon_net_req DESC
            """,
            (run_id,),
        )
        need_rows = cur.fetchall()

        # Count distinct triggered weeks per product (net_requirement > 0)
        cur.execute(
            """
            SELECT dp.product,
                   COUNT(DISTINCT r.target_week_date) AS triggered_weeks
            FROM vw_procurement_requirement r
            JOIN dim_product dp ON dp.product_key = r.product_key
            WHERE r.forecast_run_id = %s
              AND r.net_requirement  > 0
            GROUP BY dp.product
            """,
            (run_id,),
        )
        trig_map = {row[0]: int(row[1]) for row in cur.fetchall()}

    if not need_rows:
        return f"No procurement data found for forecast_run_id={run_id}."

    need_by_product = {r[0]: float(r[1]) for r in need_rows}
    action_required = [p for p, n in need_by_product.items() if n > 0]
    total_net = sum(need_by_product.values())

    status_line = (
        f"  {len(action_required)} of {len(need_by_product)} component"
        f"{'s' if len(need_by_product) != 1 else ''} require procurement this cycle."
        if action_required
        else "  All components are covered by existing inventory. No procurement needed."
    )

    lines = [
        "═" * _W,
        "  PROCUREMENT RECOMMENDATION",
        f"  As of {decision_date}  ·  Horizon: {horizon_start} → {horizon_end}"
        f"  ({n_horizon_weeks} wks)",
        "═" * _W,
        "",
        status_line,
        "",
        (
            f"  {'Component':<36}"
            f" {'LP Net Req':>12}"
            f" {'Triggered Wks':>14}"
            f" {'Action':>8}"
        ),
        _rule(),
    ]

    for prod, net_req in sorted(need_by_product.items(), key=lambda x: -x[1]):
        trig_wks = trig_map.get(prod, 0)
        action   = "🔴 Buy" if net_req > 0 else "🟢 Covered"
        lines.append(
            f"  {prod:<36}"
            f" {net_req:>12,.0f}"
            f" {trig_wks:>6} / {n_horizon_weeks:<6}"
            f" {action:>8}"
        )

    lines += [
        _rule(),
        f"  {'TOTAL':<36} {total_net:>12,.0f}",
        "",
        "  Next steps:",
        "    · get_aggregated_procurement_need_tool()          — full LP demand detail",
        "    · get_triggered_procurement_rows_tool(product=…)  — when/why per component",
        "    · run LP optimizer to allocate across suppliers",
        "",
        "  Note: LP Net Req = horizon gross demand − inventory offset (applied once).",
        "  Triggered Wks = distinct forecast weeks where demand exceeds remaining stock.",
        "",
        "═" * _W,
    ]

    return "\n".join(lines)


# ── LangChain @tool wrappers (Option B — no demo/* modified) ─────────────────

@tool
def get_component_requirements_summary_tool(forecast_run_id: int = 0) -> str:
    """Return the full-horizon BOM-exploded component requirements summary.

    Shows gross component demand across all facilities and all forecast weeks,
    before any inventory or safety stock adjustment. Use this to understand
    the raw procurement volume implied by the finished-goods demand forecast.

    Args:
        forecast_run_id: Specific forecast run to retrieve. Pass 0 (default)
                         to retrieve the most recent production forecast run.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        return format_component_requirements(conn, forecast_run_id=run_id)
    except Exception as e:
        logger.error("[COMPONENT_REQ] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving component requirements: {e}"
    finally:
        conn.close()


@tool
def get_procurement_status_summary_tool(forecast_run_id: int = 0) -> str:
    """[DIAGNOSTIC / DEEP-DIVE] Return the full week-by-week procurement status block.

    Produces a detailed multi-section output covering the stateful rolling
    depletion formula, all metric definitions, and a per-component trigger
    summary. Use this for thorough planning diagnostics or audit purposes —
    not as the default answer to "Do we need to buy anything?"

    For a concise procurement answer use get_procurement_recommendation_tool().
    For triggered-week detail use get_triggered_procurement_rows_tool().
    For the LP demand quantity use get_aggregated_procurement_need_tool().

    Args:
        forecast_run_id: Specific forecast run to retrieve. Pass 0 (default)
                         to retrieve the most recent production forecast run.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        return format_procurement_status(conn, forecast_run_id=run_id)
    except Exception as e:
        logger.error("[PROCUREMENT_STATUS] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving procurement status: {e}"
    finally:
        conn.close()


@tool
def get_procurement_planning_summary_tool(forecast_run_id: int = 0) -> str:
    """[DIAGNOSTIC / DEEP-DIVE] Return gross component requirements and weekly trigger in sequence.

    Combines the full BOM-exploded gross demand and the week-by-week
    inventory trigger signal into a single extended output. Use for thorough
    planning audit — output is intentionally long.

    For a concise procurement answer use get_procurement_recommendation_tool().
    For the LP demand quantity use get_aggregated_procurement_need_tool().

    Args:
        forecast_run_id: Specific forecast run to retrieve. Pass 0 (default)
                         to retrieve the most recent production forecast run.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        comp_req = format_component_requirements(conn, forecast_run_id=run_id)
        proc_status = format_procurement_status(conn, forecast_run_id=run_id)
        return comp_req + "\n\n" + proc_status
    except Exception as e:
        logger.error("[PROCUREMENT_PLANNING] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving procurement planning summary: {e}"
    finally:
        conn.close()


@tool
def get_aggregated_procurement_need_tool(
    forecast_run_id: int = 0,
    product: str = "",
    facility_id: str = "",
) -> str:
    """Return the horizon-level aggregated procurement need used by the LP optimizer.

    This is the quantity the LP actually allocates across suppliers: total
    horizon gross demand minus the inventory offset (on-hand, safety stock,
    scheduled receipts) applied ONCE per facility — not once per forecast week.

    Use this to answer:
      - "What demand quantity is the LP actually optimizing?"
      - "What is the total procurement need across the planning horizon?"
      - "How does the LP demand floor differ from the weekly trigger signal?"

    This differs from Procurement Status, which shows the week-by-week
    trigger signal and is NOT the LP demand floor.

    Args:
        forecast_run_id: Specific forecast run ID. Pass 0 (default) to use
                         the most recent production forecast run.
        product:         Component to filter to (e.g. 'transistors'). Leave
                         blank to return all components.
        facility_id:     Facility to filter to (e.g. 'FAC_001'). Leave blank
                         to return all facilities.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        prod   = product.strip() or None
        fac    = facility_id.strip() or None
        return format_aggregated_procurement_need(
            conn, forecast_run_id=run_id, product=prod, facility_id=fac
        )
    except Exception as e:
        logger.error("[AGGREGATED_NEED] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving aggregated procurement need: {e}"
    finally:
        conn.close()


@tool
def get_procurement_recommendation_tool(forecast_run_id: int = 0) -> str:
    """Return a concise procurement recommendation for the current planning cycle.

    Answers questions like:
      - "Do we need to procure anything?"
      - "What do we need to buy?"
      - "What is the procurement status?"

    Returns a one-screen summary showing:
      - which components require procurement action
      - the LP-level net requirement (horizon total) per component
      - how many forecast weeks triggered procurement per component
      - next-step tool suggestions for detail

    This is the DEFAULT starting point for procurement questions.
    For full LP demand detail: get_aggregated_procurement_need_tool()
    For triggered-week explainability: get_triggered_procurement_rows_tool()

    Args:
        forecast_run_id: Specific forecast run to retrieve. Pass 0 (default)
                         to retrieve the most recent production forecast run.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        return format_procurement_recommendation(conn, forecast_run_id=run_id)
    except Exception as e:
        logger.error("[PROCUREMENT_REC] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving procurement recommendation: {e}"
    finally:
        conn.close()


@tool
def get_triggered_procurement_rows_tool(
    forecast_run_id: int = 0,
    product: str = "",
    facility_id: str = "",
) -> str:
    """Return the weeks and facilities where procurement is triggered (net_requirement > 0).

    Answers questions like:
      - "Why do we need to buy transistors?"
      - "Which weeks trigger procurement for power_devices?"
      - "When does inventory run out?"

    Shows only rows where gross demand exceeds the remaining usable inventory
    (above the safety stock floor), after stateful week-by-week depletion.
    Each row includes: horizon week number, date, facility, gross demand,
    starting on-hand, SS floor, remaining inventory, and net requirement.

    Modes:
      no filter         → all triggered rows, all components, all facilities
      product=…         → triggered rows for that component, all facilities
      product + facility → triggered rows for that component, that facility

    Facility filtering is optional drill-down. The agent should NOT require
    facility by default — only use it when the user explicitly asks for a
    specific facility.

    Args:
        forecast_run_id: Specific forecast run. Pass 0 (default) for latest.
        product:         Component to filter (e.g. 'transistors'). Leave blank
                         for all components.
        facility_id:     Facility to filter (e.g. 'FAC_001'). Only applied
                         when product is also specified. Leave blank for all.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        prod   = product.strip() or None
        fac    = facility_id.strip() or None
        return get_triggered_procurement_rows(
            conn, forecast_run_id=run_id, product=prod, facility_id=fac
        )
    except Exception as e:
        logger.error("[TRIGGERED_ROWS] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving triggered procurement rows: {e}"
    finally:
        conn.close()


# ── BOM Translation Explainability ───────────────────────────────────────────

def format_bom_translation(
    conn,
    semiconductor_id: str,
    forecast_run_id=None,
    facility_id: str | None = None,
    target_week_date: str | None = None,
) -> str:
    """
    Return a business-facing explanation of how a finished-good semiconductor SKU
    is translated through the BOM into procurement component demand.

    Mode A — SKU-level BOM recipe (semiconductor_id only):
        Shows the BOM structure for the SKU: which components are required
        and how many units per finished SKU. No forecast data needed.

    Mode B — Forecast-row explosion (all args provided):
        Shows a specific forecast week's demand for the SKU, applies the BOM
        multipliers, and explains the resulting gross component requirement.
        Includes context block (SKU, facility, week, run) and a gross vs net note.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    semiconductor_id : str
        The finished-good SKU to explain (e.g. 'SEMICONDUCTOR_6').
    forecast_run_id : int, optional
        Specific forecast run. If None, uses the most recent run (Mode B only).
    facility_id : str, optional
        Facility to filter to. If None, Mode A is used regardless of other args.
    target_week_date : str, optional
        ISO date string (YYYY-MM-DD) for the specific forecast week (Mode B).
        If None, Mode A is used.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    # ── Mode A: SKU-level BOM recipe ──────────────────────────────────────────
    if facility_id is None or target_week_date is None:
        with conn.cursor() as cur:
            # SKU display name
            cur.execute(
                """
                SELECT s.semiconductor_id
                FROM dim_bom b
                JOIN dim_product s ON s.product_key = b.semiconductor_product_key
                WHERE s.semiconductor_id = %s
                LIMIT 1
                """,
                (semiconductor_id,),
            )
            sku_row = cur.fetchone()
            if sku_row is None:
                return (
                    f"No BOM record found for semiconductor_id '{semiconductor_id}'.\n"
                    "Check that the SKU exists in dim_bom."
                )

            # BOM components for this SKU
            cur.execute(
                """
                SELECT
                    p.product                       AS component_name,
                    b.units_per_sku                 AS units_per_sku
                FROM dim_bom b
                JOIN dim_product s ON s.product_key = b.semiconductor_product_key
                JOIN dim_product p ON p.product_key = b.component_product_key
                WHERE s.semiconductor_id = %s
                ORDER BY b.units_per_sku DESC, p.product
                """,
                (semiconductor_id,),
            )
            bom_rows = cur.fetchall()

        total_units_per_sku = sum(float(r[1]) for r in bom_rows)
        n_components = len(bom_rows)

        lines = [
            "═" * _W,
            f"  BOM TRANSLATION — {semiconductor_id}",
            "═" * _W,
            "",
            "  This output explains how one finished-good semiconductor SKU maps",
            "  to procurement components via the Bill of Materials (BOM).",
            "",
            "  The BOM defines how many units of each component are required",
            "  to produce one unit of the finished SKU.",
            "",
            _rule("SKU"),
            f"  Semiconductor ID   : {semiconductor_id}",
            f"  Component types    : {n_components}",
            f"  Total units / SKU  : {total_units_per_sku:,.1f}  "
            f"(sum of all component quantities per finished unit)",
            "",
            _rule("BOM Recipe — Units Required per Finished SKU"),
            f"  {'Component':<32}  {'Units / SKU':>12}",
            "  " + "-" * (_W - 4),
        ]
        for component_name, units_per_sku in bom_rows:
            lines.append(f"  {component_name:<32}  {float(units_per_sku):>12,.1f}")
        lines += [
            "  " + "-" * (_W - 4),
            f"  {'TOTAL':<32}  {total_units_per_sku:>12,.1f}",
            "",
            _rule("How to Read This"),
            "  To calculate gross component demand for any forecast period:",
            "    gross_component_requirement = forecasted_SKU_demand × units_per_sku",
            "",
            "  Example: if demand for this SKU is 1,000 units in a given week,",
        ]
        for component_name, units_per_sku in bom_rows:
            ex_units = 1000 * float(units_per_sku)
            lines.append(
                f"    → {ex_units:>10,.0f}  units of  {component_name}  required"
            )
        lines += [
            "",
            "  These gross figures are before any inventory offset.",
            "  Run format_procurement_status() for the net buy signal.",
            "═" * _W,
        ]
        return "\n".join(lines)

    # ── Mode B: Forecast-row explosion ────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                d.semiconductor_id,
                v.facility_id,
                v.target_week_date,
                v.forecast_run_id,
                p.product                       AS component_name,
                v.predicted_demand,
                b.units_per_sku,
                v.gross_component_requirement
            FROM vw_component_requirement_detail v
            JOIN dim_product s ON s.product_key = v.semiconductor_product_key
            JOIN dim_product p ON p.product_key = v.product_key
            JOIN dim_bom b
                ON  b.semiconductor_product_key = v.semiconductor_product_key
                AND b.component_product_key     = v.product_key
            JOIN (
                SELECT DISTINCT semiconductor_id, product_key AS semiconductor_product_key
                FROM dim_bom
                JOIN dim_product ON dim_product.product_key = dim_bom.semiconductor_product_key
            ) d ON d.semiconductor_product_key = v.semiconductor_product_key
            WHERE s.semiconductor_id = %s
              AND v.facility_id      = %s
              AND v.target_week_date = %s
              AND v.forecast_run_id  = %s
            ORDER BY v.gross_component_requirement DESC, p.product
            """,
            (semiconductor_id, facility_id, target_week_date, run_id),
        )
        detail_rows = cur.fetchall()

    if not detail_rows:
        return (
            f"No BOM explosion data found for:\n"
            f"  semiconductor_id : {semiconductor_id}\n"
            f"  facility_id      : {facility_id}\n"
            f"  target_week_date : {target_week_date}\n"
            f"  forecast_run_id  : {run_id}\n\n"
            "Check that the SKU, facility, and week exist in vw_component_requirement_detail."
        )

    # All rows share the same context fields
    _, fac, week, actual_run_id, _, predicted_demand, _, _ = detail_rows[0]
    predicted_demand = float(predicted_demand)
    total_gross = sum(float(r[7]) for r in detail_rows)
    n_components = len(detail_rows)

    lines = [
        "═" * _W,
        f"  BOM TRANSLATION — {semiconductor_id}  (Forecast-Row Explosion)",
        "═" * _W,
        "",
        "  This output explains how a specific forecast week's finished-good",
        "  demand for this SKU is translated through the BOM into gross",
        "  procurement component demand.",
        "",
        _rule("Context"),
        f"  Semiconductor ID   : {semiconductor_id}",
        f"  Facility           : {fac}",
        f"  Week               : {week}",
        f"  Forecast run ID    : {actual_run_id}",
        "",
        _rule("Forecast Demand"),
        f"  Predicted demand   : {predicted_demand:>12,.1f}  finished units",
        "",
        _rule("BOM Explosion — Gross Component Requirement"),
        f"  {'Component':<32}  {'Units/SKU':>10}  {'Gross Req':>12}",
        "  " + "-" * (_W - 4),
    ]
    for _, _, _, _, component_name, _, units_per_sku, gross_req in detail_rows:
        lines.append(
            f"  {component_name:<32}  {float(units_per_sku):>10,.1f}  "
            f"{float(gross_req):>12,.1f}"
        )
    lines += [
        "  " + "-" * (_W - 4),
        f"  {'TOTAL GROSS COMPONENT DEMAND':<32}  {'':>10}  {total_gross:>12,.1f}",
        "",
        _rule("How to Read This"),
        "  gross_component_requirement = predicted_demand × units_per_sku",
        "",
    ]
    for _, _, _, _, component_name, _, units_per_sku, gross_req in detail_rows:
        lines.append(
            f"    {predicted_demand:,.1f}  ×  {float(units_per_sku):.1f}  =  "
            f"{float(gross_req):,.1f}  units of  {component_name}"
        )
    lines += [
        "",
        _rule("Gross vs Net Demand"),
        "  The figures above are GROSS component demand — before any inventory",
        "  offset, safety stock, or open receipt credit is applied.",
        "",
        "  The NET procurement requirement (the actual buy signal) accounts for:",
        "    • on-hand inventory at the facility",
        "    • open purchase receipts already in transit",
        "    • safety stock policy targets",
        "",
        "  Run format_procurement_status() to see the net buy signal.",
        "═" * _W,
    ]
    return "\n".join(lines)


@tool
def get_bom_translation_tool(
    semiconductor_id: str,
    forecast_run_id: int = 0,
    facility_id: str = "",
    target_week_date: str = "",
) -> str:
    """Explain how a finished-good semiconductor SKU maps to procurement components.

    Two modes depending on arguments provided:

    Mode A — BOM recipe (semiconductor_id only):
        Shows the BOM structure: which components are required per finished unit.
        Use when the user asks about the BOM recipe, component breakdown, or
        "what goes into" a semiconductor SKU. No forecast run needed.

    Mode B — Forecast-row explosion (all args):
        Shows a specific forecast week's SKU demand exploded through the BOM
        into gross component demand. Use when the user asks how a specific
        forecast translates into component procurement need.

    Args:
        semiconductor_id: The finished-good SKU (e.g. 'SEMICONDUCTOR_6').
        forecast_run_id:  Specific forecast run ID. Pass 0 (default) to use
                          the most recent run (Mode B only).
        facility_id:      Facility to filter to (e.g. 'FAC_001'). Leave blank
                          for Mode A (BOM recipe only).
        target_week_date: ISO date of the forecast week (e.g. '2024-03-04').
                          Leave blank for Mode A.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        fac    = facility_id.strip() or None
        week   = target_week_date.strip() or None
        return format_bom_translation(
            conn,
            semiconductor_id=semiconductor_id,
            forecast_run_id=run_id,
            facility_id=fac,
            target_week_date=week,
        )
    except Exception as e:
        logger.error("[BOM_TRANSLATION] Tool call failed: %s", e, exc_info=True)
        return f"Error retrieving BOM translation: {e}"
    finally:
        conn.close()
