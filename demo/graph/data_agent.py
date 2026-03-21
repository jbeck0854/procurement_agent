import logging
import time

from langgraph.prebuilt import create_react_agent

from graph.state import AgentState
from llm import get_llm
from mcp_client import mcp_session, get_mcp_tools
from tools.scoring import score_suppliers

logger = logging.getLogger(__name__)

# Map of tool names to their callable objects
DIRECT_TOOLS = {
    "score_suppliers": score_suppliers,
}

DATA_AGENT_PROMPT = """You are a data agent for a procurement supply chain PostgreSQL database.

DATABASE SCHEMA:
- vw_supplier_complete_profile (VIEW - use this for most supplier queries):
  supplier_id, country_code, product, lead_time_mean, lead_time_stddev,
  disruption_probability, compliance_eligibility, logistics_reliability,
  baseline_price, price_volatility, probability_of_defect, bulk_discount,
  bulk_units, hts8, mfn_text_rate_pct, tariff_description

- dim_supplier: supplier_id, country_code, and supplier attributes
- dim_product: product details
- dim_country: country_code, country_name
- dim_tariff_code: tariff/HTS code details

IMPORTANT RULES:
- Use vw_supplier_complete_profile for supplier queries. Do NOT guess table names.
- For supplier scoring/ranking, use the score_suppliers tool instead of writing SQL.
- For simple data queries (counts, filters, aggregates), use the execute_sql tool.
- Always use the schema above. Never assume table names like "suppliers" or "products".
"""


async def _run_direct(task: dict) -> tuple[str, dict]:
    """Directly invoke a tool without LLM reasoning."""
    tool_name = task["tool"]
    params = task.get("params") or {}
    tool_fn = DIRECT_TOOLS[tool_name]

    t0 = time.perf_counter()
    content = tool_fn.invoke(params)
    elapsed = round(time.perf_counter() - t0, 3)

    logger.info(f"[DIRECT] Called {tool_name}({params}) in {elapsed:.3f}s")
    timings = {"data_agent.direct_tool": elapsed}
    return content, timings


async def _run_react(task: dict) -> tuple[str, dict]:
    """Fall back to ReAct loop for exploratory queries."""
    timings = {}
    prompt = (
        f"Objective: {task['objective']}\n"
        f"Context: {task['context']}\n"
        f"Instructions: {task['instructions']}"
    )
    llm = get_llm()

    t0 = time.perf_counter()
    async with mcp_session() as session:
        mcp_tools = await get_mcp_tools(session)
        timings["data_agent.mcp_init"] = round(time.perf_counter() - t0, 3)
        logger.info(f"[TIMING] MCP session init: {timings['data_agent.mcp_init']:.3f}s")

        all_tools = [*mcp_tools, score_suppliers]
        agent = create_react_agent(llm, all_tools, prompt=DATA_AGENT_PROMPT)

        t1 = time.perf_counter()
        result = await agent.ainvoke({"messages": [("user", prompt)]})
        timings["data_agent.react_loop"] = round(time.perf_counter() - t1, 3)
        logger.info(f"[TIMING] ReAct loop: {timings['data_agent.react_loop']:.3f}s")

    # Log ReAct iteration details
    msgs = result["messages"]
    ai_msgs = [m for m in msgs if m.type == "ai"]
    tool_msgs = [m for m in msgs if m.type == "tool"]
    tool_calls_total = sum(len(m.tool_calls) for m in ai_msgs if hasattr(m, "tool_calls"))
    logger.info(
        f"[REACT] {len(ai_msgs)} AI messages, {len(tool_msgs)} tool messages, "
        f"{tool_calls_total} tool calls total"
    )
    for i, m in enumerate(msgs):
        if m.type == "ai" and hasattr(m, "tool_calls") and m.tool_calls:
            tools_called = [tc["name"] for tc in m.tool_calls]
            logger.info(f"[REACT] Step {i}: AI called tools: {tools_called}")
        elif m.type == "ai":
            preview = m.content[:100] if m.content else "(empty)"
            logger.info(f"[REACT] Step {i}: AI response: {preview}...")
        elif m.type == "tool":
            logger.info(f"[REACT] Step {i}: Tool '{m.name}' returned {len(m.content)} chars")

    content = result["messages"][-1].content
    return content, timings


def _find_task(state: AgentState, agent_name: str) -> dict:
    """Find the task assigned to this agent."""
    for task in state.get("tasks", []):
        if task.get("agent") == agent_name:
            return task
    return state["tasks"][0]  # fallback


async def data_agent_node(state: AgentState) -> dict:
    start = time.perf_counter()
    task = _find_task(state, "data_agent")

    # Direct tool call when orchestrator specified exact tool + params
    tool_name = task.get("tool")
    if tool_name and tool_name in DIRECT_TOOLS:
        logger.info(f"[DATA_AGENT] Direct mode: {tool_name}")
        content, timings = await _run_direct(task)
    else:
        logger.info("[DATA_AGENT] ReAct mode (exploratory query)")
        content, timings = await _run_react(task)

    total = time.perf_counter() - start
    timings["data_agent"] = round(total, 3)
    logger.info(f"[TIMING] data_agent total: {total:.3f}s")

    prev_timings = state.get("timings") or {}
    return {"agent_results": {"data_agent": content}, "timings": {**prev_timings, **timings}}
