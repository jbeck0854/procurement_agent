"""
Procurement Supply Chain Agent — Streamlit UI.

All user input flows through the LLM Orchestrator → Agent execution → Rendering.
No keyword routing. Parameter extraction is handled by param_extractor.py.
"""

import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime

import nest_asyncio
import streamlit as st
from langgraph.types import Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

nest_asyncio.apply()

from graph.builder import build_graph
from param_extractor import extract_lp_params, merge_with_prior, fill_defaults

# ── UI module imports ────────────────────────────────────────────────────────
from ui.common import _inject_scroll_to_bottom, _inject_scroll_to_anchor
from ui.lp_views import _build_run_entry, _render_lp_result, _render_procurement_status_bar
from ui.executive_summary import _render_executive_summary
from ui.forecast_views import _render_forecast_summary_structured, _render_forecast_expanders
from ui.session_helpers import _store_approved_run, _merge_final_states
from ui.theme import (
    inject_css, FAVICON, LOGO_B64, USER_AVATAR, CPU_AVATAR,
    SECTION_STYLE, section_header, render_charts,
    render_header, render_sidebar, render_landing,
    render_history_list, render_history_detail,
)

# Keys that belong to other agents (not pipeline results).
_NON_PIPELINE_KEYS = frozenset({
    "data_agent", "risk_agent", "pipeline_agent", "pipeline_errors",
    "lp_agent", "lp_agent_errors", "chart_agent",
})

# ── Pre-written plan descriptions per tool ──────────────────────────────────
# Provides business-quality text for plan approval cards.
# LLM identifies intent (agentic); these provide polished display (quality);
# no extra LLM call needed (speed).
TOOL_PLAN_INFO = {
    "query_forecast_summary": {
        "title": "Demand Forecasting",
        "desc": (
            "Retrieve the production demand forecast across all 4 facilities "
            "and 12 semiconductor SKUs for the upcoming 20-week planning horizon."
        ),
    },
    "query_forecast_drilldown": {
        "title": "Forecast Detail — Facility & SKU Breakdown",
        "desc": (
            "Detailed week-by-week forecast breakdown by facility and SKU, "
            "with 90% confidence interval bounds."
        ),
    },
    "query_forecast_model_assessment": {
        "title": "Forecast Model Assessment",
        "desc": (
            "Evaluate the forecast model's training performance, feature importance, "
            "or baseline comparison to validate prediction reliability."
        ),
    },
    "query_component_requirements": {
        "title": "BOM Component Requirements — Full Horizon",
        "desc": (
            "Translate finished-goods forecast into gross component-level demand "
            "(transistors, ICs, power devices, microprocessors) using Bill of Materials recipes. "
            "Aggregated across all facilities and forecast weeks, before inventory offset."
        ),
    },
    "query_bom_translation": {
        "title": "BOM Translation — How SKU Demand Becomes Component Demand",
        "desc": (
            "Show how each finished SKU's forecasted demand converts to gross component demand. "
            "Every finished unit requires a specific mix of inputs — the BOM defines "
            "how many units of each component are needed per SKU."
        ),
    },
    "query_procurement_status": {
        "title": "Inventory & Safety Stock Policy",
        "desc": (
            "Review the base-stock inventory policy, safety stock formula, "
            "and weekly procurement trigger logic across all facilities."
        ),
    },
    "query_procurement_planning_summary": {
        "title": "Procurement Planning Summary",
        "desc": (
            "Overview of the inventory position and procurement requirements "
            "across all components and facilities."
        ),
    },
    "query_aggregated_procurement_need": {
        "title": "Net Procurement Requirement — After Inventory",
        "desc": (
            "Calculate the net quantity that must be procured for each component after "
            "accounting for on-hand inventory, scheduled receipts, backorders, "
            "and safety stock reserves."
        ),
    },
    "query_procurement_drilldown": {
        "title": "Procurement Drilldown by Week & Facility",
        "desc": (
            "Week-by-week, facility-by-facility breakdown of procurement requirements "
            "showing where and when orders are needed."
        ),
    },
    "query_triggered_procurement_rows": {
        "title": "Triggered Procurement Rows",
        "desc": (
            "Identify the specific weeks and facilities where procurement is triggered — "
            "where usable inventory (above safety stock floor) reaches zero."
        ),
    },
    "run_optimization": {
        "title": "Supplier Allocation Optimization (LP)",
        "desc": (
            "Run the linear programming optimizer to allocate procurement across "
            "eligible suppliers, balancing landed cost against supply risk "
            "under the specified constraints."
        ),
    },
    "plot_score_breakdown": {
        "title": "Supplier Score Breakdown",
        "desc": "Visualize supplier scoring components for the selected product.",
    },
    "plot_supplier_comparison": {
        "title": "Supplier Comparison",
        "desc": "Compare supplier profiles side-by-side on cost, risk, and capacity.",
    },
}

# Fallback descriptions for ReAct agents (no specific tool — agent decides autonomously)
_AGENT_PLAN_INFO = {
    "data_agent": {
        "title": "Exploratory Data Analysis",
        "desc": "Free-form SQL exploration against the procurement database. "
                "The agent autonomously decides which tables to query.",
    },
    "risk_agent": {
        "title": "Geopolitical Risk Assessment",
        "desc": "Web search for supply chain risks, tariffs, sanctions, "
                "and geopolitical events affecting procurement regions.",
    },
}


# ── Streamlit config ─────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Procurement Pilot",
    page_icon=FAVICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()


# ── Session state initialization ─────────────────────────────────────────────

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
if "forecast_expander_cache" not in st.session_state:
    st.session_state.forecast_expander_cache = {}
if "inventory_expander_cache" not in st.session_state:
    st.session_state.inventory_expander_cache = {}

# Scroll tracking
if "_scroll_msg_count" not in st.session_state:
    st.session_state._scroll_msg_count = 0
if "_pending_scroll" not in st.session_state:
    st.session_state._pending_scroll = None

# LP approval
if "waiting_for_lp_approval" not in st.session_state:
    st.session_state.waiting_for_lp_approval = False
if "pending_lp_result" not in st.session_state:
    st.session_state.pending_lp_result = None
if "lp_partial_state" not in st.session_state:
    st.session_state.lp_partial_state = {}
if "saved_plan" not in st.session_state:
    st.session_state.saved_plan = {}

# LP modify mode
if "lp_modify_mode" not in st.session_state:
    st.session_state.lp_modify_mode = False
if "lp_modify_baseline" not in st.session_state:
    st.session_state.lp_modify_baseline = {}

# Session-level approved LP runs
if "approved_lp_runs" not in st.session_state:
    st.session_state.approved_lp_runs = []
if "last_lp_raw_full" not in st.session_state:
    st.session_state.last_lp_raw_full = {}
if "lp_params_history" not in st.session_state:
    st.session_state.lp_params_history = {}

# Executive summary flag
if "show_executive_summary" not in st.session_state:
    st.session_state.show_executive_summary = False

# Navigation / session history
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "current_view" not in st.session_state:
    st.session_state.current_view = "chat"
if "viewing_session" not in st.session_state:
    st.session_state.viewing_session = None
if "suggested_query" not in st.session_state:
    st.session_state.suggested_query = ""


# ── Graph execution helpers ──────────────────────────────────────────────────

