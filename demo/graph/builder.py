from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from graph.state import AgentState
from graph.orchestrator import orchestrator_node
from graph.data_agent import data_agent_node
from graph.risk_agent import risk_agent_node
from graph.chart_agent import chart_agent_node
from graph.lp_agent import lp_agent_node
from graph.pipeline_agent import pipeline_agent_node
from graph.synthesizer import synthesizer_node

PHASE1_AGENTS = {"data_agent", "risk_agent", "pipeline_agent"}
PHASE2_AGENTS = {"chart_agent", "lp_agent"}


def route_phase1(state: AgentState) -> list[str]:
    """Fan-out to Phase 1 agents based on orchestrator tasks."""
    tasks = state.get("tasks", [])
    agents = {
        task["agent"] for task in tasks
        if task.get("phase", 1) == 1 and task.get("agent") in PHASE1_AGENTS
    }
    if not agents:
        return ["phase2_router"]
    return list(agents)


def route_phase2(state: AgentState) -> list[str]:
    """Fan-out to Phase 2 agents, or skip directly to synthesizer."""
    tasks = state.get("tasks", [])
    agents = {
        task["agent"] for task in tasks
        if task.get("phase") == 2 and task.get("agent") in PHASE2_AGENTS
    }
    return list(agents) if agents else ["synthesizer"]


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("data_agent", data_agent_node)
    graph.add_node("risk_agent", risk_agent_node)
    graph.add_node("pipeline_agent", pipeline_agent_node)
    graph.add_node("phase2_router", lambda state: {})
    graph.add_node("chart_agent", chart_agent_node)
    graph.add_node("lp_agent", lp_agent_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        route_phase1,
        ["data_agent", "risk_agent", "pipeline_agent", "phase2_router"],
    )

    graph.add_edge("data_agent", "phase2_router")
    graph.add_edge("risk_agent", "phase2_router")
    graph.add_edge("pipeline_agent", "phase2_router")

    graph.add_conditional_edges(
        "phase2_router",
        route_phase2,
        ["chart_agent", "lp_agent", "synthesizer"],
    )

    graph.add_edge("chart_agent", "synthesizer")
    graph.add_edge("lp_agent", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile(checkpointer=MemorySaver())
