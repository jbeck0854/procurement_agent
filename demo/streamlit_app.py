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
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("content"):
            st.markdown(msg["content"])
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

        # ── Fast forecast model assessment ────────────────────────────────
        elif _forecast_assessment_direction(prompt) is not None:
            direction = _forecast_assessment_direction(prompt)
            transition, label = _FORECAST_ASSESS_META[direction]
            with st.spinner("Retrieving forecast model assessment..."):
                from tools.pipeline_queries import query_forecast_model_assessment
                result = query_forecast_model_assessment(direction=direction)
                result_text = result.get("content", "")
                artifact_path = result.get("artifact_path", "")
            with st.chat_message("assistant"):
                st.markdown(transition)
                st.divider()
                st.subheader(label)
                # Render PNG artifact directly if available — plot comes first.
                if artifact_path:
                    abs_path = os.path.join(_ARTIFACTS_BASE, artifact_path)
                    if os.path.exists(abs_path):
                        st.image(abs_path)
                # Compact markdown text — wraps properly, no horizontal overflow.
                st.markdown(result_text)
            # Store for replay — images are not persisted across reruns,
            # but the markdown text is always readable.
            combined = f"{transition}\n\n---\n\n**{label}**\n\n{result_text}"
            st.session_state.messages.append({
                "role": "assistant",
                "content": combined,
                "has_trace": False,
                "summary": "",
            })
            st.rerun()

        # ── Fast forecast drill-down ───────────────────────────────────────
        elif _is_forecast_drilldown_request(prompt):
            transition = (
                "Here is the detailed production forecast by week, "
                "facility, and semiconductor SKU."
            )
            with st.spinner("Retrieving forecast drill-down..."):
                from tools.pipeline_queries import query_forecast_drilldown
                result = query_forecast_drilldown()
                result_text = result.get("content", "")
            combined = (
                f"{transition}\n\n---\n\n"
                f"**📊 Forecast Drill-Down**\n\n```\n{result_text}\n```"
            )
            with st.chat_message("assistant"):
                st.markdown(transition)
                st.divider()
                st.subheader("📊 Forecast Drill-Down")
                st.code(result_text)
            st.session_state.messages.append({
                "role": "assistant",
                "content": combined,
                "has_trace": False,
                "summary": "",
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