def show_trace(trace):
    with st.expander("◈  Execution Trace"):
        timings = trace.get("timings") or {}
        if timings:
            st.markdown("""
            <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
               text-transform:uppercase; color:#879580; margin-bottom:0.5rem;">Performance</p>
            """, unsafe_allow_html=True)
            top_level = ["orchestrator", "data_agent", "risk_agent", "pipeline_agent",
                         "chart_agent", "lp_agent", "synthesizer"]
            active_agents = [n for n in top_level if timings.get(n) is not None]
            if active_agents:
                cols = st.columns(len(active_agents))
                for col, name in zip(cols, active_agents):
                    col.metric(name.replace("_", " ").title(), f"{timings[name]:.2f}s")
            total = sum(timings.get(k, 0) for k in top_level)
            st.caption(f"Total pipeline time: {total:.2f}s")
            sub_steps = {k: v for k, v in timings.items() if "." in k}
            if sub_steps:
                st.markdown("**Step breakdown:**\n" + "\n".join(
                    f"- {k}: {v:.3f}s" for k, v in sub_steps.items()
                ))
            st.divider()

        st.markdown("""
        <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
           text-transform:uppercase; color:#879580; margin-bottom:0.5rem;">Orchestrator</p>
        """, unsafe_allow_html=True)
        st.markdown(
            f"<span style='color:#AEFFA0; font-family:Manrope,sans-serif; font-weight:600;'>"
            f"{trace.get('intent', '')}</span>",
            unsafe_allow_html=True,
        )
        for i, task in enumerate(trace.get("tasks", [])):
            agent = task.get("agent", "")
            st.markdown(f"""
            <div style="background:rgba(25,46,37,0.5); border:1px solid rgba(61,74,57,0.15);
                        border-radius:0.25rem; padding:0.7rem 1rem; margin:0.35rem 0;">
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.12em;
                        text-transform:uppercase; color:#5AEB56; margin-bottom:0.3rem;">
                Task {i+1} — {agent}
              </p>
              <p style="font-family:'Manrope',sans-serif; font-size:0.85rem; color:#D0E8DA; margin:0;">
                {task.get('tool', 'auto')}
              </p>
            </div>""", unsafe_allow_html=True)

        if trace.get("tasks"):
            routed = list({t["agent"] for t in trace["tasks"]})
            st.caption("Routed to: " + ", ".join(routed))

        pipeline_results = {k: v for k, v in trace.get("agent_results", {}).items()
                           if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")
                           and not k.endswith("__structured")}
        if pipeline_results:
            st.divider()
            st.caption("Pipeline Agent")
            for key, content in pipeline_results.items():
                st.caption(key.replace("_", " ").title())
                st.code(content[:500] if len(str(content)) > 500 else content)

        for agent_name, label in [("data_agent", "Data Agent"), ("risk_agent", "Risk Agent")]:
            raw = trace.get("agent_results", {}).get(agent_name)
            if raw:
                st.divider()
                st.caption(label)
                st.code(raw[:500] + ("..." if len(raw) > 500 else ""))

        lp_results = {k: v for k, v in trace.get("agent_results", {}).items() if k.startswith("lp_")}
        if lp_results:
            st.divider()
            st.caption("LP Optimization")
            for key, content in lp_results.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                st.caption(f"Product: {product}")
                st.code(content)

        chart_results = trace.get("chart_results") or {}
        if chart_results:
            st.divider()
            st.caption("Charts")
            for chart_name, b64_img in chart_results.items():
                st.caption(chart_name)
                st.image(base64.b64decode(b64_img))

        st.divider()
        st.caption("Synthesizer — final response generated")


def extract_plan(state):
    interrupts = []
    for task in state.tasks or []:
        interrupts.extend(task.interrupts or [])
    return interrupts[0].value if interrupts else None


AGENT_STEPS = [
    ("pipeline_agent", "Querying forecast & inventory data"),
    ("data_agent",     "Running exploratory SQL analysis"),
    ("risk_agent",     "Scanning geopolitical risk signals"),
    ("chart_agent",    "Generating visualizations & scoring"),
    ("lp_agent",       "Optimizing supplier allocation"),
    ("synthesizer",    "Synthesizing executive summary"),
]


