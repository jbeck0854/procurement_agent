"""
Direct-mode query tools for the upstream pipeline (forecast, BOM, inventory).
These bypass the ReAct loop — each tool runs pre-built queries and returns
a formatted business-friendly summary. Designed for speed in the demo flow.

Delegates to Jonathan's helper modules in forecasting/ and inventory/.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import psycopg2

from config import DATABASE_URL

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


# ── Forecast helpers (from forecasting/forecast_summary.py) ─────────────────

from forecasting.forecast_summary import (
    get_forecast_summary_tool,
    get_forecast_drilldown_tool,
    get_forecast_model_assessment,
)

# ── Inventory/Procurement helpers (from inventory/procurement_summary.py) ───

from inventory.procurement_summary import (
    get_component_requirements_summary_tool,
    get_procurement_status_summary_tool,
    get_procurement_planning_summary_tool,
    get_aggregated_procurement_need_tool,
    get_bom_translation_tool,
    get_procurement_requirement_drilldown,
    get_triggered_procurement_rows,
)


# ── Wrappers ────────────────────────────────────────────────────────────────
#
# Jonathan's @tool-decorated helpers manage their own DB connections.
# We wrap them so pipeline_agent gets a uniform {content, name} interface.
#
# For functions that require a `conn` argument (drill-down, triggered rows),
# we manage the connection here.
# ────────────────────────────────────────────────────────────────────────────


def query_forecast_summary(**kwargs) -> dict:
    """Business-friendly production demand forecast summary."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_forecast_summary_tool.invoke({"forecast_run_id": forecast_run_id})
    return {"content": result, "name": "forecast_summary"}


