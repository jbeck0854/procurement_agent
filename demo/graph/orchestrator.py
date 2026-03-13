from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from graph.state import AgentState
from llm import get_llm

class TaskOutput(BaseModel):
    agent: str
    objective: str
    context: str
    instructions: str

class OrchestratorOutput(BaseModel):
    intent: str
    tasks: list[TaskOutput]

ORCHESTRATOR_PROMPT = """You are the orchestrator of a procurement supply-chain analysis system.
Your job: understand the user's request, extract key parameters, and generate concise work orders for sub-agents.

AVAILABLE SUB-AGENTS:
- data_agent: Can query a PostgreSQL supplier database and run a supplier scoring/ranking engine.
  It has a score_suppliers tool (params: product, quantity, lambda_risk, top_k) and SQL query tools.
  It knows the database schema — do NOT write SQL for it.

HOW TO WRITE WORK ORDERS:
- objective: One sentence — WHAT the agent should accomplish. Not HOW.
- context: Business background from the user's message. Extract: product, quantity, risk preference, time constraints, any special requirements.
- instructions: Keep to 3-5 lines max. Only include:
  * Which tool to use (score_suppliers for ranking, SQL for data queries)
  * Key parameters extracted from the user's request (product name, quantity, lambda_risk value, top_k)
  * What to include in the output (e.g. "include risk factors" or "break down by country")

DO NOT include in instructions:
- SQL queries (the agent knows the database schema)
- Scoring formulas (the agent has a scoring engine)
- Implementation details

LAMBDA_RISK GUIDE (extract from user's language):
- "low risk" / "cost focused" → lambda_risk = 0.2-0.3
- "balanced" / "moderate" → lambda_risk = 0.5
- "risk averse" / "care about risk" → lambda_risk = 0.7-0.8
- "very risk averse" / "risk is top priority" → lambda_risk = 0.9

If the request is simple, generate one task. If complex, you may generate multiple tasks.
Always generate at least one task."""

async def orchestrator_node(state: AgentState) -> dict:
    llm = get_llm().with_structured_output(OrchestratorOutput)
    messages = [SystemMessage(content=ORCHESTRATOR_PROMPT)] + state["messages"]
    response = await llm.ainvoke(messages)
    return {"intent": response.intent, "tasks": [task.model_dump() for task in response.tasks]}
