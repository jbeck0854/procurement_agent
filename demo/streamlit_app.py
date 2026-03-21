import asyncio
import logging
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

st.set_page_config(page_title="Procurement Agent", layout="wide")
st.title("Procurement Supply Chain Agent")


@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

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


def show_trace(trace):
    with st.expander("Execution Trace"):
        # --- Timing breakdown ---
        timings = trace.get("timings") or {}
        if timings:
            st.subheader("Performance")
            top_level = ["orchestrator", "data_agent", "search_agent", "synthesizer"]
            cols = st.columns(len(top_level))
            for col, name in zip(cols, top_level):
                val = timings.get(name)
                if val is not None:
                    col.metric(name, f"{val:.2f}s")
            total = sum(timings.get(k, 0) for k in top_level)
            st.caption(f"Total pipeline time: **{total:.2f}s**")

            # Show sub-step details
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
            st.write(f"Routed to: **{trace['tasks'][0]['agent']}**")

        st.subheader("Data Agent")
        raw = trace["agent_results"].get("data_agent", "No result")
        if len(raw) > 500:
            raw = raw[:500] + "..."
        st.code(raw)

        search_raw = trace["agent_results"].get("search_agent")
        if search_raw:
            st.subheader("Search Agent")
            if len(search_raw) > 500:
                search_raw = search_raw[:500] + "..."
            st.code(search_raw)

        st.subheader("Synthesizer")
        st.write("Final response generated")


assistant_index = 0
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
    if msg["role"] == "assistant" and assistant_index < len(st.session_state.traces):
        show_trace(st.session_state.traces[assistant_index])
        assistant_index += 1


def extract_plan(state):
    interrupts = []
    for task in state.tasks or []:
        interrupts.extend(task.interrupts or [])
    return interrupts[0].value if interrupts else None


def stream_graph(command, config):
    placeholder = st.empty()
    final_state = {"agent_results": {}}

    def _render_streaming(placeholder):
        """Re-render the placeholder with all agent results collected so far."""
        with placeholder.container():
            if final_state.get("latest_data_agent"):
                st.subheader("📊 Supplier Analysis")
                st.markdown(final_state["latest_data_agent"])
            if final_state.get("latest_search_agent"):
                st.divider()
                st.subheader("🌐 Geopolitical Risk Analysis")
                st.markdown(final_state["latest_search_agent"])
            if final_state.get("final_response"):
                st.divider()
                st.subheader("📋 Summary & Recommendations")
                st.markdown(final_state["final_response"])

    async def stream_results():
        async for event in graph.astream(command, config=config):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                if "intent" in node_output:
                    final_state["intent"] = node_output["intent"]
                if "tasks" in node_output:
                    final_state["tasks"] = node_output["tasks"]
                if "agent_results" in node_output:
                    final_state.setdefault("agent_results", {}).update(node_output["agent_results"] or {})
                if node_name == "data_agent" and node_output.get("agent_results"):
                    data_text = node_output["agent_results"].get("data_agent")
                    if data_text:
                        final_state["latest_data_agent"] = data_text
                        _render_streaming(placeholder)
                if node_name == "search_agent" and node_output.get("agent_results"):
                    search_text = node_output["agent_results"].get("search_agent")
                    if search_text:
                        final_state["latest_search_agent"] = search_text
                        _render_streaming(placeholder)
                if node_name == "synthesizer" and "final_response" in node_output:
                    final_state["final_response"] = node_output["final_response"]
                    final_state["timings"] = node_output.get("timings", {})
                    _render_streaming(placeholder)
                final_state[node_name] = node_output
        return final_state

    return asyncio.run(stream_results())


def finalize_execution(final_state, fallback_plan=None):
    plan = fallback_plan or {}
    trace = {
        "intent": final_state.get("intent") or plan.get("intent", ""),
        "tasks": final_state.get("tasks") or plan.get("tasks", []),
        "agent_results": final_state.get("agent_results", {}),
        "timings": final_state.get("timings") or plan.get("timings", {}),
    }
    st.session_state.traces.append(trace)

    # Combine all agent results + synthesizer summary into one message
    parts = []
    data_agent_result = trace["agent_results"].get("data_agent", "")
    if data_agent_result:
        parts.append(data_agent_result)
    search_agent_result = trace["agent_results"].get("search_agent", "")
    if search_agent_result:
        parts.append("---\n\n**🌐 Geopolitical Risk Analysis**\n\n" + search_agent_result)
    final_response = final_state.get("final_response", "")
    if final_response:
        parts.append("---\n\n**📋 Summary & Recommendations**\n\n" + final_response)
    combined = "\n\n".join(parts)

    if combined:
        with st.chat_message("assistant"):
            st.markdown(combined)
        st.session_state.messages.append({"role": "assistant", "content": combined})
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


if st.session_state.waiting_for_approval and st.session_state.pending_plan:
    render_pending_plan()
elif not st.session_state.waiting_for_approval:
    prompt = st.chat_input("Ask about suppliers...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
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
