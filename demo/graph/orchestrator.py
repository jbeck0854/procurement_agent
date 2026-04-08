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

Phase 1 (data + risk + pipeline):
- pipeline_agent (phase=1): Runs pre-built pipeline queries for demand forecasts, component
  requirements, and procurement status. FAST (sub-second). Use this instead of data_agent
  for forecast, BOM, inventory, and procurement queries. Set tool to one of the pipeline tools below.
- data_agent (phase=1): Queries a PostgreSQL supplier database via SQL.
  Use for: supplier data lookups and general exploratory database queries.
  Do NOT use data_agent for forecast, component requirement, or procurement status queries
  — use pipeline_agent instead (it is much faster).
- risk_agent (phase=1): Searches the web for recent geopolitical risks, tariffs, trade policies,
  sanctions, and supply chain disruptions via Tavily. ONLY use when user explicitly asks about
  geopolitical risks, news, current events, tariffs, sanctions, or trade policy.
  Do NOT generate risk_agent for standard supplier ranking, scoring, or charting requests.

Phase 2 (visualization + optimization — runs after Phase 1):
- chart_agent (phase=2): Generates visualizations AND scoring. The chart tools internally
  score and rank suppliers — you do NOT need a separate scoring step.
  Set tool to one of the chart tools below.
- lp_agent (phase=2): Runs LP procurement optimization for a specific product.
  Returns optimized supplier allocation, cost summary, and executive summary.
  Set tool to "run_optimization". Generate one lp_agent task per product that needs optimization.

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

PIPELINE TOOLS (for pipeline_agent):

Forecast:
- "query_forecast_summary": Business-facing production demand forecast summary.
  Shows planning horizon, total demand, weekly totals, model metadata. No params needed.
- "query_forecast_drilldown": Week × facility × SKU detail with confidence bounds.
  params: {"forecast_run_id": int} (optional, 0 = latest)
- "query_forecast_model_assessment": Model explainability — validation, feature importance, or baseline.
  params: {"direction": str} — use "validation", "features", or "baseline"

BOM / Component Requirements:
- "query_component_requirements": Full-horizon gross BOM demand across all components.
  Shows raw procurement volume before inventory offset. No params needed.
- "query_bom_translation": Explain how a finished-good SKU maps to procurement components.
  params: {"semiconductor_id": str} (required, e.g. "SEMICONDUCTOR_6")
  Optional: {"facility_id": str, "target_week_date": str} for forecast-row explosion.

Inventory / Procurement:
- "query_procurement_status": Week-by-week inventory-adjusted procurement trigger signal.
  Shows WHERE and WHEN procurement is activated. NOT the LP demand floor. No params needed.
- "query_procurement_planning_summary": Combined gross demand + weekly trigger signal. No params needed.
- "query_aggregated_procurement_need": Horizon-level LP demand floor — the quantity the optimizer
  actually allocates. params: {"product": str, "facility_id": str} (both optional, filter scope).
- "query_procurement_drilldown": Full week-by-week detail at component × facility × week grain.
  params: {"product": str} (required), optional: {"facility_id": str}
- "query_triggered_procurement_rows": Only weeks/facilities where net requirement > 0.
  params: {"product": str} (optional), optional: {"facility_id": str}

LP TOOLS (for lp_agent):
- "run_optimization": Optimize supplier allocation for one product.
  params: {"product": str, "lambda_risk": float, "max_supplier_share": float,
           "budget_cap": float or null, "compliance_threshold": float,
           "service_level_target": float, "urgency": bool,
           "exclude_supplier_ids": list of supplier ID strings or [],
           "facility_id": str or null,
           "diversification_mode": str — "none", "supplier_share_only", or "country_diversified"}
  Only "product" is required. Defaults: lambda_risk=0.5, max_supplier_share=1.0,
  compliance_threshold=0.5, service_level_target=1.0, urgency=false, exclude_supplier_ids=[],
  diversification_mode="none".
  - "none": No diversification constraint.
  - "supplier_share_only": Enforce max_supplier_share cap per supplier.
  - "country_diversified": Exactly 3 suppliers, each from a different country, ~33% each (MIP).

HOW TO WRITE WORK ORDERS:
- objective: One sentence — WHAT the agent should accomplish.
- context: Business background extracted from the user's message.
- instructions: 3-5 lines max. No SQL, no formulas, no implementation details.
- tool: The exact tool name (required for chart_agent, null for data_agent/risk_agent).
- params_json: A JSON string with tool parameters (required when tool is set). Example: '{"product": "transistors", "Q": 5000}'
- phase: 1 or 2. Phase 1 agents run first; Phase 2 agents run after Phase 1 completes.

