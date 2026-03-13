from graph.state import AgentState


def route_to_agent(state: AgentState) -> str:
    tasks = state.get("tasks", [])
    if tasks:
        return tasks[0]["agent"]
    return "data_agent"