def query_forecast_drilldown(**kwargs) -> dict:
    """Week × facility × SKU forecast detail with confidence bounds."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    export_csv = kwargs.get("export_csv", False)
    result = get_forecast_drilldown_tool.invoke({
        "forecast_run_id": forecast_run_id,
        "export_csv": export_csv,
    })
    return {"content": result, "name": "forecast_drilldown"}


def get_forecast_drilldown_df(forecast_run_id=None):
    """Return the full forecast drill-down as a DataFrame for custom rendering."""
    from forecasting.forecast_summary import get_production_forecast_drilldown
    conn = _get_conn()
    try:
        return get_production_forecast_drilldown(conn, forecast_run_id=forecast_run_id)
    finally:
        conn.close()


def _plot_facility_forecast(df, facility_id: str):
    """Single-facility line chart — one line per SKU with shaded 90% CI. Returns fig."""
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    fac_df = df[df["facility_id"] == facility_id].copy()
    fac_df["target_week_date"] = fac_df["target_week_date"].astype(str)
    skus = sorted(fac_df["semiconductor_id"].unique())
    palette = [cm.tab10(i / 10) for i in range(min(len(skus), 10))]

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, sku in enumerate(skus):
        s = fac_df[fac_df["semiconductor_id"] == sku].sort_values("target_week_date")
        c = palette[i % len(palette)]
        ax.plot(s["target_week_date"], s["predicted_demand"],
                label=sku, color=c, linewidth=1.8)
        ax.fill_between(s["target_week_date"],
                        s["interval_lower_90"], s["interval_upper_90"],
                        alpha=0.07, color=c)

    ax.set_title(f"Production Demand Forecast — {facility_id}", fontsize=13, pad=10)
    ax.set_xlabel("Week")
    ax.set_ylabel("Forecasted Demand (units)")
    ax.legend(fontsize=7, ncol=max(1, len(skus) // 4), loc="upper right")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.tight_layout()
    return fig


def _narrative_facility(df, facility_id: str) -> str:
    """Four-sentence business narrative for a single-facility forecast chart."""
    fac_df = df[df["facility_id"] == facility_id]
    weekly = fac_df.groupby("target_week_date")["predicted_demand"].sum()
    total = weekly.sum()
    avg = weekly.mean()
    peak_week = str(weekly.idxmax())
    peak_val = weekly.max()
    low_week = str(weekly.idxmin())
    low_val = weekly.min()
    by_sku = fac_df.groupby("semiconductor_id")["predicted_demand"].sum()
    top_sku = by_sku.idxmax()
    top_share = by_sku.max() / by_sku.sum() * 100
    n_skus = by_sku.nunique()
    dist_note = (
        f"Demand is concentrated: **{top_sku}** accounts for {top_share:.0f}% of total facility volume."
        if top_share > 40
        else f"Demand is broadly distributed across {n_skus} SKUs; "
             f"no single SKU dominates (top share: {top_share:.0f}%)."
    )
    return (
        f"{facility_id} has a total forecasted demand of **{total:,.0f} units** "
        f"across the planning horizon, averaging **{avg:,.0f} units/week**. "
        f"Peak demand occurs in week **{peak_week}** at **{peak_val:,.0f} units**. "
        f"The lowest demand week is **{low_week}** at **{low_val:,.0f} units**. "
        f"{dist_note}"
    )


def _plot_all_facilities_forecast(df):
    """All-facilities line chart — one aggregated line per facility. Returns fig."""
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    weekly = (
        df.groupby(["facility_id", "target_week_date"])["predicted_demand"]
        .sum()
        .reset_index()
    )
    weekly["target_week_date"] = weekly["target_week_date"].astype(str)
    facilities = sorted(weekly["facility_id"].unique())
    palette = [cm.tab10(i / 10) for i in range(min(len(facilities), 10))]

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, fac in enumerate(facilities):
        s = weekly[weekly["facility_id"] == fac].sort_values("target_week_date")
        ax.plot(s["target_week_date"], s["predicted_demand"],
                label=fac, color=palette[i], linewidth=2)

    ax.set_title("Production Demand Forecast — All Facilities", fontsize=13, pad=10)
    ax.set_xlabel("Week")
    ax.set_ylabel("Total Forecasted Demand (units)")
    ax.legend(fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.tight_layout()
    return fig


def _narrative_all_facilities(df) -> str:
    """Concise bullet summary for the all-facilities forecast chart."""
    import re
    import pandas as pd

    def _fac_label(fid: str) -> str:
        """'FACILITY_1' → 'Facility 1'."""
        m = re.match(r'FACILITY_(\d+)', str(fid), re.IGNORECASE)
        return f"Facility {m.group(1)}" if m else str(fid)

    by_fac_week = df.groupby(["facility_id", "target_week_date"])["predicted_demand"].sum()
    by_fac = pd.to_numeric(
        by_fac_week.groupby("facility_id").sum(), errors="coerce"
    ).fillna(0.0)
    total   = by_fac.sum()
    weeks   = df["target_week_date"].nunique()
    top_fid = by_fac.idxmax()
    top_val = by_fac.max()
    bot_fid = by_fac.idxmin()
    bot_val = by_fac.min()

    lines = [
        f"- Forecast covers **{len(by_fac)} facilities over {weeks} weeks**, "
        f"with a combined total of **{total:,.0f} units**",
        f"- **Highest-demand facility:** {_fac_label(top_fid)} with "
        f"**{top_val:,.0f} units** (~{top_val / total * 100:.0f}% of total demand)",
        f"- **Lowest-demand facility:** {_fac_label(bot_fid)} with "
        f"**{bot_val:,.0f} units** (~{bot_val / total * 100:.0f}% of total demand)",
    ]
    return "\n".join(lines)


# Compact, business-facing markdown summaries for each assessment direction.
# Rendered with st.markdown() in the app — wraps properly, no horizontal overflow.
# Artifact paths are relative to the project root (one level above demo/).
_ASSESSMENT_COMPACT = {
    "validation": (
        "artifacts/forecasting/system_full_history_holdout.png",
        """\
**Model:** HistGradientBoosting Regressor (HGB), trained jointly on all 48 facility–SKU \
series (4 facilities × 12 semiconductor SKUs, weeks 1–145).

**Validation design:**
- 5-fold time-series cross-validation, 243 hyperparameter configurations tested
- 10-week holdout (weeks 136–145) held out before any model fitting

