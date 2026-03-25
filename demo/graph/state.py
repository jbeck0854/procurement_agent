from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class Task(TypedDict, total=False):
    agent: str
    objective: str
    context: str
    instructions: str
    tool: str | None
    params: dict | None  # serialized from ToolParams
    phase: int  # 1 = data layer, 2 = analysis layer


def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer that merges dicts instead of overwriting — needed for parallel agents."""
    merged = left.copy() if left else {}
    if right:
        merged.update(right)
    return merged


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    tasks: list[Task]
    current_agent: str
    agent_results: Annotated[dict, merge_dicts]
    chart_results: Annotated[dict, merge_dicts]  # {chart_name: base64_png}
    raw_data: Annotated[dict, merge_dicts]  # structured data from data_agent
    final_response: str
    timings: Annotated[dict, merge_dicts]
