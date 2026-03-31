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


def _append_lp_runs(left: list | None, right: list | None) -> list:
    """Reducer that accumulates approved LP runs across turns."""
    return (left or []) + (right or [])


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
    # ── LP session state ──────────────────────────────────────────────────────
    pending_lp_run: dict | None  # LP result awaiting user approval; None = no pending run
    approved_lp_runs: Annotated[list, _append_lp_runs]  # session-approved LP runs (accumulates)
