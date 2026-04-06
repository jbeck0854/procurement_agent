import asyncio
import base64
import logging
import os
import uuid

import nest_asyncio
import streamlit as st

from langgraph.types import Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)

nest_asyncio.apply()

from graph.builder import build_graph

# Keys that belong to other agents (not pipeline results).
# Used to filter agent_results → pipeline-only items by exclusion.
_NON_PIPELINE_KEYS = frozenset({
    "data_agent", "risk_agent", "pipeline_agent", "pipeline_errors",
    "lp_agent", "lp_agent_errors", "chart_agent",
})

# User inputs that trigger a session-level summary (bypass graph entirely).
_SUMMARY_TRIGGERS = frozenset({
    "final summary", "session summary", "summarize session",
    "summarize all", "full summary", "what did we decide",
})

# ── Opening kickoff detection ──────────────────────────────────────────────────
# Substring signals (lowercase). All four groups must match for kickoff to fire.
_KICKOFF_DEMAND  = ("demand", "planning horizon", "planning", "horizon", "weeks")
_KICKOFF_SUBJECT = ("semiconductor", "semionductor", "procurement", "component")
_KICKOFF_COST    = ("cost", "minim", "efficien", "budget")
_KICKOFF_RISK    = ("risk", "disruption", "reliab", "supplier")

# Responses that confirm the demand data and advance to the pipeline.
_PROCEED_TRIGGERS = frozenset({
    "yes", "yes, proceed", "looks correct", "proceed", "continue", "confirmed", "correct",
})

# Deterministic transition sentence shown immediately after kickoff confirmation.
# Appears before the forecast result so the user sees instant acknowledgement.
_KICKOFF_TRANSITION_SENTENCE = (
    "I will now generate forecasts over the upcoming planning horizon "
    "(20-week period), based on your historical demand data."
)

# ── Fast forecast-layer direct paths ──────────────────────────────────────────
# Context guard — at least one of these must appear for forecast routes to fire.
_FORECAST_CONTEXT = ("forecast", "model", "predict", "planning window", "forecastin")

# Model assessment direction signals (mirrors keywords in forecast_summary.py).
_FORECAST_BASELINE_SIGNALS = (
    "baseline", "benchmark", "compar", "naive", "better than", "versus",
    " vs ", "stack up", "improve",
)
_FORECAST_FEATURES_SIGNALS = (
    "feature", "features", "drove", "importance", "influential", "driver",
    "drivers", "what drives", "signal", "signals", "inputs",
)
_FORECAST_VALIDATE_SIGNALS = (
    "reliable", "how was", "trained", "validated", "validation", "training",
    "performance", "accuracy", "holdout", "trust", "can we trust",
)

# Drill-down signals — detail by facility / SKU / week.
_FORECAST_DRILLDOWN_SIGNALS = (
    "drill", "detail", "by facility", "by sku", "which sku",
    "per facility", "per sku", "breakdown", "where is demand",
    "concentration", "week by week", "week-by-week",
)

# Case B — specific facility chart (e.g. "Show forecast for Facility 2").
_FORECAST_FACILITY_SIGNALS = (
    "facility 1", "facility 2", "facility 3", "facility 4",
    "facility_1", "facility_2", "facility_3", "facility_4",
    "facility1", "facility2", "facility3", "facility4",
    "for facility", "for fac",
)

# Case C — all-facilities comparison chart.
_FORECAST_ALL_FACILITIES_SIGNALS = (
    "all facilit", "four facilit", "each facilit",
    "compare facilit", "across facilit", "facility-level",
    "facility level", "each of the four",
)

# Component requirements route — gross BOM demand before inventory netting.
# Specific enough that no context guard is needed.
_COMPONENT_REQ_SIGNALS = (
    "component requirement", "component demand",
    "gross component", "total component",
    "bom demand", "gross bom",
)
# Combined-match signals: "component(s)" + one of these fires the same route.
_COMPONENT_REQ_HORIZON_SIGNALS = (
    "planning window", "planning horizon", "demand window", "upcoming horizon",
)

# Inventory / procurement summary route — horizon-level net procurement requirement.
# Canonical queries: "Do we need to buy anything?" and inventory-adjusted variants.
# Checked AFTER BOM/component-requirements (those signals are more specific).
_PROC_SUMMARY_SIGNALS = (
    "do we need to buy",
    "need to order",
    "needs to be ordered",
    "inventory is factored",
    "inventory is accounted",
    "still need to buy",
    "inventory-adjusted procurement",
    "net procurement requirement",
    "what do we need to order",
    "what do we need to procure",
    "how much of each component",
    "what components do we need to buy",
)
# Combined guard: "inventory" + buy/order/procure intent fires the same route.
_PROC_SUMMARY_BUY_SIGNALS = ("order", "buy", "procure", "purchase")

# BOM translation explainability route — "how does/is SKU demand translated into component demand?"
# Canonical anchor phrase: "How exactly is forecasted SKU demand translated into component demand?"
# Direct signals must NOT overlap with _COMPONENT_REQ_SIGNALS; checked first in the elif chain.
_BOM_TRANSLATION_SIGNALS = (
    "translated into component",   # canonical anchor phrase (new primary)
    "translate into component",
    "translates into component",
    "bom convert",
    "bom translation",
    "demand becomes component",
    "sku demand translate",
    "explain how finished",
    "finished-goods demand becomes",
    "finished goods demand becomes",
)
# Combined guard: "bom" + any explanation-intent word fires the same route.
_BOM_TRANSLATION_EXPLAIN_SIGNALS = (
    "explain", "how does", "how is", "how do", "convert", "converts",
)

# Weekly trigger signal route — weekly-grain procurement trigger rows.
# Canonical query: "In which weeks and where is procurement actually triggered
# across the planning horizon?"
# Checked AFTER procurement summary (more specific drill-down).
_WEEKLY_TRIGGER_SIGNALS = (
    "triggered across the planning",
    "when is procurement triggered",
    "where and when do we actually need to buy",
    "weekly procurement trigger",
    "weekly trigger signal",
    "triggered procurement rows",
    "triggered rows",
    "which weeks and facilities trigger",
    "which weeks is procurement",
    "in which weeks",
)
# Combined guard: "triggered" + procurement/week/facility context fires the same route.
_WEEKLY_TRIGGER_CONTEXT_SIGNALS = ("procurement", "weeks", "facilities", "orders")


def _is_weekly_trigger_request(text: str) -> bool:
    """True for weekly-grain procurement trigger drill-down queries."""
    t = text.lower()
    if any(s in t for s in _WEEKLY_TRIGGER_SIGNALS):
        return True
    if "triggered" in t and any(s in t for s in _WEEKLY_TRIGGER_CONTEXT_SIGNALS):
        return True
    return False


# Safety stock / inventory policy explainability route.
# Canonical queries: "How is safety stock calculated?", "Explain safety stock policy",
# "How does base stock policy work?"
# Pure text output — no DB query required.
_SS_POLICY_SIGNALS = (
    "how is safety stock calculated",
    "explain safety stock policy",
    "how does base stock policy work",
    "base stock policy",
    "base-stock policy",
    "safety stock formula",
    "how is safety stock computed",
    "safety stock calculation",
    "explain the inventory policy",
)
# Combined guard: "safety stock" + explanation-intent word fires the same route.
_SS_POLICY_EXPLAIN_SIGNALS = (
    "explain", "how is", "how does", "what is", "calculate", "computed", "formula",
)


def _is_ss_policy_request(text: str) -> bool:
    """True for safety stock / inventory policy explainability queries."""
    t = text.lower()
    if any(s in t for s in _SS_POLICY_SIGNALS):
        return True
    if "safety stock" in t and any(s in t for s in _SS_POLICY_EXPLAIN_SIGNALS):
        return True
    return False


# Full inventory planning horizon drilldown route — diagnostic / traceability only.
# Returns ALL horizon rows (triggered + non-triggered) at facility × component × week.
# Canonical queries: "Show full horizon inventory drilldown",
#                    "Show all upcoming demand weeks across each facility for inventory planning"
# Must NOT overlap with: _is_procurement_summary_request (horizon-level net totals)
#                        _is_weekly_trigger_request (triggered rows only)
_FULL_HORIZON_SIGNALS = (
    "full horizon inventory",
    "full inventory planning",
    "full facility-component-week",
    "all upcoming demand weeks",
    "all planning rows for inventory",
    "full horizon drilldown",
    "all demand weeks across",
    "planning horizon drilldown",
    "full planning detail",
    "full horizon planning",
)
# Combined guard: "full" + "inventory" + drill-down-intent fires the same route.
_FULL_HORIZON_CONTEXT_SIGNALS = ("drilldown", "drill-down", "detail", "all weeks", "all rows")


def _is_full_horizon_drilldown_request(text: str) -> bool:
    """True for full-horizon inventory planning diagnostic / traceability queries."""
    t = text.lower()
    if any(s in t for s in _FULL_HORIZON_SIGNALS):
        return True
    if "full" in t and "inventory" in t and any(s in t for s in _FULL_HORIZON_CONTEXT_SIGNALS):
        return True
    return False


# Transition sentences and section headings for each assessment direction.
_FORECAST_ASSESS_META = {
    "validation": (
        "Yes — I can explain how the forecast model was trained and validated. "
        "Here is the model assessment summary.",
        "📐 Forecast Model — Validation & Training Performance",
    ),
    "features": (
        "Here is a breakdown of which features drove the forecast model most, "
        "based on permutation importance measured on the held-out validation set.",
        "📐 Forecast Model — Feature Importance",
    ),
    "baseline": (
        "Here is how the production forecast compares with the baseline approaches "
        "used for validation.",
        "📐 Forecast Model — Baseline Comparison",
    ),
}

# Project root — one level up from demo/. Used to resolve artifact PNG paths.
_ARTIFACTS_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# Path to the historical demand CSV (relative to this file).
_CSV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "cleaned_data", "finished_goods_demand_table.csv")
)

