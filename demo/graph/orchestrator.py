"""
Orchestrator — LLM intent classification + code-side parameter extraction.

The LLM classifies user intent and selects the right agent/tool (~4-5s).
For LP tasks, param_extractor fills in parameters deterministically (0ms).
"""

import json
import logging
import time

from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from langgraph.types import interrupt

from graph.state import AgentState
from llm import get_llm
from param_extractor import extract_lp_params, merge_with_prior, fill_defaults

logger = logging.getLogger(__name__)


# ── Simplified output schema ─────────────────────────────────────────────────

class TaskOutput(BaseModel):
    agent: str                       # pipeline_agent | lp_agent | chart_agent | data_agent | risk_agent | out_of_scope
    tool: str | None = None          # exact tool name (required for pipeline/chart/lp agents)
    params_json: str | None = None   # JSON string with tool parameters

class OrchestratorOutput(BaseModel):
    intent: str                      # one short sentence
    tasks: list[TaskOutput]


# ── System prompt ────────────────────────────────────────────────────────────

ORCHESTRATOR_PROMPT = """\
You are a router for a procurement supply-chain system.
Given a user message, output the intent and one or more tasks.
Each task specifies which agent and tool to call. Keep output minimal — no explanations.

AGENTS AND TOOLS:

pipeline_agent — pre-built fast queries (sub-second). Tools:
  Forecast: query_forecast_summary (no params) | query_forecast_drilldown (optional: forecast_run_id) | query_forecast_model_assessment (direction: "validation"|"features"|"baseline")
  BOM: query_component_requirements (no params) | query_bom_translation (semiconductor_id, default "SEMICONDUCTOR_6")
  Inventory: query_procurement_status (no params) | query_procurement_planning_summary (no params) | query_aggregated_procurement_need (optional: product, facility_id) | query_procurement_drilldown (product required) | query_triggered_procurement_rows (optional: product)

lp_agent — LP procurement optimization. Tool: run_optimization
  params: product (required). All other params (lambda_risk, max_supplier_share, etc.) are extracted automatically — you only need to provide product.

chart_agent — supplier visualizations. Tools:
  plot_score_breakdown (product, Q, lambda_risk) | plot_supplier_comparison (supplier_ids, product, Q) | plot_country_comparison (country_codes) | plot_price_trend (country_code, product) | plot_volatility_trend (country_code, product, window) | plot_cross_country_volatility (product, country_codes) | plot_price_vs_commodity (country_code, product)

data_agent — free-form PostgreSQL queries. No tool/params needed.
risk_agent — web search for geopolitical risks, tariffs, sanctions. No tool/params needed.
planner — user is initiating a new procurement planning session (e.g. "help me plan", "I need to plan procurement"). Returns workflow overview. No tool/params needed.
out_of_scope — request is unrelated to procurement/supply-chain. No tool/params needed.

VALID PRODUCT NAMES (use exactly as written):
  transistors | microprocessors | integrated_circuit_components | power_devices
  Map user terms: "integrated circuits" / "IC" / "IC components" → "integrated_circuit_components"

RULES:
- "what if" / "unavailable" / "exclude" + a supplier ID (SUP_XXX_NN) → ALWAYS route to lp_agent.
- "expedite" / "urgent" / "behind schedule" → ALWAYS route to lp_agent.
- chart_agent tools are self-contained. Do NOT add data_agent alongside chart_agent.
- One lp_agent task per product. Do NOT add chart_agent alongside lp_agent.
- ALWAYS output at least one task. Use defaults for missing params.
- For lp_agent: product param MUST be one of the valid product names above.

EXAMPLES:

User: "I need to plan procurement for semiconductors over the next 16 weeks. Minimize cost, moderate risk."
→ intent: "Initialize procurement planning workflow"
  tasks: [{agent: "planner"}]

User: "Help me plan procurement for the upcoming 20 week planning horizon with a balance between cost and reliability."
→ intent: "Initialize procurement planning workflow"
  tasks: [{agent: "planner"}]

User: "Yes, proceed" / "Confirmed" / "Looks correct, continue"
→ intent: "User confirmed — retrieve forecast summary"
  tasks: [{agent: "pipeline_agent", tool: "query_forecast_summary"}]

User: "Compare forecast demand across all facilities"
→ intent: "Cross-facility forecast comparison"
  tasks: [{agent: "pipeline_agent", tool: "query_forecast_drilldown"}]

User: "Show forecast detail for Facility 2"
→ intent: "Single-facility forecast drilldown"
  tasks: [{agent: "pipeline_agent", tool: "query_forecast_drilldown"}]

User: "Are these forecasts reliable? How was the model trained?"
→ intent: "Forecast model validation"
  tasks: [{agent: "pipeline_agent", tool: "query_forecast_model_assessment", params: {"direction": "validation"}}]

User: "How does this model compare to baseline approaches?"
→ intent: "Forecast baseline comparison"
  tasks: [{agent: "pipeline_agent", tool: "query_forecast_model_assessment", params: {"direction": "baseline"}}]

User: "What features drive the forecast?"
→ intent: "Forecast feature importance"
  tasks: [{agent: "pipeline_agent", tool: "query_forecast_model_assessment", params: {"direction": "features"}}]

User: "Show total component requirements for the upcoming demand window"
→ intent: "Full-horizon gross component demand"
  tasks: [{agent: "pipeline_agent", tool: "query_component_requirements"}]

User: "How exactly is forecasted SKU demand translated into component demand?"
→ intent: "BOM translation explainability"
  tasks: [{agent: "pipeline_agent", tool: "query_bom_translation", params: {"semiconductor_id": "SEMICONDUCTOR_6"}}]

User: "After inventory is factored in, what needs to be ordered for each component?"
→ intent: "Net procurement requirement after inventory"
  tasks: [{agent: "pipeline_agent", tool: "query_aggregated_procurement_need"}]

User: "In which weeks and where is procurement triggered across the planning horizon?"
→ intent: "Weekly procurement trigger drilldown"
  tasks: [{agent: "pipeline_agent", tool: "query_triggered_procurement_rows"}]

User: "How is safety stock calculated?" / "Explain the base stock policy"
→ intent: "Inventory policy explainability"
  tasks: [{agent: "pipeline_agent", tool: "query_procurement_status"}]

User: "Provide a procurement plan for transistors with moderate risk. No supplier should exceed 40%."
→ intent: "LP optimization — transistors"
  tasks: [{agent: "lp_agent", tool: "run_optimization", params: {"product": "transistors"}}]

User: "Procurement plan for integrated circuit components with moderate risk aversion. No supplier should exceed 40%."
→ intent: "LP optimization — integrated circuit components"
  tasks: [{agent: "lp_agent", tool: "run_optimization", params: {"product": "integrated_circuit_components"}}]

User: "What if SUP_HKG_38 becomes unavailable?"
→ intent: "What-if disruption — exclude SUP_HKG_38"
  tasks: [{agent: "lp_agent", tool: "run_optimization", params: {"product": "transistors"}}]

User: "We need to expedite this component"
→ intent: "Urgency rerun"
  tasks: [{agent: "lp_agent", tool: "run_optimization", params: {"product": "transistors"}}]

User: "Rank the top suppliers for power_devices"
→ intent: "Supplier scoring and ranking"
  tasks: [{agent: "chart_agent", tool: "plot_score_breakdown", params: {"product": "power_devices", "Q": 5000, "lambda_risk": 0.5}}]

User: "What's the weather like today?" / "Tell me a joke"
→ intent: "Out of scope"
  tasks: [{agent: "out_of_scope"}]

MULTI-TASK EXAMPLES (emit MORE THAN ONE task when the user asks two independent questions in one message):

User: "Show me where and when we need to trigger procurement in the upcoming horizon, and scan recent news for any semiconductor supply chain disruptions or tariff changes."
→ intent: "Internal procurement triggers with external supply-chain risk scan"
  tasks: [
    {agent: "pipeline_agent", tool: "query_triggered_procurement_rows"},
    {agent: "risk_agent"}
  ]

User: "Which weeks do we need to order components, and what's happening globally that could affect supply?"
→ intent: "Procurement schedule with geopolitical risk overlay"
  tasks: [
    {agent: "pipeline_agent", tool: "query_triggered_procurement_rows"},
    {agent: "risk_agent"}
  ]

User: "Compare forecast across facilities and check recent tariff news."
→ intent: "Cross-facility forecast with tariff news"
  tasks: [
    {agent: "pipeline_agent", tool: "query_forecast_drilldown"},
    {agent: "risk_agent"}
  ]
"""


