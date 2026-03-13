from langgraph.graph import StateGraph, START, END

from graph.state import AgentState
from graph.orchestrator import orchestrator_node
from graph.router import route_to_agent
from graph.data_agent import data_agent_node
from graph.synthesizer import synthesizer_node


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("data_agent", data_agent_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges("orchestrator", route_to_agent, {"data_agent": "data_agent"})
    graph.add_edge("data_agent", "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile()