def stream_graph(command, config):
    placeholder = st.empty()
    final_state = {"agent_results": {}}

    def _render_streaming(placeholder):
        with placeholder.container():
            completed = set(final_state.get("_completed_agents") or [])
            active = final_state.get("_active_agent")

            # Progress feed
            rows = ""
            for agent_key, label in AGENT_STEPS:
                if agent_key in completed:
                    rows += (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0; opacity:0.6;'>"
                        f"<span style='color:#5AEB56; flex-shrink:0;'>✓</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#D0E8DA;'>{label}</span></div>"
                    )
                elif agent_key == active:
                    rows += (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0;'>"
                        f"<span style='color:#5AEB56; flex-shrink:0;'>◌</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#5AEB56; font-weight:700;'>{label}</span></div>"
                    )
                else:
                    rows += (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0; opacity:0.55;'>"
                        f"<span style='color:#BCCBB4; flex-shrink:0;'>○</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#BCCBB4;'>{label}</span></div>"
                    )

            st.markdown(
                f"<div style='{SECTION_STYLE}'>"
                + section_header("⬡", "Active Engine Progress", "#5AEB56")
                + rows
                + "</div>",
                unsafe_allow_html=True,
            )

            # Pipeline results glass card
            pipeline_results = final_state.get("pipeline_results") or {}
            if pipeline_results:
                _PIPELINE_LABELS = {
                    "forecast_summary": "Forecast Summary",
                    "component_requirements": "Component Requirements",
                    "procurement_status": "Procurement Status",
                }
                inner = "".join(
                    f"<p class='result-label'>{_PIPELINE_LABELS.get(k, k.replace('_',' ').title())}</p>"
                    f"<pre class='result-pre'>{v}</pre>"
                    for k, v in pipeline_results.items()
                )
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("✦", "Pipeline Results", "#AEFFA0")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Data agent glass card
            if final_state.get("latest_data_agent"):
                inner = (
                    f"<div class='summary-body' style='font-size:0.88rem; color:#D0E8DA; line-height:1.65;'>"
                    f"{final_state['latest_data_agent']}</div>"
                )
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("◈", "Data Query", "#AAF8FF")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Risk agent glass card
            if final_state.get("latest_risk_agent"):
                inner = (
                    f"<div class='summary-body' style='font-size:0.88rem; color:#D0E8DA; line-height:1.65;'>"
                    f"{final_state['latest_risk_agent']}</div>"
                )
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("⊕", "Geopolitical Risk Analysis", "#78F5FF")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # LP results glass card
            lp_results = final_state.get("lp_results") or {}
            if lp_results:
                lp_style = (
                    "background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);"
                    "border:1px solid rgba(61,74,57,0.15); border-left:3px solid #5AEB56;"
                    "border-radius:0.5rem; padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
                )
                inner = "".join(
                    f"<p class='result-label'>Product: {k.replace('lp_','').replace('_',' ').title()}</p>"
                    f"<pre class='result-pre'>{v}</pre>"
                    for k, v in lp_results.items()
                )
                st.markdown(
                    f"<div style='{lp_style}'>"
                    + section_header("◬", "LP Optimization Results", "#5AEB56")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Charts — 2-column grid
            charts = final_state.get("chart_results") or {}
            if charts:
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("◎", "Visualizations", "#6CDD7F")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                render_charts(charts)

            # Summary glass card
            if final_state.get("final_response"):
                summary_style = (
                    "background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);"
                    "border:1px solid rgba(90,235,86,0.18); border-radius:0.5rem;"
                    "padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
                    "box-shadow:0 0 40px rgba(90,235,86,0.08);"
                )
                inner = (
                    f"<div class='summary-body'>{final_state['final_response']}</div>"
                )
                st.markdown(
                    f"<div style='{summary_style}'>"
                    + section_header("✦", "Intelligence Summary", "#AEFFA0")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

    async def stream_results():
        agent_order = [s[0] for s in AGENT_STEPS]
        async for event in graph.astream(command, config=config):
            for node_name, node_output in event.items():
                # LP interrupt handling (Frank's architecture)
                if node_name == "__interrupt__":
                    interrupts = node_output
                    if interrupts:
                        intr = interrupts[0]
                        intr_val = intr.value if hasattr(intr, "value") else {}
                        if isinstance(intr_val, dict) and intr_val.get("type") == "lp_approval":
                            final_state["__interrupt__"] = intr_val
                    return final_state

                if not isinstance(node_output, dict):
                    continue

                # Track active agent for progress display
                if node_name in agent_order:
                    final_state["_active_agent"] = node_name

                if "intent" in node_output:
                    final_state["intent"] = node_output["intent"]
                if "tasks" in node_output:
                    final_state["tasks"] = node_output["tasks"]
                if "agent_results" in node_output:
                    final_state.setdefault("agent_results", {}).update(
                        node_output["agent_results"] or {}
                    )

                # Pipeline results — extract for streaming display
                if node_name == "pipeline_agent" and node_output.get("agent_results"):
                    items = {
                        k: v for k, v in node_output["agent_results"].items()
                        if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")
                        and not k.endswith("__structured")
                    }
                    if items:
                        final_state.setdefault("pipeline_results", {}).update(items)
                        final_state.setdefault("_completed_agents", []).append("pipeline_agent")
                        _render_streaming(placeholder)

                # Data agent
                if node_name == "data_agent" and node_output.get("agent_results"):
                    data_text = node_output["agent_results"].get("data_agent")
                    if data_text:
                        final_state["latest_data_agent"] = data_text
                        final_state.setdefault("_completed_agents", []).append("data_agent")
                        _render_streaming(placeholder)

                # Risk agent
                if node_name == "risk_agent" and node_output.get("agent_results"):
                    risk_text = node_output["agent_results"].get("risk_agent")
                    if risk_text:
                        final_state["latest_risk_agent"] = risk_text
                        final_state.setdefault("_completed_agents", []).append("risk_agent")
                        _render_streaming(placeholder)

                # LP agent
                if node_name == "lp_agent" and node_output.get("agent_results"):
                    lp_items = {
                        k: v for k, v in node_output["agent_results"].items()
                        if k.startswith("lp_")
                    }
                    if lp_items:
                        final_state.setdefault("lp_results", {}).update(lp_items)
                        final_state.setdefault("_completed_agents", []).append("lp_agent")
                        _render_streaming(placeholder)

                # Chart agent
                if node_name == "chart_agent" and node_output.get("chart_results"):
                    final_state.setdefault("chart_results", {}).update(
                        node_output["chart_results"]
                    )
                    final_state.setdefault("_completed_agents", []).append("chart_agent")
                    _render_streaming(placeholder)

                # Synthesizer
                if node_name == "synthesizer" and "final_response" in node_output:
                    final_state["final_response"] = node_output["final_response"]
                    final_state.setdefault("_completed_agents", []).append("synthesizer")
                    _render_streaming(placeholder)

                if "final_response" in node_output:
                    final_state["final_response"] = node_output["final_response"]
                if node_output.get("chart_results"):
                    final_state.setdefault("chart_results", {}).update(node_output["chart_results"])
                if "timings" in node_output:
                    final_state.setdefault("timings", {}).update(node_output.get("timings") or {})
                final_state[node_name] = node_output
        return final_state

    return asyncio.run(stream_results())


# ── Forecast expander cache loader ──────────────────────────────────────────

def _populate_forecast_expander_cache():
    """Pre-load data for the 3 forecast expanders (detail, model, baselines).

    Called once per session when forecast summary is first rendered.
    Stores in st.session_state.forecast_expander_cache so replay has no DB hit.
    """
    import base64 as _b64
    from tools.pipeline_queries import (
        get_forecast_drilldown_df,
        query_forecast_model_assessment,
    )

    cache = {}

    # 1. Forecast drilldown DataFrame
    try:
        cache["drilldown_df"] = get_forecast_drilldown_df()
    except Exception as e:
        logger.warning("[FORECAST CACHE] drilldown failed: %s", e)

    # Artifact PNGs live at project root (../artifacts/forecasting/ relative to demo/)
    _project_root = os.path.join(os.path.dirname(__file__), "..")

    def _resolve_artifact(rel_path: str) -> str:
        """Try relative to cwd first, then relative to project root."""
        if rel_path and os.path.isfile(rel_path):
            return rel_path
        alt = os.path.join(_project_root, rel_path)
        if os.path.isfile(alt):
            return alt
        return ""

    # 2. Model validation
    try:
        val = query_forecast_model_assessment(direction="validation")
        val_entry = {"content": val.get("content", "")}
        resolved = _resolve_artifact(val.get("artifact_path", ""))
        if resolved:
            with open(resolved, "rb") as f:
                val_entry["chart_b64"] = _b64.b64encode(f.read()).decode()
        cache["validation"] = val_entry
    except Exception as e:
        logger.warning("[FORECAST CACHE] validation failed: %s", e)

    # 3. Baseline comparison
    try:
        base = query_forecast_model_assessment(direction="baseline")
        base_entry = {"content": base.get("content", "")}
        resolved = _resolve_artifact(base.get("artifact_path", ""))
        if resolved:
            with open(resolved, "rb") as f:
                base_entry["chart_b64"] = _b64.b64encode(f.read()).decode()
        cache["baseline"] = base_entry
    except Exception as e:
        logger.warning("[FORECAST CACHE] baseline failed: %s", e)

    st.session_state.forecast_expander_cache = cache
    logger.info("[FORECAST CACHE] loaded: %s", list(cache.keys()))


# ── Inventory expander cache loader ─────────────────────────────────────────

# Safety stock policy text constants (from Jonathan's version)
_SS_FORMULA_TEXT = (
    "**S = μᴅ (r + μₗ) + z · "
    "√((r + μₗ) σᴅ² + μᴅ² σₗ²)**"
)
_SS_TERMS_TEXT = (
    "| Symbol | Definition |\n"
    "|---|---|\n"
    "| μᴅ | Average weekly component demand |\n"
    "| σᴅ | Demand standard deviation |\n"
    "| μₗ | Average lead time (weeks) |\n"
    "| σₗ | Lead time standard deviation |\n"
    "| r | Review period — **8 weeks** |\n"
    "| z | Service level factor — **≈1.65** for 95% target |"
)
_SS_BUSINESS_TEXT = (
    "- The formula computes the **base-stock level (S)** — the total inventory "
    "required to meet demand across the review period and lead time under uncertainty.\n"
    "- **Safety stock** is the buffer component embedded within this level, covering "
    "demand and lead-time variability.\n"
    "- In this system, safety stock is enforced as a **protected inventory floor** "
    "per facility × component. It is not consumed during planning.\n"
    "- Only inventory **above** this floor is used to satisfy weekly demand."
)
_SS_CYCLE_STOCK_TEXT = (
    "The base-stock level (S) has two distinct components:\n\n"
    "**1. Cycle Stock** — μᴅ × (r + μₗ)\n"
    "- Covers **expected demand** over the review period and lead time\n"
    "- This is the primary driver of inventory volume\n\n"
    "**2. Safety Stock** — z · √((r + μₗ)σᴅ² "
    "+ μᴅ²σₗ²)\n"
    "- Covers **uncertainty** in demand and lead time\n"
    "- This is a buffer — NOT intended to cover expected demand\n\n"
    "On-hand inventory at the start of planning is anchored at "
    "**S = Cycle Stock + Safety Stock**. "
    "Safety stock alone will often appear small relative to weekly demand — "
    "this is expected and correct."
)
_SS_PLANNING_TEXT = (
    "- Weekly procurement is triggered when **usable inventory** (above the safety "
    "stock floor) reaches zero.\n"
    "- Safety stock is already accounted for before any weekly demand calculations "
    "begin — it does not appear as a deduction in the weekly trigger table.\n"
    "- The weekly trigger table reflects how demand consumes usable inventory, "
    "not safety stock itself."
)
_TRIG_BULLETS_TEXT = (
    "- **Gross Requirement:** forecast-driven component demand for that week.\n"
    "- **Usable Inventory Before Demand:** inventory available after preserving "
    "the safety stock floor.\n"
    "- **Direct Procurement Needed:** portion of demand not covered by usable "
    "inventory.\n"
    "- **Cumulative Procurement Pressure:** total procurement required up to that "
    "week, per facility × component.\n"
    "- **Safety Stock Utilization (%):** how much of the safety buffer is being "
    "matched by cumulative procurement demand.\n"
    "- **Urgency Level:** qualitative indicator — Low / Medium / High / "
    "Critical — based on how close cumulative pressure is to the safety "
    "buffer.\n"
    "- Procurement is triggered when usable inventory reaches zero."
)


def _populate_inventory_expander_cache():
    """Pre-load data for the 3 inventory expanders."""
    import pandas as _pd_inv
    from tools.pipeline_queries import (
        query_triggered_rows_structured,
        query_full_horizon_drilldown,
    )

    cache = {}

    # 1. Triggered procurement rows
    try:
        raw = query_triggered_rows_structured()
        rows = raw.get("rows", [])
        cache["triggered_df"] = _pd_inv.DataFrame(rows) if rows else _pd_inv.DataFrame()
        cache["triggered_meta"] = {
            "run_id": raw.get("run_id", ""),
            "n_rows": len(rows),
        }
    except Exception as e:
        logger.warning("[INVENTORY CACHE] triggered rows failed: %s", e)

    # 2. Base stock policy — pure text, no data needed

    # 3. Full horizon drilldown
    try:
        raw = query_full_horizon_drilldown()
        rows = raw.get("rows", [])
        cache["full_horizon_df"] = _pd_inv.DataFrame(rows) if rows else _pd_inv.DataFrame()
        cache["full_horizon_meta"] = {
            "run_id": raw.get("run_id", ""),
            "horizon_start": raw.get("horizon_start", ""),
            "horizon_end": raw.get("horizon_end", ""),
            "n_weeks": raw.get("n_weeks", ""),
            "n_rows": len(rows),
        }
    except Exception as e:
        logger.warning("[INVENTORY CACHE] full horizon failed: %s", e)

    st.session_state.inventory_expander_cache = cache
    logger.info("[INVENTORY CACHE] loaded: %s", list(cache.keys()))


def _render_inventory_expanders():
    """Render 3 collapsed expanders below the procurement summary."""
    import pandas as _pd_inv2
    cache = st.session_state.get("inventory_expander_cache", {})
    if not cache:
        return

    # Expander 1: Triggered procurement rows
    trig_df = cache.get("triggered_df", _pd_inv2.DataFrame())
    trig_meta = cache.get("triggered_meta", {})
    with st.expander(
        "In which weeks and where is procurement actually triggered "
        "across the planning horizon?",
        expanded=False,
    ):
        if trig_meta:
            st.caption(f"Forecast run {trig_meta.get('run_id', '')}  ·  "
                       f"{trig_meta.get('n_rows', 0)} triggered rows")
        if not trig_df.empty:
            _df_t = trig_df.copy()
            # Filters
            _fac_opts_t = sorted(_df_t["Facility"].unique().tolist()) if "Facility" in _df_t.columns else []
            _comp_opts_t = sorted(_df_t["Component"].unique().tolist()) if "Component" in _df_t.columns else []
            _fc1, _fc2 = st.columns(2)
            with _fc1:
                _sel_fac_t = st.multiselect("Filter by Facility", _fac_opts_t, default=_fac_opts_t, key="inv_trig_fac")
            with _fc2:
                _sel_comp_t = st.multiselect("Filter by Component", _comp_opts_t, default=_comp_opts_t, key="inv_trig_comp")
            if _sel_fac_t and "Facility" in _df_t.columns:
                _df_t = _df_t[_df_t["Facility"].isin(_sel_fac_t)]
            if _sel_comp_t and "Component" in _df_t.columns:
                _df_t = _df_t[_df_t["Component"].isin(_sel_comp_t)]
            st.caption(f"{len(_df_t)} rows shown")
            _fmt = {c: "{:,.0f}" for c in _df_t.columns
                    if c not in ("Week", "Component", "Facility", "Triggered?")}
            st.dataframe(
                _df_t.style.format({c: v for c, v in _fmt.items() if c in _df_t.columns}),
                use_container_width=True, hide_index=True, height=500,
            )
        else:
            st.info("No triggered rows — all inventory positions appear sufficient.")
        st.markdown(_TRIG_BULLETS_TEXT)

    # Expander 2: Base Stock Policy
    with st.expander("Detail on Base Stock Policy", expanded=False):
        st.subheader("Inventory Policy — Safety Stock and Base-Stock Logic")
        st.markdown("**Base-Stock Formula**")
        st.markdown(_SS_FORMULA_TEXT)
        st.markdown("**Term Definitions**")
        st.markdown(_SS_TERMS_TEXT)
        st.markdown("**How It Works**")
        st.markdown(_SS_BUSINESS_TEXT)
        st.markdown("**Cycle Stock vs Safety Stock (Key Distinction)**")
        st.markdown(_SS_CYCLE_STOCK_TEXT)
        st.markdown("**Connection to Planning Outputs**")
        st.markdown(_SS_PLANNING_TEXT)

    # Expander 3: Full horizon drilldown
    fh_df = cache.get("full_horizon_df", _pd_inv2.DataFrame())
    fh_meta = cache.get("full_horizon_meta", {})
    with st.expander(
        "Show all upcoming demand weeks across each facility for inventory planning",
        expanded=False,
    ):
        if fh_meta:
            st.caption(
                f"Forecast run {fh_meta.get('run_id', '')}  ·  "
                f"{fh_meta.get('horizon_start', '')} → {fh_meta.get('horizon_end', '')}  ·  "
                f"{fh_meta.get('n_weeks', '')} weeks  ·  "
                f"{fh_meta.get('n_rows', 0):,} rows total"
            )
        if not fh_df.empty:
            _df_fh = fh_df.copy()
            _fac_opts_fh = sorted(_df_fh["Facility"].unique().tolist()) if "Facility" in _df_fh.columns else []
            _comp_opts_fh = sorted(_df_fh["Component"].unique().tolist()) if "Component" in _df_fh.columns else []
            _fc1_fh, _fc2_fh = st.columns(2)
            with _fc1_fh:
                _sel_fac_fh = st.multiselect("Filter by Facility", _fac_opts_fh, default=_fac_opts_fh, key="inv_fh_fac")
            with _fc2_fh:
                _sel_comp_fh = st.multiselect("Filter by Component", _comp_opts_fh, default=_comp_opts_fh, key="inv_fh_comp")
            if _sel_fac_fh and "Facility" in _df_fh.columns:
                _df_fh = _df_fh[_df_fh["Facility"].isin(_sel_fac_fh)]
            if _sel_comp_fh and "Component" in _df_fh.columns:
                _df_fh = _df_fh[_df_fh["Component"].isin(_sel_comp_fh)]
            st.caption(f"{len(_df_fh)} rows shown")
            _fmt = {c: "{:,.0f}" for c in _df_fh.columns
                    if c not in ("Week", "Component", "Facility", "Triggered?")}
            st.dataframe(
                _df_fh.style.format({c: v for c, v in _fmt.items() if c in _df_fh.columns}),
                use_container_width=True, hide_index=True, height=600,
            )
        else:
            st.info("No planning rows found for this forecast run.")


# ── Rich rendering dispatcher ───────────────────────────────────────────────

def _try_rich_render(key: str, content: str, structured) -> bool:
    """Try to render a pipeline result using rich Streamlit widgets.

    Returns True if rich rendering was used, False to fall back to st.code().
    """
    import pandas as pd

    if key == "forecast_summary" and structured:
        st.subheader("Production Demand Forecast")
        _render_forecast_summary_structured(structured)
        # Populate and render the 3 forecast expanders (detail, model, baselines)
        if not st.session_state.forecast_expander_cache:
            _populate_forecast_expander_cache()
        _render_forecast_expanders(key_suffix="live")
        return True

    if key == "component_requirements" and structured:
        _EXEC_NOTE = (
            "These totals represent BOM-implied component demand required to "
            "fulfill the finished-goods forecast across the planning horizon. "
            "Each finished unit consumes a defined mix of components, aggregated "
            "here across all facilities and forecast weeks. "
            "Inventory has not yet been netted out."
        )
        _BOM_XLATE_NOTE = (
            "- This step shows what components are required to build the products "
            "our customers are expecting.\n"
            "- Every finished unit requires a specific mix of inputs — the BOM "
            "defines how many units of each component are needed per SKU.\n"
            "- Multiplying that recipe by the forecasted demand yields the gross "
            "component requirements shown below.\n"
            "- These totals are calculated before any inventory has been considered."
        )
        meta = structured.get("horizon_meta", {})
        bom_rows = structured.get("bom_xlate_rows", [])

        if meta:
            st.subheader("Component Requirements — Full Horizon Gross Demand")
            st.markdown(_EXEC_NOTE)

            # Planning Window
            st.caption("Planning Window")
            df_window = pd.DataFrame([{
                "Forecast Start":  meta.get("start_date", ""),
                "Forecast End":    meta.get("end_date", ""),
                "Horizon Weeks":   meta.get("n_weeks", ""),
                "Forecast Run ID": meta.get("run_id", ""),
            }])
            st.dataframe(df_window, use_container_width=True, hide_index=True)

            # Aggregation Scope
            st.caption("Aggregation Scope")
            df_scope = pd.DataFrame([{
                "Facilities":      meta.get("n_facilities", ""),
                "Component Types": meta.get("n_components", ""),
                "Aggregation":     f"All {meta.get('n_facilities','')} facilities "
                                   f"× {meta.get('n_weeks','')} forecast weeks",
            }])
            st.dataframe(df_scope, use_container_width=True, hide_index=True)

            # Component totals with TOTAL row
            st.caption("Full-Horizon Gross Requirement by Component")
            comp_data = list(meta.get("rows", []))
            total = sum(v for _, v in comp_data)
            comp_data.append(("TOTAL", total))
            df_comp = pd.DataFrame(comp_data, columns=["Component", "Units Required"])
            st.dataframe(
                df_comp.style.format({"Units Required": "{:,.0f}"}),
                use_container_width=True, hide_index=True,
            )

            # BOM Translation expander
            if bom_rows:
                with st.expander(
                    "How forecasted semiconductor SKU demand translates into component demand",
                    expanded=False,
                ):
                    st.subheader("BOM Translation — How Finished Demand Becomes Component Demand")
                    st.caption(
                        "How each finished SKU's forecasted demand converts to gross "
                        "component demand across all facilities and forecast weeks"
                    )
                    df_bom = pd.DataFrame(bom_rows)
                    if not df_bom.empty:
                        fmt = {c: "{:,.0f}" for c in ["Forecast (units)", "Gross Component Demand"] if c in df_bom.columns}
                        if "Units / SKU" in df_bom.columns:
                            fmt["Units / SKU"] = "{:,.2f}"
                        st.dataframe(
                            df_bom.style.format(fmt),
                            height=420, use_container_width=True, hide_index=True,
                        )
                    st.markdown(_BOM_XLATE_NOTE)
            return True

        # Fallback: raw rows
        elif structured.get("rows"):
            st.subheader("Component Requirements — BOM Explosion")
            df = pd.DataFrame(structured["rows"])
            st.dataframe(df, use_container_width=True, hide_index=True, height=420)
            return True

    if key == "aggregated_procurement_need" and structured and structured.get("rows"):
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
        st.subheader("Net Component Procurement Requirement — Planning Horizon")
        st.caption(
            f"Horizon: {structured.get('horizon_start', '')} → "
            f"{structured.get('horizon_end', '')} ({structured.get('n_weeks', '')} weeks)"
        )
        st.markdown("All values are aggregated across the full planning horizon.")
        st.markdown(_PROC_BULLETS)
        df = pd.DataFrame(structured["rows"])
        fmt_cols = [c for c in df.columns if c != "Component"]
        st.dataframe(
            df.style.format({c: "{:,.0f}" for c in fmt_cols}),
            use_container_width=True, hide_index=True, height=300,
        )
        # Populate and render inventory expanders
        if not st.session_state.inventory_expander_cache:
            _populate_inventory_expander_cache()
        _render_inventory_expanders()
        return True

    if key == "triggered_procurement_rows" and structured and structured.get("rows"):
        st.subheader("Procurement Trigger Rows")
        st.caption(
            f"Weeks × facilities where net requirement > 0 — procurement is actually needed"
        )
        df = pd.DataFrame(structured["rows"])
        fmt_cols = [c for c in df.columns if c not in ("Forecast Week", "Week", "Component", "Facility")]
        st.dataframe(
            df.style.format({c: "{:,.0f}" for c in fmt_cols}),
            use_container_width=True, hide_index=True, height=500,
        )
        return True

    if key == "forecast_model_assessment" and content:
        _project_root = os.path.join(os.path.dirname(__file__), "..")
        # Detect direction from artifact path in content
        _title = "Forecast Model Assessment"
        _text = content if isinstance(content, str) else str(content)
        if "baseline" in _text.lower():
            _title = "Forecast Model — Baseline Comparison"
        elif "feature" in _text.lower() or "importance" in _text.lower():
            _title = "Forecast Model — Feature Importance"
        elif "validation" in _text.lower() or "holdout" in _text.lower():
            _title = "Forecast Model — Validation & Training Performance"
        st.subheader(_title)
        # Try to render artifact chart from structured data
        _artifact = (structured or {}).get("artifact_path", "") if isinstance(structured, dict) else ""
        for _try_path in [_artifact, os.path.join(_project_root, _artifact)] if _artifact else []:
            if os.path.isfile(_try_path):
                with open(_try_path, "rb") as f:
                    st.image(f.read())
                break
        st.markdown(_text)
        return True

    if key == "forecast_drilldown" and content:
        st.subheader("Forecast Detail — Facility & SKU Breakdown")
        _text = content if isinstance(content, str) else str(content)
        st.markdown(_text)
        return True

    if key == "procurement_status" and content:
        st.subheader("Inventory & Safety Stock Policy")
        _text = content if isinstance(content, str) else str(content)
        st.markdown(_text)
        return True

    return False


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

    agent_results = trace["agent_results"]
    pipeline_items = {k: v for k, v in agent_results.items()
                     if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")
                     and not k.endswith("__structured")}
    lp_items = {k: v for k, v in agent_results.items() if k.startswith("lp_")}
    is_lp_flow = bool(lp_items)

    # Build text content for message history
    parts = []
    if pipeline_items:
        pip_parts = [
            f"**{k.replace('_', ' ').title()}**\n\n```\n{v}\n```"
            for k, v in pipeline_items.items()
        ]
        parts.append("**Pipeline Results**\n\n" + "\n\n".join(pip_parts))

    data_result = agent_results.get("data_agent", "")
    if data_result:
        parts.append(data_result)
    risk_result = agent_results.get("risk_agent", "")
    if risk_result:
        parts.append("---\n\n**Geopolitical Risk Analysis**\n\n" + risk_result)
    if lp_items:
        lp_parts = [
            f"**{k.replace('lp_', '').replace('_', ' ').title()}**\n\n```\n{v}\n```"
            for k, v in lp_items.items()
        ]
        parts.append("---\n\n**LP Optimization Results**\n\n" + "\n\n".join(lp_parts))

    final_response = final_state.get("final_response", "")
    summary_text = ("---\n\n**Intelligence Summary**\n\n" + final_response) if final_response else ""
    combined = "\n\n".join(parts)

    with st.chat_message("assistant", avatar=CPU_AVATAR):
        # Pipeline items — rich rendering when structured data available
        if pipeline_items:
            _PIPELINE_EXPAND_DEFAULT = {
                "forecast_summary": True,
                "component_requirements": False,
                "procurement_status": False,
            }
            st.markdown(
                "<p style='font-family:Inter,sans-serif; font-size:0.6rem; letter-spacing:0.12em;"
                "text-transform:uppercase; color:#879580; margin:0 0 0.4rem;'>Pipeline Results</p>",
                unsafe_allow_html=True,
            )
            for key, content in pipeline_items.items():
                structured = agent_results.get(f"{key}__structured")
                try:
                    rendered = _try_rich_render(key, content, structured)
                except Exception as _re:
                    logger.warning(f"[RENDER] Rich render failed for {key}: {_re}")
                    rendered = False
                if not rendered:
                    label = key.replace("_", " ").title()
                    expanded = _PIPELINE_EXPAND_DEFAULT.get(key, False)
                    with st.expander(label, expanded=expanded):
                        st.code(str(content) if content else "(no content)", language=None)
        if data_result:
            st.markdown(data_result)
        if risk_result:
            st.markdown("---\n\n**Geopolitical Risk Analysis**\n\n" + risk_result)
        if lp_items:
            st.markdown("---")
            st.markdown(
                "<p style='font-family:Inter,sans-serif; font-size:0.6rem; letter-spacing:0.12em;"
                "text-transform:uppercase; color:#879580; margin:0 0 0.4rem;'>LP Optimization Results</p>",
                unsafe_allow_html=True,
            )
            for key, content in lp_items.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                with st.expander(f"Product: {product}", expanded=True):
                    st.code(content, language=None)
        chart_results = trace.get("chart_results") or {}
        if chart_results:
            st.markdown(
                f"<div style='margin:0.75rem 0 0.5rem;'>"
                + section_header("◎", "Visualizations", "#6CDD7F")
                + "</div>",
                unsafe_allow_html=True,
            )
            render_charts(chart_results)
        if summary_text:
            st.markdown(summary_text)

    st.session_state.messages.append({
        "role": "assistant",
        "content": combined,
        "summary": summary_text,
        "has_trace": True,
    })
    show_trace(trace)

    # Export button
    export_content = f"# Procurement Intelligence Report\n\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    if trace.get("intent"):
        export_content += f"**Query Intent:** {trace['intent']}\n\n---\n\n"
    if combined:
        export_content += combined + "\n\n"
    if final_response:
        export_content += "## Intelligence Summary\n\n" + final_response
    if export_content.strip():
        st.download_button(
            label="↓  Export Report",
            data=export_content,
            file_name=f"procurement_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            key=f"export_{len(st.session_state.traces)}",
        )

    return combined


def render_pending_plan():
    plan = st.session_state.pending_plan or {}
    tasks = plan.get("tasks", [])

    lp_tasks    = [t for t in tasks if t.get("agent") == "lp_agent"]
    other_tasks = [t for t in tasks if t.get("agent") not in ("lp_agent", "chart_agent")]
    is_lp_only  = len(lp_tasks) > 0 and len(other_tasks) == 0

    if is_lp_only:
        # Compact LP-only header
        st.markdown(
            f"<div style='{SECTION_STYLE}'>"
            + section_header("◬", "Procurement Optimization — Ready to Run", "#5AEB56")
            + "</div>",
            unsafe_allow_html=True,
        )
        for t in lp_tasks:
            params = t.get("params") or {}
            prod = (params.get("product") or "").replace("_", " ").title()
            lam = params.get("lambda_risk", 0.5)
            share = params.get("max_supplier_share", 1.0)
            st.markdown(f"**{prod}**  ·  λ = {lam}  ·  Max share: {share:.0%}")
    else:
        # Full plan card with intent + question + task cards
        question_html = ""
        if plan.get("question"):
            question_html = (
                "<div style='background:rgba(170,248,255,0.05); border:1px solid rgba(170,248,255,0.15);"
                "border-radius:0.25rem; padding:0.75rem 1rem; margin-bottom:1.25rem;'>"
                f"<p style='font-family:Manrope,sans-serif; font-size:0.875rem; color:#AAF8FF; margin:0;'>"
                f"{plan['question']}</p></div>"
            )

        st.markdown(
            f"<div style='{SECTION_STYLE}'>"
            "<div style='display:flex; align-items:center; gap:0.55rem; margin-bottom:1.25rem;'>"
            "<span style='font-size:1rem; color:#5AEB56;'>✦</span>"
            "<h2 style='font-family:Space Grotesk,sans-serif; font-size:1.2rem; font-weight:700;"
            "letter-spacing:-0.02em; color:#D0E8DA; margin:0;'>Intelligence Plan Ready</h2>"
            "</div>"
            "<div style='background:rgba(90,235,86,0.06); border:1px solid rgba(90,235,86,0.14);"
            "border-radius:0.25rem; padding:0.75rem 1rem; margin-bottom:1.25rem;'>"
            "<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
            "text-transform:uppercase; color:#879580; margin-bottom:0.3rem;'>Intent</p>"
            f"<p style='font-family:Manrope,sans-serif; font-size:0.9rem; color:#AEFFA0; margin:0;"
            f"font-weight:600;'>{plan.get('intent', '')}</p>"
            "</div>"
            + question_html
            + f"<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
            f"text-transform:uppercase; color:#879580; margin-bottom:0.75rem;'>"
            f"Work Orders — {len(tasks)} task{'s' if len(tasks) != 1 else ''}</p>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Task cards with agent-colored accents + business descriptions
        agent_accent = {
            "pipeline_agent": "#AEFFA0",
            "data_agent":     "#AAF8FF",
            "risk_agent":     "#78F5FF",
            "chart_agent":    "#6CDD7F",
            "lp_agent":       "#AEFFA0",
        }
        agent_label = {
            "pipeline_agent": "Pipeline",
            "data_agent":     "Data Explorer",
            "risk_agent":     "Risk Monitor",
            "chart_agent":    "Visualization",
            "lp_agent":       "Optimizer",
        }
        for i, task in enumerate(tasks):
            agent = task.get("agent", "")
            accent = agent_accent.get(agent, "#BCCBB4")
            tool_name = task.get("tool", "auto")
            display_label = agent_label.get(agent, agent)

            # Look up pre-written business description
            info = TOOL_PLAN_INFO.get(tool_name, {})
            if not info and agent:
                info = _AGENT_PLAN_INFO.get(agent, {})
            title = info.get("title", tool_name or "auto")
            desc = info.get("desc", "")

            desc_html = ""
            if desc:
                desc_html = (
                    f"<p style='font-family:Manrope,sans-serif; font-size:0.8rem;"
                    f"color:#A0B89A; margin:0.35rem 0 0 0; line-height:1.4;'>{desc}</p>"
                )

            st.markdown(
                "<div style='background:rgba(25,46,37,0.7); border:1px solid rgba(61,74,57,0.2);"
                "border-radius:0.25rem; padding:0.875rem 1.25rem; margin-bottom:0.4rem;'>"
                "<div style='display:flex; align-items:center; gap:0.5rem; margin-bottom:0.4rem;'>"
                f"<span style='font-family:Inter,sans-serif; font-size:0.55rem; letter-spacing:0.12em;"
                f"text-transform:uppercase; color:#879580;'>Task {i+1}</span>"
                f"<span style='font-family:Inter,sans-serif; font-size:0.55rem; font-weight:600;"
                f"letter-spacing:0.1em; text-transform:uppercase; color:{accent};"
                f"background:rgba(90,235,86,0.07); border:1px solid rgba(90,235,86,0.14);"
                f"padding:0.1rem 0.45rem; border-radius:0.125rem;'>{display_label}</span>"
                "</div>"
                f"<p style='font-family:Manrope,sans-serif; font-size:0.925rem; font-weight:600;"
                f"color:#D0E8DA; margin:0;'>{title}</p>"
                + desc_html
                + "</div>",
                unsafe_allow_html=True,
            )

    # Input + centered approve button
    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.text_input(
            "Modify the plan (optional)",
            key="plan_feedback",
            placeholder="Leave blank to approve as-is...",
        )
        if st.button("Approve & Execute", key="approve_plan", use_container_width=True):
            with st.spinner("Executing approved plan..."):
                feedback = st.session_state.plan_feedback.strip() or "ok"
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                final_state = stream_graph(Command(resume=feedback), config=config)

            lp_interrupt = final_state.get("__interrupt__")
            if lp_interrupt and lp_interrupt.get("type") == "lp_approval":
                st.session_state.waiting_for_lp_approval = True
                st.session_state.pending_lp_result = lp_interrupt
                st.session_state.lp_partial_state = final_state
                st.session_state.last_lp_raw_full = lp_interrupt.get("raw", {})
                st.session_state.saved_plan = plan
                st.session_state.waiting_for_approval = False
                st.session_state.pending_plan = None
                # Persist LP params for carry-forward
                for _pk, _rv in lp_interrupt.get("raw", {}).items():
                    _recap = _rv.get("params_recap", {})
                    if _recap:
                        _product = _recap.get("product", "")
                        if _product:
                            st.session_state.lp_params_history[_product] = _recap
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


def _run_lp_direct(params: dict) -> None:
    """Execute LP optimization without the orchestrator or LangGraph graph.

    Used by modify-mode to rerun LP with adjusted parameters.
    """
    import time as _time
    from tools.optimization import run_optimization

    product = params.get("product", "transistors")
    t0 = _time.perf_counter()
    logger.info("[LP DIRECT] params=%s", params)

    try:
        result = run_optimization(
            product=product,
            lambda_risk=params.get("lambda_risk", 0.5),
            max_supplier_share=params.get("max_supplier_share", 1.0),
            diversification_mode=params.get("diversification_mode", "none"),
            urgency=params.get("urgency", False),
            exclude_supplier_ids=params.get("exclude_supplier_ids") or [],
            budget_cap=params.get("budget_cap"),
            service_level_target=params.get("service_level_target", 1.0),
            compliance_threshold=params.get("compliance_threshold", 0.50),
            facility_id=params.get("facility_id"),
        )
        logger.info("[LP DIRECT] solve_elapsed=%.3fs", _time.perf_counter() - t0)
    except Exception as _e:
        logger.error("[LP DIRECT] LP solve failed: %s", _e, exc_info=True)
        st.error(f"LP optimization failed: {_e}")
        return

    result_key = f"lp_{product}"

    # Persist params for carry-forward
    params_recap = result.get("params_recap", {})
    if params_recap:
        st.session_state.lp_params_history[product] = params_recap

    lp_interrupt_payload = {
        "type": "lp_approval",
        "direct_mode": True,
        "raw": {result_key: result},
        "formatted": {result_key: ""},
    }

    st.session_state.waiting_for_lp_approval = True
    st.session_state.pending_lp_result = lp_interrupt_payload
    st.session_state.lp_partial_state = {}
    st.session_state.last_lp_raw_full = {result_key: result}
    st.session_state.saved_plan = {}
    st.rerun()


def render_lp_approval():
    """Show LP results and present Approve / Modify / Discard actions."""
    st.markdown('<div id="lp-result-top"></div>', unsafe_allow_html=True)

    lp_interrupt = st.session_state.pending_lp_result or {}
    raw = lp_interrupt.get("raw", {})
    partial = st.session_state.get("lp_partial_state") or {}
    is_direct = lp_interrupt.get("direct_mode", False)
    in_modify = st.session_state.get("lp_modify_mode", False)

    if in_modify:
        st.subheader("LP Optimization Results — Modify Mode")
        st.info("Describe your change in the input below and the scenario will rerun immediately.")
    else:
        st.subheader("LP Optimization Results — Pending Your Approval")

    _pending_labels = [k.replace("lp_", "").replace("_", " ").title() for k in raw.keys()]
    _render_procurement_status_bar(pending_products=_pending_labels)

    for product_key, result_dict in raw.items():
        product_label = product_key.replace("lp_", "").replace("_", " ").title()
        st.markdown(f"### {product_label}")
        _render_lp_result(result_dict)

    st.divider()
    if not in_modify:
        st.info("**Approve** to include in the session plan, **Modify** to refine, or **Discard** to exclude.")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Approve Recommendation", key="approve_lp_btn"):
            for result_dict in raw.values():
                _store_approved_run(result_dict)
            if is_direct:
                _approved = [k.replace("lp_", "").replace("_", " ").title() for k in raw]
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Procurement plan for **{', '.join(_approved)}** approved.",
                    "has_trace": False, "summary": "",
                })
            else:
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                with st.spinner("Finalizing..."):
                    second_state = stream_graph(Command(resume="approve"), config=config)
                merged = _merge_final_states(partial, second_state)
                finalize_execution(merged, fallback_plan=st.session_state.get("saved_plan", {}))

            st.session_state.waiting_for_lp_approval = False
            st.session_state.pending_lp_result = None
            st.session_state.lp_partial_state = {}
            st.session_state.saved_plan = {}
            st.session_state.lp_modify_mode = False
            st.session_state.lp_modify_baseline = {}
            st.rerun()

    with col2:
        if st.button("Modify Recommendation", key="modify_lp_btn"):
            if "lp_modify_baseline" not in st.session_state:
                st.session_state.lp_modify_baseline = {}
            for result_dict in raw.values():
                entry = _build_run_entry(result_dict)
                st.session_state.lp_modify_baseline[entry["product"]] = entry
            st.session_state.lp_modify_mode = True
            st.rerun()

    with col3:
        if st.button("Discard", key="discard_lp_btn"):
            if not is_direct:
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                with st.spinner("Discarding..."):
                    second_state = stream_graph(Command(resume="discard"), config=config)
                merged = _merge_final_states(partial, second_state)
                finalize_execution(merged, fallback_plan=st.session_state.get("saved_plan", {}))
            st.session_state.waiting_for_lp_approval = False
            st.session_state.pending_lp_result = None
            st.session_state.lp_partial_state = {}
            st.session_state.saved_plan = {}
            st.session_state.lp_modify_mode = False
            st.session_state.lp_modify_baseline = {}
            st.rerun()

    # Modify-mode chat input
    if in_modify:
        st.divider()
        _modify_prompt = st.chat_input(
            "Describe your modification (e.g. 'exclude SUP_HKG_38', 'expedite', 'diversify')…",
            key="lp_modify_chat_input",
        )
        if _modify_prompt:
            _base_params: dict = {}
            for _rv in raw.values():
                _base_params = dict(_rv.get("params_recap") or {})
                break
            if _base_params:
                _merged = merge_with_prior(_modify_prompt, _base_params)
                st.session_state.messages.append({
                    "role": "user", "content": _modify_prompt, "has_trace": False,
                })
                st.session_state._pending_scroll = "lp_result_top"
                with st.spinner("Rerunning optimization…"):
                    _run_lp_direct(_merged)
            else:
                st.warning("Unable to apply modifications — no parameter baseline found for this run.")


# ── Theme injection ──────────────────────────────────────────────────────────
inject_css()
render_header()

with st.sidebar:
    render_sidebar()


# ── View routing ─────────────────────────────────────────────────────────────

if st.session_state.current_view == "history":
    render_history_list()

elif st.session_state.current_view == "history_detail":
    render_history_detail(show_trace_fn=show_trace)

else:
    # ── current_view == "chat" ───────────────────────────────────────────

    # Message replay
    assistant_index = 0
    for _msg_loop_idx, msg in enumerate(st.session_state.messages):
        _avatar = USER_AVATAR if msg["role"] == "user" else CPU_AVATAR
        with st.chat_message(msg["role"], avatar=_avatar):
            _b64 = msg.get("chart_b64", "")
            if _b64 and msg.get("chart_first"):
                st.image(base64.b64decode(_b64))

            # Rich replay for trace-backed messages
            if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
                _trace = st.session_state.traces[assistant_index]
                _ar = _trace.get("agent_results", {})
                _pip = {k: v for k, v in _ar.items()
                        if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")
                        and not k.endswith("__structured")}


                # Pipeline results — rich rendering
                if _pip:
                    st.markdown(
                        "<p style='font-family:Inter,sans-serif; font-size:0.6rem; letter-spacing:0.12em;"
                        "text-transform:uppercase; color:#879580; margin:0 0 0.4rem;'>Pipeline Results</p>",
                        unsafe_allow_html=True,
                    )
                    for _pk, _pv in _pip.items():
                        _ps = _ar.get(f"{_pk}__structured")
                        try:
                            _rendered = _try_rich_render(_pk, _pv, _ps)
                        except Exception as _re:
                            logger.warning(f"[RENDER] Rich render failed for {_pk}: {_re}")
                            _rendered = False
                        if not _rendered:
                            _pl = _pk.replace("_", " ").title()
                            _pe = {"forecast_summary": True}.get(_pk, False)
                            with st.expander(_pl, expanded=_pe):
                                st.code(str(_pv) if _pv else "(no content)", language=None)

                # LP results — render with rich LP views
                _lp = {k: v for k, v in _ar.items() if k.startswith("lp_")}
                if _lp:
                    for _lk, _lv in _lp.items():
                        _product = _lk.replace("lp_", "").replace("_", " ").title()
                        if isinstance(_lv, dict):
                            st.markdown(f"### {_product}")
                            _render_lp_result(_lv)
                        elif _lv:
                            with st.expander(f"LP: {_product}", expanded=True):
                                st.code(str(_lv), language=None)

                # Data / risk agent text
                _da = _ar.get("data_agent", "")
                if _da:
                    st.markdown(_da)
                _ra = _ar.get("risk_agent", "")
                if _ra:
                    st.markdown("---\n\n**Geopolitical Risk Analysis**\n\n" + _ra)

                # Charts — 2-column grid
                chart_results = _trace.get("chart_results") or {}
                if chart_results:
                    st.markdown(
                        "<div style='margin:0.75rem 0 0.35rem;'>"
                        + section_header("◎", "Visualizations", "#6CDD7F")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
            else:
                # Non-trace messages: render content as-is
                if msg.get("content"):
                    st.markdown(msg["content"])

            if _b64 and not msg.get("chart_first"):
                st.image(base64.b64decode(_b64))
        if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
            show_trace(st.session_state.traces[assistant_index])
            assistant_index += 1

    # Scroll management
    _cur_msg_count = len(st.session_state.messages)
    _pending_scroll = st.session_state.get("_pending_scroll")
    if _pending_scroll:
        st.session_state._pending_scroll = None
        st.session_state._scroll_msg_count = _cur_msg_count
        if _pending_scroll == "exec_summary":
            _inject_scroll_to_anchor("exec-summary-top")
        elif _pending_scroll == "lp_result_top":
            _inject_scroll_to_anchor("lp-result-top")
    elif _cur_msg_count != st.session_state._scroll_msg_count:
        st.session_state._scroll_msg_count = _cur_msg_count
        _inject_scroll_to_bottom()

    # ── Main rendering logic ─────────────────────────────────────────────

    if not st.session_state.messages:
        render_landing()

    if st.session_state.get("show_executive_summary"):
        _render_executive_summary()

    elif st.session_state.waiting_for_lp_approval and st.session_state.pending_lp_result:
        render_lp_approval()

    elif st.session_state.waiting_for_approval and st.session_state.pending_plan:
        render_pending_plan()

    elif not st.session_state.waiting_for_approval and not st.session_state.waiting_for_lp_approval:
        # Persistent procurement status bar
        _render_procurement_status_bar()

        # Check for suggestion chip click, then fall back to typed input
        _suggested = st.session_state.pop("suggested_query", "") or ""
        prompt = _suggested or st.chat_input("Ask a sourcing query...")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar=USER_AVATAR):
                st.write(prompt)

            # ── All input goes through the Orchestrator ──────────────────
            with st.spinner("Initializing procurement matrix..."):
                thread_id = str(uuid.uuid4())
                st.session_state.thread_id = thread_id
                config = {"configurable": {"thread_id": thread_id}}
                result = asyncio.run(
                    graph.ainvoke({
                        "messages": [("user", prompt)],
                        "approved_lp_runs": st.session_state.approved_lp_runs,
                    }, config=config)
                )
                state = asyncio.run(graph.aget_state(config=config))

            plan = extract_plan(state)

            # ── Direct-response check (planner / out_of_scope) ────────
            # These tasks produce a final_response in the orchestrator and
            # should never show the work-order approval card.
            final_resp = ""
            if isinstance(result, dict):
                final_resp = result.get("final_response", "")

            _direct_agents = {"planner", "out_of_scope"}
            _plan_tasks = (plan or {}).get("tasks", []) if isinstance(plan, dict) else []
            _is_direct = _plan_tasks and all(
                t.get("agent") in _direct_agents for t in _plan_tasks
            )

            if state.next and plan and not _is_direct and not final_resp:
                # Normal task plan — show work-order approval card
                st.session_state.waiting_for_approval = True
                st.session_state.pending_plan = plan
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "Intelligence plan ready. Review the work orders below and approve when ready.",
                })
                st.rerun()
            else:
                # Graph completed (or planner/out_of_scope) — show text directly
                if final_resp:
                    with st.chat_message("assistant", avatar=CPU_AVATAR):
                        st.markdown(final_resp)
                    st.session_state.messages.append({
                        "role": "assistant", "content": final_resp,
                        "has_trace": False, "summary": "",
                    })
                    st.rerun()
