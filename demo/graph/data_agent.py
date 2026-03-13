from langgraph.prebuilt import create_react_agent

from graph.state import AgentState
from llm import get_llm
from mcp_client import mcp_session, get_mcp_tools
from tools.scoring import score_suppliers

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


async def data_agent_node(state: AgentState) -> dict:
    task = state["tasks"][0]
    prompt = (
        f"Objective: {task['objective']}\n"
        f"Context: {task['context']}\n"
        f"Instructions: {task['instructions']}"
    )
    llm = get_llm()
    async with mcp_session() as session:
        mcp_tools = await get_mcp_tools(session)
        all_tools = [*mcp_tools, score_suppliers]
        agent = create_react_agent(llm, all_tools, prompt=DATA_AGENT_PROMPT)
        result = await agent.ainvoke({"messages": [("user", prompt)]})
    content = result["messages"][-1].content
    return {"agent_results": {"data_agent": content}}
