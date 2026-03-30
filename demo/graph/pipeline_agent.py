"""
Pipeline Agent — runs direct-mode upstream pipeline queries
(forecast, BOM requirements, procurement status).
No ReAct loop — orchestrator specifies tool + params, agent executes directly.
"""

import logging
import time

from graph.state import AgentState
from tools.pipeline_queries import DIRECT_PIPELINE_TOOLS

logger = logging.getLogger(__name__)


def _find_tasks(state: AgentState, agent_name: str) -> list[dict]:
    """Find all tasks assigned to this agent."""
    return [
        task for task in state.get("tasks", [])
        if task.get("agent") == agent_name
    ]


async def pipeline_agent_node(state: AgentState) -> dict:
    start = time.perf_counter()
    tasks = _find_tasks(state, "pipeline_agent")

    if not tasks:
        logger.warning("[PIPELINE_AGENT] No tasks found, skipping")
        return {
            "agent_results": {"pipeline_agent": "No pipeline tasks assigned."},
            "timings": {"pipeline_agent": 0.0},
        }

    agent_results = {}
    timings = {}
    errors = []

    for task in tasks:
        tool_name = task.get("tool", "")
        params = task.get("params") or {}
        logger.info(f"[PIPELINE_AGENT] Task: tool={tool_name}, params={params}")

        if tool_name not in DIRECT_PIPELINE_TOOLS:
            logger.error(f"[PIPELINE_AGENT] Unknown tool: {tool_name}")
            errors.append(f"Unknown tool: {tool_name}")
            continue

        tool_fn = DIRECT_PIPELINE_TOOLS[tool_name]
        t0 = time.perf_counter()
        try:
            result = tool_fn(**params)
            elapsed = round(time.perf_counter() - t0, 3)
            timings[f"pipeline_agent.{tool_name}"] = elapsed
            agent_results[result["name"]] = result["content"]
            logger.info(f"[PIPELINE_AGENT] Completed {tool_name} in {elapsed:.3f}s")
        except Exception as e:
            elapsed = round(time.perf_counter() - t0, 3)
            timings[f"pipeline_agent.{tool_name}"] = elapsed
            errors.append(f"{tool_name}: {e}")
            logger.error(f"[PIPELINE_AGENT] Failed {tool_name}: {e}", exc_info=True)

    total = round(time.perf_counter() - start, 3)
    timings["pipeline_agent"] = total
    logger.info(f"[TIMING] pipeline_agent total: {total:.3f}s")

    if errors:
        agent_results["pipeline_errors"] = "; ".join(errors)

    return {
        "agent_results": agent_results,
        "timings": timings,
    }
