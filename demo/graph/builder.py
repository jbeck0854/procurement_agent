from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from graph.state import AgentState
from graph.orchestrator import orchestrator_node
from graph.data_agent import data_agent_node
from graph.search_agent import search_agent_node
from graph.synthesizer import synthesizer_node


def route_after_orchestrator(state: AgentState) -> list[str]:
    """Determine which agents to run based on tasks."""
    tasks = state.get("tasks", [])
    agents = set()
    for task in tasks:
        agent = task.get("agent")
        if agent in ("data_agent", "search_agent"):
            agents.add(agent)
    if not agents:
        agents.add("data_agent")
    return list(agents)


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("data_agent", data_agent_node)
    graph.add_node("search_agent", search_agent_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "orchestrator")

    # After orchestrator, fan out to whichever agents are in the task list
    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        ["data_agent", "search_agent"],
    )

    # Both agents converge into synthesizer
    graph.add_edge("data_agent", "synthesizer")
    graph.add_edge("search_agent", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile(checkpointer=MemorySaver())