**Holdout performance (unseen data):**
- Row-level MAE: **205.93** units/series/week
- RMSE: 289.37 &nbsp;|&nbsp; MAPE: 23.75% &nbsp;|&nbsp; R²: **0.778**
- System-level weekly MAE: ~4,012 units — less than 8% of typical weekly demand

The model explains **~78% of demand variance** on held-out data. \
The production model retrains on the full 145-week history before generating the planning horizon.\
""",
    ),
    "features": (
        "artifacts/forecasting/permutation_importance.png",
        """\
**Method:** Permutation importance measured on the 10-week held-out validation set. \
Each feature is shuffled independently; the accuracy drop indicates its contribution.

**Top drivers:**
- **lag_1** (prior-week demand for same series) — single strongest predictor
- **roll_mean_4 / roll_mean_8** (near-term demand momentum) — also rank highly
- **Price & promotional signals** (realized_selling_price, emailer, homepage) — meaningful, secondary to demand history
- **Cyclical time encodings** (week_sin_52 / week_cos_52) — capture seasonal patterns
- **global_mean_lag_1** — cross-series shared demand signal

*Correlated features can mutually suppress each other's measured importance.*\
""",
    ),
    "baseline": (
        "artifacts/forecasting/baseline_system_comparison.png",
        """\
**Baselines evaluated on the same 10-week holdout (weeks 136–145):**
- **Lag-1:** repeat last week's observed demand
- **Rolling Mean-4:** 4-week trailing average

| Model | Row-Level MAE |
|---|---|
| HGB (production) | 205.93 |
| Lag-1 baseline | 223.06 |
| Rolling Mean-4 baseline | 266.42 |

The production model achieves **7.7% lower error than lag-1** and **22.7% lower than rolling mean-4**. \
Gains are consistent across most of the 48 series. \
Better demand accuracy translates directly into tighter inventory targets, \
fewer unnecessary safety stock buffers, and more reliable supplier allocation decisions.\
""",
    ),
}


def query_forecast_model_assessment(**kwargs) -> dict:
    """Model explainability: validation, feature importance, or baseline comparison.

    Returns a compact markdown summary and the artifact PNG path — no path/why-it-matters clutter.
    Calls get_forecast_model_assessment() to validate the direction and confirm the artifact exists.
    """
    direction = kwargs.get("direction", "validation")
    try:
        # Validates direction is recognised and artifact file exists; raises on failure.
        get_forecast_model_assessment(direction)
        artifact_path, compact_text = _ASSESSMENT_COMPACT.get(
            direction, ("", f"Assessment direction '{direction}' not found in compact registry.")
        )
        return {
            "content": compact_text,
            "artifact_path": artifact_path,
            "name": "forecast_model_assessment",
        }
    except (ValueError, FileNotFoundError) as e:
        return {"content": f"Error: {e}", "artifact_path": "", "name": "forecast_model_assessment"}


def query_component_requirements(**kwargs) -> dict:
    """Full-horizon gross BOM demand (before inventory offset)."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_component_requirements_summary_tool.invoke({
        "forecast_run_id": forecast_run_id,
    })
    return {"content": result, "name": "component_requirements"}


def query_procurement_status(**kwargs) -> dict:
    """Week-by-week inventory-adjusted procurement trigger signal."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_procurement_status_summary_tool.invoke({
        "forecast_run_id": forecast_run_id,
    })
    return {"content": result, "name": "procurement_status"}


def query_procurement_planning_summary(**kwargs) -> dict:
    """Combined: gross BOM demand + weekly procurement trigger signal."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_procurement_planning_summary_tool.invoke({
        "forecast_run_id": forecast_run_id,
    })
    return {"content": result, "name": "procurement_planning_summary"}


def query_aggregated_procurement_need(**kwargs) -> dict:
    """Horizon-level LP demand floor — what the optimizer allocates against."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    product = kwargs.get("product", "")
    facility_id = kwargs.get("facility_id", "")
    result = get_aggregated_procurement_need_tool.invoke({
        "forecast_run_id": forecast_run_id,
        "product": product,
        "facility_id": facility_id,
    })
    return {"content": result, "name": "aggregated_procurement_need"}


