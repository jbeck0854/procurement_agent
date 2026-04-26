import streamlit as st

from ui.common import _format_facility_label

# ── Base-stock / safety stock policy content ─────────────────────────────────
_SS_FORMULA_TEXT = (
    "**S = \u03bc\u1d05 (r + \u03bc\u2097) + z \u00b7 "
    "\u221a((r + \u03bc\u2097) \u03c3\u1d05\u00b2 + \u03bc\u1d05\u00b2 \u03c3\u2097\u00b2)**"
)
_SS_TERMS_TEXT = (
    "| Symbol | Definition |\n"
    "|---|---|\n"
    "| \u03bc\u1d05 | Average weekly component demand |\n"
    "| \u03c3\u1d05 | Demand standard deviation |\n"
    "| \u03bc\u2097 | Average lead time (weeks) |\n"
    "| \u03c3\u2097 | Lead time standard deviation |\n"
    "| r | Review period \u2014 **8 weeks** |\n"
    "| z | Service level factor \u2014 **\u22481.65** for 95% target |"
)
_SS_BUSINESS_HTML = (
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "The formula computes the <strong>base-stock level (S)</strong> \u2014 the total inventory "
    "required to meet demand across the review period and lead time under uncertainty.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Safety stock</strong> is the buffer component embedded within this level, covering "
    "demand and lead-time variability.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "In this system, safety stock is enforced as a <strong>protected inventory floor</strong> "
    "per facility \u00d7 component. It is not consumed during planning.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Only inventory <strong>above</strong> this floor is used to satisfy weekly demand.</p></div>"
)
_SS_CYCLE_STOCK_HTML = (
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; line-height:1.55;'>"
    "The base-stock level (S) has two distinct components:</p>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; line-height:1.55;'>"
    "<strong>1. Cycle Stock</strong> \u2014 \u03bc\u1d05 \u00d7 (r + \u03bc\u2097)</p>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Covers <strong>expected demand</strong> over the review period and lead time</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "This is the primary driver of inventory volume</p></div>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; line-height:1.55; margin-top:0.6rem;'>"
    "<strong>2. Safety Stock</strong> \u2014 z \u00b7 \u221a((r + \u03bc\u2097)\u03c3\u1d05\u00b2 "
    "+ \u03bc\u1d05\u00b2\u03c3\u2097\u00b2)</p>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Covers <strong>uncertainty</strong> in demand and lead time</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "This is a buffer \u2014 NOT intended to cover expected demand</p></div>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; line-height:1.55; margin-top:0.6rem;'>"
    "On-hand inventory at the start of planning is anchored at "
    "<strong>S = Cycle Stock + Safety Stock</strong>. "
    "Safety stock alone will often appear small relative to weekly demand \u2014 "
    "this is expected and correct.</p>"
)
_SS_PLANNING_HTML = (
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Weekly procurement is triggered when <strong>usable inventory</strong> (above the safety "
    "stock floor) reaches zero.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Safety stock is already accounted for before any weekly demand calculations "
    "begin \u2014 it does not appear as a deduction in the weekly trigger table.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "The weekly trigger table reflects how demand consumes usable inventory, "
    "not safety stock itself.</p></div>"
)

# ── Weekly trigger column constants ──────────────────────────────────────────
_TRIG_COL_ORDER_DISPLAY = [
    "Forecast Week", "Week", "Component", "Facility",
    "Gross Requirement", "Available Inventory Before Demand",
    "Direct Procurement Needed", "Cumulative Procurement Pressure",
    "Safety Stock Utilization (%)", "Urgency Level",
]
_TRIG_FMT_DISPLAY = {
    "Gross Requirement":                  "{:,.0f}",
    "Available Inventory Before Demand":  "{:,.0f}",
    "Direct Procurement Needed":          "{:,.0f}",
    "Cumulative Procurement Pressure":    "{:,.0f}",
    "Safety Stock Utilization (%)":       "{:.1f}%",
    "Forecast Week":                      "{:,.0f}",
}
_TRIG_BULLETS_HTML = (
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Gross Requirement:</strong> forecast-driven component demand for that week.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Available Inventory Before Demand:</strong> usable inventory remaining above the "
    "safety stock floor at the start of this week (rolling — decreases each week as prior "
    "demand is consumed).</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Direct Procurement Needed:</strong> portion of demand not covered by usable "
    "inventory.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Cumulative Procurement Pressure:</strong> total procurement required up to that "
    "week, per facility \u00d7 component.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Safety Stock Utilization (%):</strong> how much of the safety buffer is being "
    "matched by cumulative procurement demand.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "<strong>Urgency Level:</strong> qualitative indicator \u2014 Low / Medium / High / "
    "Critical \u2014 based on how close cumulative pressure is to the safety "
    "buffer.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Procurement is triggered when usable inventory reaches zero.</p></div>"
)

_BOM_XLATE_EXEC_NOTE_HTML = (
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "This step shows what components are required to build the products "
    "our customers are expecting.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Every finished unit requires a specific mix of inputs \u2014 the BOM "
    "defines how many units of each component are needed per SKU.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "Multiplying that recipe by the forecasted demand yields the gross "
    "component requirements shown below.</p></div>"
    "<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
    "padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
    "<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
    "These totals are calculated before any inventory has been considered.</p></div>"
)


def _fetch_component_req_data() -> dict:
    """Fetch structured component requirement data for DataFrame rendering.

    Queries the same source as format_component_requirements() but returns
    structured dicts/lists instead of formatted text — used by the demo render
    block to build proper DataFrames. No computation is changed.
    """
    import psycopg2
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
    from config import DATABASE_URL

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Resolve latest forecast run (matches _resolve_run_id contract)
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "ORDER BY forecast_run_id DESC LIMIT 1"
            )
            row = cur.fetchone()
            run_id = int(row[0]) if row else 0

            # Planning window metadata
            cur.execute(
                """
                SELECT MIN(target_week_date), MAX(target_week_date),
                       COUNT(DISTINCT target_week_date),
                       COUNT(DISTINCT facility_id),
                       COUNT(DISTINCT product_key)
                FROM vw_component_requirement_lp
                WHERE forecast_run_id = %s
                """,
                (run_id,),
            )
            start_date, end_date, n_weeks, n_fac, n_comp = cur.fetchone()

            # Per-component totals, ordered by descending volume
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
    finally:
        conn.close()

    return {
        "run_id":       run_id,
        "start_date":   str(start_date),
        "end_date":     str(end_date),
        "n_weeks":      int(n_weeks),
        "n_facilities": int(n_fac),
        "n_components": int(n_comp),
        "rows":         [(r[0], float(r[1])) for r in comp_rows],
    }