LAMBDA_RISK GUIDE (use EXACT values — do not interpolate):
- "cost only" / "no risk" / "cost-only" → 0.0
- "cost focused" / "low risk" / "low" → 0.25
- "balanced" / "moderate" / "moderate risk" / "moderate risk aversion" → 0.5
- "risk averse" / "risk aversion" / "high risk" → 1.0
- "very risk averse" / "risk first" / "risk priority" → 1.5
Default if no preference stated: 0.5

If the user message contains [LP_PARAMS: ...], extract the JSON object inside and use those
values VERBATIM in the lp_agent params_json — do not change, merge, or override them.

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
- For procurement optimization / supplier allocation / "optimize" / "allocate" / "procurement plan":
  generate lp_agent (phase=2) with tool="run_optimization".
  Generate one lp_agent task PER product that needs optimization.
  Do NOT generate a separate chart_agent task alongside LP runs — supplier score breakdowns
  are available on-demand from within the LP result panel.
  Example: "optimize transistors with moderate risk and 40% max share" → one lp_agent task only.
  Example: "optimize all components" → one lp_agent task per product (transistors, power_devices, etc.).
- For disruption / what-if scenarios ("what if supplier X is unavailable"):
  generate lp_agent with exclude_supplier_ids=["SUP_XXX_NN"].
  CRITICAL: You MUST copy ALL parameters from the most recent lp_agent task in this conversation
  into the new params_json. Only add/change the exclusion. Do NOT omit parameters — if the previous
  run used max_supplier_share=0.4, the new params_json MUST include "max_supplier_share": 0.4.
  Example: previous params were {"product":"transistors","lambda_risk":0.5,"max_supplier_share":0.4}
  → new params_json: {"product":"transistors","lambda_risk":0.5,"max_supplier_share":0.4,"exclude_supplier_ids":["SUP_HKG_38"]}
- For urgency scenarios: generate lp_agent with urgency=true.
  CRITICAL: same rule — copy ALL parameters from the most recent lp_agent task, only add urgency=true.
- For diversification / "diversify across countries" / "different countries" / "diversify":
  generate lp_agent (phase=2) as the FIRST task, with diversification_mode="country_diversified".
  CRITICAL: same rule — copy ALL parameters from the most recent lp_agent task.
  Do NOT generate chart_agent as the first task for diversification requests.
- For geopolitical/risk context: ALSO generate risk_agent (phase=1). ONLY when user explicitly mentions
  geopolitical, news, tariffs, sanctions, trade policy, or similar keywords.
- For demand forecast / "what demand" / "forecast" / "planning window":
  generate pipeline_agent (phase=1) with tool="query_forecast_summary".
- For forecast drill-down / "detail by facility" / "breakdown by SKU":
  generate pipeline_agent (phase=1) with tool="query_forecast_drilldown".
- For model assessment / "how was model validated" / "what drives forecast" / "compare to baseline":
  generate pipeline_agent (phase=1) with tool="query_forecast_model_assessment".
  Set direction to "validation", "features", or "baseline" based on user intent.
- For component requirements / "what do we need" / "what components" / "total component demand":
  generate pipeline_agent (phase=1) with tool="query_component_requirements".
  Use this for AGGREGATE component demand across the horizon (how many units of each component).
- For BOM translation / "what goes into" / "BOM recipe" / "how does SKU translate" /
  "translate into component" / "how does demand translate" / "BOM breakdown":
  generate pipeline_agent (phase=1) with tool="query_bom_translation".
  Use this when the user asks HOW finished-good demand converts to component demand (the recipe/math).
  If user specifies a semiconductor ID, set semiconductor_id (e.g. "SEMICONDUCTOR_6").
  If no specific SKU is mentioned, use "SEMICONDUCTOR_6" as default to show the translation logic.
- For inventory check / "do we have enough" / "procurement status" / weekly trigger:
  generate pipeline_agent (phase=1) with tool="query_procurement_status".
- For full planning summary (gross demand + trigger signal together):
  generate pipeline_agent (phase=1) with tool="query_procurement_planning_summary".
- For LP demand floor / "what does optimizer use" / "aggregated procurement need" / "how much to buy":
  generate pipeline_agent (phase=1) with tool="query_aggregated_procurement_need".
  Set product if user specifies one (e.g. "transistors").
- For drill-down on specific component / "drill down transistors" / "week-by-week detail":
  generate pipeline_agent (phase=1) with tool="query_procurement_drilldown".
  Set product (required) and optionally facility_id.
- For triggered procurement / "which weeks need action" / "where is procurement triggered":
  generate pipeline_agent (phase=1) with tool="query_triggered_procurement_rows".
  Optionally set product to filter.
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
    _PHASE2_AGENTS = {"chart_agent", "lp_agent"}
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