# Fixed opening response — no variability.
_KICKOFF_OPENING_RESPONSE = """\
Understood. We will:

1. Verify your historical demand across all four facilities and semiconductor SKUs
2. Translate that demand into the exact component requirements needed to support production
3. Assess inventory coverage and identify where procurement is required
4. Optimize supplier allocation to minimize cost while controlling supplier risk and disruption

Your objective balances cost efficiency with supply reliability:
- **Lower emphasis** prioritizes cost minimization
- **Higher emphasis** prioritizes more stable, lower-risk suppliers even if slightly more expensive

Let's begin by validating the historical demand that drives this entire workflow.

Please review the historical demand file below and confirm it looks correct. Once reviewed, \
reply with **'Yes, proceed'** to continue.\
"""

st.set_page_config(page_title="Procurement Agent", layout="wide")
st.title("Procurement Supply Chain Agent")


@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

# ── Core session state ─────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "traces" not in st.session_state:
    st.session_state.traces = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "waiting_for_approval" not in st.session_state:
    st.session_state.waiting_for_approval = False
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "plan_feedback" not in st.session_state:
    st.session_state.plan_feedback = ""

# ── Fast-path visual persistence ──────────────────────────────────────────────
# DataFrames for Case-A drilldown. Stored by index so replay loop can re-render
# them after st.rerun(). Charts are stored as base64 PNG in the message dict.
if "fast_path_dfs" not in st.session_state:
    st.session_state.fast_path_dfs = []

# ── LP approval session state ──────────────────────────────────────────────────
if "waiting_for_lp_approval" not in st.session_state:
    st.session_state.waiting_for_lp_approval = False
if "pending_lp_result" not in st.session_state:
    st.session_state.pending_lp_result = None
if "lp_partial_state" not in st.session_state:
    st.session_state.lp_partial_state = {}
if "saved_plan" not in st.session_state:
    st.session_state.saved_plan = {}

# ── Session-level approved LP runs ─────────────────────────────────────────────
if "approved_lp_runs" not in st.session_state:
    st.session_state.approved_lp_runs = []

# ── Opening kickoff state ──────────────────────────────────────────────────────
if "historical_demand_verification_pending" not in st.session_state:
    st.session_state.historical_demand_verification_pending = False


# ── Session-level helpers ──────────────────────────────────────────────────────

def _store_approved_run(result: dict) -> None:
    """Append one approved LP result dict to the session-level store."""
    entry = {
        "product":           (result.get("params_recap") or {}).get("product", "unknown"),
        "allocated_qty":     (result.get("constraint_diagnostics") or {}).get("total_allocated", 0),
        "total_cost":        (result.get("cost_summary") or {}).get("total_cost_usd", 0.0),
        "n_suppliers":       (result.get("supplier_pool") or {}).get("n_selected_by_lp", 0),
        "executive_summary": result.get("executive_summary", ""),
        "allocation":        result.get("allocation", []),
    }
    st.session_state.approved_lp_runs.append(entry)


def _format_session_summary(approved_runs: list) -> str:
    """Format a session-level procurement summary from all approved LP runs."""
    if not approved_runs:
        return (
            "No approved LP runs in this session yet. "
            "Complete and approve at least one LP optimization to generate a session summary."
        )
    lines = ["**Session Procurement Plan — Approved Runs**\n"]
    total_spend = 0.0
    for run in approved_runs:
        product = (run.get("product") or "unknown").replace("_", " ").title()
        qty     = run.get("allocated_qty") or 0
        cost    = run.get("total_cost") or 0.0
        n_sup   = run.get("n_suppliers") or 0
        exec_s  = (run.get("executive_summary") or "").strip()
        total_spend += cost
        lines.append(f"- **{product}**: {qty:,} units · {n_sup} supplier(s) · ${cost:,.2f}")
        if exec_s:
            lines.append(f"  ↳ {exec_s}")
    lines.append(f"\n**Total Committed Spend: ${total_spend:,.2f}**")
    lines.append("\n*Review approved recommendations, confirm lead times, and place orders.*")
    return "\n".join(lines)


def _merge_final_states(first: dict, second: dict) -> dict:
    """Merge two partial graph stream states into one for finalize_execution.

    `first`  — state collected before the LP interrupt (pipeline, charts).
    `second` — state collected after approve/discard resume (LP result, synthesizer).
    """
    merged = dict(first)
    for key in ("agent_results", "chart_results", "timings", "pipeline_results", "lp_results"):
        merged[key] = {
            **(first.get(key) or {}),
            **(second.get(key) or {}),
        }
    for key in ("final_response", "intent", "tasks"):
        if second.get(key):
            merged[key] = second[key]
    merged.pop("__interrupt__", None)
    return merged


# ── Opening kickoff helpers ────────────────────────────────────────────────────

def _is_first_user_turn() -> bool:
    """True when no assistant message has been rendered yet in this session."""
    return not any(m.get("role") == "assistant" for m in st.session_state.messages)


def _is_opening_kickoff(text: str) -> bool:
    """True when first user message signals a broad planning + cost + risk objective.

    Uses substring matching so minor misspellings (e.g. 'semionductor', 'plannning')
    are handled without NLP. All four signal groups must be present.
    """
    t = text.lower()
    return (
        any(s in t for s in _KICKOFF_DEMAND)
        and any(s in t for s in _KICKOFF_SUBJECT)
        and any(s in t for s in _KICKOFF_COST)
        and any(s in t for s in _KICKOFF_RISK)
    )


def _is_proceed_response(text: str) -> bool:
    """True when user confirms the demand data and wants to advance."""
    t = text.lower().strip()
    return any(trigger in t for trigger in _PROCEED_TRIGGERS)


def _forecast_assessment_direction(text: str) -> str | None:
    """Return the assessment direction ('validation', 'features', 'baseline') or None.

    Requires at least one _FORECAST_CONTEXT signal. Among the three directions,
    baseline is checked first (most specific phrase), then features, then validation.
    Returns None if no forecast-context + direction signal is found.
    """
    t = text.lower()
    if not any(s in t for s in _FORECAST_CONTEXT):
        return None
    if any(s in t for s in _FORECAST_BASELINE_SIGNALS):
        return "baseline"
    if any(s in t for s in _FORECAST_FEATURES_SIGNALS):
        return "features"
    if any(s in t for s in _FORECAST_VALIDATE_SIGNALS):
        return "validation"
    return None


def _is_forecast_drilldown_request(text: str) -> bool:
    """True when the user asks for forecast detail by facility/SKU/week."""
    t = text.lower()
    return (
        any(s in t for s in _FORECAST_CONTEXT)
        and any(s in t for s in _FORECAST_DRILLDOWN_SIGNALS)
    )


def _is_all_facilities_forecast(text: str) -> bool:
    """True when the user asks for a cross-facility forecast comparison.

    Checked BEFORE _forecast_assessment_direction so that queries containing
    'compare' (e.g. 'Compare forecast demand across all facilities') are not
    misrouted to the model-baseline assessment route, which also matches 'compar'.
    Requires at least one _FORECAST_CONTEXT signal plus one all-facilities signal.
    """
    t = text.lower()
    return (
        any(s in t for s in _FORECAST_CONTEXT)
        and any(s in t for s in _FORECAST_ALL_FACILITIES_SIGNALS)
    )


def _is_component_requirements_request(text: str) -> bool:
    """True when the user asks for full-horizon gross component demand (pre-inventory).

    Fires on direct signals (e.g. 'component requirement', 'gross bom') or on the
    combined pattern: 'component(s)' + a horizon/window context term.
    Does NOT touch procurement-status or LP routes.
    """
    t = text.lower()
    if any(s in t for s in _COMPONENT_REQ_SIGNALS):
        return True
    # Combined: 'component' + planning horizon / window context
    if "component" in t and any(s in t for s in _COMPONENT_REQ_HORIZON_SIGNALS):
        return True
    return False


def _is_bom_translation_request(text: str) -> bool:
    """True when the user asks how finished-good SKU demand converts to component demand.

    Fires on direct phrasing (e.g. 'translated into component', 'bom translation')
    or on the combined pattern: 'bom' + an explanation-intent word.
    Must be checked BEFORE _is_component_requirements_request() in the elif chain
    so that queries containing 'component demand' in a translation context route here
    and not to the component totals summary.
    """
    t = text.lower()
    if any(s in t for s in _BOM_TRANSLATION_SIGNALS):
        return True
    # Combined: BOM mentioned + explanation intent (excludes pure demand-total queries)
    if "bom" in t and any(s in t for s in _BOM_TRANSLATION_EXPLAIN_SIGNALS):
        return True
    return False


def _is_procurement_summary_request(text: str) -> bool:
    """True for horizon-level inventory-adjusted procurement need queries.

    Catches 'Do we need to buy anything?', 'What is our net procurement
    requirement?', and similar. Fires AFTER BOM/component-requirements routes
    so those more specific signals are not shadowed.
    """
    t = text.lower()
    if any(s in t for s in _PROC_SUMMARY_SIGNALS):
        return True
    # "procurement" + requirement/need intent
    if "procurement" in t and any(s in t for s in ("requirement", "need", "needed")):
        return True
    # "inventory" + buy/order/procure intent
    if "inventory" in t and any(s in t for s in _PROC_SUMMARY_BUY_SIGNALS):
        return True
    return False


def _extract_facility_id(text: str) -> str | None:
    """Extract FACILITY_N from free text (e.g. 'Facility 2' → 'FACILITY_2')."""
    import re
    m = re.search(r'facilit(?:y|_)?[\s_]?(\d)', text.lower())
    return f"FACILITY_{m.group(1)}" if m else None


def _format_facility_label(facility_id: str) -> str:
    """Convert DB-format 'FACILITY_1' to business-facing 'Facility 1'."""
    import re
    m = re.match(r'FACILITY_(\d+)', facility_id, re.IGNORECASE)
    return f"Facility {m.group(1)}" if m else facility_id


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