def query_procurement_drilldown(**kwargs) -> dict:
    """Week-by-week drill-down at component × facility × week grain."""
    product = kwargs.get("product", None)
    facility_id = kwargs.get("facility_id", None)
    forecast_run_id = kwargs.get("forecast_run_id", None)
    conn = _get_conn()
    try:
        result = get_procurement_requirement_drilldown(
            conn,
            forecast_run_id=forecast_run_id,
            product=product,
            facility_id=facility_id,
        )
        return {"content": result, "name": "procurement_drilldown"}
    finally:
        conn.close()


def query_triggered_procurement_rows(**kwargs) -> dict:
    """Only weeks/facilities where net requirement > 0."""
    product = kwargs.get("product", None)
    facility_id = kwargs.get("facility_id", None)
    forecast_run_id = kwargs.get("forecast_run_id", None)
    conn = _get_conn()
    try:
        result = get_triggered_procurement_rows(
            conn,
            forecast_run_id=forecast_run_id,
            product=product,
            facility_id=facility_id,
        )
        return {"content": result, "name": "triggered_procurement_rows"}
    finally:
        conn.close()


def query_bom_translation(**kwargs) -> dict:
    """BOM recipe or forecast-row explosion for a semiconductor SKU."""
    semiconductor_id = kwargs.get("semiconductor_id", "")
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    facility_id = kwargs.get("facility_id", "")
    target_week_date = kwargs.get("target_week_date", "")
    result = get_bom_translation_tool.invoke({
        "semiconductor_id": semiconductor_id,
        "forecast_run_id": forecast_run_id,
        "facility_id": facility_id,
        "target_week_date": target_week_date,
    })
    return {"content": result, "name": "bom_translation"}


