"""
procurement_summary.py — Business-facing BOM / inventory planning layer summaries.

Entry points (independently callable):
    format_component_requirements(conn, forecast_run_id=None) -> str
    format_procurement_status(conn, forecast_run_id=None)     -> str

LangChain @tool wrappers (manage their own DB connection):
    get_component_requirements_summary_tool(forecast_run_id=0) -> str
    get_procurement_status_summary_tool(forecast_run_id=0)     -> str
    get_procurement_planning_summary_tool(forecast_run_id=0)   -> str

Reads from:
    vw_component_requirement_lp          (BOM-exploded full-horizon demand)
    vw_procurement_requirement           (inventory-adjusted net requirement)
    fact_component_inventory_history     (decision-point on-hand / inventory state)
    fact_inventory_policy                (safety stock and policy parameters)
    dim_forecast_run                     (run metadata)
    dim_product                          (product name lookup)

Does NOT modify any computational logic, formulas, or DB tables.
All values are read from pre-computed tables and views.
No @tool wrappers — these are pure formatting helpers for future integration.

Usage:
    import psycopg2
    from inventory.procurement_summary import (
        format_component_requirements,
        format_procurement_status,
    )

    conn = psycopg2.connect(DATABASE_URL)
    print(format_component_requirements(conn))
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
    Return a business-facing inventory-adjusted procurement buy signal.

    Shows net procurement requirement after applying inventory position and
    safety stock policy to the BOM-exploded component demand. This is the
    direct input to the procurement optimization layer.

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

        # Per-component aggregates using consistent triggered-row scope.
        #
        # All six formula inputs (gross, backorder, SS, on_hand, sched, net)
        # are summed over the same subset of rows: those where net_requirement > 0.
        # This ensures the column totals satisfy the formula exactly:
        #   SUM(triggered_gross) + SUM(triggered_backorder) + SUM(triggered_SS)
        #   - SUM(triggered_on_hand) - SUM(triggered_sched) = SUM(net_requirement)
        #
        # on_hand and SS are constant per (facility, product) across all forecast
        # weeks, so summing over triggered rows captures the per-facility values
        # for only the facilities and weeks where procurement is required.
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
        "  policy to the BOM-exploded component demand to derive the net",
        "  quantity that must be procured. It is the direct input to the",
        "  procurement optimization layer.",
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
        _rule("Procurement Formula"),
        "  net_requirement = max( 0,",
        "      gross_requirement        [+]   BOM-translated forecast demand",
        "    + backorder_qty            [+]   unfilled demand carried forward",
        "    + safety_stock_qty         [+]   policy buffer (95% service level)",
        "    - on_hand_qty              [-]   inventory at decision point",
        "    - scheduled_receipts_qty   [-]   on-order at decision point",
        "  )",
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
        "  safety_stock_qty         [+]",
        "    Policy-required buffer stock per facility × component.",
        "    Periodic-review base-stock formula, z = 1.65 (95% service level).",
        "    Fixed at the decision point — the same physical value applies to",
        "    every forecast week. In the summary table below it is summed over",
        "    procurement-triggered rows only, not across the full horizon.",
        "",
        "  on_hand_qty              [-]",
        "    Inventory on hand at the decision point.",
        "    Set to safety_stock + one week of average demand (SS + μ_D).",
        "    Fixed at the decision point — the same physical value applies to",
        "    every forecast week. In the summary table below it is summed over",
        "    procurement-triggered rows only, not across the full horizon.",
        "",
        "  scheduled_receipts_qty   [-]",
        "    Quantity already on order at the decision point.",
        "    Currently 0 — set to zero at the planning decision point by design.",
        "",
        "  net_requirement",
        "    Actual procurement need after all offsets.",
        "    The procurement optimizer uses this as the demand floor for",
        "    supplier allocation decisions.",
        "",
        _rule("Procurement Signal by Component"),
        "  Metrics summed over procurement-triggered rows (net_requirement > 0).",
        "  on_hand and safety stock reflect values for those rows and facilities.",
        "",
        (
            f"  {'Component':<36}"
            f" {'Gross Req [+]':>13}"
            f" {'On Hand [-]':>11}"
            f" {'Sched Rec [-]':>13}"
            f" {'Backorder [+]':>13}"
            f" {'Safety Stk [+]':>14}"
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
    """Return the inventory-adjusted procurement buy signal.

    Shows net procurement requirement after applying current inventory position
    and safety stock policy to the BOM-exploded component demand. This is the
    direct input to the LP procurement optimization layer.

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
    """Return both the component requirements and procurement buy signal in sequence.

    Combines format_component_requirements (gross BOM-exploded demand) and
    format_procurement_status (inventory-adjusted net requirement) into a single
    output. Use this for a complete view of the procurement planning picture:
    from raw component demand through to the final buy signal.

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
