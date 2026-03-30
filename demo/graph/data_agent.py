import logging
import time

from langgraph.prebuilt import create_react_agent

from graph.state import AgentState
from llm import get_llm
from mcp_client import mcp_session, get_mcp_tools

logger = logging.getLogger(__name__)

DATA_AGENT_PROMPT = """You are a data agent for a procurement supply chain PostgreSQL database.

DATABASE SCHEMA:

SUPPLIER TABLES:
- vw_supplier_complete_profile (VIEW - use this for most supplier queries):
  supplier_id, country_code, product, lead_time_mean, lead_time_stddev,
  disruption_probability, compliance_eligibility, logistics_reliability,
  baseline_price, price_volatility, probability_of_defect, bulk_discount,
  bulk_units, hts8, mfn_text_rate_pct, tariff_description
- dim_supplier: supplier_id, country_code, and supplier attributes
- dim_product: product_key, product (name string e.g. 'transistors')
- dim_country: country_code, country_name
- dim_tariff_code: tariff/HTS code details

DEMAND FORECAST TABLES:
- dim_forecast_run: forecast_run_id, model_name, trained_on_rows, horizon_weeks,
  created_at. Use MAX(forecast_run_id) to get the latest run.
- fact_semiconductor_demand_forecast: forecast_run_id, facility_id, semiconductor_id,
  target_week_date, predicted_demand, lower_90, upper_90.
  Weekly forward demand by finished-good SKU and facility. Precomputed.
- fact_semiconductor_demand: Historical actuals. facility_id, semiconductor_id,
  week_date, num_orders (actual demand).
- dim_semiconductor: semiconductor_key, semiconductor_id, semiconductor_name.
- dim_facility: facility_key, facility_id, facility_name, region.

BOM & COMPONENT REQUIREMENT VIEWS:
- dim_bom: semiconductor_id, product_key, units_per_sku. Maps finished-good SKUs
  to procurement components (transistors, power_devices, etc.).
- vw_component_requirement_lp: forecast_run_id, target_week_date, facility_id,
  product_key, total_component_requirement. Aggregated component demand per week.
  JOIN with dim_product ON product_key to get product name.

INVENTORY & PROCUREMENT REQUIREMENT:
- fact_component_inventory_history: facility_id, product_key, week_date, on_hand_qty,
  scheduled_receipts_qty, backorder_qty, inventory_position.
- fact_inventory_policy: forecast_run_id, facility_id, product_key, safety_stock_qty,
  base_stock_target_qty, mean_demand, review_period_weeks.
- vw_procurement_requirement: forecast_run_id, target_week_date, facility_id,
  product_key, gross_requirement, on_hand_qty, safety_stock_qty, net_requirement.
  Use this to find what needs to be procured. Filter net_requirement > 0 for action items.
  JOIN with dim_product ON product_key to get product names.

IMPORTANT RULES:
- Use vw_supplier_complete_profile for supplier queries. Do NOT guess table names.
- For demand forecasts, use fact_semiconductor_demand_forecast with the latest forecast_run_id.
- For component requirements, use vw_component_requirement_lp joined with dim_product.
- For procurement needs, use vw_procurement_requirement joined with dim_product.
- For simple data queries (counts, filters, aggregates), use the execute_sql tool.
- Always use the schema above. Never assume table names like "suppliers" or "products".
- Scoring and ranking are handled by a separate agent — focus on data retrieval only.
"""


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

        agent = create_react_agent(llm, mcp_tools, prompt=DATA_AGENT_PROMPT)

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

    logger.info("[DATA_AGENT] ReAct mode (SQL query)")
    content, timings = await _run_react(task)

    total = time.perf_counter() - start
    timings["data_agent"] = round(total, 3)
    logger.info(f"[TIMING] data_agent total: {total:.3f}s")

    return {"agent_results": {"data_agent": content}, "timings": timings}
