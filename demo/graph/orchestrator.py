import json
import logging
import time

from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from langgraph.types import interrupt

from graph.state import AgentState
from llm import get_llm

logger = logging.getLogger(__name__)

class TaskOutput(BaseModel):
    agent: str
    objective: str
    context: str
    instructions: str
    tool: str | None = None
    params_json: str | None = None  # JSON string, parsed downstream
    phase: int = 1

class OrchestratorOutput(BaseModel):
    intent: str
    tasks: list[TaskOutput]

ORCHESTRATOR_PROMPT = """You are the orchestrator of a procurement supply-chain analysis system.
Your job: understand the user's request, extract key parameters, and generate work orders for sub-agents.

Execution is TWO-PHASE:
  Phase 1 runs first (data retrieval + risk intelligence). Phase 2 runs after Phase 1 completes (visualization).

AVAILABLE SUB-AGENTS:

Phase 1 (data + risk):
- data_agent (phase=1): Queries a PostgreSQL supplier database via SQL.
  Use for exploratory queries (counts, filters, aggregates, raw data lookups).
  It knows the schema — do NOT write SQL for it.
- risk_agent (phase=1): Searches the web for recent geopolitical risks, tariffs, trade policies,
  sanctions, and supply chain disruptions via Tavily. ONLY use when user explicitly asks about
  geopolitical risks, news, current events, tariffs, sanctions, or trade policy.
  Do NOT generate risk_agent for standard supplier ranking, scoring, or charting requests.

Phase 2 (visualization — runs after Phase 1):
- chart_agent (phase=2): Generates visualizations AND scoring. The chart tools internally
  score and rank suppliers — you do NOT need a separate scoring step.
  Set tool to one of the chart tools below.

CHART TOOLS (for chart_agent):
- "plot_score_breakdown": Supplier score decomposition (4 panels: final score, cost drivers, risk penalty, risk components).
  This tool SCORES suppliers internally — use it for ranking + visualization in one step.
  params: {"product": str, "Q": int, "lambda_risk": float}
  Note: supplier_ids are auto-resolved from scoring results (top 3). You may optionally specify them.
- "plot_supplier_comparison": Side-by-side supplier comparison on cost, volatility, discount, lead time.
  params: {"supplier_ids": [...], "product": str, "Q": int}
- "plot_country_comparison": Country logistics (LPI) and governance (WGI) indicators.
  params: {"country_codes": ["CHN","VNM","TWN"]}
- "plot_price_trend": Product price trend over time for one country.
  params: {"country_code": str, "product": str}
- "plot_volatility_trend": Rolling price volatility for one country + product.
  params: {"country_code": str, "product": str, "window": int}
- "plot_cross_country_volatility": Compare rolling price volatility across countries.
  params: {"product": str, "country_codes": ["CHN","VNM"]}
- "plot_price_vs_commodity": Product price vs commodity baseline trends.
  params: {"country_code": str, "product": str}

HOW TO WRITE WORK ORDERS:
- objective: One sentence — WHAT the agent should accomplish.
- context: Business background extracted from the user's message.
- instructions: 3-5 lines max. No SQL, no formulas, no implementation details.
- tool: The exact tool name (required for chart_agent, null for data_agent/risk_agent).
- params_json: A JSON string with tool parameters (required when tool is set). Example: '{"product": "transistors", "Q": 5000}'
- phase: 1 or 2. Phase 1 agents run first; Phase 2 agents run after Phase 1 completes.

LAMBDA_RISK GUIDE:
- "low risk" / "cost focused" → 0.2-0.3
- "balanced" / "moderate" → 0.5
- "risk averse" / "care about risk" → 0.7-0.8
- "very risk averse" / "risk is top priority" → 0.9

CRITICAL — CHART TOOLS ARE SELF-CONTAINED:
  chart_agent tools query the database, score suppliers, and render charts ALL internally.
  They do NOT depend on data_agent or risk_agent output.
  If the user only needs ranking, scoring, or visualization → generate ONLY chart_agent task(s).
  Do NOT add data_agent or risk_agent unless the user explicitly needs them.

TASK GENERATION RULES:
- For supplier ranking/scoring/comparison: generate ONLY chart_agent (phase=2).
  Example: "rank top 3 transistor suppliers" → one chart_agent task with plot_score_breakdown. That's it.
- For other visualizations (price trends, volatility, country comparison): generate ONLY chart_agent (phase=2).
  You may generate MULTIPLE chart_agent tasks for multi-chart requests.
- For geopolitical/risk context: ALSO generate risk_agent (phase=1). ONLY when user explicitly mentions
  geopolitical, news, tariffs, sanctions, trade policy, or similar keywords.
- For database exploration (counts, filters, "how many", "which"): generate data_agent (phase=1).
- Do NOT set tool/params for data_agent or risk_agent — they decide their own tools.
- ALWAYS generate at least one task. Never respond with zero tasks or ask for clarification.
  If parameters are missing, use sensible defaults (Q=5000, lambda_risk=0.5).
  The intent field should describe the user's goal, NOT be "clarify" or "ask_for_info"."""

async def orchestrator_node(state: AgentState) -> dict:
    start = time.perf_counter()

    llm = get_llm().with_structured_output(OrchestratorOutput)
    messages = [SystemMessage(content=ORCHESTRATOR_PROMPT)] + state["messages"]
    response = await llm.ainvoke(messages)

    llm_elapsed = time.perf_counter() - start
    logger.info(f"[TIMING] orchestrator LLM call: {llm_elapsed:.3f}s")

    # Convert params_json string → params dict, and enforce phase by agent name
    _PHASE2_AGENTS = {"chart_agent"}
    tasks_serialized = []
    for task in response.tasks:
        d = task.model_dump()
        raw_json = d.pop("params_json", None)
        try:
            d["params"] = json.loads(raw_json) if raw_json else None
        except (json.JSONDecodeError, TypeError):
            d["params"] = None
        # Auto-assign phase based on agent name (don't rely on LLM)
        d["phase"] = 2 if d.get("agent") in _PHASE2_AGENTS else 1
        tasks_serialized.append(d)

    plan_payload = {
        "intent": response.intent,
        "tasks": tasks_serialized,
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
