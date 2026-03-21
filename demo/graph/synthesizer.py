import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import AgentState
from llm import get_llm

logger = logging.getLogger(__name__)

SYNTHESIZER_PROMPT = """You are the final synthesizer of a procurement supply-chain analysis system.
You receive the user's original question and pre-formatted summaries from sub-agents.
The sub-agents already presented their detailed findings directly to the user.
Do NOT repeat the full details; instead:
1. Provide a brief executive summary (2-3 sentences max).
2. Identify cross-cutting insights or conflicts between agent results (e.g., a top-ranked supplier is in a geopolitically risky region).
3. Offer 2-3 actionable next steps.
Keep your response under 150 words and respond in the same language the user used."""


async def synthesizer_node(state: AgentState) -> dict:
    start = time.perf_counter()

    llm = get_llm()
    agent_results = state["agent_results"]
    formatted = "\n\n".join(f"## {name}\n{value}" for name, value in agent_results.items())
    response = await llm.ainvoke([
        SystemMessage(content=SYNTHESIZER_PROMPT),
        *state["messages"],
        HumanMessage(content=f"Sub-agent results:\n\n{formatted}"),
    ])

    elapsed = time.perf_counter() - start
    logger.info(f"[TIMING] synthesizer: {elapsed:.3f}s")

    prev_timings = state.get("timings") or {}
    timings = {**prev_timings, "synthesizer": round(elapsed, 3)}
    return {"final_response": response.content, "timings": timings}
