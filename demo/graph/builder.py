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
# Agents whose output benefits from LLM summarization (free-form text results).
_NEEDS_SYNTHESIS = {"data_agent", "risk_agent"}


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
    """Fan-out to Phase 2 agents, or route to synthesizer/END."""
    tasks = state.get("tasks", [])
    agents = {
        task["agent"] for task in tasks
        if task.get("phase") == 2 and task.get("agent") in PHASE2_AGENTS
    }
    if agents:
        return list(agents)
    # No Phase 2 agents — check if synthesis is needed
    return _route_post_execution(state)


def _route_post_execution(state: AgentState) -> list[str]:
    """After all agents finish, decide: synthesizer (LLM summary) or END (direct).

    Synthesizer is only needed when data_agent or risk_agent participated,
    since they return free-form text that benefits from LLM summarization.
    Pipeline/chart/LP results are already structured — skip synthesizer for speed.
    """
    tasks = state.get("tasks", [])
    all_agents = {task["agent"] for task in tasks}
    if all_agents & _NEEDS_SYNTHESIS:
        return ["synthesizer"]
    return [END]


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
        ["chart_agent", "lp_agent", "synthesizer", END],
    )

    # After Phase 2 agents: synthesizer only if data/risk agent participated
    graph.add_conditional_edges("chart_agent", _route_post_execution, ["synthesizer", END])
    graph.add_conditional_edges("lp_agent", _route_post_execution, ["synthesizer", END])
    graph.add_edge("synthesizer", END)

    return graph.compile(checkpointer=MemorySaver())
