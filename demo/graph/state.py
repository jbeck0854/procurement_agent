from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class Task(TypedDict):
    agent: str
    objective: str
    context: str
    instructions: str


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    tasks: list[Task]
    current_agent: str
    agent_results: dict
    final_response: str
