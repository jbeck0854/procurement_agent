import json
import logging
import time

from pydantic import BaseModel
from langchain_core.messages import SystemMessage
from langgraph.types import interrupt

from graph.state import AgentState
from llm import get_llm

logger = logging.getLogger(__name__)

# ── LP session-state tokens ────────────────────────────────────────────────────

_APPROVAL_TOKENS = frozenset({
    'approve', 'approved', 'lock it in', 'lock in', 'accept', 'accept this plan',
    'go ahead', 'looks good', 'perfect', 'yes',
})
_REJECTION_TOKENS = frozenset({
    'reject', 'rejected', 'rerun', 're-run', 'try again', 'discard',
    'modify constraints', 'modify', 'change', 'no', 'cancel', 'redo',
})
_SESSION_SUMMARY_TOKENS = frozenset({
    'session summary', 'final summary', 'procurement summary', 'wrap up',
    'wrap-up', 'summarize session', 'show summary',
})


def _last_human_content(state: AgentState) -> str:
    """Return the last human message content, lowercased and stripped."""
    for m in reversed(state.get('messages', [])):
        if hasattr(m, 'type') and m.type == 'human':
            return (m.content or '').lower().strip()
    return ''


def _matches_any(text: str, tokens: frozenset) -> bool:
    return any(tok in text for tok in tokens)


def _extract_lp_record(lp_result: dict) -> dict:
    """
    Extract the session-level record from a full LP result dict.
    Stored in approved_lp_runs; used by the session summary builder.
    """
    params = lp_result.get('params_recap', {})
    req    = lp_result.get('requirement', {})
    cs     = lp_result.get('cost_summary', {})
    cd     = lp_result.get('constraint_diagnostics', {})
    alloc  = lp_result.get('allocation', [])

    return {
        'product':                params.get('product', 'N/A'),
        'facility_scope':         params.get('facility_id') or 'all facilities',
        'total_units_procured':   req.get('adjusted_requirement', 0),
        'selected_suppliers':     [r['supplier_id'] for r in alloc],
        'supplier_countries':     cd.get('countries_selected', []),
        'total_cost':             cs.get('total_cost_usd', 0.0),
        'risk_adjusted_total':    cs.get('total_risk_adjusted_cost', 0.0),
        'avg_landed_unit_cost':   cs.get('avg_landed_unit_cost', 0.0),
        'avg_risk_penalty':       cs.get('avg_risk_penalty_norm', 0.0),
        'budget_cap':             params.get('budget_cap'),
        'budget_utilization_pct': cs.get('budget_utilization_pct'),
        'diversification_mode':   params.get('diversification_mode', 'none'),
        'service_level_target':   params.get('service_level_target', 1.0),
        'executive_summary':      lp_result.get('executive_summary', ''),
        'baseline':               lp_result.get('baseline', {}),
    }

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

    # ── LP approval / rejection pre-check (runs before LLM task planning) ─────
    pending = state.get('pending_lp_run')
    if pending:
        msg = _last_human_content(state)
        elapsed = round(time.perf_counter() - start, 3)

        if _matches_any(msg, _APPROVAL_TOKENS):
            logger.info("[ORCHESTRATOR] LP run approved by user")
            run_record = _extract_lp_record(pending)
            return {
                'intent':           'lp_approved',
                'tasks':            [],
                'approved_lp_runs': [run_record],
                'pending_lp_run':   None,
                'timings':          {'orchestrator': elapsed},
            }

        if _matches_any(msg, _REJECTION_TOKENS):
            logger.info("[ORCHESTRATOR] LP run rejected by user")
            return {
                'intent':         'lp_rejected',
                'tasks':          [],
                'pending_lp_run': None,
                'timings':        {'orchestrator': elapsed},
            }

    # ── Session summary request ────────────────────────────────────────────────
    msg = _last_human_content(state)
    if _matches_any(msg, _SESSION_SUMMARY_TOKENS):
        logger.info("[ORCHESTRATOR] Session summary requested")
        elapsed = round(time.perf_counter() - start, 3)
        return {
            'intent':  'session_summary',
            'tasks':   [],
            'timings': {'orchestrator': elapsed},
        }

    # ── Normal LLM task planning ───────────────────────────────────────────────
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
