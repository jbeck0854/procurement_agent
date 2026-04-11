"""
LP Agent — runs procurement optimization using the LP module.
Operates in direct mode (orchestrator specifies tool + params).
Supports multiple LP tasks (one per product) in a single invocation.
"""

import json
import logging
import time

from langgraph.types import interrupt

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

    # ── Semantic alerts (rendered first, before allocation) ─────────────────
    avoid_warn = result.get("avoid_tier_warning")
    if avoid_warn:
        parts.append(f"⚠ AVOID-TIER ALERT: {avoid_warn}")

    div_fallback = result.get("diversification_fallback_note")
    if div_fallback:
        parts.append(f"⚠ DIVERSIFICATION ALERT: {div_fallback}")

    compliance_unlock = result.get("compliance_unlocked_note")
    if compliance_unlock:
        parts.append(f"ℹ PARAMETER CHANGE NOTE: {compliance_unlock}")

    compliance_excl = result.get("compliance_exclusion_note")
    if compliance_excl:
        parts.append(f"ℹ COMPLIANCE NOTE: {compliance_excl}")

    # Executive summary (stripped of embedded alert prefix to avoid duplication)
    exec_summary = result.get("executive_summary", "")
    if exec_summary:
        # The avoid-tier alert is already surfaced above; strip it from exec_summary
        # to avoid repeating it inline.
        _stripped = exec_summary
        if _stripped.startswith("[AVOID-TIER ALERT]"):
            _prefix_end = _stripped.find("  ", len("[AVOID-TIER ALERT] "))
            if _prefix_end != -1:
                _stripped = _stripped[_prefix_end:].strip()
        parts.append(_stripped)

    # Allocation table
    allocation = result.get("allocation", [])
    if allocation:
        parts.append("\nSupplier Allocation:")
        for row in allocation:
            tier_note = (
                f" [{row.get('decision_tier', '')}]"
                if row.get("decision_tier") else ""
            )
            parts.append(
                f"  {row['supplier_id']} ({row.get('country_code', '')}){tier_note} — "
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


def _save_params_to_session(product: str, params_recap: dict) -> None:
    """Save LP params_recap to Streamlit session state for carry-forward."""
    try:
        import streamlit as st
        if "lp_params_history" not in st.session_state:
            st.session_state.lp_params_history = {}
        st.session_state.lp_params_history[product] = params_recap
    except Exception:
        pass


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
        # Parameter merging (prior run carry-forward) is handled by the
        # orchestrator via param_extractor.merge_with_prior(). No double-merge.
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

    # ── LP approval interrupt ──────────────────────────────────────────────────
    # Pause for user approval BEFORE the synthesizer finalises the turn.
    # Only fires when at least one LP product actually completed and has a
    # corresponding entry in raw_data (guards against error-only runs).
    lp_keys = [k for k in agent_results if k in raw_data]
    if lp_keys:
        approval_payload = {
            "type":      "lp_approval",
            "formatted": {k: agent_results[k] for k in lp_keys},
            "raw":       {k: raw_data[k] for k in lp_keys},
        }
        feedback = interrupt(approval_payload)
        if str(feedback).strip().lower() == "discard":
            for k in lp_keys:
                agent_results.pop(k, None)
                raw_data.pop(k, None)
            logger.info("[LP_AGENT] LP results discarded by user.")
        else:
            logger.info("[LP_AGENT] LP results approved by user.")

    total = round(time.perf_counter() - start, 3)
    timings["lp_agent"] = total

    n_ok = sum(1 for k in agent_results if k in raw_data)
    logger.info(f"[TIMING] lp_agent total: {total:.3f}s — {n_ok} product(s) retained")

    if errors:
        agent_results["lp_agent_errors"] = "; ".join(errors)

    return {
        "agent_results": agent_results,
        "raw_data": raw_data,
        "timings": timings,
    }