# ── Orchestrator node ────────────────────────────────────────────────────────

_PHASE2_AGENTS = frozenset({"chart_agent", "lp_agent"})


async def orchestrator_node(state: AgentState) -> dict:
    start = time.perf_counter()

    llm = get_llm().with_structured_output(OrchestratorOutput)
    messages = [SystemMessage(content=ORCHESTRATOR_PROMPT)] + state["messages"]
    response = await llm.ainvoke(messages)

    llm_elapsed = time.perf_counter() - start
    logger.info(f"[TIMING] orchestrator LLM call: {llm_elapsed:.3f}s")

    # Extract user text for param_extractor
    user_text = ""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "content") and hasattr(msg, "type") and msg.type == "human":
            user_text = msg.content
            break
        elif isinstance(msg, tuple) and msg[0] == "user":
            user_text = msg[1]
            break

    # ── Handle planner (workflow overview) ──────────────────────────────
    # LLM routes initialization queries to planner agent.
    logger.info("[ORCHESTRATOR] llm_agents=%s", [t.agent for t in response.tasks])

    if all(t.agent == "planner" for t in response.tasks):
        logger.info("[ORCHESTRATOR] planner detected — returning workflow overview")
        planner_tasks = [{
            "agent": "planner",
            "tool": None,
            "params": None,
            "phase": 1,
            "objective": "",
            "context": "",
            "instructions": "",
        }]
        total_elapsed = time.perf_counter() - start
        return {
            "intent": response.intent,
            "tasks": planner_tasks,
            "final_response": (
                '<p style="color:#fff;margin:0 0 1rem;">Understood. We will:</p>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">01</span>'
                'Verify your historical demand across all four facilities and semiconductor SKUs</p></div>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">02</span>'
                'Translate that demand into the exact component requirements needed to support production</p></div>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">03</span>'
                'Assess inventory coverage and identify where procurement is required</p></div>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">04</span>'
                'Optimize supplier allocation to minimize cost while controlling supplier risk and disruption</p></div>'
                '<hr style="border:none;border-top:1px solid #333;margin:1rem 0;">'
                '<p style="color:#ccc;margin:0 0 0.5rem;font-size:0.85rem;">'
                'Your objective balances <strong>cost efficiency</strong> with <strong>supply reliability</strong> — '
                'the risk parameter controls this tradeoff.</p>'
                '<p style="color:#ccc;margin:0 0 0.5rem;font-size:0.85rem;">'
                "Let's begin by validating the historical demand that drives this entire workflow.</p>"
                '<p style="color:#76b900;margin:0;font-size:0.85rem;font-weight:600;">'
                "Reply 'Yes, proceed' to continue.</p>"
            ),
            "timings": {"orchestrator": round(total_elapsed, 3), "orchestrator.llm": round(llm_elapsed, 3)},
        }

    # ── Handle out_of_scope before task serialization ──────────────────
    if all(t.agent == "out_of_scope" for t in response.tasks):
        logger.info("[ORCHESTRATOR] out_of_scope detected — returning refusal")
        out_of_scope_tasks = [{
            "agent": "out_of_scope",
            "tool": None,
            "params": None,
            "phase": 1,
            "objective": "",
            "context": "",
            "instructions": "",
        }]
        total_elapsed = time.perf_counter() - start
        return {
            "intent": response.intent,
            "tasks": out_of_scope_tasks,
            "final_response": (
                "This request is outside the scope of the procurement planning system. "
                "I can help with demand forecasting, component requirements, inventory analysis, "
                "supplier scoring, and procurement optimization."
            ),
            "timings": {"orchestrator": round(total_elapsed, 3), "orchestrator.llm": round(llm_elapsed, 3)},
        }

    # ── Resolve LP history from approved runs in state ───────────────
    # approved_lp_runs is populated by the Streamlit UI on user approval.
    lp_history: dict[str, dict] = {}
    for run in state.get("approved_lp_runs") or []:
        product_key = run.get("product", "")
        if product_key:
            lp_history[product_key] = run

    tasks_serialized = []
    for task in response.tasks:
        d = task.model_dump()
        raw_json = d.pop("params_json", None)
        try:
            d["params"] = json.loads(raw_json) if raw_json else None
        except (json.JSONDecodeError, TypeError):
            d["params"] = None
        d["phase"] = 2 if d.get("agent") in _PHASE2_AGENTS else 1

        # ── LP parameter extraction + completion ────────────────────────
        if d.get("agent") == "lp_agent" and user_text:
            # LLM only provides product name; code extracts all other params
            llm_params = d.get("params") or {}
            product = llm_params.get("product", "")

            # Check for prior LP context (what-if / urgency reruns)
            prior = lp_history.get(product)
            if prior:
                # Merge: prior run params + current prompt overrides
                final_params = merge_with_prior(user_text, prior)
                # LLM may have set a different product (e.g. user switched)
                if product:
                    final_params["product"] = product
            else:
                # Fresh LP run: extract params from user text + defaults
                extracted = extract_lp_params(user_text)
                final_params = {"product": product}
                final_params.update(extracted)

            d["params"] = fill_defaults(final_params)
            logger.info(
                "[PARAM EXTRACTOR] product=%s | prior_context=%s | final=%s",
                product, bool(prior), {k: v for k, v in d["params"].items() if k != "product"},
            )

        # Back-fill display fields for plan approval page + ReAct agent prompts.
        # ReAct agents (data_agent, risk_agent) use these to build their prompt.
        if d.get("agent") in ("data_agent", "risk_agent") and user_text:
            d.setdefault("objective", user_text)
            d.setdefault("context", f"Intent: {response.intent}")
            d.setdefault("instructions", "Answer the user's question thoroughly.")
        else:
            d.setdefault("objective", "")
            d.setdefault("context", "")
            d.setdefault("instructions", "")
        tasks_serialized.append(d)

    # ── Safety net: catch planner / out_of_scope that slipped past early checks ─
    _direct_agents = {"planner", "out_of_scope"}
    if tasks_serialized and all(t.get("agent") in _direct_agents for t in tasks_serialized):
        agent_type = tasks_serialized[0].get("agent") if tasks_serialized else "out_of_scope"
        logger.info("[ORCHESTRATOR] safety-net caught %s — returning final_response", agent_type)
        total_elapsed = time.perf_counter() - start
        if agent_type == "planner":
            resp_text = (
                '<p style="color:#fff;margin:0 0 1rem;">Understood. We will:</p>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">01</span>'
                'Verify your historical demand across all four facilities and semiconductor SKUs</p></div>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">02</span>'
                'Translate that demand into the exact component requirements needed to support production</p></div>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">03</span>'
                'Assess inventory coverage and identify where procurement is required</p></div>'
                '<div style="background:#0A1F17;border-left:3px solid #76b900;border-radius:2px;padding:0.65rem 1rem;margin:0.4rem 0;">'
                '<p style="color:#fff;margin:0;font-size:0.88rem;"><span style="color:#76b900;font-weight:300;font-size:1.1rem;margin-right:8px;">04</span>'
                'Optimize supplier allocation to minimize cost while controlling supplier risk and disruption</p></div>'
                '<hr style="border:none;border-top:1px solid #333;margin:1rem 0;">'
                '<p style="color:#ccc;margin:0 0 0.5rem;font-size:0.85rem;">'
                'Your objective balances <strong>cost efficiency</strong> with <strong>supply reliability</strong> — '
                'the risk parameter controls this tradeoff.</p>'
                '<p style="color:#ccc;margin:0 0 0.5rem;font-size:0.85rem;">'
                "Let's begin by validating the historical demand that drives this entire workflow.</p>"
                '<p style="color:#76b900;margin:0;font-size:0.85rem;font-weight:600;">'
                "Reply 'Yes, proceed' to continue.</p>"
            )
        else:
            resp_text = (
                "This request is outside the scope of the procurement planning system. "
                "I can help with demand forecasting, component requirements, inventory analysis, "
                "supplier scoring, and procurement optimization."
            )
        return {
            "intent": response.intent,
            "tasks": tasks_serialized,
            "final_response": resp_text,
            "timings": {"orchestrator": round(total_elapsed, 3), "orchestrator.llm": round(llm_elapsed, 3)},
        }

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

    total_elapsed = time.perf_counter() - start
    logger.info(f"[TIMING] orchestrator total: {total_elapsed:.3f}s")

    return {
        "intent": plan_payload["intent"],
        "tasks": tasks,
        "timings": {"orchestrator": round(total_elapsed, 3), "orchestrator.llm": round(llm_elapsed, 3)},
    }
