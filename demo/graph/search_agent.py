import logging
import time

from langgraph.prebuilt import create_react_agent

from graph.state import AgentState
from llm import get_llm
from tavily_client import tavily_mcp_session, get_tavily_tools

logger = logging.getLogger(__name__)

SEARCH_AGENT_PROMPT = """You are a geopolitical risk analyst for a procurement supply-chain system.
Your job: search for recent news that could affect supplier risk for the given countries and product.

SEARCH RULES:
- Use tavily_news_search with days=30 (last 30 days) and a SHORT, focused query (5-8 words max).
  Example good query: "semiconductor tariff export controls 2026"
  Example bad query: "semiconductor tariffs export controls sanctions Taiwan South Korea United States China Japan Germany EU microprocessor tariffs HS codes past 12 months"
- Run exactly ONE search. Do NOT search again if results are sparse.
- If the search returns no results, say "No recent news found" and stop. Do NOT fabricate analysis from your own knowledge.

OUTPUT FORMAT — keep under 200 words total:
For each relevant finding (max 5):
- **Headline** | Risk: HIGH/MEDIUM/LOW
  1-sentence impact on supply chain. [Source](url)

End with: **Overall risk assessment**: 1-2 sentences.
"""


def _find_task(state: AgentState, agent_name: str) -> dict:
    """Find the task assigned to this agent."""
    for task in state.get("tasks", []):
        if task.get("agent") == agent_name:
            return task
    return state["tasks"][0]


async def search_agent_node(state: AgentState) -> dict:
    start = time.perf_counter()
    timings = {}

    task = _find_task(state, "search_agent")
    prompt = (
        f"Objective: {task['objective']}\n"
        f"Context: {task['context']}\n"
        f"Instructions: {task['instructions']}"
    )
    llm = get_llm()

    t0 = time.perf_counter()
    async with tavily_mcp_session() as session:
        tavily_tools = await get_tavily_tools(session)
        timings["search_agent.mcp_init"] = round(time.perf_counter() - t0, 3)
        logger.info(f"[TIMING] Tavily MCP session init: {timings['search_agent.mcp_init']:.3f}s")

        agent = create_react_agent(
            llm,
            tavily_tools,
            prompt=SEARCH_AGENT_PROMPT,
        )

        t1 = time.perf_counter()
        result = await agent.ainvoke({"messages": [("user", prompt)]})
        timings["search_agent.react_loop"] = round(time.perf_counter() - t1, 3)
        logger.info(f"[TIMING] Search ReAct loop: {timings['search_agent.react_loop']:.3f}s")

    total = time.perf_counter() - start
    timings["search_agent"] = round(total, 3)
    logger.info(f"[TIMING] search_agent total: {total:.3f}s")

    # Log iteration details
    msgs = result["messages"]
    ai_msgs = [m for m in msgs if m.type == "ai"]
    tool_msgs = [m for m in msgs if m.type == "tool"]
    tool_calls_total = sum(len(m.tool_calls) for m in ai_msgs if hasattr(m, "tool_calls"))
    logger.info(
        f"[SEARCH] {len(ai_msgs)} AI messages, {len(tool_msgs)} tool messages, "
        f"{tool_calls_total} tool calls total"
    )
    for i, m in enumerate(msgs):
        if m.type == "ai" and hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                args_preview = {k: v for k, v in tc["args"].items() if k == "query"}
                logger.info(f"[SEARCH] Step {i}: AI called '{tc['name']}' query={args_preview.get('query', '?')}")
        elif m.type == "ai":
            preview = m.content[:150] if m.content else "(empty)"
            logger.info(f"[SEARCH] Step {i}: AI response ({len(m.content)} chars): {preview}...")
        elif m.type == "tool":
            content_len = len(m.content) if isinstance(m.content, str) else sum(len(c.get("text", "")) if isinstance(c, dict) else len(str(c)) for c in m.content)
            logger.info(f"[SEARCH] Step {i}: Tool '{m.name}' returned {content_len} chars")

    content = result["messages"][-1].content
    prev_timings = state.get("timings") or {}
    return {"agent_results": {"search_agent": content}, "timings": {**prev_timings, **timings}}
