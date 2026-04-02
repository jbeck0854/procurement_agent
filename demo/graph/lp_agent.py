"""
LP Agent — runs procurement optimization using the LP module.
Operates in direct mode (orchestrator specifies tool + params).
Supports multiple LP tasks (one per product) in a single invocation.
"""

import json
import logging
import time

from graph.state import AgentState
from tools.optimization import DIRECT_LP_TOOLS

logger = logging.getLogger(__name__)


def _find_tasks(state: AgentState, agent_name: str) -> list[dict]:
    """Find all tasks assigned to this agent."""
    return [
        task for task in state.get("tasks", [])
        if task.get("agent") == agent_name
    ]


def _format_result(result: dict) -> str:
    """Format LP result dict into a readable text summary for agent_results."""
    status = (
        result.get("constraint_diagnostics", {}).get("lp_status")
        or result.get("lp_status", "Unknown")
    )

    if status not in ("Optimal",):
        reason = result.get("reason", "No feasible solution found.")
        return f"LP Status: {status}\n{reason}"

    parts = []

    # Executive summary
    exec_summary = result.get("executive_summary", "")
    if exec_summary:
        parts.append(exec_summary)

    # Allocation table
    allocation = result.get("allocation", [])
    if allocation:
        parts.append("\nSupplier Allocation:")
        for row in allocation:
            parts.append(
                f"  {row['supplier_id']} ({row.get('country_code', '')}) — "
                f"{row['allocated_qty']:,} units ({row['share_pct']:.1f}%) "
                f"@ ${row['landed_unit_cost']:.4f}/unit "
                f"= ${row['total_cost']:,.2f}"
            )

    # Cost summary
    cost = result.get("cost_summary", {})
    if cost:
        parts.append(
            f"\nTotal cost: ${cost.get('total_cost_usd', 0):,.2f} | "
            f"Avg unit cost: ${cost.get('avg_landed_unit_cost', 0):.4f} | "
            f"Avg risk: {cost.get('avg_risk_penalty_norm', 0):.4f}"
        )

    # Formula description
    formula = result.get("formula_description", "")
    if formula:
        parts.append(f"\n{formula}")

    # Constraint diagnostics
    diag = result.get("constraint_diagnostics", {})
    if diag:
        parts.append(
            f"\nLP status: {diag.get('lp_status')} | "
            f"Demand satisfied: {diag.get('demand_satisfied')} | "
            f"Share constraints binding: {diag.get('n_share_constraints_binding', 0)}"
        )

    # Baseline comparison
    baseline = result.get("baseline", {})
    if baseline and baseline.get("total_cost_usd"):
        main_cost = cost.get("total_cost_usd", 0) if cost else 0
        baseline_cost = baseline["total_cost_usd"]
        delta = main_cost - baseline_cost
        delta_pct = (delta / baseline_cost * 100) if baseline_cost else 0
        parts.append(
            f"\nBaseline comparison (cost-only, no risk/diversification):"
            f"\n  Baseline cost: ${baseline_cost:,.2f}"
            f"\n  Current plan:  ${main_cost:,.2f}"
            f"\n  Delta: ${delta:+,.2f} ({delta_pct:+.1f}%)"
        )

    return "\n".join(parts)


def _find_previous_params(product: str) -> dict:
    """
    Look up params_recap from the most recent LP run for the same product
    across all previous traces stored in Streamlit session state.
    Returns the params_recap dict, or empty dict if not found.
    """
    try:
        import streamlit as st
        traces = st.session_state.get("traces", [])
    except Exception:
        return {}

    # Search traces in reverse (most recent first)
    for trace in reversed(traces):
        agent_results = trace.get("agent_results", {})
        # Check if this trace has raw_data with LP results for this product
        # raw_data is stored separately, but we can check the timings/agent_results
        # to confirm LP ran for this product
        pass

    # Traces don't store raw_data directly. Use a dedicated session store instead.
    lp_history = st.session_state.get("lp_params_history", {})
    return lp_history.get(product, {})


