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
from ui.forecast_views import _render_forecast_summary_structured, _render_forecast_expanders, _render_csv_button
from ui.session_helpers import _store_approved_run, _merge_final_states
from ui.theme import (
    inject_css, FAVICON, LOGO_B64, USER_AVATAR, CPU_AVATAR,
    SECTION_STYLE, section_header, render_charts,
    render_header, render_sidebar, render_landing, render_architecture,
    render_data_pipeline,
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

# ── Demo Flow — pre-packaged prompts for end-to-end business cycle demo ────
# Each section has a label, short tag (for flowchart), and ordered prompt list.
# Prompts are consumed in order; once all prompts in a section are used,
# the flow advances to the next section.

DEMO_FLOW = [
    {
        "tag": "Initialization",
        "label": "Planning Initialization",
        "context": "Set the procurement objective — balancing cost efficiency against supply reliability across the 20-week horizon.",
        "prompts": [
            ("Plan Procurement",
             "Help me plan procurement for the upcoming 20 week planning horizon "
             "with a balance between cost and reliability."),
        ],
    },
    {
        "tag": "Forecast",
        "label": "Demand Forecasting",
        "context": "Begin by understanding the demand landscape — what products are needed, where, and when across the planning horizon.",
        "prompts": [
            ("Yes, Proceed",
             "Yes, proceed"),
        ],
    },
    {
        "tag": "BOM",
        "label": "BOM Requirements",
        "context": "Translate finished-goods demand into raw component requirements using Bill of Materials recipes.",
        "prompts": [
            ("Component Requirements",
             "Show total component requirements for the upcoming demand window."),
        ],
    },
    {
        "tag": "Inventory",
        "label": "Inventory Planning",
        "context": "Factor in existing inventory to identify the net procurement gap — where and when orders are actually needed.",
        "prompts": [
            ("Net Procurement Need",
             "After our inventory is factored in, what is the total amount that needs to be "
             "ordered for each component to meet our upcoming demand?"),
        ],
    },
    {
        "tag": "LP — IC",
        "label": "LP: IC Components",
        "context": "Optimize supplier allocation for integrated circuit components, balancing cost against supply risk.",
        "prompts": [
            ("Optimize IC Components",
             "From our available suppliers, provide a procurement plan to ensure we have enough "
             "integrated circuit components across all facilities to meet our upcoming demand window. "
             "Implement a moderate risk aversion supply strategy. "
             "No supplier should exceed 40% of total supply volume for this order."),
        ],
    },
    {
        "tag": "LP — Trans",
        "label": "LP: Transistors",
        "context": "Run a second optimization round for transistors and explore what-if scenarios for supply disruption.",
        "prompts": [
            ("Optimize Transistors",
             "From our available suppliers, provide a procurement plan to ensure we have enough "
             "transistors across all facilities to meet our upcoming demand window. "
             "Implement a moderate risk aversion supply strategy. "
             "No supplier should exceed 35% of total supply volume for this order."),
        ],
    },
    {
        "tag": "Summary",
        "label": "Executive Summary",
        "context": "Consolidate all findings into a board-ready procurement recommendation.",
        "prompts": [
            ("Complete Plan",
             "Complete Procurement Plan"),
        ],
    },
]

# Stepper advancement — maps a tool/agent to the DEMO_FLOW stage it completes.
# Stage indices (must match DEMO_FLOW order):
#   0 Initialization | 1 Forecast | 2 BOM | 3 Inventory
#   4 LP-IC          | 5 LP-Trans | 6 Summary
_TOOL_TO_STAGE = {
    # Forecast
    "query_forecast_summary": 1,
    "query_forecast_drilldown": 1,
    "query_forecast_model_assessment": 1,
    # BOM
    "query_component_requirements": 2,
    "query_bom_translation": 2,
    "query_bom_translation_explainer": 2,
    # Inventory
    "query_procurement_status": 3,
    "query_procurement_planning_summary": 3,
    "query_aggregated_procurement_need": 3,
    "query_procurement_drilldown": 3,
    "query_procurement_summary_data": 3,
    "query_triggered_procurement_rows": 3,
    "query_triggered_rows_structured": 3,
    "query_full_horizon_drilldown": 3,
}


def _advance_stage(completed_stage: int) -> None:
    """Mark a stage as completed. Set-based tracking lets skipped stages
    stay visually uncompleted (e.g. if user jumps straight to Summary
    after IC without running Trans, LP-Trans is NOT falsely marked ✓).
    """
    completed = st.session_state.get("demo_completed_stages")
    if completed is None:
        completed = set()
        st.session_state.demo_completed_stages = completed
    completed.add(completed_stage)
    st.session_state.demo_prompt = 0


def _demo_current_stage() -> int | None:
    """First uncompleted stage, or None if demo has ended.

    Summary (final stage) completing ends the demo — any stages skipped
    along the way remain uncompleted but the demo is over.
    """
    completed = st.session_state.get("demo_completed_stages", set())
    final_idx = len(DEMO_FLOW) - 1
    if final_idx in completed:
        return None
    for i in range(len(DEMO_FLOW)):
        if i not in completed:
            return i
    return None


def _infer_stage_from_plan(plan) -> int | None:
    """Inspect plan.tasks → return the highest stage represented, or None.

    Planner → 0. Known forecast/BOM/inventory tool → 1/2/3. LP agent →
    4 (IC) or 5 (Transistor) based on the `product` param.
    """
    if not isinstance(plan, dict):
        return None
    completed = set()
    for task in plan.get("tasks", []) or []:
        agent = task.get("agent")
        tool = task.get("tool")
        params = task.get("params") or {}
        if agent == "planner":
            completed.add(0)
        elif tool in _TOOL_TO_STAGE:
            completed.add(_TOOL_TO_STAGE[tool])
        elif agent == "lp_agent":
            product = (params.get("product") or "").lower()
            completed.add(5 if "trans" in product else 4)
    return max(completed) if completed else None


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

# Demo flow progress: tracks which section/prompt we're at
if "demo_completed_stages" not in st.session_state:
    st.session_state.demo_completed_stages = set()
if "demo_prompt" not in st.session_state:
    st.session_state.demo_prompt = 0


# ── Demo flow rendering ─────────────────────────────────────────────────────

def render_demo_flowchart():
    """Render horizontal business-cycle flowchart showing current position."""
    completed = st.session_state.get("demo_completed_stages", set())
    current = _demo_current_stage()
    tags = [s["tag"] for s in DEMO_FLOW]

    nodes = ""
    for i, tag in enumerate(tags):
        if i in completed:
            # Completed
            border = "#76b900"
            text_color = "#76b900"
            bg = "#0A1F17"
            icon = "✓ "
            opacity = "0.5"
            is_current = False
        elif current is not None and i == current:
            # Current
            border = "#76b900"
            text_color = "#ffffff"
            bg = "rgba(118,185,0,0.12)"
            icon = "● "
            opacity = "1"
            is_current = True
        else:
            # Upcoming OR skipped (both render the same — greyed out)
            border = "#333333"
            text_color = "#555555"
            bg = "transparent"
            icon = ""
            opacity = "0.6"
            is_current = False

        # Current step gets a subtle glow border
        border_w = "2px" if is_current else "1px"
        shadow = "box-shadow:0 0 12px rgba(118,185,0,0.25);" if is_current else ""

        node = (
            f"<div style='display:flex; flex-direction:column; align-items:center;"
            f"opacity:{opacity};'>"
            f"<div style='background:{bg}; border:{border_w} solid {border}; border-radius:2px;"
            f"padding:0.45rem 1rem; white-space:nowrap; {shadow}'>"
            f"<span style='font-family:Inter,sans-serif; font-size:0.78rem; font-weight:700;"
            f"color:{text_color}; text-transform:uppercase; letter-spacing:0.08em;'>"
            f"{icon}{tag}</span>"
            f"</div></div>"
        )
        if i > 0:
            # Arrow is green if the previous stage is completed (flow passed through)
            arrow_color = "#76b900" if (i - 1) in completed else "#333333"
            arrow = (
                f"<span style='color:{arrow_color}; font-size:1.1rem; margin:0 6px;"
                f"align-self:center;'>→</span>"
            )
            nodes += arrow
        nodes += node

    st.markdown(
        f"<div style='display:flex; align-items:center; justify-content:center;"
        f"gap:0; padding:0.75rem 0 1rem; overflow-x:auto;'>{nodes}</div>",
        unsafe_allow_html=True,
    )


def render_demo_buttons():
    """Render prompt buttons for the current demo section."""
    sec_idx = _demo_current_stage()
    prompt_idx = st.session_state.get("demo_prompt", 0)

    if sec_idx is None:
        st.markdown(
            "<p style='text-align:center; font-family:Inter,sans-serif; font-size:0.7rem;"
            "color:#76b900; text-transform:uppercase; letter-spacing:0.1em; margin:0.5rem 0;'>"
            "✓ Demo Complete</p>",
            unsafe_allow_html=True,
        )
        return

    # Summary stage has no demo button — the Complete action lives in the
    # Procurement Status bar (Complete Procurement Plan) which is the only
    # path that actually triggers show_executive_summary. Rendering another
    # button here duplicates the control and confuses users.
    if sec_idx == len(DEMO_FLOW) - 1:
        return

    section = DEMO_FLOW[sec_idx]
    remaining = section["prompts"][prompt_idx:]

    if not remaining:
        # Should not happen with single-prompt stages; reset and retry.
        st.session_state.demo_prompt = 0
        return

    # Section label
    st.markdown(
        f"<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
        f"text-transform:uppercase; color:#888888; margin:0.4rem 0 0.3rem; text-align:center;'>"
        f"{section['label']} — Step {prompt_idx + 1} of {len(section['prompts'])}</p>",
        unsafe_allow_html=True,
    )

    # Context card
    if section.get("context"):
        st.markdown(
            f"<div style='background:#0A1F17; border-left:2px solid #76b900; border-radius:2px;"
            f"padding:0.6rem 1rem; margin:0.3rem 0 0.5rem;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.8rem; color:#cccccc;"
            f"margin:0; line-height:1.55; font-weight:300; font-style:italic;'>"
            f"{section['context']}</p></div>",
            unsafe_allow_html=True,
        )

    # Show only the NEXT button (one at a time, sequential)
    # Button click only injects the canned prompt — stepper advances
    # only after the AI actually runs the corresponding tool (see
    # `_advance_stage_from_plan` call sites).
    label, query = remaining[0]
    _cols = st.columns([1, 2, 1])
    with _cols[1]:
        btn_key = f"demo_{sec_idx}_{prompt_idx}_{label[:12]}"
        if st.button(label, key=btn_key, use_container_width=True):
            st.session_state.suggested_query = query
            st.rerun()


# ── Graph execution helpers ──────────────────────────────────────────────────

def render_progress_panel(trace):
    """Persistent Active Engine Progress panel — rendered after streaming
    completes. Sits above the Execution Trace in both live and replay views.
    Reads `trace["tasks"]` (from orchestrator plan) and `trace["timings"]`
    (agent wall-clock seconds). All planned agents render as completed (✓)
    with their final timing."""
    tasks = trace.get("tasks") or []
    timings = trace.get("timings") or {}
    planned = {t.get("agent") for t in tasks if t.get("agent")}
    if planned & _SYNTH_TRIGGERS:
        planned = planned | {"synthesizer"}
    label_map = dict(AGENT_STEPS)

    phase_eyebrow = (
        "font-family:'Inter',sans-serif; font-size:0.58rem;"
        "letter-spacing:0.18em; text-transform:uppercase; color:#888888;"
        "margin:0.85rem 0 0.35rem; padding:0; font-weight:600;"
    )
    body = ""
    for phase_label, agent_keys in PHASE_GROUPS:
        phase_agents = [a for a in agent_keys if a in planned]
        if not phase_agents:
            continue
        body += f"<p style=\"{phase_eyebrow}\">{phase_label}</p>"
        for agent_key in phase_agents:
            label = label_map.get(agent_key, agent_key)
            secs = timings.get(agent_key)
            time_html = (
                f"<span style='font-family:\"Space Grotesk\",sans-serif;"
                f"font-size:0.72rem; font-weight:700; color:#76b900;"
                f"margin-left:auto; white-space:nowrap;'>{secs:.2f}s</span>"
                if isinstance(secs, (int, float)) else ""
            )
            body += (
                f"<div style='display:flex; align-items:center; gap:0.75rem;"
                f"padding:0.35rem 0;'>"
                f"<span style='color:#76b900; flex-shrink:0;'>✓</span>"
                f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                f"color:#FFFFFF;'>{label}</span>"
                f"{time_html}"
                f"</div>"
            )

    if not body:
        return

    st.markdown(
        f"<div style='{SECTION_STYLE}'>"
        + section_header("—", "Active Engine Progress", "#76b900")
        + body
        + "</div>",
        unsafe_allow_html=True,
    )


def show_trace(trace):
    """Render an expandable Execution Trace — vertical animated architecture flowchart."""
    import json as _json
    import streamlit.components.v1 as components
    from collections import OrderedDict

    timings = trace.get("timings") or {}
    tasks = trace.get("tasks") or []

    # All possible agents in execution order
    all_agents = ["orchestrator", "pipeline_agent", "data_agent", "risk_agent",
                  "chart_agent", "lp_agent", "synthesizer"]
    ran = set(a for a in all_agents if timings.get(a) is not None)
    total_time = sum(timings.get(a, 0) for a in all_agents)

    agent_labels = {
        "orchestrator": "Orchestrator", "pipeline_agent": "Pipeline Agent",
        "data_agent": "Data", "risk_agent": "Risk",
        "chart_agent": "Chart", "lp_agent": "LP Optimizer",
        "synthesizer": "Synthesizer",
    }

    # Group tasks by agent
    agent_tasks = OrderedDict()
    for t in tasks:
        ag = t.get("agent", "unknown")
        agent_tasks.setdefault(ag, []).append(t)

    # Build tool/param info per agent
    agent_tool_info = {}
    for agent_key in all_agents:
        tools_list = []
        for t in agent_tasks.get(agent_key, []):
            tool_name = t.get("tool", "")
            if not tool_name:
                continue
            tool_dur = timings.get(f"{agent_key}.{tool_name}")
            params_raw = t.get("params") or t.get("params_json")
            param_str = ""
            if params_raw and agent_key == "lp_agent":
                if isinstance(params_raw, str):
                    try:
                        params_raw = _json.loads(params_raw)
                    except Exception:
                        params_raw = {}
                if isinstance(params_raw, dict):
                    parts = []
                    for pk in ["product", "lambda_risk", "max_supplier_share",
                               "diversification_mode", "urgency"]:
                        if pk in params_raw and params_raw[pk] is not None:
                            parts.append(f"{pk}={params_raw[pk]}")
                    param_str = ", ".join(parts)
            tools_list.append({
                "name": tool_name,
                "dur": round(tool_dur, 2) if tool_dur is not None else None,
                "params": param_str,
            })
        if agent_key == "synthesizer" and not tools_list and agent_key in ran:
            tools_list.append({"name": "generate_summary", "dur": None, "params": ""})
        agent_tool_info[agent_key] = tools_list

    # Build JSON data for the canvas
    trace_data = {
        "intent": trace.get("intent", ""),
        "totalTime": round(total_time, 2),
        "agents": {},
    }
    for a in all_agents:
        trace_data["agents"][a] = {
            "label": agent_labels.get(a, a),
            "active": a in ran,
            "time": round(timings.get(a, 0), 2),
            "tools": agent_tool_info.get(a, []),
        }

    trace_json = _json.dumps(trace_data)

    count = len([a for a in ran if a != "orchestrator"])
    title = f"Execution Trace ({count} agent{'s' if count != 1 else ''}, {total_time:.1f}s)"

    html_string = f'''<!DOCTYPE html>
<html><head><style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0A1F17; overflow:hidden; font-family:Inter,system-ui,-apple-system,sans-serif; }}
canvas {{ display:block; }}
#tooltip {{
  position:absolute; display:none; pointer-events:none;
  background:rgba(10,31,23,0.95); border:1px solid #76b900; border-radius:3px;
  padding:8px 12px; font-size:11px; color:#ccc; max-width:240px;
  box-shadow:0 4px 20px rgba(0,0,0,0.5); z-index:10;
}}
#tooltip .tt-label {{ color:#fff; font-weight:700; font-size:12px; text-transform:uppercase;
  letter-spacing:0.06em; margin-bottom:4px; }}
#tooltip .tt-time {{ color:#76b900; font-size:11px; margin-bottom:4px; }}
#tooltip .tt-tool {{ color:#aaa; font-size:10px; margin-top:2px; }}
#tooltip .tt-param {{ color:#888; font-size:9px; margin-left:8px; }}
</style></head><body>
<canvas id="c"></canvas>
<div id="tooltip"></div>
<script>
const DATA = {trace_json};
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const tooltip = document.getElementById("tooltip");
const DPR = window.devicePixelRatio || 1;
const ACCENT = "118,185,0";
const TAU = Math.PI * 2;

let W, H;
function resize() {{
  W = canvas.parentElement.clientWidth || 800;
  H = 520;
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}}
resize();

// ── Layout: VERTICAL top-to-bottom ──
const NODE_W = 110, NODE_H = 36, NODE_R = 3;
const ORCH_SUB_W = 90, ORCH_SUB_H = 30;
const ROW_GAP = 70;
const COL_GAP = 20;
const centerX = W / 2;

// Row Y positions
const R = {{
  user: 30,
  orch: 30 + ROW_GAP,
  phase1: 30 + ROW_GAP * 2,
  phase2: 30 + ROW_GAP * 3,
  synth: 30 + ROW_GAP * 4,
  resp: 30 + ROW_GAP * 5,
}};

// Node definitions: id, label, cx, cy, w, h, agentKey
const nodes = [
  // Row 0: User
  {{ id:"user", label:"User Input", cx:centerX, cy:R.user, w:NODE_W, h:NODE_H, agentKey:null }},
  // Row 1: Orchestrator (3 sub-nodes horizontal)
  {{ id:"orch_classify", label:"LLM Classify", cx:centerX-ORCH_SUB_W-COL_GAP, cy:R.orch, w:ORCH_SUB_W, h:ORCH_SUB_H, agentKey:"orchestrator" }},
  {{ id:"orch_fewshot",  label:"Few-Shot", cx:centerX, cy:R.orch, w:ORCH_SUB_W, h:ORCH_SUB_H, agentKey:"orchestrator" }},
  {{ id:"orch_extract",  label:"Param Extract", cx:centerX+ORCH_SUB_W+COL_GAP, cy:R.orch, w:ORCH_SUB_W, h:ORCH_SUB_H, agentKey:"orchestrator" }},
  // Row 2: Phase 1 (3 parallel)
  {{ id:"pipeline_agent", label:"Pipeline Agent", cx:centerX-(NODE_W+COL_GAP), cy:R.phase1, w:NODE_W, h:NODE_H, agentKey:"pipeline_agent" }},
  {{ id:"data_agent",     label:"Data Agent", cx:centerX, cy:R.phase1, w:NODE_W, h:NODE_H, agentKey:"data_agent" }},
  {{ id:"risk_agent",     label:"Risk Agent", cx:centerX+(NODE_W+COL_GAP), cy:R.phase1, w:NODE_W, h:NODE_H, agentKey:"risk_agent" }},
  // Row 3: Phase 2 (2 parallel)
  {{ id:"chart_agent", label:"Chart Builder", cx:centerX-(NODE_W/2+COL_GAP/2), cy:R.phase2, w:NODE_W, h:NODE_H, agentKey:"chart_agent" }},
  {{ id:"lp_agent",    label:"LP Optimizer", cx:centerX+(NODE_W/2+COL_GAP/2), cy:R.phase2, w:NODE_W, h:NODE_H, agentKey:"lp_agent" }},
  // Row 4: Synthesizer
  {{ id:"synthesizer", label:"Synthesizer", cx:centerX, cy:R.synth, w:NODE_W, h:NODE_H, agentKey:"synthesizer" }},
  // Row 5: Response
  {{ id:"response", label:"Response", cx:centerX, cy:R.resp, w:NODE_W, h:NODE_H, agentKey:null }},
];

// Add x, y computed from cx, cy
nodes.forEach(n => {{
  n.x = n.cx - n.w / 2;
  n.y = n.cy - n.h / 2;
  n.active = (n.agentKey === null) || (DATA.agents[n.agentKey] && DATA.agents[n.agentKey].active);
}});

const nodeMap = {{}};
nodes.forEach(n => nodeMap[n.id] = n);

// Row index for animation stagger
const rowOf = {{ user:0, orch_classify:1, orch_fewshot:1, orch_extract:1,
  pipeline_agent:2, data_agent:2, risk_agent:2,
  chart_agent:3, lp_agent:3, synthesizer:4, response:5 }};

// Edges: dynamically built based on which agents actually ran
// Static structure edges
const EDGE_DEFS = [
  ["user","orch_classify"], ["user","orch_fewshot"], ["user","orch_extract"],
  ["orch_classify","pipeline_agent"], ["orch_fewshot","data_agent"], ["orch_extract","risk_agent"],
  ["pipeline_agent","chart_agent"], ["pipeline_agent","lp_agent"],
  ["data_agent","chart_agent"], ["data_agent","lp_agent"],
  ["risk_agent","chart_agent"], ["risk_agent","lp_agent"],
  ["chart_agent","synthesizer"], ["lp_agent","synthesizer"],
  ["synthesizer","response"],
];
// Dynamic shortcut edges based on which agents actually ran
const p1ids = ["pipeline_agent","data_agent","risk_agent"];
const p2ids = ["chart_agent","lp_agent"];
const p1Active = p1ids.some(id => nodeMap[id].active);
const p2Active = p2ids.some(id => nodeMap[id].active);
const synthActive = nodeMap["synthesizer"].active;
// Phase 2 active but NO Phase 1: Orchestrator → Phase 2 directly
if (p2Active && !p1Active) {{
  p2ids.forEach(id => {{ if (nodeMap[id].active) EDGE_DEFS.push(["orch_extract", id]); }});
}}
// Phase 1 active but NO Phase 2: Phase 1 → Synthesizer or Response
if (p1Active && !p2Active && synthActive) {{
  p1ids.forEach(id => {{ if (nodeMap[id].active) EDGE_DEFS.push([id, "synthesizer"]); }});
}}
if (p1Active && !p2Active && !synthActive) {{
  p1ids.forEach(id => {{ if (nodeMap[id].active) EDGE_DEFS.push([id, "response"]); }});
}}
// Phase 2 active but Synthesizer not: Phase 2 → Response directly
if (p2Active && !synthActive) {{
  p2ids.forEach(id => {{ if (nodeMap[id].active) EDGE_DEFS.push([id, "response"]); }});
}}

const edges = EDGE_DEFS.map(([fid, tid]) => {{
  const a = nodeMap[fid], b = nodeMap[tid];
  if (!a || !b) return null;
  return {{
    x1: a.cx, y1: a.cy + a.h / 2,
    x2: b.cx, y2: b.cy - b.h / 2,
    active: a.active && b.active,
    fromRow: rowOf[fid] || 0,
  }};
}}).filter(Boolean);

// Flowing particles
const particles = [];
edges.forEach(e => {{
  if (!e.active) return;
  for (let i = 0; i < 2; i++) {{
    particles.push({{ edge:e, offset:i/2, speed:0.35+Math.random()*0.3 }});
  }}
}});

// ── Orchestrator group box ──
const orchActive = DATA.agents.orchestrator && DATA.agents.orchestrator.active;
const orchTime = orchActive ? DATA.agents.orchestrator.time : 0;

// ── Drawing ──
function drawRR(x,y,w,h,r) {{
  ctx.beginPath();
  ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.arcTo(x+w,y,x+w,y+r,r);
  ctx.lineTo(x+w,y+h-r); ctx.arcTo(x+w,y+h,x+w-r,y+h,r);
  ctx.lineTo(x+r,y+h); ctx.arcTo(x,y+h,x,y+h-r,r);
  ctx.lineTo(x,y+r); ctx.arcTo(x,y,x+r,y,r); ctx.closePath();
}}
function clamp(v,lo,hi) {{ return Math.max(lo,Math.min(hi,v)); }}
function easeOut(t) {{ return 1-Math.pow(1-t,3); }}

// ── Hover ──
let hoverNode = null;
canvas.addEventListener("mousemove", function(evt) {{
  const rect = canvas.getBoundingClientRect();
  const mx = evt.clientX - rect.left, my = evt.clientY - rect.top;
  hoverNode = null;
  for (const n of nodes) {{
    if (mx >= n.x && mx <= n.x+n.w && my >= n.y && my <= n.y+n.h) {{ hoverNode = n; break; }}
  }}
  if (hoverNode) {{
    let html = '<div class="tt-label">' + hoverNode.label + '</div>';
    const key = hoverNode.agentKey;
    if (key && DATA.agents[key]) {{
      const ag = DATA.agents[key];
      if (ag.time > 0) html += '<div class="tt-time">' + ag.time.toFixed(2) + 's</div>';
      ag.tools.forEach(t => {{
        let line = t.name + '()';
        if (t.dur !== null) line += ' ✓ ' + t.dur.toFixed(2) + 's';
        html += '<div class="tt-tool">' + line + '</div>';
        if (t.params) html += '<div class="tt-param">' + t.params + '</div>';
      }});
      if (!ag.active) html += '<div class="tt-tool" style="color:#555">— not invoked —</div>';
    }}
    if (hoverNode.id === "user") html += '<div class="tt-tool">Intent: ' + (DATA.intent||"—") + '</div>';
    if (hoverNode.id === "response") html += '<div class="tt-time">Total: ' + DATA.totalTime.toFixed(2) + 's</div>';
    tooltip.innerHTML = html;
    tooltip.style.display = "block";
    let tx = mx + 14, ty = my - 10;
    if (tx + 240 > W) tx = mx - 250;
    if (ty + 100 > H) ty = my - 100;
    tooltip.style.left = tx + "px";
    tooltip.style.top = ty + "px";
  }} else {{ tooltip.style.display = "none"; }}
}});
canvas.addEventListener("mouseleave", () => {{ tooltip.style.display = "none"; }});

// ── Main loop ──
const ANIM_DUR = 2800;
let startTime = null;

function draw(ts) {{
  if (!startTime) startTime = ts;
  const elapsed = ts - startTime;
  const progress = clamp(elapsed / ANIM_DUR, 0, 1);

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#0A1F17";
  ctx.fillRect(0, 0, W, H);

  // ── Orchestrator group box (dashed) ──
  const orchNs = nodes.filter(n => n.agentKey === "orchestrator");
  if (orchNs.length) {{
    const pad = 12;
    const gx = Math.min(...orchNs.map(n=>n.x)) - pad;
    const gy = Math.min(...orchNs.map(n=>n.y)) - 22;
    const gw = Math.max(...orchNs.map(n=>n.x+n.w)) - gx + pad;
    const gh = Math.max(...orchNs.map(n=>n.y+n.h)) - gy + pad;
    const gAlpha = easeOut(clamp(progress*3,0,1));
    ctx.save();
    ctx.globalAlpha = gAlpha * (orchActive ? 0.12 : 0.04);
    drawRR(gx, gy, gw, gh, 4);
    ctx.fillStyle = orchActive ? "#76b900" : "#333";
    ctx.fill();
    ctx.globalAlpha = gAlpha * (orchActive ? 0.45 : 0.12);
    ctx.setLineDash([5,3]); ctx.strokeStyle = orchActive ? "#76b900" : "#333"; ctx.lineWidth = 1;
    ctx.stroke(); ctx.setLineDash([]);
    ctx.globalAlpha = gAlpha * (orchActive ? 0.65 : 0.25);
    ctx.font = "700 9px Inter,sans-serif"; ctx.fillStyle = orchActive ? "#76b900" : "#555";
    ctx.textAlign = "left";
    ctx.fillText("ORCHESTRATOR" + (orchActive ? "  " + orchTime.toFixed(2) + "s" : ""), gx+6, gy+12);
    ctx.restore();
  }}

  // ── Phase labels ──
  const phases = [
    {{ y:R.phase1, label:"PHASE 1 — PARALLEL" }},
    {{ y:R.phase2, label:"PHASE 2 — PARALLEL" }},
  ];
  phases.forEach(pl => {{
    const a = easeOut(clamp((progress-0.15)*3,0,1));
    ctx.save(); ctx.globalAlpha = a*0.35;
    ctx.font = "700 8px Inter,sans-serif"; ctx.fillStyle = "#76b900";
    ctx.textAlign = "center";
    ctx.fillText(pl.label, centerX, pl.y - NODE_H/2 - 10);
    ctx.restore();
  }});

  // ── Draw edges ──
  edges.forEach(e => {{
    const delay = e.fromRow * 0.12;
    const ep = easeOut(clamp((progress - delay) / 0.25, 0, 1));
    if (ep <= 0) return;

    const mx = (e.x1 + e.x2) / 2;
    const my = (e.y1 + e.y2) / 2;

    ctx.beginPath();
    ctx.moveTo(e.x1, e.y1);
    if (ep < 1) {{
      const steps = 20;
      for (let i = 1; i <= Math.floor(steps*ep); i++) {{
        const t = i/steps, u = 1-t;
        const px = u*u*u*e.x1 + 3*u*u*t*e.x1 + 3*u*t*t*e.x2 + t*t*t*e.x2;
        const py = u*u*u*e.y1 + 3*u*u*t*my + 3*u*t*t*my + t*t*t*e.y2;
        ctx.lineTo(px, py);
      }}
    }} else {{
      ctx.bezierCurveTo(e.x1, my, e.x2, my, e.x2, e.y2);
    }}
    ctx.strokeStyle = e.active ? "rgba("+ACCENT+",0.3)" : "rgba(51,51,51,0.2)";
    ctx.lineWidth = e.active ? 1.5 : 0.7;
    ctx.stroke();
  }});

  // ── Flowing particles ──
  if (progress > 0.25) {{
    const pAlpha = clamp((progress-0.25)/0.15, 0, 1);
    particles.forEach(p => {{
      const e = p.edge;
      const cycle = 2200 / p.speed;
      const t = ((elapsed + p.offset*cycle) % cycle) / cycle;
      const mx = (e.x1+e.x2)/2, my = (e.y1+e.y2)/2;
      const u = 1-t;
      const px = u*u*u*e.x1 + 3*u*u*t*e.x1 + 3*u*t*t*e.x2 + t*t*t*e.x2;
      const py = u*u*u*e.y1 + 3*u*u*t*my + 3*u*t*t*my + t*t*t*e.y2;

      const grad = ctx.createRadialGradient(px,py,0, px,py,7);
      grad.addColorStop(0, "rgba("+ACCENT+","+(0.5*pAlpha)+")");
      grad.addColorStop(1, "rgba("+ACCENT+",0)");
      ctx.fillStyle = grad;
      ctx.fillRect(px-7, py-7, 14, 14);

      ctx.beginPath();
      ctx.arc(px, py, 2, 0, TAU);
      ctx.fillStyle = "rgba("+ACCENT+","+(0.85*pAlpha)+")";
      ctx.fill();
    }});
  }}

  // ── Draw nodes ──
  nodes.forEach(n => {{
    const row = rowOf[n.id] || 0;
    const delay = row * 0.1;
    const np = easeOut(clamp((progress - delay) / 0.2, 0, 1));
    if (np <= 0) return;

    const scale = 0.75 + 0.25 * np;
    ctx.save();
    ctx.globalAlpha = np;
    ctx.translate(n.cx, n.cy);
    ctx.scale(scale, scale);
    ctx.translate(-n.cx, -n.cy);

    const isTerminal = !n.agentKey;

    // Glow for active nodes
    if (n.active && progress > 0.5) {{
      const pulse = 0.5 + 0.5 * Math.sin(elapsed/400);
      const gs = 10 + pulse*5;
      const grad = ctx.createRadialGradient(n.cx,n.cy,0, n.cx,n.cy,n.w/2+gs);
      grad.addColorStop(0, "rgba("+ACCENT+","+(0.07+pulse*0.03)+")");
      grad.addColorStop(1, "rgba("+ACCENT+",0)");
      ctx.fillStyle = grad;
      ctx.fillRect(n.x-gs, n.y-gs, n.w+gs*2, n.h+gs*2);
    }}

    // Node box
    drawRR(n.x, n.y, n.w, n.h, NODE_R);
    ctx.fillStyle = n.active ? "rgba(10,31,23,0.9)" : "rgba(10,31,23,0.4)";
    ctx.fill();
    ctx.strokeStyle = n.active ? "#76b900" : "#333";
    ctx.lineWidth = n.active ? 2 : 1;
    ctx.stroke();

    // Label
    ctx.font = "700 " + (n.h < 34 ? "9" : "10") + "px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = n.active ? "#fff" : "#555";
    const hasTime = n.agentKey && DATA.agents[n.agentKey] && DATA.agents[n.agentKey].time > 0 && n.active && !n.id.startsWith("orch_");
    ctx.fillText(n.label.toUpperCase(), n.cx, n.cy - (hasTime ? 4 : 0));

    // Time
    if (hasTime) {{
      ctx.font = "600 8px Inter,sans-serif";
      ctx.fillStyle = "#76b900";
      ctx.fillText(DATA.agents[n.agentKey].time.toFixed(2) + "s", n.cx, n.cy + 10);
    }}

    ctx.restore();
  }});

  // ── Footer badges ──
  if (progress > 0.8) {{
    const ba = clamp((progress-0.8)/0.2, 0, 1);
    ctx.save(); ctx.globalAlpha = ba;
    ctx.font = "600 9px Inter,sans-serif";
    ctx.textAlign = "right"; ctx.fillStyle = "#888";
    ctx.fillText("TOTAL PIPELINE: " + DATA.totalTime.toFixed(2) + "s", W-20, H-8);
    if (DATA.intent) {{
      ctx.textAlign = "left"; ctx.fillStyle = "#555";
      const intentStr = DATA.intent.length > 60 ? DATA.intent.substring(0,57)+"..." : DATA.intent;
      ctx.fillText("INTENT: " + intentStr.toUpperCase(), 20, H-8);
    }}
    ctx.restore();
  }}

  requestAnimationFrame(draw);
}}
requestAnimationFrame(draw);
</script></body></html>'''

    with st.expander(f"◈  {title}"):
        components.html(html_string, height=530)


def extract_plan(state):
    interrupts = []
    for task in state.tasks or []:
        interrupts.extend(task.interrupts or [])
    return interrupts[0].value if interrupts else None


AGENT_STEPS = [
    ("pipeline_agent", "Pipeline · Structured query"),
    ("data_agent",     "Data Agent · ReAct SQL (PostgreSQL MCP)"),
    ("risk_agent",     "Risk Monitor · Tavily news retrieval"),
    ("chart_agent",    "Chart Builder · Matplotlib synthesis"),
    ("lp_agent",       "LP Optimizer · PuLP/CBC solve"),
    ("synthesizer",    "Synthesizer · Cross-signal reasoning"),
]

PHASE_GROUPS = [
    ("PHASE 1 — PARALLEL FAN-OUT", ["pipeline_agent", "data_agent", "risk_agent"]),
    ("PHASE 2 — PARALLEL",         ["chart_agent", "lp_agent"]),
    ("SYNTHESIS",                  ["synthesizer"]),
]

# Synthesizer auto-triggers when data_agent or risk_agent participates
# (mirrors builder.py::_NEEDS_SYNTHESIS).
_SYNTH_TRIGGERS = {"data_agent", "risk_agent"}


def stream_graph(command, config):
    placeholder = st.empty()
    final_state = {"agent_results": {}}

    def _render_streaming(placeholder):
        with placeholder.container():
            completed = set(final_state.get("_completed_agents") or [])
            active = final_state.get("_active_agent")
            timings = final_state.get("timings") or {}

            # ── Filter agents to this plan only ─────────────────────────────
            planned_agents = {
                t.get("agent") for t in (final_state.get("tasks") or [])
                if t.get("agent")
            }
            # Auto-include synthesizer when data/risk participates
            if planned_agents & _SYNTH_TRIGGERS:
                planned_agents = planned_agents | {"synthesizer"}

            label_map = dict(AGENT_STEPS)

            def _row_html(agent_key: str) -> str:
                label = label_map.get(agent_key, agent_key)
                if agent_key in completed:
                    secs = timings.get(agent_key)
                    time_html = (
                        f"<span style='font-family:\"Space Grotesk\",sans-serif;"
                        f"font-size:0.72rem; font-weight:700; color:#76b900;"
                        f"margin-left:auto; white-space:nowrap;'>{secs:.2f}s</span>"
                        if isinstance(secs, (int, float)) else ""
                    )
                    return (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0;'>"
                        f"<span style='color:#76b900; flex-shrink:0;'>✓</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#FFFFFF;'>{label}</span>"
                        f"{time_html}"
                        f"</div>"
                    )
                elif agent_key == active:
                    return (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0;'>"
                        f"<span style='color:#76b900; flex-shrink:0;'>◌</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#76b900; font-weight:700;'>{label}</span>"
                        f"<span style='font-family:\"Space Grotesk\",sans-serif;"
                        f"font-size:0.72rem; font-weight:500; color:#76b900;"
                        f"margin-left:auto; opacity:0.75; white-space:nowrap;'>running…</span>"
                        f"</div>"
                    )
                else:
                    return (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0; opacity:0.55;'>"
                        f"<span style='color:#555555; flex-shrink:0;'>○</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#555555;'>{label}</span></div>"
                    )

            # ── Assemble by phase, drop empty buckets ───────────────────────
            phase_eyebrow = (
                "font-family:'Inter',sans-serif; font-size:0.58rem;"
                "letter-spacing:0.18em; text-transform:uppercase; color:#888888;"
                "margin:0.85rem 0 0.35rem; padding:0; font-weight:600;"
            )
            body = ""
            for phase_label, agent_keys in PHASE_GROUPS:
                phase_agents = [a for a in agent_keys if a in planned_agents]
                if not phase_agents:
                    continue
                body += f"<p style=\"{phase_eyebrow}\">{phase_label}</p>"
                for agent_key in phase_agents:
                    body += _row_html(agent_key)

            # Defensive: if plan info hasn't arrived yet (first tick), show
            # a single placeholder line instead of an empty panel.
            if not body:
                body = (
                    "<div style='display:flex; align-items:center; gap:0.75rem;"
                    "padding:0.35rem 0; opacity:0.55;'>"
                    "<span style='color:#555555; flex-shrink:0;'>○</span>"
                    "<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                    "color:#555555;'>Awaiting orchestrator plan…</span></div>"
                )

            st.markdown(
                f"<div style='{SECTION_STYLE}'>"
                + section_header("—", "Active Engine Progress", "#76b900")
                + body
                + "</div>",
                unsafe_allow_html=True,
            )

            # Pipeline results glass card — during streaming show a ready
            # placeholder instead of raw markdown. Final structured render
            # happens after stream completes (render_data_pipeline path).
            pipeline_results = final_state.get("pipeline_results") or {}
            if pipeline_results:
                _PIPELINE_LABELS = {
                    "forecast_summary": "Forecast Summary",
                    "component_requirements": "Component Requirements",
                    "procurement_status": "Procurement Status",
                    "triggered_procurement_rows": "Triggered Procurement Rows",
                }
                inner = "".join(
                    f"<div style='display:flex;align-items:center;gap:0.6rem;"
                    f"padding:0.5rem 0;'>"
                    f"<span style='color:#76b900;flex-shrink:0;font-size:0.9rem;'>✓</span>"
                    f"<span style='font-family:Manrope,sans-serif;font-size:0.85rem;"
                    f"color:#CCCCCC;'>{_PIPELINE_LABELS.get(k, k.replace('_',' ').title())} "
                    f"ready — structured view renders below after all agents finish.</span></div>"
                    for k in pipeline_results.keys()
                )
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("·", "01 — Pipeline Results", "#76b900")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Data agent glass card
            if final_state.get("latest_data_agent"):
                inner = (
                    f"<div class='summary-body' style='font-size:0.88rem; color:#FFFFFF; line-height:1.65;'>"
                    f"{final_state['latest_data_agent']}</div>"
                )
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("·", "Data Query", "#76b900")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Risk agent glass card
            if final_state.get("latest_risk_agent"):
                inner = (
                    f"<div class='summary-body' style='font-size:0.88rem; color:#FFFFFF; line-height:1.65;'>"
                    f"{final_state['latest_risk_agent']}</div>"
                )
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("·", "Geopolitical Risk Analysis", "#76b900")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # LP results glass card
            lp_results = final_state.get("lp_results") or {}
            if lp_results:
                lp_style = (
                    "background:#0A1F17;"
                    "border:1px solid #333333; border-left:3px solid #76b900;"
                    "border-radius:2px; padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
                )
                inner = "".join(
                    f"<p class='result-label'>Product: {k.replace('lp_','').replace('_',' ').title()}</p>"
                    f"<pre class='result-pre'>{v}</pre>"
                    for k, v in lp_results.items()
                )
                st.markdown(
                    f"<div style='{lp_style}'>"
                    + section_header("·", "02 — Optimization Results", "#76b900")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Charts — 2-column grid
            charts = final_state.get("chart_results") or {}
            if charts:
                st.markdown(
                    f"<div style='{SECTION_STYLE}'>"
                    + section_header("·", "03 — Visualizations", "#76b900")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                render_charts(charts)

            # Summary glass card
            if final_state.get("final_response"):
                summary_style = (
                    "background:#0A1F17;"
                    "border:1px solid #76b900; border-radius:2px;"
                    "padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
                    "box-shadow:rgba(0,0,0,0.3) 0px 0px 5px;"
                )
                inner = (
                    f"<div class='summary-body'>{final_state['final_response']}</div>"
                )
                st.markdown(
                    f"<div style='{summary_style}'>"
                    + section_header("·", "04 — Intelligence Summary", "#76b900")
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
                if "raw_data" in node_output:
                    final_state.setdefault("raw_data", {}).update(
                        node_output["raw_data"] or {}
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
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>The formula computes the <strong>base-stock level (S)</strong> — the total inventory required to meet demand across the review period and lead time under uncertainty.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Safety stock</strong> is the buffer component embedded within this level, covering demand and lead-time variability.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>In this system, safety stock is enforced as a <strong>protected inventory floor</strong> per facility × component. It is not consumed during planning.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>Only inventory <strong>above</strong> this floor is used to satisfy weekly demand.</p></div>"
)
_SS_CYCLE_STOCK_TEXT = (
    "<p style='color:#fff;margin:0 0 0.6rem;font-size:0.88rem;'>The base-stock level (S) has two distinct components:</p>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#76b900;margin:0 0 0.2rem;font-size:0.78rem;font-weight:600;'>1. Cycle Stock — μᴅ × (r + μₗ)</p>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>Covers <strong>expected demand</strong> over the review period and lead time. This is the primary driver of inventory volume.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#76b900;margin:0 0 0.2rem;font-size:0.78rem;font-weight:600;'>2. Safety Stock — z · √((r + μₗ)σᴅ² + μᴅ²σₗ²)</p>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>Covers <strong>uncertainty</strong> in demand and lead time. This is a buffer — NOT intended to cover expected demand.</p></div>"
    "<p style='color:#ccc;margin:0.6rem 0 0;font-size:0.84rem;'>On-hand inventory at the start of planning is anchored at <strong>S = Cycle Stock + Safety Stock</strong>. "
    "Safety stock alone will often appear small relative to weekly demand — this is expected and correct.</p>"
)
_SS_PLANNING_TEXT = (
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>Weekly procurement is triggered when <strong>usable inventory</strong> (above the safety stock floor) reaches zero.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>Safety stock is already accounted for before any weekly demand calculations begin — it does not appear as a deduction in the weekly trigger table.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>The weekly trigger table reflects how demand consumes usable inventory, not safety stock itself.</p></div>"
)
_TRIG_BULLETS_TEXT = (
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Gross Requirement:</strong> forecast-driven component demand for that week.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Available Inventory Before Demand:</strong> usable inventory remaining above the safety stock floor at the start of this week (rolling — decreases each week as prior demand is consumed).</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Direct Procurement Needed:</strong> portion of demand not covered by usable inventory.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Cumulative Procurement Pressure:</strong> total procurement required up to that week, per facility × component.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Safety Stock Utilization (%):</strong> how much of the safety buffer is being matched by cumulative procurement demand.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Urgency Level:</strong> qualitative indicator — Low / Medium / High / Critical.</p></div>"
    "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
    "<p style='color:#fff;margin:0;font-size:0.84rem;'>Procurement is triggered when usable inventory reaches zero.</p></div>"
)


def _populate_inventory_expander_cache():
    """Pre-load data for the 3 inventory expanders."""
    import pandas as _pd_inv
    from tools.pipeline_queries import (
        query_triggered_rows_structured,
        query_full_horizon_drilldown,
    )
    from ui.inventory_views import _prepare_trigger_df_from_raw

    cache = {}

    # 1. Triggered procurement rows — apply full presentation transforms
    try:
        raw = query_triggered_rows_structured()
        rows = raw.get("rows", [])
        if rows:
            df_display, ss_ctx, _ = _prepare_trigger_df_from_raw(raw)
        else:
            df_display = _pd_inv.DataFrame()
            ss_ctx = []
        cache["triggered_df"] = df_display
        cache["triggered_ss_ctx"] = ss_ctx
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
    from ui.inventory_views import _TRIG_COL_ORDER_DISPLAY, _TRIG_FMT_DISPLAY
    import pandas as _pd_trig_render
    trig_df = cache.get("triggered_df", _pd_trig_render.DataFrame())
    trig_ss_ctx = cache.get("triggered_ss_ctx", [])
    trig_meta = cache.get("triggered_meta", {})
    with st.expander(
        "In which weeks and where is procurement actually triggered "
        "across the planning horizon?",
        expanded=False,
    ):
        if trig_meta:
            st.caption(f"Forecast run {trig_meta.get('run_id', '')}  ·  "
                       f"{trig_meta.get('n_rows', 0)} triggered rows")
        # Safety stock floor table
        if trig_ss_ctx:
            st.markdown("**Safety Stock Floor by Facility × Component**")
            st.caption("Protected inventory floor — demand is only drawn from inventory above this level.")
            _ss_df = _pd_trig_render.DataFrame(trig_ss_ctx)
            st.dataframe(
                _ss_df.style.format({"Safety Stock (Protected Floor)": "{:,.0f}"}),
                use_container_width=True, hide_index=True,
            )
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
            # Apply column ordering
            _df_t = _df_t[[c for c in _TRIG_COL_ORDER_DISPLAY if c in _df_t.columns]]
            st.caption(f"{len(_df_t)} rows shown")
            st.dataframe(
                _df_t.style.format({c: v for c, v in _TRIG_FMT_DISPLAY.items() if c in _df_t.columns}),
                use_container_width=True, hide_index=True, height=500,
            )
        else:
            st.info("No triggered rows — all inventory positions appear sufficient.")
        st.markdown(_TRIG_BULLETS_TEXT, unsafe_allow_html=True)

    # Expander 2: Base Stock Policy
    with st.expander("Detail on Base Stock Policy", expanded=False):
        st.subheader("Inventory Policy — Safety Stock and Base-Stock Logic")
        st.markdown("**Base-Stock Formula**")
        st.markdown(_SS_FORMULA_TEXT)
        st.markdown("**Term Definitions**")
        st.markdown(_SS_TERMS_TEXT)
        st.markdown("**How It Works**")
        st.markdown(_SS_BUSINESS_TEXT, unsafe_allow_html=True)
        st.markdown("**Cycle Stock vs Safety Stock (Key Distinction)**")
        st.markdown(_SS_CYCLE_STOCK_TEXT, unsafe_allow_html=True)
        st.markdown("**Connection to Planning Outputs**")
        st.markdown(_SS_PLANNING_TEXT, unsafe_allow_html=True)

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
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'>This step shows what components are required to build the products our customers are expecting.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'>Every finished unit requires a specific mix of inputs — the BOM defines how many units of each component are needed per SKU.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'>Multiplying that recipe by the forecasted demand yields the gross component requirements shown below.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'>These totals are calculated before any inventory has been considered.</p></div>"
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
                    st.markdown(_BOM_XLATE_NOTE, unsafe_allow_html=True)
            return True

        # Fallback: raw rows
        elif structured.get("rows"):
            st.subheader("Component Requirements — BOM Explosion")
            df = pd.DataFrame(structured["rows"])
            st.dataframe(df, use_container_width=True, hide_index=True, height=420)
            return True

    if key == "aggregated_procurement_need" and structured and structured.get("rows"):
        _PROC_BULLETS = (
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'>This table starts from the current inventory position — <strong>Starting On-Hand</strong> — at the beginning of the planning horizon.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Gross Component Demand</strong> represents total required component volume based on forecasted production.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Starting On-Hand</strong>, <strong>Scheduled Receipts</strong>, and <strong>Backorders</strong> adjust available inventory over the planning horizon.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Safety Stock Reserve</strong> represents required buffer inventory to maintain the target service level and must be procured if not already available.</p></div>"
            "<div style='background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.5rem 0.9rem;margin:0.3rem 0;'>"
            "<p style='color:#fff;margin:0;font-size:0.84rem;'><strong>Net Procurement Requirement</strong> is the remaining quantity that must be ordered after accounting for all inventory and policy constraints.</p></div>"
        )
        st.subheader("Net Component Procurement Requirement — Planning Horizon")
        st.caption(
            f"Horizon: {structured.get('horizon_start', '')} → "
            f"{structured.get('horizon_end', '')} ({structured.get('n_weeks', '')} weeks)"
        )
        st.markdown("All values are aggregated across the full planning horizon.")
        st.markdown(_PROC_BULLETS, unsafe_allow_html=True)
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
        st.markdown(_text, unsafe_allow_html=True)
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
        "raw_data": final_state.get("raw_data") or {},
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

    # Chart agent — always include output when chart_agent ran
    chart_results = trace.get("chart_results") or {}
    chart_summary = agent_results.get("chart_agent", "")
    timings = trace.get("timings") or {}
    chart_ran = timings.get("chart_agent") is not None
    if chart_ran or chart_results or chart_summary:
        label = chart_summary or ("Generated charts" if chart_results else "Chart agent completed — no charts produced")
        parts.append(f"**Visualizations** — {label}")

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
                "color:#888888; margin:0 0 0.4rem;'><span style='color:#76b900; font-weight:300; font-size:1.1rem; margin-right:8px;'>01</span>Pipeline Results</p>",
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
                "color:#888888; margin:0 0 0.4rem;'><span style='color:#76b900; font-weight:300; font-size:1.1rem; margin-right:8px;'>02</span>Optimization Results</p>",
                unsafe_allow_html=True,
            )
            _raw = trace.get("raw_data") or {}
            for key, content in lp_items.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                raw_dict = _raw.get(key)
                if isinstance(raw_dict, dict):
                    st.markdown(f"### {product}")
                    _render_lp_result(raw_dict)
                elif content:
                    with st.expander(f"Product: {product}", expanded=True):
                        st.code(str(content), language=None)
        if chart_results:
            st.markdown(
                f"<div style='margin:0.75rem 0 0.5rem;'>"
                + section_header("·", "03 — Visualizations", "#76b900")
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
    render_progress_panel(trace)
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
            + section_header("·", "Procurement Optimization — Ready to Run", "#76b900")
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
                "<div style='background:#0A1F17; border:1px solid #333333;"
                "border-radius:2px; padding:0.75rem 1rem; margin-bottom:1.25rem;'>"
                f"<p style='font-family:Manrope,sans-serif; font-size:0.875rem; color:#76b900; margin:0;'>"
                f"{plan['question']}</p></div>"
            )

        st.markdown(
            f"<div style='{SECTION_STYLE}'>"
            "<div style='display:flex; align-items:center; gap:0.55rem; margin-bottom:1.25rem;'>"
            "<span style='font-size:1rem; color:#76b900;'>✦</span>"
            "<h2 style='font-family:Space Grotesk,sans-serif; font-size:1.2rem; font-weight:700;"
            "letter-spacing:-0.02em; color:#FFFFFF; margin:0;'>Intelligence Plan Ready</h2>"
            "</div>"
            "<div style='background:#0A1F17; border:1px solid #333333;"
            "border-radius:2px; padding:0.75rem 1rem; margin-bottom:1.25rem;'>"
            "<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
            "text-transform:uppercase; color:#888888; margin-bottom:0.3rem;'>Intent</p>"
            f"<p style='font-family:Manrope,sans-serif; font-size:0.9rem; color:#76b900; margin:0;"
            f"font-weight:600;'>{plan.get('intent', '')}</p>"
            "</div>"
            + question_html
            + f"<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
            f"text-transform:uppercase; color:#888888; margin-bottom:0.75rem;'>"
            f"Work Orders — {len(tasks)} task{'s' if len(tasks) != 1 else ''}</p>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Task cards with agent-colored accents + business descriptions
        agent_accent = {
            "pipeline_agent": "#76b900",
            "data_agent":     "#76b900",
            "risk_agent":     "#76b900",
            "chart_agent":    "#76b900",
            "lp_agent":       "#76b900",
        }
        agent_label = {
            "pipeline_agent": "Pipeline Agent",
            "data_agent":     "Data Explorer",
            "risk_agent":     "Risk Monitor",
            "chart_agent":    "Visualization",
            "lp_agent":       "Optimizer",
        }
        for i, task in enumerate(tasks):
            agent = task.get("agent", "")
            accent = agent_accent.get(agent, "#555555")
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
                    f"color:#888888; margin:0.35rem 0 0 0; line-height:1.4;'>{desc}</p>"
                )

            st.markdown(
                "<div style='background:#0A1F17; border:1px solid #333333;"
                "border-radius:2px; padding:0.875rem 1.25rem; margin-bottom:0.4rem;'>"
                "<div style='display:flex; align-items:center; gap:0.5rem; margin-bottom:0.4rem;'>"
                f"<span style='font-family:Inter,sans-serif; font-size:0.55rem; letter-spacing:0.12em;"
                f"text-transform:uppercase; color:#888888;'>Task {i+1}</span>"
                f"<span style='font-family:Inter,sans-serif; font-size:0.55rem; font-weight:600;"
                f"letter-spacing:0.1em; text-transform:uppercase; color:{accent};"
                f"background:transparent; border:1px solid #76b900;"
                f"padding:0.1rem 0.45rem; border-radius:2px;'>{display_label}</span>"
                "</div>"
                f"<p style='font-family:Manrope,sans-serif; font-size:0.925rem; font-weight:600;"
                f"color:#FFFFFF; margin:0;'>{title}</p>"
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
            # Immediately hide the plan card to prevent duplicate rendering
            st.session_state.waiting_for_approval = False
            st.session_state.pending_plan = None
            with st.spinner("Executing approved plan..."):
                feedback = st.session_state.plan_feedback.strip() or "ok"
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                final_state = stream_graph(Command(resume=feedback), config=config)

            # Stepper: pipeline tools (forecast/BOM/inventory) just actually ran.
            # Advance demo_section to whichever stage this plan covered.
            _stage = _infer_stage_from_plan(plan)
            if _stage is not None and _stage <= 3:
                _advance_stage(_stage)

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


def _run_scripted_demo_stage(prompt: str) -> None:
    """Route scripted demo prompts to deterministic handlers, bypassing the LLM.

    Covers all 7 scripted stages.  For each matched prompt this function
    executes the appropriate deterministic logic and then calls st.rerun(),
    which raises RerunException so control never returns to the caller.
    Unrecognised prompts return normally and the caller falls through to the
    LLM path.
    """
    from tools.pipeline_queries import (
        query_forecast_summary,
        query_component_requirements,
        query_aggregated_procurement_need,
    )

    _p = prompt.strip().lower()

    # ── 1. Planning initialization ─────────────────────────────────────────
    if _p == (
        "help me plan procurement for the upcoming 20 week planning horizon "
        "with a balance between cost and reliability."
    ):
        _html = (
            '<p style="color:#fff;margin:0 0 1rem;">Understood. We will:</p>'
            '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
            '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">01</span>'
            'Verify your historical demand across all four facilities and semiconductor SKUs</p></div>'
            '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
            '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">02</span>'
            'Translate that demand into the exact component requirements needed to support production</p></div>'
            '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
            '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">03</span>'
            'Assess inventory coverage and identify where procurement is required</p></div>'
            '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
            '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">04</span>'
            'Optimize supplier allocation to minimize cost while controlling supplier risk and disruption</p></div>'
            '<hr style="border:none;border-top:1px solid #333;margin:1rem 0;">'
            '<p style="color:#ccc;margin:0 0 0.5rem;font-size:0.85rem;">'
            'Your objective balances <strong>cost efficiency</strong> with <strong>supply reliability</strong> — '
            'the risk parameter controls this tradeoff.</p>'
            '<p style="color:#ccc;margin:0 0 0.5rem;font-size:0.85rem;">'
            "Let's begin by validating the historical demand that drives this entire workflow.</p>"
            '<p style="color:#76b900;margin:0;font-size:0.85rem;font-weight:600;">'
            "Reply 'Yes, proceed' to continue.</p>"
        )
        _advance_stage(0)
        with st.chat_message("assistant", avatar=CPU_AVATAR):
            st.markdown(_html, unsafe_allow_html=True)
            _render_csv_button()
        st.session_state.messages.append({
            "role": "assistant", "content": _html,
            "has_trace": False, "summary": "",
        })
        st.rerun()

    # ── 2. Demand forecasting ("Yes, proceed") ────────────────────────────
    if _p == "yes, proceed":
        with st.spinner("Running demand forecast…"):
            _r = query_forecast_summary()
        _fs = {
            "intent": "demand_forecasting",
            "tasks": [{"agent": "pipeline_agent", "tool": "query_forecast_summary"}],
            "agent_results": {
                "forecast_summary": _r.get("content", ""),
                "forecast_summary__structured": _r.get("structured"),
            },
            "raw_data": {},
            "chart_results": {},
            "timings": {"pipeline_agent": 0.0},
            "final_response": "",
        }
        finalize_execution(_fs)
        _advance_stage(1)
        st.rerun()

    # ── 3. BOM — component requirements ──────────────────────────────────
    if _p == "show total component requirements for the upcoming demand window.":
        with st.spinner("Loading component requirements…"):
            _r = query_component_requirements()
        _fs = {
            "intent": "component_requirements",
            "tasks": [{"agent": "pipeline_agent", "tool": "query_component_requirements"}],
            "agent_results": {
                "component_requirements": _r.get("content", ""),
                "component_requirements__structured": _r.get("structured"),
            },
            "raw_data": {},
            "chart_results": {},
            "timings": {"pipeline_agent": 0.0},
            "final_response": "",
        }
        finalize_execution(_fs)
        _advance_stage(2)
        st.rerun()

    # ── 4. Net inventory / procurement need ───────────────────────────────
    if _p == (
        "after our inventory is factored in, what is the total amount that needs to be "
        "ordered for each component to meet our upcoming demand?"
    ):
        with st.spinner("Calculating net procurement requirement…"):
            _r = query_aggregated_procurement_need()
        _fs = {
            "intent": "inventory_planning",
            "tasks": [{"agent": "pipeline_agent", "tool": "query_aggregated_procurement_need"}],
            "agent_results": {
                "aggregated_procurement_need": _r.get("content", ""),
                "aggregated_procurement_need__structured": _r.get("structured"),
            },
            "raw_data": {},
            "chart_results": {},
            "timings": {"pipeline_agent": 0.0},
            "final_response": "",
        }
        finalize_execution(_fs)
        _advance_stage(3)
        st.rerun()

    # ── 5. LP — integrated circuit components ─────────────────────────────
    if _p == (
        "from our available suppliers, provide a procurement plan to ensure we have enough "
        "integrated circuit components across all facilities to meet our upcoming demand window. "
        "implement a moderate risk aversion supply strategy. "
        "no supplier should exceed 40% of total supply volume for this order."
    ):
        _run_lp_direct(fill_defaults({
            "product": "integrated_circuit_components",
            "lambda_risk": 0.5,
            "max_supplier_share": 0.40,
        }))

    # ── 6. Expedite (urgency re-run of the last LP) ───────────────────────
    if _p == "expedite this":
        _prior = st.session_state.lp_params_history.get("integrated_circuit_components") or {}
        if not _prior:
            for _pv in st.session_state.lp_params_history.values():
                _prior = _pv
                break
        if _prior:
            _epar = merge_with_prior("expedite this", _prior)
        else:
            _epar = fill_defaults({
                "product": "integrated_circuit_components",
                "urgency": True,
            })
        _run_lp_direct(_epar)

    # ── 7. Complete Procurement Plan (executive summary) ──────────────────
    if _p == "complete procurement plan":
        st.session_state.show_executive_summary = True
        _advance_stage(6)
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Generating final procurement executive summary…",
            "has_trace": False, "summary": "",
        })
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
                # Stepper: LP run approved → advance LP-IC (4) or LP-Trans (5)
                _recap = (result_dict or {}).get("params_recap") or {}
                _product = (_recap.get("product") or "").lower()
                _advance_stage(5 if "trans" in _product else 4)
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


# ── Intro animation gate ────────────────────────────────────────────────────

if "intro_done" not in st.session_state:
    st.session_state.intro_done = False

# Pick up query-param signal from the animation's LAUNCH button
if st.query_params.get("launched") == "1":
    st.session_state.intro_done = True
    st.query_params.clear()

if not st.session_state.intro_done:
    # Hide ALL Streamlit chrome for a clean full-screen animation
    st.markdown(
        "<style>"
        "header[data-testid='stHeader'],"
        "[data-testid='stSidebar'],"
        "[data-testid='stSidebarNav'],"
        "footer,.stDeployButton{display:none!important}"
        ".stApp{background:#000!important}"
        "section.main>div,.block-container"
        "{padding:0!important;max-width:100vw!important}"
        "div[data-testid='stVerticalBlock']{gap:0!important}"
        ".stButton>button{"
        "background:#f5f5f5!important;color:#0a0a0a!important;"
        "-webkit-text-fill-color:#0a0a0a!important;"
        "border:none!important;border-radius:999px!important;"
        "font-family:'Inter',sans-serif!important;font-weight:500!important;"
        "font-size:0.82rem!important;letter-spacing:0.02em!important;"
        "padding:0.75rem 2.2rem!important;"
        "margin:0 auto!important;display:block!important;"
        "transition:all 0.3s ease!important}"
        ".stButton>button:hover{"
        "background:transparent!important;color:#f5f5f5!important;"
        "-webkit-text-fill-color:#f5f5f5!important;"
        "box-shadow:0 0 0 2px #76b900!important;"
        "transform:scale(1.04)!important}"
        ".stButton>button p,.stButton>button span{"
        "color:inherit!important;-webkit-text-fill-color:inherit!important}"
        "</style>",
        unsafe_allow_html=True,
    )

    # Build self-contained animation HTML (inline CSS + JS)
    _anim_dir = os.path.join(os.path.dirname(__file__), "intro_animation")
    with open(os.path.join(_anim_dir, "style.css")) as _f:
        _css = _f.read()
    with open(os.path.join(_anim_dir, "script.js")) as _f:
        _js = _f.read()

    # Remove the in-animation button (we use a native Streamlit button instead)
    _js = _js.replace(
        "window.location.href = 'http://localhost:8501/';",
        "// handled by Streamlit button",
    )

    _animation_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Instrument+Serif:ital@1&display=swap" rel="stylesheet">
<style>{_css}
#launch-chatbot-btn {{display:none!important}}
</style>
</head>
<body>
<canvas id="anim-canvas"></canvas>
<div id="loading-screen">
  <div class="load-top-left"><span class="load-label">Procurement Pilot v1.0</span></div>
  <div class="load-center">
    <div id="cycling-word" class="cycling-word">Initializing</div>
    <div class="load-sub">Multi-Agent Orchestration Engine</div>
  </div>
  <div class="load-bottom-right">
    <span id="counter" class="counter">000</span>
    <span class="counter-label">System Boot</span>
  </div>
  <div class="load-boot" id="boot-log">
    <div class="boot-line" id="boot-0">[SYS] Connecting to database ... <span class="ok">OK</span></div>
    <div class="boot-line" id="boot-1">[LLM] Loading orchestrator model ... <span class="ok">OK</span></div>
    <div class="boot-line" id="boot-2">[MCP] Initializing tool servers ... <span class="ok">OK</span></div>
    <div class="boot-line" id="boot-3">[AGT] Pipeline / Data / Risk / Chart / LP ... <span class="ok">READY</span></div>
    <div class="boot-line" id="boot-4">[OPT] PuLP/CBC solver loaded ... <span class="ok">OK</span></div>
  </div>
  <div class="load-progress"><div class="progress-track"><div id="progress-bar" class="progress-fill"></div></div></div>
</div>
<div id="main-content" class="main-content hidden">
  <div class="hero">
    <p class="eyebrow blur-in">Multi-Agent Intelligence System</p>
    <h1 class="hero-title name-reveal">Procurement<br><em>Pilot</em></h1>
    <p class="hero-role blur-in">A <span id="role-word" class="role-word">Forecasting</span> engine for global supply chains.</p>
    <p class="hero-desc blur-in">Orchestrating 5 specialized AI agents across 89 suppliers and 21 countries to optimize semiconductor procurement in real-time.</p>
  </div>
</div>
<script>{_js}</script>
</body></html>"""

    import streamlit.components.v1 as components
    components.html(_animation_html, height=900, scrolling=False)

    # Native Streamlit button — centered
    _cols = st.columns([1, 1, 1])
    with _cols[1]:
        if st.button("LAUNCH CHATBOT", use_container_width=True, key="intro_launch"):
            st.session_state.intro_done = True
            st.rerun()
    st.stop()


# ── Theme injection ──────────────────────────────────────────────────────────
inject_css()
render_header()

with st.sidebar:
    render_sidebar()


# ── View routing ─────────────────────────────────────────────────────────────

if st.session_state.current_view == "architecture":
    render_architecture()

elif st.session_state.current_view == "data_pipeline":
    render_data_pipeline()

elif st.session_state.current_view == "history":
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
                        "color:#888888; margin:0 0 0.4rem;'><span style='color:#76b900; font-weight:300; font-size:1.1rem; margin-right:8px;'>01</span>Pipeline Results</p>",
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
                    _raw_replay = _trace.get("raw_data") or {}
                    for _lk, _lv in _lp.items():
                        _product = _lk.replace("lp_", "").replace("_", " ").title()
                        _raw_dict = _raw_replay.get(_lk)
                        if isinstance(_raw_dict, dict):
                            st.markdown(f"### {_product}")
                            _render_lp_result(_raw_dict)
                        elif isinstance(_lv, dict):
                            # fallback: agent_results occasionally stores the dict directly
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
                        + section_header("·", "03 — Visualizations", "#76b900")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
            else:
                # Non-trace messages: render content as-is
                if msg.get("content"):
                    st.markdown(msg["content"], unsafe_allow_html=True)
                    if "validating the historical demand" in msg.get("content", ""):
                        _render_csv_button()

            if _b64 and not msg.get("chart_first"):
                st.image(base64.b64decode(_b64))
        if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
            render_progress_panel(st.session_state.traces[assistant_index])
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

    # Horizontal business-cycle flowchart (always visible)
    render_demo_flowchart()

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

        # Demo flow buttons — show next available prompts
        render_demo_buttons()

        # Check for suggestion chip click, then fall back to typed input
        _suggested = st.session_state.pop("suggested_query", "") or ""
        prompt = _suggested or st.chat_input("Ask a sourcing query...")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar=USER_AVATAR):
                st.write(prompt)

            # ── Scripted demo router ──────────────────────────────────────
            # Handles all 7 scripted stages without calling the LLM.
            # Matched prompts call st.rerun() inside and never return here.
            # Unrecognised prompts fall through to the LLM path below.
            _run_scripted_demo_stage(prompt)

            # ── Non-scripted: all input goes through the Orchestrator ─────
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

            # Stepper: planner is the only direct-response path that advances
            # immediately (no approval/execution step). Planner does NOT
            # produce a graph interrupt, so extract_plan(state) returns None
            # for planner responses — we must read tasks from `result`
            # (the ainvoke return) instead. Other agents advance
            # post-approval in render_pending_plan / render_lp_approval.
            _result_tasks = (
                result.get("tasks") if isinstance(result, dict) else None
            ) or []
            if any(t.get("agent") == "planner" for t in _result_tasks):
                _advance_stage(0)

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
                        st.markdown(final_resp, unsafe_allow_html=True)
                        if any(t.get("agent") == "planner" for t in _result_tasks):
                            _render_csv_button()
                    st.session_state.messages.append({
                        "role": "assistant", "content": final_resp,
                        "has_trace": False, "summary": "",
                    })
                    st.rerun()