def _render_bom_translation_body(rows: list) -> None:
    """
    Render the BOM translation dataframe + explanatory bullets.
    Shared by the direct BOM translation query handler and the
    collapsible expander beneath component requirements — no logic duplication.
    """
    import pandas as _pd_bom
    st.subheader("BOM Translation — How Finished Demand Becomes Component Demand")
    st.caption(
        "How each finished SKU's forecasted demand converts to gross "
        "component demand across all facilities and forecast weeks"
    )
    _df_bom = _pd_bom.DataFrame(rows)
    if not _df_bom.empty:
        st.dataframe(
            _df_bom.style.format({
                "Units / SKU":            "{:,.2f}",
                "Forecast (units)":       "{:,.0f}",
                "Gross Component Demand": "{:,.0f}",
            }),
            height=420,
            use_container_width=True,
            hide_index=True,
        )
    st.markdown(_BOM_XLATE_EXEC_NOTE_HTML, unsafe_allow_html=True)


def _render_ss_policy_body() -> None:
    """
    Render the full base-stock / safety stock policy explanation.
    Pure text — no DB query. Shared by the direct query handler and the
    'Detail on Base Stock Policy' expander beneath the inventory summary.
    """
    st.subheader("Inventory Policy \u2014 Safety Stock and Base-Stock Logic")
    st.markdown("**Base-Stock Formula**")
    st.markdown(_SS_FORMULA_TEXT)
    st.markdown("**Term Definitions**")
    st.markdown(_SS_TERMS_TEXT)
    st.markdown("**How It Works**")
    st.markdown(_SS_BUSINESS_HTML, unsafe_allow_html=True)
    st.markdown("**Cycle Stock vs Safety Stock (Key Distinction)**")
    st.markdown(_SS_CYCLE_STOCK_HTML, unsafe_allow_html=True)
    st.markdown("**Connection to Planning Outputs**")
    st.markdown(_SS_PLANNING_HTML, unsafe_allow_html=True)


def _prepare_trigger_df_from_raw(trig_data: dict):
    """
    Apply all presentation transforms to a query_triggered_rows_structured() result.
    Returns (df_display, ss_context_records, display_rows).
    No inventory logic — purely column renames, derived display columns, and ordering.
    """
    import pandas as _pd_trig

    _rows = trig_data.get("rows", [])
    df = _pd_trig.DataFrame(_rows)

    if not df.empty and "Facility" in df.columns:
        df["Facility"] = df["Facility"].apply(_format_facility_label)

    df = df.rename(columns={
        "Procurement Need": "Direct Procurement Needed",
    })

    # Extract SS context before column reorder
    ss_ctx = []
    if not df.empty and "Safety Stock Reserve" in df.columns:
        ss_ctx = (
            df[["Facility", "Component", "Safety Stock Reserve"]]
            .drop_duplicates()
            .sort_values(["Facility", "Component"])
            .rename(columns={"Safety Stock Reserve": "Safety Stock (Protected Floor)"})
            .to_dict("records")
        )

    # Derived display columns (no inventory formula change)
    if not df.empty and "Safety Stock Reserve" in df.columns:
        df = df.sort_values(["Component", "Facility", "Week"])
        df["Cumulative Procurement Pressure"] = (
            df.groupby(["Facility", "Component"])["Direct Procurement Needed"]
            .cumsum()
        )
        df["Safety Stock Utilization (%)"] = df.apply(
            lambda r: round(r["Cumulative Procurement Pressure"] / r["Safety Stock Reserve"] * 100, 1)
            if r["Safety Stock Reserve"] > 0 else 100.0,
            axis=1,
        )
        df["Urgency Level"] = df["Safety Stock Utilization (%)"].apply(
            lambda u: "Critical" if u >= 100 else
                      "High"     if u >= 75  else
                      "Medium"   if u >= 50  else
                      "Low"
        )

    if not df.empty:
        df = df[[c for c in _TRIG_COL_ORDER_DISPLAY if c in df.columns]]

    return df, ss_ctx, df.to_dict("records")