def _save_params_to_session(product: str, params_recap: dict) -> None:
    """Save LP params_recap to Streamlit session state for carry-forward."""
    try:
        import streamlit as st
        if "lp_params_history" not in st.session_state:
            st.session_state.lp_params_history = {}
        st.session_state.lp_params_history[product] = params_recap
    except Exception:
        pass


def _merge_with_previous_params(params: dict) -> dict:
    """
    For what-if / disruption reruns, carry forward parameters from the
    previous LP run for the same product. Only fill in missing keys —
    never overwrite what the orchestrator explicitly set.
    """
    product = params.get("product")
    if not product:
        return params

    prev_recap = _find_previous_params(product)
    if not prev_recap:
        return params

    # Default values from run_optimization — if orchestrator passes these,
    # it likely didn't intentionally set them, so prefer previous run's values.
    defaults = {
        "lambda_risk": 0.50,
        "max_supplier_share": 1.00,
        "budget_cap": None,
        "compliance_threshold": 0.60,
        "service_level_target": 1.00,
        "order_quantity": 5_000,
        "urgency": False,
        "facility_id": None,
        "diversification_mode": "none",
        "forecast_run_id": None,
    }

    merged = dict(params)
    carried = []
    for key, default_val in defaults.items():
        prev_val = prev_recap.get(key)
        current_val = merged.get(key)
        # Carry forward if: previous run had a non-default value AND
        # current params either missing or still at default
        if prev_val is not None and prev_val != default_val and current_val == default_val:
            merged[key] = prev_val
            carried.append(f"{key}={prev_val}")

    if carried:
        logger.info(f"[LP_AGENT] Carried forward from previous run: {', '.join(carried)}")

    return merged


async def lp_agent_node(state: AgentState) -> dict:
    start = time.perf_counter()
    tasks = _find_tasks(state, "lp_agent")

    if not tasks:
        logger.warning("[LP_AGENT] No tasks found, skipping")
        return {
            "agent_results": {"lp_agent": "No LP optimization tasks assigned."},
            "raw_data": {},
            "timings": {"lp_agent": 0.0},
        }

    agent_results = {}
    raw_data = {}
    errors = []
    timings = {}

    for task in tasks:
        tool_name = task.get("tool", "run_optimization")
        params = task.get("params") or {}
        params = _merge_with_previous_params(params)
        product = params.get("product", "unknown")
        result_key = f"lp_{product}"
        logger.info(f"[LP_AGENT] Task: tool={tool_name}, product={product}, params={params}")

        if tool_name not in DIRECT_LP_TOOLS:
            logger.error(f"[LP_AGENT] Unknown LP tool: {tool_name}")
            errors.append(f"Unknown tool: {tool_name}")
            continue

        tool_fn = DIRECT_LP_TOOLS[tool_name]
        t0 = time.perf_counter()
        try:
            result = tool_fn(**params)
            elapsed = round(time.perf_counter() - t0, 3)
            timings[f"lp_agent.{product}"] = elapsed

            agent_results[result_key] = _format_result(result)
            raw_data[result_key] = result

            # Save params for carry-forward in future what-if scenarios
            params_recap = result.get("params_recap", {})
            if params_recap:
                _save_params_to_session(product, params_recap)

            logger.info(f"[LP_AGENT] Completed {product} in {elapsed:.3f}s")
        except Exception as e:
            elapsed = round(time.perf_counter() - t0, 3)
            timings[f"lp_agent.{product}"] = elapsed
            error_msg = f"{product}: {e}"
            errors.append(error_msg)
            agent_results[result_key] = f"LP optimization failed for {product}: {e}"
            logger.error(f"[LP_AGENT] Failed {product}: {e}", exc_info=True)

    total = round(time.perf_counter() - start, 3)
    timings["lp_agent"] = total

    n_ok = sum(1 for k in agent_results if "failed" not in agent_results[k].lower())
    logger.info(f"[TIMING] lp_agent total: {total:.3f}s — {n_ok} product(s) optimized")

    if errors:
        agent_results["lp_agent_errors"] = "; ".join(errors)

    return {
        "agent_results": agent_results,
        "raw_data": raw_data,
        "timings": timings,
    }
