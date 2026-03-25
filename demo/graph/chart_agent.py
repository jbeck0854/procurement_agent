"""
Chart Agent — generates visualizations using the analytics chart modules.
Operates in direct mode only (orchestrator specifies tool + params).
Supports multiple chart tasks in a single invocation.

When supplier_ids are missing or contain placeholders, the agent runs a
quick scoring pass (~0.03s) to discover the top supplier IDs itself.
This keeps chart_agent fully independent of risk_agent.
"""

import logging
import time

from graph.state import AgentState
from tools.chart_tools import DIRECT_CHART_TOOLS

logger = logging.getLogger(__name__)

# Tools that require supplier_ids
_NEEDS_SUPPLIER_IDS = {"plot_score_breakdown", "plot_supplier_comparison"}


def _find_tasks(state: AgentState, agent_name: str) -> list[dict]:
    """Find all tasks assigned to this agent."""
    return [
        task for task in state.get("tasks", [])
        if task.get("agent") == agent_name
    ]


def _quick_score_top_ids(product: str, top_k: int = 3, **score_kwargs) -> list[str]:
    """Run a fast scoring pass to discover top supplier IDs."""
    from tools.scoring import score_suppliers

    # score_suppliers returns a formatted string; parse the IDs from it
    import re
    result_text = score_suppliers.invoke({
        "product": product,
        "quantity": score_kwargs.get("Q", 5000),
        "lambda_risk": score_kwargs.get("lambda_risk", 0.5),
        "top_k": top_k,
    })
    ids = re.findall(r"SUP_[A-Z]{2,3}_\d+", result_text)
    return list(dict.fromkeys(ids))[:top_k]


def _resolve_params(params: dict, tool_name: str) -> dict:
    """Ensure supplier_ids are real IDs, running a quick score if needed."""
    resolved = dict(params)

    if tool_name not in _NEEDS_SUPPLIER_IDS:
        return resolved

    supplier_ids = resolved.get("supplier_ids")
    needs_resolve = (
        not supplier_ids
        or not isinstance(supplier_ids, list)
        or any(isinstance(s, str) and (s.startswith("<") or not s.startswith("SUP_")) for s in supplier_ids)
    )

    if needs_resolve:
        product = resolved.get("product", "")
        if product:
            logger.info(f"[CHART_AGENT] No valid supplier_ids — running quick score for '{product}'")
            real_ids = _quick_score_top_ids(
                product=product,
                top_k=3,
                Q=resolved.get("Q", 5000),
                lambda_risk=resolved.get("lambda_risk", 0.5),
            )
            if real_ids:
                resolved["supplier_ids"] = real_ids
                logger.info(f"[CHART_AGENT] Resolved supplier_ids via scoring: {real_ids}")
            else:
                logger.warning("[CHART_AGENT] Quick score returned no supplier IDs")
        else:
            logger.warning("[CHART_AGENT] Cannot resolve supplier_ids: no product specified")

    return resolved


async def chart_agent_node(state: AgentState) -> dict:
    start = time.perf_counter()
    tasks = _find_tasks(state, "chart_agent")

    if not tasks:
        logger.warning("[CHART_AGENT] No tasks found, skipping")
        return {
            "agent_results": {"chart_agent": "No chart tasks assigned."},
            "chart_results": {},
            "timings": {"chart_agent": 0.0},
        }

    chart_results = {}
    generated = []
    errors = []
    timings = {}

    for task in tasks:
        tool_name = task.get("tool")
        params = task.get("params") or {}
        logger.info(f"[CHART_AGENT] Task: tool={tool_name}, raw_params={params}")

        if not tool_name or tool_name not in DIRECT_CHART_TOOLS:
            logger.error(f"[CHART_AGENT] Unknown chart tool: {tool_name}")
            errors.append(f"Unknown tool: {tool_name}")
            continue

        # Resolve any placeholder params (runs quick score if needed)
        params = _resolve_params(params, tool_name)
        logger.info(f"[CHART_AGENT] Resolved params: {params}")
        tool_fn = DIRECT_CHART_TOOLS[tool_name]

        t0 = time.perf_counter()
        try:
            result = tool_fn(**params)
            elapsed = round(time.perf_counter() - t0, 3)
            chart_results[result["name"]] = result["image"]
            generated.append(result["name"])
            timings[f"chart_agent.{tool_name}"] = elapsed
            logger.info(f"[CHART_AGENT] Generated {tool_name} in {elapsed:.3f}s")
        except Exception as e:
            elapsed = round(time.perf_counter() - t0, 3)
            timings[f"chart_agent.{tool_name}"] = elapsed
            errors.append(f"{tool_name}: {e}")
            logger.error(f"[CHART_AGENT] Failed {tool_name}: {e}", exc_info=True)

    total = round(time.perf_counter() - start, 3)
    timings["chart_agent"] = total
    logger.info(f"[TIMING] chart_agent total: {total:.3f}s — generated {len(generated)} chart(s)")

    parts = []
    if generated:
        parts.append(f"Generated {len(generated)} chart(s): {', '.join(generated)}")
    if errors:
        parts.append(f"Errors: {'; '.join(errors)}")
    summary = " | ".join(parts) if parts else "No charts generated."

    return {
        "agent_results": {"chart_agent": summary},
        "chart_results": chart_results,
        "timings": timings,
    }
