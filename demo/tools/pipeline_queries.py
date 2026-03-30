"""
Direct-mode query tools for the upstream pipeline (forecast, BOM, inventory).
These bypass the ReAct loop — each tool runs 1-2 SQL queries and returns
a formatted summary. Designed for speed in the demo flow.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import psycopg2
import psycopg2.extras

from config import DATABASE_URL

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def query_forecast_summary(**kwargs) -> dict:
    """
    Return a summary of the latest demand forecast:
    - forecast metadata (model, horizon, dates)
    - weekly aggregated demand (total across all SKUs/facilities)
    """
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Forecast run metadata
        cur.execute("""
            SELECT forecast_run_id, model_version, forecast_origin_date,
                   observed_through_week_date, horizon_weeks_max, n_series,
                   n_forecast_rows, run_status, created_at
            FROM dim_forecast_run
            WHERE forecast_run_id = (SELECT MAX(forecast_run_id) FROM dim_forecast_run)
        """)
        run_meta = dict(cur.fetchone())
        run_id = run_meta["forecast_run_id"]

        # Weekly aggregated forecast
        cur.execute("""
            SELECT target_week_date,
                   ROUND(SUM(predicted_demand)::numeric, 0) AS total_demand,
                   ROUND(SUM(interval_lower_90)::numeric, 0) AS total_lower_90,
                   ROUND(SUM(interval_upper_90)::numeric, 0) AS total_upper_90
            FROM fact_semiconductor_demand_forecast
            WHERE forecast_run_id = %s
            GROUP BY target_week_date
            ORDER BY target_week_date
        """, (run_id,))
        weekly = [dict(row) for row in cur.fetchall()]

        # Summary stats
        demands = [int(w["total_demand"]) for w in weekly]
        total = sum(demands)
        avg = round(total / len(demands)) if demands else 0
        peak_week = max(weekly, key=lambda w: w["total_demand"]) if weekly else {}
        low_week = min(weekly, key=lambda w: w["total_demand"]) if weekly else {}

        # Format output
        lines = [
            f"Forecast Run: {run_meta['model_version']} (run_id={run_id})",
            f"Created: {run_meta['created_at']}",
            f"Horizon: {run_meta['horizon_weeks_max']} weeks "
            f"({weekly[0]['target_week_date']} to {weekly[-1]['target_week_date']})" if weekly else "No data",
            f"Series: {run_meta['n_series']} (SKU × facility combinations)",
            "",
            f"Total forecasted demand: {total:,} units",
            f"Average weekly demand: {avg:,} units",
            f"Peak week: {peak_week.get('target_week_date', 'N/A')} ({int(peak_week.get('total_demand', 0)):,} units)",
            f"Lowest week: {low_week.get('target_week_date', 'N/A')} ({int(low_week.get('total_demand', 0)):,} units)",
            "",
            "Weekly Forecast:",
        ]
        for w in weekly:
            lines.append(
                f"  {w['target_week_date']}: {int(w['total_demand']):>8,} units "
                f"(90% CI: {int(w['total_lower_90']):,} – {int(w['total_upper_90']):,})"
            )

        return {"content": "\n".join(lines), "name": "forecast_summary"}
    finally:
        conn.close()


def query_component_requirements(**kwargs) -> dict:
    """
    Return aggregated component requirements from the BOM layer,
    showing gross requirement by product type across the forecast horizon.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get latest forecast run
        cur.execute("SELECT MAX(forecast_run_id) AS run_id FROM dim_forecast_run")
        run_id = cur.fetchone()["run_id"]

        # Component requirements aggregated by product
        cur.execute("""
            SELECT dp.product,
                   ROUND(SUM(lp.total_component_requirement)::numeric, 0) AS gross_requirement,
                   COUNT(DISTINCT lp.facility_id) AS n_facilities,
                   COUNT(DISTINCT lp.target_week_date) AS n_weeks,
                   MIN(lp.target_week_date) AS first_week,
                   MAX(lp.target_week_date) AS last_week
            FROM vw_component_requirement_lp lp
            JOIN dim_product dp ON dp.product_key = lp.product_key
            WHERE lp.forecast_run_id = %s
            GROUP BY dp.product
            ORDER BY gross_requirement DESC
        """, (run_id,))
        rows = [dict(r) for r in cur.fetchall()]

        total = sum(int(r["gross_requirement"]) for r in rows)

        lines = [
            f"Component Requirements (forecast_run_id={run_id})",
            f"Planning window: {rows[0]['first_week']} to {rows[0]['last_week']}" if rows else "No data",
            f"Total gross requirement: {total:,} units across {len(rows)} component types",
            "",
            f"{'Component':<35} {'Gross Req':>12} {'Facilities':>10} {'Weeks':>6}",
            "-" * 65,
        ]
        for r in rows:
            lines.append(
                f"{r['product']:<35} {int(r['gross_requirement']):>12,} "
                f"{r['n_facilities']:>10} {r['n_weeks']:>6}"
            )

        return {"content": "\n".join(lines), "name": "component_requirements"}
    finally:
        conn.close()


