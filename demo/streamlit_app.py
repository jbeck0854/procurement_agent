import asyncio

import nest_asyncio
import streamlit as st

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


def show_trace(trace):
    with st.expander("Execution Trace"):
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

        st.subheader("Synthesizer")
        st.write("Final response generated")


assistant_index = 0
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
    if msg["role"] == "assistant" and assistant_index < len(st.session_state.traces):
        show_trace(st.session_state.traces[assistant_index])
        assistant_index += 1

prompt = st.chat_input("Ask about suppliers...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.spinner("Thinking..."):
        result = asyncio.run(graph.ainvoke({"messages": [("user", prompt)]}))
    trace = {
        "intent": result["intent"],
        "tasks": result["tasks"],
        "agent_results": result["agent_results"],
    }
    st.session_state.traces.append(trace)
    final_response = result["final_response"]
    with st.chat_message("assistant"):
        st.write(final_response)
    show_trace(trace)
    st.session_state.messages.append({"role": "assistant", "content": final_response})