def query_procurement_summary_data(**kwargs) -> dict:
    """Horizon-level inventory-adjusted procurement requirement per component.

    Applies the LP demand-floor formula per facility (same as
    format_aggregated_procurement_need), then sums across all facilities
    to give a component-level breakdown suitable for the opening inventory
    question: 'Do we need to buy anything?' / 'What is our net procurement need?'

    Returns structured rows for DataFrame rendering — no ASCII formatting.
    """
    forecast_run_id = kwargs.get("forecast_run_id", None)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Resolve latest run
            if forecast_run_id:
                run_id = int(forecast_run_id)
            else:
                cur.execute(
                    "SELECT forecast_run_id FROM dim_forecast_run "
                    "ORDER BY forecast_run_id DESC LIMIT 1"
                )
                row = cur.fetchone()
                run_id = int(row[0]) if row else 0

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
            horizon_start, horizon_end, n_weeks = cur.fetchone()

            # Per-component horizon summary:
            # LP formula applied per facility, then summed across facilities.
            # Breakdown columns (on_hand, sr, bo, ss) summed across facilities
            # for transparent display; net_req is the LP-correct sum of
            # per-facility GREATEST(0, ...) values.
            cur.execute(
                """
                SELECT
                    dp.product                                       AS component,
                    SUM(dp_snap.on_hand_qty)                         AS on_hand_total,
                    SUM(dp_snap.scheduled_receipts_qty)              AS sr_total,
                    SUM(dp_snap.backorder_qty)                       AS bo_total,
                    SUM(pol.safety_stock_qty)                        AS ss_total,
                    SUM(lp_agg.gross_demand)                         AS gross_demand_total,
                    SUM(GREATEST(0,
                        lp_agg.gross_demand
                        + dp_snap.backorder_qty
                        + pol.safety_stock_qty
                        - dp_snap.on_hand_qty
                        - dp_snap.scheduled_receipts_qty
                    ))                                               AS net_req_total
                FROM (
                    SELECT facility_id, product_key,
                           SUM(total_component_requirement) AS gross_demand
                    FROM vw_component_requirement_lp
                    WHERE forecast_run_id = %s
                    GROUP BY facility_id, product_key
                ) lp_agg
                JOIN dim_product dp ON dp.product_key = lp_agg.product_key
                JOIN (
                    SELECT facility_id, product_key,
                           on_hand_qty, scheduled_receipts_qty, backorder_qty
                    FROM fact_component_inventory_history
                    WHERE week_date = (
                        SELECT MAX(week_date) FROM fact_component_inventory_history
                    )
                ) dp_snap
                    ON  dp_snap.facility_id = lp_agg.facility_id
                    AND dp_snap.product_key  = lp_agg.product_key
                JOIN fact_inventory_policy pol
                    ON  pol.forecast_run_id = %s
                    AND pol.facility_id     = lp_agg.facility_id
                    AND pol.product_key     = lp_agg.product_key
                GROUP BY dp.product
                ORDER BY net_req_total DESC, gross_demand_total DESC
                """,
                (run_id, run_id),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return {
        "run_id":        run_id,
        "horizon_start": str(horizon_start),
        "horizon_end":   str(horizon_end),
        "n_weeks":       int(n_weeks),
        "rows": [
            {
                "Component":                   r[0],
                "Starting On-Hand":            float(r[1]),
                "Scheduled Receipts (+)":      float(r[2]),
                "Backorders (\u2212)":         float(r[3]),
                "Safety Stock Reserve (\u2212)": float(r[4]),
                "Gross Component Demand":      float(r[5]),
                "Net Procurement Requirement": float(r[6]),
            }
            for r in rows
        ],
        "name": "procurement_summary",
    }


def query_bom_translation_explainer(**kwargs) -> dict:
    """Horizon-level BOM explosion summary: SKU × component × forecast totals.

    Returns structured rows suitable for DataFrame rendering. Shows how each
    finished-good SKU's forecasted demand, multiplied by BOM units_per_sku,
    produces the gross component requirement — aggregated across all facilities
    and all forecast weeks. No inventory offset applied.
    """
    forecast_run_id = kwargs.get("forecast_run_id", None)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Resolve latest run
            if forecast_run_id:
                run_id = int(forecast_run_id)
            else:
                cur.execute(
                    "SELECT forecast_run_id FROM dim_forecast_run "
                    "ORDER BY forecast_run_id DESC LIMIT 1"
                )
                row = cur.fetchone()
                run_id = int(row[0]) if row else 0

            cur.execute(
                """
                SELECT
                    v.semiconductor_id                        AS sku,
                    p.product                                 AS component,
                    b.units_per_sku                           AS units_per_sku,
                    SUM(v.predicted_demand)                   AS total_forecast,
                    SUM(v.gross_component_requirement)        AS gross_component_demand,
                    COUNT(DISTINCT v.facility_id)             AS n_facilities
                FROM vw_component_requirement_detail v
                JOIN dim_product p ON p.product_key = v.product_key
                JOIN dim_bom b
                    ON  b.semiconductor_id = v.semiconductor_id
                    AND b.product_key      = v.product_key
                WHERE v.forecast_run_id = %s
                GROUP BY v.semiconductor_id, p.product, b.units_per_sku
                ORDER BY v.semiconductor_id, SUM(v.gross_component_requirement) DESC
                """,
                (run_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "rows": [
            {
                "Finished SKU":           r[0],
                "Component":              r[1],
                "Units / SKU":            float(r[2]),
                "Forecast (units)":       float(r[3]),
                "Gross Component Demand": float(r[4]),
                "Facilities":             int(r[5]),
            }
            for r in rows
        ],
        "name": "bom_translation_explainer",
    }


# ── Tool registry ───────────────────────────────────────────────────────────

DIRECT_PIPELINE_TOOLS = {
    # Forecast
    "query_forecast_summary": query_forecast_summary,
    "query_forecast_drilldown": query_forecast_drilldown,
    "query_forecast_model_assessment": query_forecast_model_assessment,
    # BOM / Component requirements
    "query_component_requirements": query_component_requirements,
    "query_bom_translation": query_bom_translation,
    # Inventory / Procurement
    "query_procurement_status": query_procurement_status,
    "query_procurement_planning_summary": query_procurement_planning_summary,
    "query_aggregated_procurement_need": query_aggregated_procurement_need,
    "query_procurement_drilldown": query_procurement_drilldown,
    "query_triggered_procurement_rows": query_triggered_procurement_rows,
}