def query_procurement_status(**kwargs) -> dict:
    """
    Return procurement status from vw_procurement_requirement:
    which components need action, how much, and current inventory position.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Aggregated procurement requirement by product
        cur.execute("""
            SELECT dp.product,
                   ROUND(SUM(pr.gross_requirement)::numeric, 0) AS gross_req,
                   ROUND(AVG(pr.on_hand_qty)::numeric, 0) AS avg_on_hand,
                   ROUND(AVG(pr.safety_stock_qty)::numeric, 0) AS avg_safety_stock,
                   ROUND(SUM(pr.net_requirement)::numeric, 0) AS net_req,
                   COUNT(*) AS weeks_with_need
            FROM vw_procurement_requirement pr
            JOIN dim_product dp ON dp.product_key = pr.product_key
            WHERE pr.net_requirement > 0
            GROUP BY dp.product
            ORDER BY SUM(pr.net_requirement) DESC
        """)
        action_rows = [dict(r) for r in cur.fetchall()]

        # Also get products with NO procurement need
        cur.execute("""
            SELECT dp.product,
                   ROUND(SUM(pr.gross_requirement)::numeric, 0) AS gross_req,
                   ROUND(AVG(pr.on_hand_qty)::numeric, 0) AS avg_on_hand,
                   0 AS net_req
            FROM vw_procurement_requirement pr
            JOIN dim_product dp ON dp.product_key = pr.product_key
            WHERE pr.net_requirement <= 0
              AND dp.product NOT IN (
                  SELECT dp2.product FROM vw_procurement_requirement pr2
                  JOIN dim_product dp2 ON dp2.product_key = pr2.product_key
                  WHERE pr2.net_requirement > 0
              )
            GROUP BY dp.product
        """)
        covered_rows = [dict(r) for r in cur.fetchall()]

        total_net = sum(int(r["net_req"]) for r in action_rows)

        lines = [
            "Procurement Status — Inventory vs. Forecast Requirements",
            "",
            f"Components requiring action: {len(action_rows)} of {len(action_rows) + len(covered_rows)}",
            f"Total net procurement requirement: {total_net:,} units",
            "",
            f"{'Component':<35} {'Gross Req':>10} {'On-Hand':>10} {'Safety Stk':>10} {'Net Req':>10} {'Status':>12}",
            "-" * 90,
        ]
        for r in action_rows:
            lines.append(
                f"{r['product']:<35} {int(r['gross_req']):>10,} {int(r['avg_on_hand']):>10,} "
                f"{int(r['avg_safety_stock']):>10,} {int(r['net_req']):>10,} {'ACTION':>12}"
            )
        for r in covered_rows:
            lines.append(
                f"{r['product']:<35} {int(r['gross_req']):>10,} {int(r['avg_on_hand']):>10,} "
                f"{'—':>10} {0:>10,} {'COVERED':>12}"
            )

        return {"content": "\n".join(lines), "name": "procurement_status"}
    finally:
        conn.close()


DIRECT_PIPELINE_TOOLS = {
    "query_forecast_summary": query_forecast_summary,
    "query_component_requirements": query_component_requirements,
    "query_procurement_status": query_procurement_status,
}