def _render_csv_button() -> None:
    """Compact summary line + download button for historical demand CSV.

    Shows dataset shape and key dimensions without rendering the full table inline.
    """
    try:
        import pandas as pd
        df = pd.read_csv(_CSV_PATH)
        n_rows, n_cols = df.shape
        facilities = df["facility_id"].nunique() if "facility_id" in df.columns else "?"
        skus       = df["semiconductor_id"].nunique() if "semiconductor_id" in df.columns else "?"
        weeks      = df["week"].nunique() if "week" in df.columns else "?"
        st.caption(
            f"Historical demand file: **{n_rows:,} rows** · **{n_cols} columns** · "
            f"**{facilities} facilities** · **{skus} SKUs** · **{weeks} weeks**"
        )
        st.download_button(
            label="📥 Download Historical Demand CSV",
            data=df.to_csv(index=False).encode(),
            file_name="finished_goods_demand_table.csv",
            mime="text/csv",
            key="kickoff_csv_download",
        )
    except Exception:
        st.caption("Historical demand file: `cleaned_data/finished_goods_demand_table.csv`")


def _render_kickoff_response() -> None:
    """Render the deterministic opening assistant message and CSV button (first turn only)."""
    with st.chat_message("assistant"):
        st.markdown(_KICKOFF_OPENING_RESPONSE)
        _render_csv_button()
    st.session_state.messages.append({
        "role": "assistant",
        "content": _KICKOFF_OPENING_RESPONSE,
        "has_trace": False,
        "summary": "",
    })


def _render_demand_verification_banner() -> None:
    """Persistent info banner + CSV button shown on every rerender while verification is pending."""
    st.info(
        "Waiting for your confirmation on the historical demand data. "
        "Reply **'Yes, proceed'** when ready to begin the analysis pipeline.",
        icon="📋",
    )
    _render_csv_button()
    st.divider()


def _fig_to_b64(fig) -> str:
    """Serialize a matplotlib Figure to base64-encoded PNG string.

    Used by fast-path drill-down handlers to persist charts across st.rerun().
    The b64 string is stored in the message dict under 'chart_b64' and decoded
    by the replay loop with st.image(base64.b64decode(msg['chart_b64'])).
    """
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _plot_facility_faceted(df, facility_id: str):
    """6×2 faceted figure — one subplot per semiconductor SKU for a single facility.

    Each panel shows the 20-week predicted demand line with a lightly shaded 90% CI.
    SKUs are sorted alphabetically so the layout is deterministic across facilities.
    """
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import pandas as pd

    fac_df = df[df["facility_id"] == facility_id].copy()
    # Coerce numeric columns — psycopg2 returns Decimal, pandas stores as object.
    for col in ("predicted_demand", "interval_lower_90", "interval_upper_90"):
        fac_df[col] = pd.to_numeric(fac_df[col], errors="coerce").fillna(0.0)
    fac_df["target_week_date"] = fac_df["target_week_date"].astype(str)
    skus = sorted(fac_df["semiconductor_id"].unique())
    n_skus = len(skus)
    ncols = 2
    nrows = (n_skus + 1) // 2  # ceil division — handles odd counts cleanly
    palette = [cm.tab10(i / 10) for i in range(min(n_skus, 10))]

    fig, axes = plt.subplots(nrows, ncols, figsize=(12, nrows * 3), sharey=False)
    axes = axes.flatten()

    for i, sku in enumerate(skus):
        ax = axes[i]
        s = fac_df[fac_df["semiconductor_id"] == sku].sort_values("target_week_date")
        color = palette[i % len(palette)]
        ax.plot(s["target_week_date"], s["predicted_demand"],
                color=color, linewidth=1.8)
        ax.fill_between(
            s["target_week_date"],
            s["interval_lower_90"], s["interval_upper_90"],
            alpha=0.12, color=color,
        )
        ax.set_title(sku, fontsize=9, pad=4)
        ax.tick_params(axis="x", rotation=45, labelsize=6)
        ax.tick_params(axis="y", labelsize=7)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

    # Hide any unused subplot panels (if SKU count is odd)
    for j in range(n_skus, len(axes)):
        axes[j].set_visible(False)

    label = _format_facility_label(facility_id)
    fig.suptitle(
        f"Production Demand Forecast — {label} by SKU",
        fontsize=12, y=1.005,
    )
    fig.tight_layout()
    return fig


def _narrative_facility_bullets(df, facility_id: str) -> str:
    """Markdown bullet summary for a single-facility faceted forecast view.

    Covers: total/avg demand, peak + lowest week, SKU concentration, and a
    cross-SKU comparative insight (highest-volume SKUs + most/least volatile).
    Returned string is passed directly to st.markdown().
    """
    import pandas as pd
    fac_df = df[df["facility_id"] == facility_id].copy()
    # Coerce to numeric — psycopg2 returns Decimal, which groupby().sum() keeps as
    # object dtype, causing nlargest() / arithmetic to fail.
    fac_df["predicted_demand"] = pd.to_numeric(fac_df["predicted_demand"], errors="coerce").fillna(0.0)
    weekly = fac_df.groupby("target_week_date")["predicted_demand"].sum()
    total     = weekly.sum()
    avg       = weekly.mean()
    n_weeks   = weekly.nunique()
    peak_week = str(weekly.idxmax())
    peak_val  = weekly.max()
    low_week  = str(weekly.idxmin())
    low_val   = weekly.min()

    by_sku = fac_df.groupby("semiconductor_id")["predicted_demand"].sum()
    top_sku   = by_sku.idxmax()
    top_share = by_sku.max() / by_sku.sum() * 100
    n_skus    = by_sku.nunique()

    if top_share > 40:
        concentration = (
            f"Demand is concentrated — **{top_sku}** accounts for "
            f"**{top_share:.0f}%** of facility volume"
        )
    else:
        concentration = (
            f"Demand is broadly distributed across {n_skus} SKUs "
            f"(top SKU: **{top_sku}** at **{top_share:.0f}%**)"
        )

    # Top 3 by total volume and SKU-level coefficient of variation (volatility proxy)
    top3 = by_sku.nlargest(3).index.tolist()
    top3_str = ", ".join(f"**{s}**" for s in top3)
    sku_cv = (
        fac_df.groupby("semiconductor_id")["predicted_demand"]
        .apply(lambda x: x.std() / x.mean() if x.mean() > 0 else 0.0)
    )
    most_volatile  = sku_cv.idxmax()
    least_volatile = sku_cv.idxmin()
    cross_sku = (
        f"{top3_str} lead in total volume; "
        f"**{most_volatile}** shows the highest week-to-week variability "
        f"while **{least_volatile}** is the most stable"
    )

    return "\n".join([
        f"- **Total horizon demand:** {total:,.0f} units across {n_weeks} weeks",
        f"- **Average weekly demand:** {avg:,.0f} units/week",
        f"- **Peak week:** {peak_week} → {peak_val:,.0f} units",
        f"- **Lowest week:** {low_week} → {low_val:,.0f} units",
        f"- **SKU concentration:** {concentration}",
        f"- **Cross-SKU insight:** {cross_sku}",
    ])


