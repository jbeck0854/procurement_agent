import logging
import time

from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from langgraph.types import interrupt

from graph.state import AgentState
from llm import get_llm

logger = logging.getLogger(__name__)

class ToolParams(BaseModel):
    product: str = ""
    quantity: int = 5000
    lambda_risk: float = 0.5
    top_k: int = 5

class TaskOutput(BaseModel):
    agent: str
    objective: str
    context: str
    instructions: str
    tool: str | None = None
    params: ToolParams | None = None

class OrchestratorOutput(BaseModel):
    intent: str
    tasks: list[TaskOutput]

ORCHESTRATOR_PROMPT = """You are the orchestrator of a procurement supply-chain analysis system.
Your job: understand the user's request, extract key parameters, and generate concise work orders for sub-agents.

AVAILABLE SUB-AGENTS:
- data_agent: Can query a PostgreSQL supplier database and run a supplier scoring/ranking engine.
  It has a score_suppliers tool (params: product, quantity, lambda_risk, top_k) and SQL query tools.
  It knows the database schema — do NOT write SQL for it.
- search_agent: Can search the web for recent news about geopolitical risks, tariffs, trade policies,
  sanctions, and supply chain disruptions relevant to the product and supplier countries.
  Use it whenever the query involves supplier ranking or risk analysis — it provides real-time context.

HOW TO WRITE WORK ORDERS:
- objective: One sentence — WHAT the agent should accomplish. Not HOW.
- context: Business background from the user's message. Extract: product, quantity, risk preference, time constraints, any special requirements.
- instructions: Keep to 3-5 lines max. Only include:
  * Which tool to use (score_suppliers for ranking, SQL for data queries)
  * Key parameters extracted from the user's request (product name, quantity, lambda_risk value, top_k)
  * What to include in the output (e.g. "include risk factors" or "break down by country")
- tool: If you know exactly which tool the agent should call, set this field.
  * "score_suppliers" — for supplier ranking/scoring tasks
  * null — for exploratory SQL queries or when the agent needs to decide
- params: If tool is set, provide the exact parameters as a JSON object.
  * For score_suppliers: {"product": "...", "quantity": ..., "lambda_risk": ..., "top_k": ...}

DO NOT include in instructions:
- SQL queries (the agent knows the database schema)
- Scoring formulas (the agent has a scoring engine)
- Implementation details

LAMBDA_RISK GUIDE (extract from user's language):
- "low risk" / "cost focused" → lambda_risk = 0.2-0.3
- "balanced" / "moderate" → lambda_risk = 0.5
- "risk averse" / "care about risk" → lambda_risk = 0.7-0.8
- "very risk averse" / "risk is top priority" → lambda_risk = 0.9

TASK GENERATION RULES:
- Always generate a data_agent task for supplier queries.
- For any supplier ranking or risk-related query, ALSO generate a search_agent task to check recent
  geopolitical/tariff news for the relevant product and countries.
  The search_agent task should specify: the product, likely supplier countries, and what risks to look for.
- For simple data-only queries (e.g. "how many products do we have?"), only generate a data_agent task.
- tool and params fields are only for data_agent (score_suppliers). Do NOT set tool/params for search_agent."""

async def orchestrator_node(state: AgentState) -> dict:
    start = time.perf_counter()

    llm = get_llm().with_structured_output(OrchestratorOutput)
    messages = [SystemMessage(content=ORCHESTRATOR_PROMPT)] + state["messages"]
    response = await llm.ainvoke(messages)

    llm_elapsed = time.perf_counter() - start
    logger.info(f"[TIMING] orchestrator LLM call: {llm_elapsed:.3f}s")

    plan_payload = {
        "intent": response.intent,
        "tasks": [task.model_dump() for task in response.tasks],
        "question": "Please review the proposed work orders and reply 'ok' or 'approve' to continue, or send edits.",
    }
    feedback = interrupt(plan_payload)
    tasks = plan_payload["tasks"]
    if isinstance(feedback, dict) and "tasks" in feedback:
        tasks = feedback["tasks"]
    elif isinstance(feedback, str) and feedback.lower() in {"ok", "approve"}:
        pass
    # other responses fall back to the original plan for now
    total_elapsed = time.perf_counter() - start
    logger.info(f"[TIMING] orchestrator total: {total_elapsed:.3f}s")

    return {
        "intent": plan_payload["intent"],
        "tasks": tasks,
        "timings": {"orchestrator": round(total_elapsed, 3), "orchestrator.llm": round(llm_elapsed, 3)},
    }
