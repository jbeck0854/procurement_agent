import streamlit as st

from ui.lp_views import _build_run_entry


def _store_approved_run(result: dict) -> None:
    """Append one approved LP result dict to the session-level approved_lp_runs store."""
    st.session_state.approved_lp_runs.append(_build_run_entry(result))


def _format_session_summary(approved_runs: list) -> str:
    """Format a session-level procurement summary from all approved LP runs."""
    if not approved_runs:
        return (
            "No approved LP runs in this session yet. "
            "Complete and approve at least one LP optimization to generate a session summary."
        )

    lines = ["**Session Procurement Plan — Approved Runs**\n"]
    total_spend   = 0.0
    total_baseline = 0.0
    has_baseline  = False

    for i, run in enumerate(approved_runs, start=1):
        product   = (run.get("product") or "unknown").replace("_", " ").title()
        qty       = run.get("allocated_qty") or 0
        cost      = run.get("total_cost") or 0.0
        n_sup     = run.get("n_suppliers") or 0
        lam       = run.get("lambda_risk", 0.5)
        share     = run.get("max_supplier_share", 1.0)
        div_mode  = run.get("diversification_mode", "none")
        urgency   = run.get("urgency", False)
        countries = run.get("countries") or []
        b_cost    = run.get("baseline_cost")
        b_n_sup   = run.get("baseline_n_suppliers", 0)
        b_n_ctry  = run.get("baseline_country_count", 0)

        total_spend += cost
        if b_cost:
            total_baseline += b_cost
            has_baseline = True

        # Header line
        lines.append(f"**Run {i} — {product}**")

        # Core metrics
        lines.append(f"- Quantity: {qty:,} units · Suppliers selected: {n_sup}")
        lines.append(f"- Committed cost: ${cost:,.2f}")
        if countries:
            lines.append(f"- Countries: {', '.join(countries)}")

        # Run parameters
        param_parts = [f"λ = {lam}", f"Max share: {share:.0%}"]
        if div_mode != "none":
            param_parts.append(f"Diversification: {div_mode.replace('_', ' ')}")
        if urgency:
            param_parts.append("Urgency: on")
        lines.append(f"- Settings: {' · '.join(param_parts)}")

        # Baseline comparison
        if b_cost and b_cost > 0:
            delta_abs = cost - b_cost
            delta_pct = (delta_abs / b_cost) * 100
            if abs(delta_pct) <= 1.0:
                classification = "negligible"
            elif abs(delta_pct) <= 10.0:
                classification = "modest"
            else:
                classification = "material"

            direction = "premium" if delta_abs >= 0 else "savings"
            lines.append(
                f"- vs. cost-only baseline: ${abs(delta_abs):,.2f} {direction} "
                f"({abs(delta_pct):.1f}% — {classification})"
            )
            if n_sup != b_n_sup or len(countries) != b_n_ctry:
                sup_delta  = n_sup - b_n_sup
                ctry_delta = len(countries) - b_n_ctry
                delta_str_parts = []
                if sup_delta != 0:
                    delta_str_parts.append(
                        f"{abs(sup_delta)} more supplier{'s' if abs(sup_delta) != 1 else ''}"
                        if sup_delta > 0 else
                        f"{abs(sup_delta)} fewer supplier{'s' if abs(sup_delta) != 1 else ''}"
                    )
                if ctry_delta != 0:
                    delta_str_parts.append(
                        f"{abs(ctry_delta)} more {'countries' if abs(ctry_delta) != 1 else 'country'}"
                        if ctry_delta > 0 else
                        f"{abs(ctry_delta)} fewer {'countries' if abs(ctry_delta) != 1 else 'country'}"
                    )
                if delta_str_parts:
                    lines.append(f"  ↳ {', '.join(delta_str_parts)} vs. unconstrained baseline")

        lines.append("")  # blank line between runs

    # Session totals
    lines.append(f"**Total Committed Spend: ${total_spend:,.2f}**")

    if has_baseline and total_baseline > 0:
        session_delta_abs = total_spend - total_baseline
        session_delta_pct = (session_delta_abs / total_baseline) * 100
        if abs(session_delta_pct) <= 1.0:
            session_class = "negligible"
        elif abs(session_delta_pct) <= 10.0:
            session_class = "modest"
        else:
            session_class = "material"
        session_dir = "above" if session_delta_abs >= 0 else "below"
        lines.append(
            f"Session risk/diversification premium: ${abs(session_delta_abs):,.2f} "
            f"({abs(session_delta_pct):.1f}% {session_dir} cost-only baseline — {session_class})"
        )

    lines.append("\n*Review approved recommendations, confirm lead times, and place orders.*")
    return "\n".join(lines)


def _merge_final_states(first: dict, second: dict) -> dict:
    """Merge two partial graph stream states into one for finalize_execution.

    `first`  — state collected before the LP interrupt (pipeline, charts).
    `second` — state collected after approve/discard resume (LP result, synthesizer).
    """
    merged = dict(first)
    for key in ("agent_results", "chart_results", "timings", "pipeline_results", "lp_results"):
        merged[key] = {
            **(first.get(key) or {}),
            **(second.get(key) or {}),
        }
    for key in ("final_response", "intent", "tasks"):
        if second.get(key):
            merged[key] = second[key]
    merged.pop("__interrupt__", None)
    return merged