def show_trace(trace):
    with st.expander("Execution Trace"):
        # --- Timing breakdown ---
        timings = trace.get("timings") or {}
        if timings:
            st.subheader("Performance")
            top_level = ["orchestrator", "data_agent", "risk_agent", "pipeline_agent", "chart_agent", "lp_agent", "synthesizer"]
            active = [name for name in top_level if timings.get(name) is not None]
            if active:
                cols = st.columns(len(active))
                for col, name in zip(cols, active):
                    col.metric(name, f"{timings[name]:.2f}s")
            total = sum(timings.get(k, 0) for k in top_level)
            st.caption(f"Total pipeline time: **{total:.2f}s**")

            sub_steps = {k: v for k, v in timings.items() if "." in k}
            if sub_steps:
                detail_lines = [f"- {k}: {v:.3f}s" for k, v in sub_steps.items()]
                st.markdown("**Step breakdown:**\n" + "\n".join(detail_lines))
            st.divider()

        st.subheader("Orchestrator")
        st.write(f"**Intent:** {trace['intent']}")
        for i, task in enumerate(trace["tasks"]):
            st.write(f"**Task {i+1}**")
            st.write(f"- Agent: {task['agent']}")
            st.write(f"- Objective: {task['objective']}")
            st.write(f"- Context: {task['context']}")
            st.write(f"- Instructions: {task['instructions']}")

        st.subheader("Router")
        if trace["tasks"]:
            routed_agents = list({task["agent"] for task in trace["tasks"]})
            st.write(f"Routed to: **{', '.join(routed_agents)}**")

        pipeline_results = {k: v for k, v in trace["agent_results"].items()
                           if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")}
        if pipeline_results:
            st.subheader("Pipeline Agent")
            for key, content in pipeline_results.items():
                st.caption(key.replace("_", " ").title())
                st.code(content)

        for agent_name, label in [("data_agent", "Data Agent"), ("risk_agent", "Risk Agent")]:
            raw = trace["agent_results"].get(agent_name)
            if raw:
                st.subheader(label)
                display = raw[:500] + "..." if len(raw) > 500 else raw
                st.code(display)

        lp_results = {k: v for k, v in trace["agent_results"].items() if k.startswith("lp_")}
        if lp_results:
            st.subheader("LP Optimization Agent")
            for key, content in lp_results.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                st.caption(f"Product: {product}")
                st.code(content)

        chart_results = trace.get("chart_results") or {}
        if chart_results:
            st.subheader("Chart Agent")
            for chart_name, b64_img in chart_results.items():
                st.caption(chart_name)
                st.image(base64.b64decode(b64_img))

        st.subheader("Synthesizer")
        st.write("Final response generated")


# ── Message history replay ─────────────────────────────────────────────────────

assistant_index = 0
for _msg_loop_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        # ── Fast-path chart replay (Case B / Case C drilldown) ────────────
        # Assessment routes set chart_first=True so the plot renders before
        # the text summary (transition + result_text are stored together in
        # content, so the only way to get image-first is to render the chart
        # before calling st.markdown on content).
        _b64 = msg.get("chart_b64", "")
        if _b64 and msg.get("chart_first"):
            st.image(base64.b64decode(_b64))
        if msg.get("content"):
            st.markdown(msg["content"])
        if _b64 and not msg.get("chart_first"):
            if msg.get("chart_scroll"):
                # Case B: render inside a scrollable HTML div so the chart
                # area scrolls independently and the summary stays fixed above.
                st.markdown(
                    f'<div style="height:640px;overflow-y:auto;'
                    f'border:1px solid #e6e9ef;border-radius:6px;padding:4px;">'
                    f'<img src="data:image/png;base64,{_b64}"'
                    f' style="width:100%;display:block;" /></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.image(base64.b64decode(_b64))
        # ── Fast-path dataframe replay (Case A drilldown) ─────────────────
        df_idx = msg.get("df_index")
        if df_idx is not None and df_idx < len(st.session_state.fast_path_dfs):
            _replay_df = st.session_state.fast_path_dfs[df_idx]
            st.dataframe(
                _replay_df.style.format({
                    "Forecast":   "{:,.0f}",
                    "Lower 90%":  "{:,.0f}",
                    "Upper 90%":  "{:,.0f}",
                }),
                use_container_width=True,
            )
        # ── Fast-path component-requirements replay ────────────────────────
        _comp_req_dfs = msg.get("comp_req_dfs")
        if _comp_req_dfs:
            import pandas as _pd
            for _spec in _comp_req_dfs:
                st.caption(_spec["caption"])
                _cdf = _pd.DataFrame(_spec["records"])
                if "Units Required" in _cdf.columns:
                    st.dataframe(
                        _cdf.style.format({"Units Required": "{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.dataframe(_cdf, use_container_width=True, hide_index=True)
        # ── Fast-path BOM translation replay ──────────────────────────────
        _bom_xlate = msg.get("bom_xlate_df")
        if _bom_xlate:
            import pandas as _pd
            _bdf = _pd.DataFrame(_bom_xlate)
            st.dataframe(
                _bdf.style.format({
                    "Units / SKU":            "{:,.2f}",
                    "Forecast (units)":       "{:,.0f}",
                    "Gross Component Demand": "{:,.0f}",
                }),
                height=420,
                use_container_width=True,
                hide_index=True,
            )
        # ── Fast-path procurement summary replay ──────────────────────────
        _proc_rows = msg.get("proc_summary_df")
        if _proc_rows:
            import pandas as _pd
            _proc_df = _pd.DataFrame(_proc_rows)
            _proc_fmt = {
                c: "{:,.0f}" for c in _proc_df.columns if c != "Component"
            }
            st.dataframe(
                _proc_df.style.format(_proc_fmt),
                use_container_width=True,
                hide_index=True,
            )
        # ── Fast-path weekly trigger replay ───────────────────────────────
        _trig_rows = msg.get("weekly_trigger_df")
        if _trig_rows:
            import pandas as _pd
            _trig_df = _pd.DataFrame(_trig_rows)
            # Filters — applied in-memory on the stored unfiltered rows
            _fac_opts  = sorted(_trig_df["Facility"].unique().tolist())  if "Facility"  in _trig_df.columns else []
            _comp_opts = sorted(_trig_df["Component"].unique().tolist()) if "Component" in _trig_df.columns else []
            _col_f, _col_c = st.columns(2)
            with _col_f:
                _sel_fac = st.multiselect(
                    "Filter by Facility",
                    options=_fac_opts,
                    default=_fac_opts,
                    key=f"trig_fac_{_msg_loop_idx}",
                )
            with _col_c:
                _sel_comp = st.multiselect(
                    "Filter by Component",
                    options=_comp_opts,
                    default=_comp_opts,
                    key=f"trig_comp_{_msg_loop_idx}",
                )
            if _sel_fac:
                _trig_df = _trig_df[_trig_df["Facility"].isin(_sel_fac)]
            if _sel_comp:
                _trig_df = _trig_df[_trig_df["Component"].isin(_sel_comp)]
            # Safety Stock context block (above primary table)
            _ss_ctx = msg.get("ss_context", [])
            if _ss_ctx:
                _ss_ctx_df = _pd.DataFrame(_ss_ctx)
                # Apply facility filter to context block if active
                if _sel_fac and "Facility" in _ss_ctx_df.columns:
                    _ss_ctx_df = _ss_ctx_df[_ss_ctx_df["Facility"].isin(_sel_fac)]
                if _sel_comp and "Component" in _ss_ctx_df.columns:
                    _ss_ctx_df = _ss_ctx_df[_ss_ctx_df["Component"].isin(_sel_comp)]
                st.dataframe(
                    _ss_ctx_df.style.format({"Safety Stock (Protected Floor)": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "This value represents the inventory buffer required to maintain the "
                    "target service level. It is preserved in all inventory calculations "
                    "and not consumed by demand. The table below shows how procurement "
                    "pressure accumulates relative to this buffer."
                )
            _trig_fmt = {
                "Forecast Week":                  "{:,.0f}",
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Cumulative Procurement Pressure":"{:,.0f}",
                "Safety Stock Utilization (%)":   "{:.1f}%",
            }
            _trig_fmt = {c: v for c, v in _trig_fmt.items() if c in _trig_df.columns}
            st.caption(f"{len(_trig_df):,} rows shown")
            st.dataframe(
                _trig_df.style.format(_trig_fmt),
                use_container_width=True,
                hide_index=True,
                height=500,
            )
        # ── Full horizon drilldown replay (diagnostic) ────────────────────
        _fh_rows_replay = msg.get("full_horizon_df")
        if _fh_rows_replay:
            import pandas as _pd
            _fh_df = _pd.DataFrame(_fh_rows_replay)
            _fh_fac_opts  = sorted(_fh_df["Facility"].unique().tolist())  if "Facility"  in _fh_df.columns else []
            _fh_comp_opts = sorted(_fh_df["Component"].unique().tolist()) if "Component" in _fh_df.columns else []
            _fh_col_a, _fh_col_b = st.columns(2)
            with _fh_col_a:
                _fh_sel_fac = st.multiselect(
                    "Filter by Facility",
                    options=_fh_fac_opts,
                    default=_fh_fac_opts,
                    key=f"fh_fac_{_msg_loop_idx}",
                )
            with _fh_col_b:
                _fh_sel_comp = st.multiselect(
                    "Filter by Component",
                    options=_fh_comp_opts,
                    default=_fh_comp_opts,
                    key=f"fh_comp_{_msg_loop_idx}",
                )
            if _fh_sel_fac:
                _fh_df = _fh_df[_fh_df["Facility"].isin(_fh_sel_fac)]
            if _fh_sel_comp:
                _fh_df = _fh_df[_fh_df["Component"].isin(_fh_sel_comp)]
            _fh_fmt = {
                "Forecast Week":                  "{:,.0f}",
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Safety Stock (Protected Floor)": "{:,.0f}",
            }
            _fh_fmt = {c: v for c, v in _fh_fmt.items() if c in _fh_df.columns}
            st.caption(f"{len(_fh_df):,} rows shown")
            st.dataframe(
                _fh_df.style.format(_fh_fmt),
                use_container_width=True,
                hide_index=True,
                height=600,
            )
        # ── Trace-backed chart replay (graph execution path) ──────────────
        if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
            chart_results = st.session_state.traces[assistant_index].get("chart_results") or {}
            for chart_name, b64_img in chart_results.items():
                st.caption(chart_name.replace("_", " ").title())
                st.image(base64.b64decode(b64_img))
            if msg.get("summary"):
                st.markdown(msg["summary"])
    if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
        show_trace(st.session_state.traces[assistant_index])
        assistant_index += 1


# ── Graph execution helpers ────────────────────────────────────────────────────

def extract_plan(state):
    interrupts = []
    for task in state.tasks or []:
        interrupts.extend(task.interrupts or [])
    return interrupts[0].value if interrupts else None


def stream_graph(command, config):
    placeholder = st.empty()
    final_state = {"agent_results": {}}

    def _render_streaming(placeholder):
        with placeholder.container():
            pipeline_results = final_state.get("pipeline_results") or {}
            if pipeline_results:
                st.subheader("📊 Pipeline Results")
                for key, content in pipeline_results.items():
                    st.caption(key.replace("_", " ").title())
                    st.code(content)
            if final_state.get("latest_data_agent"):
                st.subheader("📊 Data Query")
                st.markdown(final_state["latest_data_agent"])
            if final_state.get("latest_risk_agent"):
                st.divider()
                st.subheader("🌐 Geopolitical Risk Analysis")
                st.markdown(final_state["latest_risk_agent"])
            lp_results = final_state.get("lp_results") or {}
            if lp_results:
                st.divider()
                st.subheader("⚙️ LP Optimization Results")
                for key, content in lp_results.items():
                    product = key.replace("lp_", "").replace("_", " ").title()
                    st.caption(f"Product: {product}")
                    st.code(content)
            charts = final_state.get("chart_results") or {}
            if charts:
                st.divider()
                st.subheader("📈 Visualizations")
                for chart_name, b64_img in charts.items():
                    st.caption(chart_name.replace("_", " ").title())
                    st.image(base64.b64decode(b64_img))
            if final_state.get("final_response"):
                st.divider()
                st.subheader("📋 Summary & Recommendations")
                st.markdown(final_state["final_response"])

    async def stream_results():
        async for event in graph.astream(command, config=config):
            for node_name, node_output in event.items():
                # ── LP approval interrupt detection ──────────────────────────
                # Must precede the isinstance(dict) check: node_output is a
                # tuple of Interrupt objects here, not a dict.
                if node_name == "__interrupt__":
                    interrupts = node_output
                    if interrupts:
                        intr = interrupts[0]
                        intr_val = intr.value if hasattr(intr, "value") else {}
                        if isinstance(intr_val, dict) and intr_val.get("type") == "lp_approval":
                            final_state["__interrupt__"] = intr_val
                    return final_state  # graph is paused — stop streaming

                # ── Normal event handling ────────────────────────────────────
                if not isinstance(node_output, dict):
                    continue
                if "intent" in node_output:
                    final_state["intent"] = node_output["intent"]
                if "tasks" in node_output:
                    final_state["tasks"] = node_output["tasks"]
                if "agent_results" in node_output:
                    final_state.setdefault("agent_results", {}).update(node_output["agent_results"] or {})
                if node_name == "pipeline_agent" and node_output.get("agent_results"):
                    pipeline_items = {k: v for k, v in node_output["agent_results"].items()
                                     if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")}
                    if pipeline_items:
                        final_state.setdefault("pipeline_results", {}).update(pipeline_items)
                if node_name == "data_agent" and node_output.get("agent_results"):
                    data_text = node_output["agent_results"].get("data_agent")
                    if data_text:
                        final_state["latest_data_agent"] = data_text
                if node_name == "risk_agent" and node_output.get("agent_results"):
                    risk_text = node_output["agent_results"].get("risk_agent")
                    if risk_text:
                        final_state["latest_risk_agent"] = risk_text
                if node_name == "lp_agent" and node_output.get("agent_results"):
                    lp_items = {k: v for k, v in node_output["agent_results"].items() if k.startswith("lp_")}
                    if lp_items:
                        final_state.setdefault("lp_results", {}).update(lp_items)
                if node_name == "chart_agent" and node_output.get("chart_results"):
                    final_state.setdefault("chart_results", {}).update(node_output["chart_results"])
                if node_name == "synthesizer" and "final_response" in node_output:
                    final_state["final_response"] = node_output["final_response"]
                    final_state["timings"] = node_output.get("timings", {})
                final_state[node_name] = node_output
        return final_state

    result = asyncio.run(stream_results())
    # Skip rendering if LP interrupt fired — render_lp_approval() handles display.
    if not result.get("__interrupt__"):
        _render_streaming(placeholder)
    return result


def finalize_execution(final_state, fallback_plan=None):
    plan = fallback_plan or {}
    trace = {
        "intent": final_state.get("intent") or plan.get("intent", ""),
        "tasks": final_state.get("tasks") or plan.get("tasks", []),
        "agent_results": final_state.get("agent_results", {}),
        "chart_results": final_state.get("chart_results") or {},
        "timings": final_state.get("timings") or plan.get("timings", {}),
    }
    st.session_state.traces.append(trace)

    parts = []
    pipeline_items = {k: v for k, v in trace["agent_results"].items()
                     if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")}
    if pipeline_items:
        pip_parts = []
        for key, content in pipeline_items.items():
            title = key.replace("_", " ").title()
            pip_parts.append(f"**{title}**\n\n```\n{content}\n```")
        parts.append("**📊 Pipeline Results**\n\n" + "\n\n".join(pip_parts))
    data_result = trace["agent_results"].get("data_agent", "")
    if data_result:
        parts.append(data_result)
    risk_result = trace["agent_results"].get("risk_agent", "")
    if risk_result:
        parts.append("---\n\n**🌐 Geopolitical Risk Analysis**\n\n" + risk_result)
    lp_items = {k: v for k, v in trace["agent_results"].items() if k.startswith("lp_")}
    if lp_items:
        lp_parts = []
        for key, content in lp_items.items():
            product = key.replace("lp_", "").replace("_", " ").title()
            lp_parts.append(f"**{product}**\n\n```\n{content}\n```")
        parts.append("---\n\n**⚙️ LP Optimization Results**\n\n" + "\n\n".join(lp_parts))
    final_response = final_state.get("final_response", "")
    summary_text = ""
    if final_response:
        summary_text = "---\n\n**📋 Summary & Recommendations**\n\n" + final_response
    combined = "\n\n".join(parts)

    with st.chat_message("assistant"):
        if combined:
            st.markdown(combined)
        for chart_name, b64_img in trace["chart_results"].items():
            st.caption(chart_name.replace("_", " ").title())
            st.image(base64.b64decode(b64_img))
        if summary_text:
            st.markdown(summary_text)

    st.session_state.messages.append({
        "role": "assistant",
        "content": combined,
        "summary": summary_text,
        "has_trace": True,
    })
    show_trace(trace)
    return combined


def render_pending_plan():
    plan = st.session_state.pending_plan or {}
    st.write("## Pending Plan")
    st.write(f"**Intent:** {plan.get('intent')}")
    if plan.get("question"):
        st.info(plan["question"])
    for i, task in enumerate(plan.get("tasks", [])):
        st.write(f"### Task {i+1}")
        st.write(f"- Agent: {task.get('agent')}")
        st.write(f"- Objective: {task.get('objective')}")
        st.write(f"- Context: {task.get('context')}")
        st.write(f"- Instructions: {task.get('instructions')}")
    st.text_input("Modify the plan (optional)", key="plan_feedback")
    if st.button("Approve Plan", key="approve_plan"):
        with st.spinner("Executing approved plan..."):
            feedback = st.session_state.plan_feedback.strip() or "ok"
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            final_state = stream_graph(Command(resume=feedback), config=config)
        # ── Check whether the LP agent raised an approval interrupt ────────
        lp_interrupt = final_state.get("__interrupt__")
        if lp_interrupt and lp_interrupt.get("type") == "lp_approval":
            st.session_state.waiting_for_lp_approval = True
            st.session_state.pending_lp_result = lp_interrupt
            st.session_state.lp_partial_state = final_state
            st.session_state.saved_plan = plan
            st.session_state.waiting_for_approval = False
            st.session_state.pending_plan = None
            st.rerun()
        else:
            state = asyncio.run(graph.aget_state(config=config))
            next_plan = extract_plan(state)
            if state.next and next_plan:
                st.session_state.pending_plan = next_plan
                st.session_state.messages.append(
                    {"role": "assistant", "content": "Plan updated. Review the new work orders below."}
                )
                st.rerun()
            else:
                finalize_execution(final_state, fallback_plan=plan)
                st.session_state.waiting_for_approval = False
                st.session_state.pending_plan = None
                st.rerun()


def render_lp_approval():
    """Show LP results and present an approve / discard decision to the user."""
    lp_interrupt = st.session_state.pending_lp_result or {}
    formatted    = lp_interrupt.get("formatted", {})
    raw          = lp_interrupt.get("raw", {})
    partial      = st.session_state.get("lp_partial_state") or {}

    # Re-display pipeline and chart results that arrived before the interrupt.
    pipeline_results = partial.get("pipeline_results") or {}
    if pipeline_results:
        st.subheader("📊 Pipeline Results")
        for key, content in pipeline_results.items():
            st.caption(key.replace("_", " ").title())
            st.code(content)
    charts = partial.get("chart_results") or {}
    if charts:
        st.subheader("📈 Visualizations")
        for chart_name, b64_img in charts.items():
            st.caption(chart_name.replace("_", " ").title())
            st.image(base64.b64decode(b64_img))

    st.divider()
    st.subheader("⚙️ LP Optimization Results — Pending Your Approval")
    st.info(
        "Review the optimization results below. "
        "**Approve** to include in the session plan, or **Discard** to exclude."
    )

    for product_key, content in formatted.items():
        product = product_key.replace("lp_", "").replace("_", " ").title()
        st.caption(f"**{product}**")
        st.code(content)

    col1, col2 = st.columns(2)
    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    with col1:
        if st.button("✅ Approve Recommendation", key="approve_lp_btn"):
            # Persist each approved LP run in Streamlit session state.
            for result_dict in raw.values():
                _store_approved_run(result_dict)
            with st.spinner("Finalizing recommendation..."):
                second_state = stream_graph(Command(resume="approve"), config=config)
            merged = _merge_final_states(partial, second_state)
            finalize_execution(merged, fallback_plan=st.session_state.get("saved_plan", {}))
            st.session_state.waiting_for_lp_approval = False
            st.session_state.pending_lp_result = None
            st.session_state.lp_partial_state = {}
            st.session_state.saved_plan = {}
            st.rerun()

    with col2:
        if st.button("❌ Discard", key="discard_lp_btn"):
            with st.spinner("Discarding..."):
                second_state = stream_graph(Command(resume="discard"), config=config)
            merged = _merge_final_states(partial, second_state)
            finalize_execution(merged, fallback_plan=st.session_state.get("saved_plan", {}))
            st.session_state.waiting_for_lp_approval = False
            st.session_state.pending_lp_result = None
            st.session_state.lp_partial_state = {}
            st.session_state.saved_plan = {}
            st.rerun()


# ── Main rendering logic ───────────────────────────────────────────────────────

# Show demand verification banner while awaiting first-turn confirmation.
# Only fires after the kickoff response has been rendered — not before.
if st.session_state.historical_demand_verification_pending:
    _render_demand_verification_banner()

if st.session_state.waiting_for_lp_approval and st.session_state.pending_lp_result:
    render_lp_approval()

elif st.session_state.waiting_for_approval and st.session_state.pending_plan:
    render_pending_plan()

elif not st.session_state.waiting_for_approval and not st.session_state.waiting_for_lp_approval:
    prompt = st.chat_input("Ask about suppliers...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # ── Session summary shortcut — bypass graph entirely ───────────────
        if any(t in prompt.lower() for t in _SUMMARY_TRIGGERS):
            summary = _format_session_summary(st.session_state.get("approved_lp_runs", []))
            with st.chat_message("assistant"):
                st.markdown(summary)
            st.session_state.messages.append({
                "role": "assistant",
                "content": summary,
                "has_trace": False,
                "summary": "",
            })
            st.rerun()

        # ── Opening kickoff: first-turn planning + cost + risk objective ───
        elif _is_first_user_turn() and _is_opening_kickoff(prompt):
            st.session_state.historical_demand_verification_pending = True
            _render_kickoff_response()
            st.rerun()

        # ── Proceed after demand verification ──────────────────────────────
        elif st.session_state.historical_demand_verification_pending and _is_proceed_response(prompt):
            st.session_state.historical_demand_verification_pending = False
            # Direct fast path — bypasses orchestrator AND synthesizer entirely.
            # query_forecast_summary() reads pre-computed DB tables; no LLM involved.
            # Saves ~12–15s of orchestrator + synthesizer round-trip latency.
            with st.spinner("Retrieving forecast summary..."):
                from tools.pipeline_queries import query_forecast_summary
                forecast_result = query_forecast_summary()
                forecast_text = forecast_result.get("content", "")
            combined = (
                f"{_KICKOFF_TRANSITION_SENTENCE}\n\n"
                f"---\n\n"
                f"**📊 Production Demand Forecast**\n\n"
                f"```\n{forecast_text}\n```"
            )
            with st.chat_message("assistant"):
                st.markdown(_KICKOFF_TRANSITION_SENTENCE)
                st.divider()
                st.subheader("📊 Production Demand Forecast")
                st.code(forecast_text)
            st.session_state.messages.append({
                "role": "assistant",
                "content": combined,
                "has_trace": False,
                "summary": "",
            })
            st.rerun()

        # ── Fast all-facilities forecast comparison ────────────────────────
        # Must precede _forecast_assessment_direction: queries like
        # "Compare forecast demand across all facilities" contain 'compar' which
        # matches _FORECAST_BASELINE_SIGNALS. Checking all-facilities signals first
        # prevents misrouting to the model-baseline assessment route.
        elif _is_all_facilities_forecast(prompt):
            import matplotlib.pyplot as plt
            with st.spinner("Retrieving forecast data..."):
                from tools.pipeline_queries import (
                    get_forecast_drilldown_df,
                    _plot_all_facilities_forecast,
                    _narrative_all_facilities,
                )
                df = get_forecast_drilldown_df()
            transition = (
                "Here is the forecasted demand trend across all four "
                "facilities over the planning horizon."
            )
            narrative = _narrative_all_facilities(df)
            fig = _plot_all_facilities_forecast(df)
            chart_b64 = _fig_to_b64(fig)
            plt.close(fig)
            with st.chat_message("assistant"):
                st.markdown(transition)
                st.divider()
                st.subheader("📊 Forecast — All Facilities")
                st.image(base64.b64decode(chart_b64))
                st.markdown(narrative)
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"{transition}\n\n{narrative}",
                "has_trace": False,
                "summary": "",
                "chart_b64": chart_b64,
            })
            st.rerun()

        # ── Fast forecast model assessment ────────────────────────────────
        elif _forecast_assessment_direction(prompt) is not None:
            direction = _forecast_assessment_direction(prompt)
            transition, label = _FORECAST_ASSESS_META[direction]
            with st.spinner("Retrieving forecast model assessment..."):
                from tools.pipeline_queries import query_forecast_model_assessment
                result = query_forecast_model_assessment(direction=direction)
                result_text = result.get("content", "")
                artifact_path = result.get("artifact_path", "")
            # Read artifact PNG → base64 so the replay loop can redisplay it
            # after st.rerun() clears the current render (same pattern as drill-down).
            chart_b64 = ""
            if artifact_path:
                abs_path = os.path.join(_ARTIFACTS_BASE, artifact_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as _f:
                        chart_b64 = base64.b64encode(_f.read()).decode()
            with st.chat_message("assistant"):
                st.subheader(label)
                if chart_b64:
                    st.image(base64.b64decode(chart_b64))
                st.markdown(result_text)
            combined = f"**{label}**\n\n{result_text}"
            st.session_state.messages.append({
                "role": "assistant",
                "content": combined,
                "has_trace": False,
                "summary": "",
                "chart_b64": chart_b64,
                "chart_first": True,  # replay loop renders image before text content
            })
            st.rerun()

        # ── Fast forecast drill-down (Cases A / B / C) ────────────────────
        elif _is_forecast_drilldown_request(prompt):
            import matplotlib.pyplot as plt
            t_low = prompt.lower()
            is_all = any(s in t_low for s in _FORECAST_ALL_FACILITIES_SIGNALS)
            facility_id = _extract_facility_id(prompt)

            with st.spinner("Retrieving forecast data..."):
                from tools.pipeline_queries import (
                    get_forecast_drilldown_df,
                    _plot_all_facilities_forecast,
                    _narrative_all_facilities,
                )
                df = get_forecast_drilldown_df()

            if is_all:
                # ── Case C: all-facilities trend chart ─────────────────────
                # Render fig → base64 before rerun so replay loop can redisplay it.
                transition = (
                    "Here is the forecasted demand trend across all four "
                    "facilities over the planning horizon."
                )
                narrative = _narrative_all_facilities(df)
                fig = _plot_all_facilities_forecast(df)
                chart_b64 = _fig_to_b64(fig)
                plt.close(fig)
                with st.chat_message("assistant"):
                    st.markdown(transition)
                    st.divider()
                    st.subheader("📊 Forecast — All Facilities")
                    st.image(base64.b64decode(chart_b64))
                    st.markdown(narrative)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"{transition}\n\n{narrative}",
                    "has_trace": False,
                    "summary": "",
                    "chart_b64": chart_b64,
                })

            elif facility_id:
                # ── Case B: single-facility faceted SKU chart (6×2) ─────────
                # Uses business-facing label ("Facility 1" not "FACILITY_1").
                # Bullets above the chart; chart rendered in a scrollable
                # container so the summary stays pinned at the top.
                # Figure → base64 before rerun so replay loop can redisplay it.
                fac_label  = _format_facility_label(facility_id)
                transition = (
                    f"Here is the production demand forecast for **{fac_label}** "
                    f"across each semiconductor SKU over the planning horizon."
                )
                bullets    = _narrative_facility_bullets(df, facility_id)
                fig        = _plot_facility_faceted(df, facility_id)
                chart_b64  = _fig_to_b64(fig)
                plt.close(fig)
                # Scrollable chart HTML — browser-native overflow so only the
                # chart area scrolls; intro + bullets stay fixed above it.
                _scroll_html = (
                    f'<div style="height:640px;overflow-y:auto;'
                    f'border:1px solid #e6e9ef;border-radius:6px;padding:4px;">'
                    f'<img src="data:image/png;base64,{chart_b64}"'
                    f' style="width:100%;display:block;" /></div>'
                )
                with st.chat_message("assistant"):
                    st.markdown(transition)       # fixed above scroll region
                    st.markdown(bullets)          # fixed above scroll region
                    st.divider()
                    st.subheader(f"📊 Forecast — {fac_label} by SKU")
                    st.markdown(_scroll_html, unsafe_allow_html=True)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"{transition}\n\n{bullets}",
                    "has_trace": False,
                    "summary": "",
                    "chart_b64": chart_b64,
                    "chart_scroll": True,  # tells replay loop to use scrollable div
                })

            else:
                # ── Case A: full tabular drill-down ─────────────────────────
                # Store display_df in fast_path_dfs so replay loop can re-render
                # the dataframe widget after st.rerun() clears the current render.
                transition = (
                    "Here is the detailed production forecast by week, "
                    "facility, and semiconductor SKU."
                )
                display_df = df[[
                    "target_week_date", "facility_id", "semiconductor_id",
                    "predicted_demand", "interval_lower_90", "interval_upper_90",
                    "horizon_weeks",
                ]].rename(columns={
                    "target_week_date": "Week",
                    "facility_id": "Facility",
                    "semiconductor_id": "SKU",
                    "predicted_demand": "Forecast",
                    "interval_lower_90": "Lower 90%",
                    "interval_upper_90": "Upper 90%",
                    "horizon_weeks": "Horizon Wk",
                })
                df_idx = len(st.session_state.fast_path_dfs)
                st.session_state.fast_path_dfs.append(display_df)
                _fmt = {"Forecast": "{:,.0f}", "Lower 90%": "{:,.0f}", "Upper 90%": "{:,.0f}"}
                with st.chat_message("assistant"):
                    st.markdown(transition)
                    st.divider()
                    st.subheader("📊 Forecast Drill-Down")
                    st.dataframe(
                        display_df.style.format(_fmt),
                        use_container_width=True,
                    )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": (
                        f"{transition}\n\n"
                        f"*(Showing {len(display_df):,} rows — "
                        f"{df['facility_id'].nunique()} facilities × "
                        f"{df['semiconductor_id'].nunique()} SKUs × "
                        f"{df['target_week_date'].nunique()} weeks)*"
                    ),
                    "has_trace": False,
                    "summary": "",
                    "df_index": df_idx,
                })
            st.rerun()

        # ── BOM translation explainability — SKU demand → component demand ──
        # Checked BEFORE component requirements: queries like "...translated into
        # component demand" contain "component demand" which would otherwise match
        # the component-requirements route first and shadow this route entirely.
        elif _is_bom_translation_request(prompt):
            with st.spinner("Building BOM translation view..."):
                from tools.pipeline_queries import query_bom_translation_explainer
                result = query_bom_translation_explainer()

            import pandas as pd
            _rows = result.get("rows", [])
            df_bom = pd.DataFrame(_rows)

            _BOM_EXEC_NOTE = (
                "- This step shows what components are required to build the products "
                "our customers are expecting.\n"
                "- Every finished unit requires a specific mix of inputs — the BOM "
                "defines how many units of each component are needed per SKU.\n"
                "- Multiplying that recipe by the forecasted demand yields the gross "
                "component requirements shown below.\n"
                "- These totals are calculated before any inventory has been considered."
            )
            with st.chat_message("assistant"):
                st.subheader("BOM Translation — How Finished Demand Becomes Component Demand")
                st.caption(
                    "How each finished SKU's forecasted demand converts to gross "
                    "component demand across all facilities and forecast weeks"
                )
                if not df_bom.empty:
                    st.dataframe(
                        df_bom.style.format({
                            "Units / SKU":            "{:,.2f}",
                            "Forecast (units)":       "{:,.0f}",
                            "Gross Component Demand": "{:,.0f}",
                        }),
                        height=420,
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown(_BOM_EXEC_NOTE)
            st.session_state.messages.append({
                "role":        "assistant",
                "content":     (
                    "**BOM Translation — How Finished Demand Becomes Component Demand**\n\n"
                    + _BOM_EXEC_NOTE
                ),
                "has_trace":   False,
                "summary":     "",
                "bom_xlate_df": _rows,
            })
            st.rerun()

        # ── Component requirements — gross BOM demand (no inventory netting) ─
        elif _is_component_requirements_request(prompt):
            with st.spinner("Retrieving component requirements..."):
                data = _fetch_component_req_data()

            import pandas as pd
            df_window = pd.DataFrame([{
                "Forecast Start":  data["start_date"],
                "Forecast End":    data["end_date"],
                "Horizon Weeks":   data["n_weeks"],
                "Forecast Run ID": data["run_id"],
            }])
            df_scope = pd.DataFrame([{
                "Facilities":      data["n_facilities"],
                "Component Types": data["n_components"],
                "Aggregation":     (
                    f"All {data['n_facilities']} facilities "
                    f"\u00d7 {data['n_weeks']} forecast weeks"
                ),
            }])
            _comp_data = list(data["rows"])
            _total = sum(v for _, v in _comp_data)
            _comp_data.append(("TOTAL", _total))
            df_components = pd.DataFrame(_comp_data, columns=["Component", "Units Required"])

            _EXEC_NOTE = (
                "These totals represent BOM-implied component demand required to "
                "fulfill the finished-goods forecast across the planning horizon. "
                "Each finished unit consumes a defined mix of components, aggregated "
                "here across all facilities and forecast weeks. "
                "Inventory has not yet been netted out."
            )
            _dfs_payload = [
                {"caption": "Planning Window",
                 "records": df_window.to_dict("records")},
                {"caption": "Aggregation Scope",
                 "records": df_scope.to_dict("records")},
                {"caption": "Full-Horizon Gross Requirement by Component",
                 "records": df_components.to_dict("records")},
            ]
            with st.chat_message("assistant"):
                st.subheader("Component Requirements — Full Horizon Gross Demand")
                st.caption("Planning Window")
                st.dataframe(df_window, use_container_width=True, hide_index=True)
                st.caption("Aggregation Scope")
                st.dataframe(df_scope, use_container_width=True, hide_index=True)
                st.caption("Full-Horizon Gross Requirement by Component")
                st.dataframe(
                    df_components.style.format({"Units Required": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                )
                st.markdown(_EXEC_NOTE)
            st.session_state.messages.append({
                "role":         "assistant",
                "content":      (
                    "**Component Requirements — Full Horizon Gross Demand**\n\n"
                    + _EXEC_NOTE
                ),
                "has_trace":    False,
                "summary":      "",
                "comp_req_dfs": _dfs_payload,
            })
            st.rerun()

        # ── Inventory-adjusted procurement requirement summary ─────────────
        # Direct fast-path — no orchestrator. Aligned to README "start here"
        # entry point (format_procurement_recommendation / aggregated need).
        elif _is_procurement_summary_request(prompt):
            with st.spinner("Computing inventory-adjusted procurement requirement..."):
                from tools.pipeline_queries import query_procurement_summary_data
                data = query_procurement_summary_data()

            import pandas as pd
            _proc_rows = data.get("rows", [])
            df_proc = pd.DataFrame(_proc_rows)

            # Rename columns for calculation-flow clarity (sign convention in label)
            df_proc = df_proc.rename(columns={
                "Starting On-Hand":              "Starting On-Hand (\u2212)",
                "Safety Stock Reserve (\u2212)": "Safety Stock Reserve (+)",
            })
            # Reorder left → right as a calculation: Gross − OnHand + SR − BO + SS = Net
            df_proc = df_proc[[
                "Component",
                "Gross Component Demand",
                "Starting On-Hand (\u2212)",
                "Scheduled Receipts (+)",
                "Backorders (\u2212)",
                "Safety Stock Reserve (+)",
                "Net Procurement Requirement",
            ]]
            _PROC_FMT = {c: "{:,.0f}" for c in df_proc.columns if c != "Component"}
            # Store renamed records so replay renders identical columns
            _proc_display_rows = df_proc.to_dict("records")

            _PROC_BULLETS = (
                "- **This table starts from the current inventory position — "
                "Starting On-Hand — at the beginning of the planning horizon.**\n"
                "- **Gross Component Demand** represents total required component "
                "volume based on forecasted production.\n"
                "- **Starting On-Hand**, **Scheduled Receipts**, and **Backorders** "
                "adjust available inventory over the planning horizon.\n"
                "- **Safety Stock Reserve** represents required buffer inventory to "
                "maintain the target service level and must be procured if not "
                "already available.\n"
                "- **Net Procurement Requirement** is the remaining quantity that "
                "must be ordered after accounting for all inventory and policy "
                "constraints."
            )
            _DATA_DICT = {
                "Gross Component Demand": (
                    "Total BOM-implied component volume required to fulfill the "
                    "finished-goods forecast across all facilities and the full "
                    "planning horizon."
                ),
                "Starting On-Hand (\u2212)": (
                    "Total component stock physically on hand at the start of the "
                    "planning horizon, summed across all facilities."
                ),
                "Scheduled Receipts (+)": (
                    "The firm currently assumes no scheduled receipts are due "
                    "within this planning snapshot."
                ),
                "Backorders (\u2212)": (
                    "Backorders are currently zero in this planning view."
                ),
                "Safety Stock Reserve (+)": (
                    "The minimum inventory buffer required to meet the 95% service "
                    "level target. This reserve must be available at all times and "
                    "is added to the procurement requirement if not already covered "
                    "by on-hand stock."
                ),
                "Net Procurement Requirement": (
                    "The quantity that must be procured. Calculated per facility as: "
                    "max(0, Gross Demand \u2212 On-Hand + Scheduled Receipts "
                    "\u2212 Backorders + Safety Stock Reserve), "
                    "then summed across all facilities."
                ),
            }

            with st.chat_message("assistant"):
                st.subheader("Net Component Procurement Requirement — Planning Horizon")
                st.caption(
                    f"Horizon: {data['horizon_start']} \u2192 {data['horizon_end']}"
                    f"  \u00b7  {data['n_weeks']} weeks"
                    f"  \u00b7  Forecast run {data['run_id']}"
                )
                st.caption("All values are aggregated across the full planning horizon.")
                if not df_proc.empty:
                    st.dataframe(
                        df_proc.style.format(_PROC_FMT),
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown(_PROC_BULLETS)
                with st.expander("Click to view data dictionary"):
                    for col, desc in _DATA_DICT.items():
                        st.markdown(f"**{col}:** {desc}")
            st.session_state.messages.append({
                "role":           "assistant",
                "content":        (
                    "**Net Component Procurement Requirement — Planning Horizon**\n\n"
                    f"Horizon: {data['horizon_start']} \u2192 {data['horizon_end']}"
                    f" ({data['n_weeks']} weeks)\n\n"
                    "All values are aggregated across the full planning horizon.\n\n"
                    + _PROC_BULLETS
                ),
                "has_trace":      False,
                "summary":        "",
                "proc_summary_df": _proc_display_rows,
            })
            st.rerun()

        # ── Safety stock / inventory policy explainability ────────────────
        elif _is_ss_policy_request(prompt):
            _SS_FORMULA = (
                "**S = \u03bc\u1d05 (r + \u03bc\u2097) + z \u00b7 "
                "\u221a((r + \u03bc\u2097) \u03c3\u1d05\u00b2 + \u03bc\u1d05\u00b2 \u03c3\u2097\u00b2)**"
            )
            _SS_TERMS = (
                "| Symbol | Definition |\n"
                "|---|---|\n"
                "| \u03bc\u1d05 | Average weekly component demand |\n"
                "| \u03c3\u1d05 | Demand standard deviation |\n"
                "| \u03bc\u2097 | Average lead time (weeks) |\n"
                "| \u03c3\u2097 | Lead time standard deviation |\n"
                "| r | Review period \u2014 **8 weeks** |\n"
                "| z | Service level factor \u2014 **\u22481.65** for 95% target |"
            )
            _SS_BUSINESS = (
                "- The formula computes the **base-stock level (S)** \u2014 the total inventory "
                "required to meet demand across the review period and lead time under uncertainty.\n"
                "- **Safety stock** is the buffer component embedded within this level, covering "
                "demand and lead-time variability.\n"
                "- In this system, safety stock is enforced as a **protected inventory floor** "
                "per facility \u00d7 component. It is not consumed during planning.\n"
                "- Only inventory **above** this floor is used to satisfy weekly demand."
            )
            _SS_CYCLE_STOCK = (
                "The base-stock level (S) has two distinct components:\n\n"
                "**1. Cycle Stock** \u2014 \u03bc\u1d05 \u00d7 (r + \u03bc\u2097)\n"
                "- Covers **expected demand** over the review period and lead time\n"
                "- This is the primary driver of inventory volume\n\n"
                "**2. Safety Stock** \u2014 z \u00b7 \u221a((r + \u03bc\u2097)\u03c3\u1d05\u00b2 "
                "+ \u03bc\u1d05\u00b2\u03c3\u2097\u00b2)\n"
                "- Covers **uncertainty** in demand and lead time\n"
                "- This is a buffer \u2014 NOT intended to cover expected demand\n\n"
                "On-hand inventory at the start of planning is anchored at "
                "**S = Cycle Stock + Safety Stock**. "
                "Safety stock alone will often appear small relative to weekly demand \u2014 "
                "this is expected and correct."
            )
            _SS_PLANNING = (
                "- Weekly procurement is triggered when **usable inventory** (above the safety "
                "stock floor) reaches zero.\n"
                "- Safety stock is already accounted for before any weekly demand calculations "
                "begin \u2014 it does not appear as a deduction in the weekly trigger table.\n"
                "- The weekly trigger table reflects how demand consumes usable inventory, "
                "not safety stock itself."
            )
            _ss_content = (
                "**Inventory Policy \u2014 Safety Stock and Base-Stock Logic**\n\n"
                "**Base-Stock Formula**\n\n"
                + _SS_FORMULA + "\n\n"
                "**Term Definitions**\n\n"
                + _SS_TERMS + "\n\n"
                "**How It Works**\n\n"
                + _SS_BUSINESS + "\n\n"
                "**Cycle Stock vs Safety Stock (Key Distinction)**\n\n"
                + _SS_CYCLE_STOCK + "\n\n"
                "**Connection to Planning Outputs**\n\n"
                + _SS_PLANNING
            )
            with st.chat_message("assistant"):
                st.subheader("Inventory Policy \u2014 Safety Stock and Base-Stock Logic")
                st.markdown("**Base-Stock Formula**")
                st.markdown(_SS_FORMULA)
                st.markdown("**Term Definitions**")
                st.markdown(_SS_TERMS)
                st.markdown("**How It Works**")
                st.markdown(_SS_BUSINESS)
                st.markdown("**Cycle Stock vs Safety Stock (Key Distinction)**")
                st.markdown(_SS_CYCLE_STOCK)
                st.markdown("**Connection to Planning Outputs**")
                st.markdown(_SS_PLANNING)
            st.session_state.messages.append({
                "role":      "assistant",
                "content":   _ss_content,
                "has_trace": False,
                "summary":   "",
            })
            st.rerun()

        # ── Full inventory planning horizon drilldown (diagnostic) ───────────
        elif _is_full_horizon_drilldown_request(prompt):
            with st.spinner("Loading full inventory planning horizon..."):
                from tools.pipeline_queries import query_full_horizon_drilldown
                fh_data = query_full_horizon_drilldown()

            import pandas as pd
            _fh_rows = fh_data.get("rows", [])
            df_fh = pd.DataFrame(_fh_rows)

            if not df_fh.empty and "Facility" in df_fh.columns:
                df_fh["Facility"] = df_fh["Facility"].apply(_format_facility_label)

            _FH_COL_ORDER = [
                "Forecast Week", "Week", "Facility", "Component",
                "Gross Requirement", "Usable Inventory Before Demand",
                "Direct Procurement Needed", "Triggered?",
                "Safety Stock (Protected Floor)",
            ]
            if not df_fh.empty:
                df_fh = df_fh[[c for c in _FH_COL_ORDER if c in df_fh.columns]]

            _FH_FMT = {
                "Forecast Week":                  "{:,.0f}",
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Safety Stock (Protected Floor)": "{:,.0f}",
            }
            _fh_display_rows = df_fh.to_dict("records")

            _n_triggered = int((df_fh["Triggered?"] == "Yes").sum()) if not df_fh.empty else 0
            _FH_NOTE = (
                "All planning weeks are shown — including weeks where inventory covers demand "
                "(Triggered? = No) and weeks where procurement is required (Triggered? = Yes). "
                "Use filters to isolate a specific facility or component."
            )

            with st.chat_message("assistant"):
                st.subheader("Inventory Planning Horizon \u2014 Full Facility \u00d7 Component \u00d7 Week Detail")
                st.caption(
                    f"Forecast run {fh_data['run_id']}"
                    f"  \u00b7  {fh_data['horizon_start']} \u2192 {fh_data['horizon_end']}"
                    f"  \u00b7  {fh_data['n_weeks']} weeks"
                    f"  \u00b7  {len(_fh_rows):,} rows total"
                    f"  \u00b7  {_n_triggered} triggered"
                )
                st.markdown(_FH_NOTE)
                if not df_fh.empty:
                    st.dataframe(
                        df_fh.style.format(_FH_FMT),
                        use_container_width=True,
                        hide_index=True,
                        height=600,
                    )
                else:
                    st.info("No planning rows found for this forecast run.")
            st.session_state.messages.append({
                "role":          "assistant",
                "content":       (
                    "**Inventory Planning Horizon \u2014 Full Facility \u00d7 Component \u00d7 Week Detail**\n\n"
                    f"Forecast run {fh_data['run_id']} \u00b7 "
                    f"{fh_data['horizon_start']} \u2192 {fh_data['horizon_end']} "
                    f"({fh_data['n_weeks']} weeks) \u00b7 {len(_fh_rows):,} rows\n\n"
                    + _FH_NOTE
                ),
                "has_trace":     False,
                "summary":       "",
                "full_horizon_df": _fh_display_rows,
            })
            st.rerun()

        # ── Weekly procurement trigger drill-down ──────────────────────────
        elif _is_weekly_trigger_request(prompt):
            with st.spinner("Fetching triggered procurement rows..."):
                from tools.pipeline_queries import query_triggered_rows_structured
                trig_data = query_triggered_rows_structured()

            import pandas as pd
            _trig_rows = trig_data.get("rows", [])
            df_trig = pd.DataFrame(_trig_rows)

            # Apply readable facility labels (raw facility_id → label)
            if not df_trig.empty and "Facility" in df_trig.columns:
                df_trig["Facility"] = df_trig["Facility"].apply(_format_facility_label)

            # ── Presentation-layer renames ──────────────────────────────────
            df_trig = df_trig.rename(columns={
                "Available Inventory Before Demand": "Usable Inventory Before Demand",
                "Procurement Need":                  "Direct Procurement Needed",
            })

            # ── Extract SS context BEFORE dropping Safety Stock Reserve ────
            # Used for the context block — stored separately in the message dict.
            _ss_context = []
            if not df_trig.empty and "Safety Stock Reserve" in df_trig.columns:
                _ss_context = (
                    df_trig[["Facility", "Component", "Safety Stock Reserve"]]
                    .drop_duplicates()
                    .sort_values(["Facility", "Component"])
                    .rename(columns={"Safety Stock Reserve": "Safety Stock (Protected Floor)"})
                    .to_dict("records")
                )

            # ── Presentation-layer derived columns ─────────────────────────
            # All computed from existing fetched values — no inventory logic change.
            if not df_trig.empty and "Safety Stock Reserve" in df_trig.columns:
                # Ensure correct per-series cumsum order (date within each series)
                df_trig = df_trig.sort_values(["Component", "Facility", "Week"])
                df_trig["Cumulative Procurement Pressure"] = (
                    df_trig.groupby(["Facility", "Component"])["Direct Procurement Needed"]
                    .cumsum()
                )
                df_trig["Safety Stock Utilization (%)"] = (
                    df_trig["Cumulative Procurement Pressure"]
                    / df_trig["Safety Stock Reserve"]
                    * 100
                ).round(1)
                df_trig["Urgency Level"] = df_trig["Safety Stock Utilization (%)"].apply(
                    lambda u: "Critical" if u >= 100 else
                              "High"     if u >= 75  else
                              "Medium"   if u >= 50  else
                              "Low"
                )

            # ── Enforce display column order (Safety Stock Reserve excluded) ─
            # Forecast Week comes from r.horizon_week (true planning horizon index).
            _TRIG_COL_ORDER = [
                "Forecast Week", "Week", "Component", "Facility",
                "Gross Requirement", "Usable Inventory Before Demand",
                "Direct Procurement Needed", "Cumulative Procurement Pressure",
                "Safety Stock Utilization (%)", "Urgency Level",
            ]
            if not df_trig.empty:
                df_trig = df_trig[[c for c in _TRIG_COL_ORDER if c in df_trig.columns]]

            # Store unfiltered rows (Forecast Week = r.horizon_week from DB, not a counter)
            _trig_display_rows = df_trig.to_dict("records")

            _TRIG_FMT = {
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Cumulative Procurement Pressure":"{:,.0f}",
                "Safety Stock Utilization (%)":   "{:.1f}%",
                "Forecast Week":                  "{:,.0f}",
            }

            _TRIG_BULLETS = (
                "- **Gross Requirement:** forecast-driven component demand for that week.\n"
                "- **Usable Inventory Before Demand:** inventory available after preserving "
                "the safety stock floor.\n"
                "- **Direct Procurement Needed:** portion of demand not covered by usable "
                "inventory.\n"
                "- **Cumulative Procurement Pressure:** total procurement required up to that "
                "week, per facility \u00d7 component.\n"
                "- **Safety Stock Utilization (%):** how much of the safety buffer is being "
                "matched by cumulative procurement demand.\n"
                "- **Urgency Level:** qualitative indicator \u2014 Low / Medium / High / "
                "Critical \u2014 based on how close cumulative pressure is to the safety "
                "buffer.\n"
                "- Procurement is triggered when usable inventory reaches zero."
            )

            with st.chat_message("assistant"):
                st.subheader("Weekly Procurement Trigger \u2014 Where and When Procurement Is Required")
                st.caption(
                    f"Forecast run {trig_data['run_id']}"
                    f"  \u00b7  {len(_trig_rows)} triggered week\u2013facility\u2013component rows"
                    "  \u00b7  Use filters to drill down by facility or component"
                )
                # ── Safety Stock context block ──────────────────────────────
                if _ss_context:
                    _ss_ctx_df = pd.DataFrame(_ss_context)
                    st.dataframe(
                        _ss_ctx_df.style.format({"Safety Stock (Protected Floor)": "{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(
                        "This value represents the inventory buffer required to maintain the "
                        "target service level. It is preserved in all inventory calculations "
                        "and not consumed by demand. The table below shows how procurement "
                        "pressure accumulates relative to this buffer."
                    )
                # ── Primary trigger table ───────────────────────────────────
                if not df_trig.empty:
                    st.dataframe(
                        df_trig.style.format(_TRIG_FMT),
                        use_container_width=True,
                        hide_index=True,
                        height=500,
                    )
                else:
                    st.info("No triggered procurement rows found \u2014 all inventory positions appear sufficient.")
                st.markdown(_TRIG_BULLETS)
            st.session_state.messages.append({
                "role":    "assistant",
                "content": (
                    "**Weekly Procurement Trigger \u2014 Where and When Procurement Is Required**\n\n"
                    f"Forecast run {trig_data['run_id']} \u00b7 {len(_trig_rows)} triggered rows\n\n"
                    + _TRIG_BULLETS
                ),
                "has_trace":         False,
                "summary":           "",
                "weekly_trigger_df": _trig_display_rows,
                "ss_context":        _ss_context,
            })
            st.rerun()

        else:
            # ── Normal graph invocation ────────────────────────────────────
            with st.spinner("Thinking..."):
                thread_id = str(uuid.uuid4())
                st.session_state.thread_id = thread_id
                config = {"configurable": {"thread_id": thread_id}}
                result = asyncio.run(graph.ainvoke({"messages": [("user", prompt)]}, config=config))
                state = asyncio.run(graph.aget_state(config=config))
            plan = extract_plan(state)
            if state.next and plan:
                st.session_state.waiting_for_approval = True
                st.session_state.pending_plan = plan
                assistant_text = "I have a plan ready. Review the work orders below and approve when ready."
                st.session_state.messages.append({"role": "assistant", "content": assistant_text})
                st.rerun()
