import re as _re
import base64
import streamlit as st


def _build_run_entry(result: dict) -> dict:
    """Build the standard entry dict from one LP result dict.

    Used by both _store_approved_run (Approve path) and the Modify baseline
    snapshot.  Contains every field needed for session-summary synthesis and
    what-if comparison rendering.
    """
    recap    = result.get("params_recap") or {}
    cost_sum = result.get("cost_summary") or {}
    req      = result.get("requirement") or {}
    pool     = result.get("supplier_pool") or {}
    diag     = result.get("constraint_diagnostics") or {}
    baseline = result.get("baseline") or {}

    allocated_qty = (
        req.get("adjusted_requirement")
        or diag.get("total_allocated")
        or 0
    )
    return {
        "product":              recap.get("product", "unknown"),
        "allocated_qty":        allocated_qty,
        "total_cost":           cost_sum.get("total_cost_usd", 0.0),
        "n_suppliers":          pool.get("n_selected_by_lp", 0),
        "executive_summary":    result.get("executive_summary", ""),
        "allocation":           result.get("allocation", []),
        "lambda_risk":          recap.get("lambda_risk", 0.5),
        "max_supplier_share":   recap.get("max_supplier_share", 1.0),
        "diversification_mode": recap.get("diversification_mode", "none"),
        "urgency":              recap.get("urgency", False),
        "budget_cap":           recap.get("budget_cap"),
        "facility_id":          recap.get("facility_id"),
        "compliance_threshold": recap.get("compliance_threshold", 0.5),
        "exclude_supplier_ids": list(recap.get("exclude_supplier_ids") or []),
        "avg_unit_cost":        cost_sum.get("avg_landed_unit_cost", 0.0),
        "avg_risk_penalty":     cost_sum.get("avg_risk_penalty_norm", 0.0),
        "n_eligible":           pool.get("n_eligible_post_compliance", 0),
        "urgency_feasibility":  result.get("urgency_feasibility"),
        "countries":            diag.get("countries_selected", []),
        "baseline_cost":               baseline.get("baseline_total_cost"),
        "baseline_selected_suppliers": list(baseline.get("baseline_selected_suppliers") or []),
        "baseline_n_suppliers":        len(baseline.get("baseline_selected_suppliers") or []),
        "baseline_country_count":      baseline.get("baseline_country_count", 0),
    }


def _render_lp_decision_explanation(raw: dict) -> None:
    """
    Render 'How was this decision made?' — structured LP decision explanation.

    Sections:
      A. Overview
      B. Objective Function
      C. Current Run Settings
      D. Active Business Rules
      E. Inactive Options You Could Change
      F. How Different Settings Would Change This Recommendation

    Pure rendering from the LP result dict — no DB calls, no new calculations.
    """
    import pandas as pd

    recap   = raw.get("params_recap", {})
    req     = raw.get("requirement", {})
    diag    = raw.get("constraint_diagnostics", {})
    alloc   = raw.get("allocation", [])
    pool    = raw.get("supplier_pool", {})

    product_label  = recap.get("product", "").replace("_", " ").title()
    lambda_risk    = recap.get("lambda_risk", 0.5)
    max_share      = recap.get("max_supplier_share", 1.0)
    div_mode       = recap.get("diversification_mode", "none")
    svc_tgt        = recap.get("service_level_target", 1.0)
    urgency        = recap.get("urgency", False)
    budget_cap     = recap.get("budget_cap")
    excl_ids       = recap.get("exclude_supplier_ids") or []
    compliance_thr = recap.get("compliance_threshold", 0.5)
    facility_id    = recap.get("facility_id")
    adj_req        = req.get("adjusted_requirement", 0)
    n_fac          = req.get("n_facilities_included", 0)
    n_selected     = pool.get("n_selected_by_lp", len(alloc))
    n_eligible     = pool.get("n_eligible_post_compliance", 0)
    countries      = diag.get("countries_selected", [])
    lambda_urgency = 0.25 if urgency else 0.0

    # ── A. Overview ───────────────────────────────────────────────────────────
    st.markdown("**A. Overview**")

    if facility_id:
        scope_str = f"Facility {facility_id} only"
    else:
        scope_str = f"all {n_fac} facilit{'y' if n_fac == 1 else 'ies'} with positive net requirement"

    if lambda_risk == 0:
        tradeoff_desc = (
            "This run used a **cost-only** objective — risk penalties were not applied. "
            "The optimizer selected the cheapest compliant supplier(s) that satisfy demand."
        )
    elif lambda_risk <= 0.25:
        tradeoff_desc = (
            "This run **weighted cost heavily**, with a modest adjustment for supplier risk. "
            "Most volume flows toward the cheapest options; only high-risk suppliers are meaningfully penalized."
        )
    elif lambda_risk <= 0.75:
        tradeoff_desc = (
            "This run **balanced cost and risk** — both factors influenced the supplier selection. "
            "Cheaper suppliers are still preferred, but riskier ones carry a noticeable cost markup in the model."
        )
    else:
        tradeoff_desc = (
            "This run **prioritized risk reduction**. "
            "The optimizer accepted higher landed cost in exchange for a more stable, lower-risk supplier mix."
        )

    urgency_note = (
        " Lead-time delivery speed is also factored in: slower suppliers carry "
        "an additional cost premium, causing the optimizer to favor faster delivery."
        if urgency else ""
    )

    st.markdown(
        f"The optimizer allocated the **{product_label}** procurement requirement "
        f"({adj_req:,} units, {scope_str}) across the eligible supplier pool.\n\n"
        f"It did not forecast demand or recompute inventory — those steps were completed upstream. "
        f"The optimizer's sole job: given a known requirement, decide **who to buy from** "
        f"and **in what quantity**.\n\n"
        f"{tradeoff_desc}{urgency_note}"
    )

    # ── B. Objective Function ─────────────────────────────────────────────────
    st.markdown("**B. Objective Function**")
    st.markdown(
        "The optimizer minimizes the following expression, evaluated for each candidate supplier `j`:"
    )
    st.markdown(
        "> **minimize:** `c_j × (1 + λ_risk × r_j + λ_urgency × lt_norm_j)`"
    )
    term_rows = [
        {"Term": "c_j",
         "Definition": "Landed unit cost (USD per unit)"},
        {"Term": "r_j",
         "Definition": "Normalized risk penalty for supplier j  —  0 = lowest risk in the eligible pool, 1 = highest"},
        {"Term": "lt_norm_j",
         "Definition": "Normalized lead-time mean within the eligible pool  —  0 = fastest, 1 = slowest"},
        {"Term": f"λ_risk = {lambda_risk}",
         "Definition": f"Risk preference weight for this run. "
                       f"A value of 0 means pure cost; higher values shift volume toward safer suppliers."},
        {"Term": f"λ_urgency = {lambda_urgency}",
         "Definition": "Urgency premium. Active at 0.25 when urgency mode is on — "
                       "causes slower suppliers to carry up to a 25% cost markup."
                       if urgency else
                       "Urgency premium. Currently 0 — lead time is not penalized in this run."},
    ]
    st.dataframe(pd.DataFrame(term_rows), use_container_width=True, hide_index=True)

    if lambda_risk == 0:
        obj_interp = (
            "With λ_risk = 0, the risk term drops out entirely. "
            "The model reduces to pure landed cost minimization."
        )
    elif urgency:
        obj_interp = (
            f"With λ_risk = {lambda_risk} and urgency on (λ_urgency = 0.25), "
            "both risk and delivery speed add a cost premium. "
            "A supplier that is both risky and slow faces the highest effective cost in the model."
        )
    else:
        markup_pct = lambda_risk * 0.5 * 100
        obj_interp = (
            f"With λ_risk = {lambda_risk}: a supplier with a normalized risk penalty of 0.5 "
            f"effectively carries a {markup_pct:.0f}% cost markup relative to an equally-priced zero-risk supplier. "
            "The optimizer balances this across the full eligible pool to find the minimum total adjusted cost."
        )
    st.markdown(obj_interp)

    # ── C. Current Run Settings ───────────────────────────────────────────────
    st.markdown("**C. Current Run Settings**")

    div_mode_display = {
        "none":                "None — LP selects lowest adjusted-cost mix",
        "supplier_share_only": f"Supplier share cap ({max_share:.0%} max per supplier)",
        "country_diversified": "Country diversification — 3 suppliers, 1 per country, ~33% each",
    }.get(div_mode, div_mode)

    svc_display = (
        f"{svc_tgt:.0%} — 1× base requirement (no additional buffer)"
        if svc_tgt == 1.0
        else f"{svc_tgt:.0%} — +{(svc_tgt - 1)*100:.0f}% buffer above base requirement"
    )

    settings_rows = [
        {"Setting": "Product",              "Value": product_label},
        {"Setting": "Facility Scope",       "Value": f"Facility {facility_id}" if facility_id else f"All {n_fac} facilities with positive requirement"},
        {"Setting": "Total Quantity (Q)",   "Value": f"{adj_req:,} units"},
        {"Setting": "Risk Weight (λ)",      "Value": str(lambda_risk)},
        {"Setting": "Supplier Share Cap",   "Value": f"{max_share:.0%}" if max_share < 1.0 else "No cap"},
        {"Setting": "Diversification Mode", "Value": div_mode_display},
        {"Setting": "Service Level Target", "Value": svc_display},
        {"Setting": "Urgency Mode",         "Value": "On — lead-time premium applied" if urgency else "Off"},
        {"Setting": "Budget Cap",           "Value": f"${budget_cap:,.0f}" if budget_cap else "None"},
        {"Setting": "Compliance Threshold", "Value": f"{compliance_thr:.0%} minimum eligibility"},
        {"Setting": "Excluded Suppliers",   "Value": ", ".join(excl_ids) if excl_ids else "None"},
        {"Setting": "Eligible / Selected",  "Value": f"{n_eligible} eligible after compliance filter  ·  {n_selected} selected by LP"},
    ]
    st.dataframe(pd.DataFrame(settings_rows), use_container_width=True, hide_index=True)

    # ── D. Active Business Rules ──────────────────────────────────────────────
    st.markdown("**D. Active Business Rules**")
    active = []

    active.append(
        f"**Demand fulfillment** — the plan must procure at least {adj_req:,} units. "
        "Partial fulfillment is not permitted."
    )
    active.append(
        f"**Compliance filter** — suppliers below {compliance_thr:.0%} eligibility are excluded before "
        f"the optimizer runs. {n_eligible} of {pool.get('n_total_for_product', n_eligible)} total suppliers "
        "passed this gate."
    )
    if lambda_risk > 0:
        active.append(
            f"**Risk-adjusted cost (λ = {lambda_risk})** — supplier risk penalties scale the effective unit cost. "
            "Riskier suppliers are more expensive in the model; volume shifts toward lower-risk alternatives."
        )
    if urgency:
        active.append(
            "**Urgency adjustment** — lead-time delivery speed is penalized. "
            "The slowest eligible supplier carries a 25% cost premium; the fastest carries none. "
            "No suppliers are excluded — it is a continuous cost dial."
        )
    if max_share < 1.0:
        active.append(
            f"**Supplier concentration cap ({max_share:.0%})** — no single supplier may receive more than "
            f"{max_share:.0%} of total volume. This constraint directly shapes how volume is spread."
        )
    if div_mode == "country_diversified":
        active.append(
            "**Country diversification** — exactly 3 suppliers are selected, each from a different country, "
            "each allocated 30–35% of total volume. Binary selection variables enforce this constraint."
        )
    elif div_mode == "supplier_share_only":
        active.append(
            f"**Supplier-share diversification** — the {max_share:.0%} share cap is the active diversification "
            "constraint. No country-level requirement applies."
        )
    if budget_cap:
        active.append(f"**Budget cap** — total procurement spend must not exceed ${budget_cap:,.0f}.")
    if svc_tgt != 1.0:
        active.append(
            f"**Service-level buffer** — procurement quantity is scaled to {svc_tgt:.0%} of base requirement, "
            f"adding a {(svc_tgt - 1)*100:.0f}% buffer. This scales the demand floor, not the safety stock."
        )
    if facility_id:
        active.append(
            f"**Facility restriction** — optimization is scoped to Facility {facility_id} only. "
            "Other facilities are excluded from this run's demand and allocation."
        )
    if excl_ids:
        active.append(
            f"**Manual exclusions** — {', '.join(excl_ids)} removed from the supplier pool before the optimizer runs."
        )

    for rule in active:
        st.markdown(f"- {rule}")

    # ── E. Inactive Options You Could Change ──────────────────────────────────
    st.markdown("**E. Inactive Options You Could Change**")
    inactive = []

    if lambda_risk == 0:
        inactive.append(
            "**Risk weighting (λ_risk > 0)** — not applied. "
            "Enabling this would shift volume away from the cheapest-but-riskier suppliers toward more stable options."
        )
    if not urgency:
        inactive.append(
            "**Urgency mode** — not applied. "
            "Enabling this would add a lead-time cost premium, causing the optimizer to favor faster-delivering suppliers."
        )
    if max_share >= 1.0 and div_mode == "none":
        inactive.append(
            "**Supplier share cap** — no cap set. "
            "Adding one (e.g., 40%) would prevent any single supplier from dominating the allocation."
        )
    if div_mode != "country_diversified":
        inactive.append(
            "**Country diversification** — not applied. "
            "Enabling this would require exactly 3 suppliers from 3 different countries, each receiving ~33% of volume."
        )
    if svc_tgt == 1.0:
        inactive.append(
            "**Service-level buffer (service_level_target > 1.0)** — not applied. "
            "A value of 1.10 would procure 10% above the computed requirement as an additional planning buffer."
        )
    if not budget_cap:
        inactive.append(
            "**Budget cap** — no spending limit set. "
            "Adding one could constrain supplier feasibility or force the optimizer toward cheaper options."
        )
    if not facility_id:
        inactive.append(
            "**Single-facility scope (facility_id)** — currently aggregated across all facilities. "
            "Restricting to one facility would reduce the demand floor and potentially change supplier selection."
        )
    if not excl_ids:
        inactive.append(
            "**Supplier exclusions (exclude_supplier_ids)** — no suppliers excluded. "
            "Removing a specific supplier forces full reallocation across the remaining pool — "
            "useful for disruption and what-if scenario testing."
        )

    if inactive:
        for opt in inactive:
            st.markdown(f"- {opt}")
    else:
        st.markdown("All supported parameters are active in this run.")

    # ── F. How Different Settings Would Change This Recommendation ────────────
    st.markdown("**F. How Different Settings Would Change This Recommendation**")

    changes = []

    if lambda_risk > 0:
        changes.append(
            f"**Lowering λ to 0** would remove risk weighting entirely — "
            "the optimizer would choose solely on landed unit cost. "
            "Volume would likely shift to the cheapest compliant supplier(s), matching the cost-only baseline."
        )
    if lambda_risk < 1.5:
        changes.append(
            f"**Raising λ above {lambda_risk}** would further penalize riskier suppliers, "
            "potentially concentrating more volume in fewer, costlier but more reliable sources."
        )

    if max_share < 1.0:
        changes.append(
            f"**Relaxing the share cap above {max_share:.0%}** would allow more volume concentration, "
            "potentially reducing cost by flowing more volume to the single lowest adjusted-cost supplier."
        )
        changes.append(
            f"**Tightening the share cap below {max_share:.0%}** would force even broader diversification, "
            "likely increasing cost as volume is spread to less competitive suppliers."
        )
    else:
        changes.append(
            "**Adding a supplier share cap** (e.g., 40%) would prevent any single supplier from "
            "dominating, distributing volume across at least two or three sources at potential cost premium."
        )

    if div_mode != "country_diversified":
        changes.append(
            "**Enabling country diversification** would constrain the plan to exactly 3 suppliers "
            "from 3 countries, each allocated ~33% of volume. "
            "Geographic risk protection is introduced, but cost may increase."
        )

    if svc_tgt == 1.0:
        changes.append(
            "**Raising service_level_target to 1.10** would increase total quantity procured by 10%, "
            "scaling all supplier allocations proportionally above the current requirement."
        )
    else:
        changes.append(
            f"**Lowering service_level_target to 1.0** would reduce total quantity by "
            f"{(svc_tgt - 1)*100:.0f}%, removing the current buffer and procuring only what the requirement demands."
        )

    if not urgency:
        changes.append(
            "**Enabling urgency mode** would add a lead-time premium. "
            "Slower suppliers would become more expensive in the model, "
            "causing the optimizer to favor faster-delivering alternatives even at higher base cost."
        )
    else:
        changes.append(
            "**Disabling urgency mode** would remove the lead-time penalty. "
            "Cost and risk alone would drive allocation — delivery speed would not be penalized."
        )

    if not budget_cap:
        changes.append(
            "**Adding a budget cap** could render the current plan infeasible if the optimal allocation "
            "exceeds the cap, forcing the optimizer toward cheaper or fewer suppliers."
        )
    else:
        changes.append(
            f"**Raising the budget cap above ${budget_cap:,.0f}** would give the optimizer "
            "more flexibility to select risk-adjusted suppliers that may cost slightly more."
        )

    if not excl_ids:
        changes.append(
            "**Excluding a specific supplier** (e.g., a single-source concentration risk) "
            "would force full reallocation across the remaining eligible pool — "
            "directly modeling a supply disruption scenario."
        )
    else:
        changes.append(
            f"**Reinstating {', '.join(excl_ids)}** would expand the eligible pool, "
            "potentially changing the cost and risk profile of the optimal allocation."
        )

    if not facility_id:
        changes.append(
            "**Restricting to a single facility** would reduce the demand floor "
            "and may change which suppliers are optimal for that facility's specific requirement."
        )

    for chg in changes:
        st.markdown(f"- {chg}")

    # ── MOQ note ─────────────────────────────────────────────────────────────
    st.markdown("**Note on MOQ / Minimum Order Quantity**")
    st.markdown(
        "Minimum order quantity (MOQ) and bulk-unit thresholds are currently surfaced in "
        "the allocation output (showing whether MOQ was met and whether bulk pricing applies) "
        "but are not enforced as hard constraints in the optimizer. "
        "This keeps the LP formulation simple and safe for the current demo scope."
    )


def _find_prev_same_product_run(product: str, approved_runs: list) -> dict | None:
    """Return the most relevant comparison baseline for the what-if section.

    Priority:
      1. lp_modify_baseline — snapshot of the pending result when user clicked Modify.
         This ensures the what-if table diffs against the PENDING (not approved) run
         when the user is iterating through modify cycles.
      2. Most recent approved run for the same product.
    Returns None if this is the first run for the product.
    """
    modify_baseline = st.session_state.get("lp_modify_baseline", {})
    if product in modify_baseline:
        return modify_baseline[product]
    for entry in reversed(approved_runs):
        if entry.get("product") == product:
            return entry
    return None


def _whatif_scenario_label(current_recap: dict, prev_entry: dict) -> tuple[str, bool]:
    """
    Build a short, business-facing description of what changed between
    the previous approved run and the current what-if scenario.

    Returns (description_str, is_expedite_whatif).
    is_expedite_whatif is True when urgency was toggled ON in this rerun.
    """
    changes: list[str] = []
    is_expedite = False

    cur_urg  = current_recap.get("urgency", False)
    prev_urg = prev_entry.get("urgency", False)
    if cur_urg and not prev_urg:
        is_expedite = True
        changes.append("expedited replenishment")
    elif not cur_urg and prev_urg:
        changes.append("removed urgency mode")

    cur_lam  = float(current_recap.get("lambda_risk", 0.5))
    prev_lam = float(prev_entry.get("lambda_risk", 0.5))
    if abs(cur_lam - prev_lam) > 0.001:
        changes.append("increased risk aversion" if cur_lam > prev_lam else "reduced risk aversion")

    cur_share  = float(current_recap.get("max_supplier_share", 1.0))
    prev_share = float(prev_entry.get("max_supplier_share", 1.0))
    if abs(cur_share - prev_share) > 0.001:
        if cur_share < prev_share:
            changes.append(f"reduced per-supplier share cap to {int(cur_share * 100)}%")
        else:
            changes.append(f"increased per-supplier share cap to {int(cur_share * 100)}%")

    cur_div  = current_recap.get("diversification_mode", "none")
    prev_div = prev_entry.get("diversification_mode", "none")
    if cur_div != prev_div:
        if cur_div == "country_diversified":
            changes.append("enforced geographic diversification across countries")
        elif cur_div == "supplier_share_only":
            changes.append("added supplier share cap constraint")
        else:
            changes.append("removed diversification constraint")

    cur_excl  = set(current_recap.get("exclude_supplier_ids") or [])
    prev_excl = set(prev_entry.get("exclude_supplier_ids") or [])
    new_excl  = cur_excl - prev_excl
    if new_excl:
        changes.append(f"excluded {', '.join(sorted(new_excl))}")

    cur_thr  = float(current_recap.get("compliance_threshold", 0.5))
    prev_thr = float(prev_entry.get("compliance_threshold", 0.5))
    if abs(cur_thr - prev_thr) > 0.001:
        changes.append(f"adjusted compliance threshold to {int(cur_thr * 100)}%")

    cur_budget  = current_recap.get("budget_cap")
    prev_budget = prev_entry.get("budget_cap")
    if cur_budget != prev_budget:
        if cur_budget:
            changes.append(f"applied budget cap of ${cur_budget:,.0f}")
        else:
            changes.append("removed budget cap")

    desc = ", ".join(changes) if changes else "modified scenario"
    return desc, is_expedite


def _build_coverage_rows(current_raw: dict, prev_entry: dict) -> list[dict]:
    """
    Build coverage-impact rows for expedite what-if comparisons.
    Uses urgency_feasibility dicts from the current result and the stored previous entry.
    Omits any row that cannot be cleanly computed from available state.

    Rows returned (in order):
      1. Earliest Replenishment Week  — when selected suppliers first deliver.
      2. Additional Weeks Covered by Selection — planning-horizon coverage gain.
         Shows "Week N onward" on both sides using min_selected_lead_weeks, and
         a count-based Change cell ("+N covered weeks in planning horizon").
    """
    cur_uf  = current_raw.get("urgency_feasibility") or {}
    prev_uf = prev_entry.get("urgency_feasibility") or {}

    if not cur_uf and not prev_uf:
        return []

    rows: list[dict] = []

    # Pre-compute lead-week anchors once; reused across both rows.
    cur_min_wk  = cur_uf.get("min_selected_lead_weeks")   # None = gap resolved
    prev_min_wk = prev_uf.get("min_selected_lead_weeks")  # None = was already fine

    # ── Earliest Replenishment Week ───────────────────────────────────────────
    if cur_min_wk is not None or prev_min_wk is not None:
        cur_val  = f"Week {cur_min_wk}" if cur_min_wk is not None else "Gap resolved"
        prev_val = f"Week {prev_min_wk}" if prev_min_wk is not None else "—"
        if cur_min_wk is not None and prev_min_wk is not None:
            diff = cur_min_wk - prev_min_wk
            chg  = "No change" if diff == 0 else f"{diff:+d} weeks"
        elif cur_min_wk is None and prev_min_wk is not None:
            chg = "Gap resolved ✓"
        else:
            chg = "—"
        rows.append({
            "Metric":            "Earliest Replenishment Week",
            "Previous Scenario": prev_val,
            "What-If Scenario":  cur_val,
            "Change":            chg,
        })

    # ── Additional Weeks Covered by Selection ────────────────────────────────
    # Gap weeks present in the previous run that are gone in the current run —
    # meaning the expedited selection now covers them before they trigger.
    # Display uses "Week N onward" framing (the point at which the supplier pool
    # starts covering) rather than a raw count, so the cell reads more naturally.
    prev_gap      = set(prev_uf.get("gap_weeks", []))
    cur_gap       = set(cur_uf.get("gap_weeks", []))
    newly_covered = sorted(prev_gap - cur_gap)
    # Only show when the previous run had gap weeks and there is measurable improvement.
    if prev_gap and newly_covered:
        n_cov = len(newly_covered)
        # "Week N onward" = the first week the suppliers can cover (min_selected_lead_weeks).
        prev_cov_val = (
            f"Week {prev_min_wk} onward" if prev_min_wk is not None else "—"
        )
        cur_cov_val = (
            f"Week {cur_min_wk} onward"
            if cur_min_wk is not None
            else "All weeks covered"
        )
        rows.append({
            "Metric":            "Additional Weeks Covered by Selection",
            "Previous Scenario": prev_cov_val,
            "What-If Scenario":  cur_cov_val,
            "Change":            f"+{n_cov} covered weeks in planning horizon",
        })

    return rows


def _render_whatif_comparison(current_raw: dict, prev_entry: dict) -> None:
    """
    Render the What-If Scenario Impact section comparing current pending result
    against the most recent approved run for the same product.

    For expedite/urgency what-ifs: coverage-impact rows appear first.
    For all other what-ifs: standard economics-only comparison.
    """
    import pandas as pd

    current_recap = current_raw.get("params_recap", {})
    current_cost  = current_raw.get("cost_summary", {})
    current_pool  = current_raw.get("supplier_pool", {})
    current_alloc = current_raw.get("allocation", [])
    current_diag  = current_raw.get("constraint_diagnostics", {})

    product_label             = current_recap.get("product", "").replace("_", " ").title()
    scenario_desc, is_expedite = _whatif_scenario_label(current_recap, prev_entry)

    # Current values
    cur_units    = sum(r.get("allocated_qty", 0) for r in current_alloc)
    cur_cost     = current_cost.get("total_cost_usd", 0.0)
    cur_avg_cost = current_cost.get("avg_landed_unit_cost", 0.0)
    cur_risk     = current_cost.get("avg_risk_penalty_norm", 0.0)
    cur_n_sel    = current_pool.get("n_selected_by_lp", len(current_alloc))
    cur_n_elig   = current_pool.get("n_eligible_post_compliance", 0)
    cur_ctries   = current_diag.get("countries_selected", [])

    # Previous values
    prev_units    = prev_entry.get("allocated_qty", 0)
    prev_cost     = prev_entry.get("total_cost", 0.0)
    prev_avg_cost = prev_entry.get("avg_unit_cost", 0.0)
    prev_risk     = prev_entry.get("avg_risk_penalty", 0.0)
    prev_n_sel    = prev_entry.get("n_suppliers", 0)
    prev_n_elig   = prev_entry.get("n_eligible", 0)
    prev_ctries   = prev_entry.get("countries", [])

    def _delta_currency(cur, prev):
        """Delta for large dollar amounts (total cost).  Threshold: $0.01."""
        d = cur - prev
        return "No change" if abs(d) < 0.01 else f"${d:+,.2f}"

    def _delta_unit_cost(cur, prev):
        """Delta for per-unit costs displayed to 4 decimal places.
        Threshold: $0.00005 (half of the last displayed digit) so that any
        difference visible at the :.4f precision is reported rather than
        suppressed.  Formats as +$0.0068 rather than the coarser ,.2f style."""
        d = cur - prev
        return "No change" if abs(d) < 0.00005 else f"${d:+.4f}"

    def _delta_float(cur, prev, decimals=4):
        d = cur - prev
        return "No change" if abs(d) < 10 ** (-decimals) else f"{d:+.{decimals}f}"

    def _delta_int(cur, prev):
        d = cur - prev
        return "No change" if d == 0 else f"{d:+,}"

    # ── Standard economics rows (always shown) ────────────────────────────────
    econ_rows = [
        {
            "Metric":            "Total Units Procured",
            "Previous Scenario": f"{prev_units:,}",
            "What-If Scenario":  f"{cur_units:,}",
            "Change":            _delta_int(cur_units, prev_units),
        },
        {
            "Metric":            "Total Procurement Cost",
            "Previous Scenario": f"${prev_cost:,.2f}",
            "What-If Scenario":  f"${cur_cost:,.2f}",
            "Change":            _delta_currency(cur_cost, prev_cost),
        },
        {
            "Metric":            "Average Unit Cost",
            "Previous Scenario": f"${prev_avg_cost:.4f}",
            "What-If Scenario":  f"${cur_avg_cost:.4f}",
            "Change":            _delta_unit_cost(cur_avg_cost, prev_avg_cost),
        },
        {
            "Metric":            "Weighted Avg Risk Penalty",
            "Previous Scenario": f"{prev_risk:.4f}",
            "What-If Scenario":  f"{cur_risk:.4f}",
            "Change":            _delta_float(cur_risk, prev_risk),
        },
        {
            "Metric":            "Suppliers Selected / Eligible",
            "Previous Scenario": f"{prev_n_sel} / {prev_n_elig}",
            "What-If Scenario":  f"{cur_n_sel} / {cur_n_elig}",
            "Change":            (
                "No change"
                if prev_n_sel == cur_n_sel and prev_n_elig == cur_n_elig
                else f"{prev_n_sel}/{prev_n_elig} → {cur_n_sel}/{cur_n_elig}"
            ),
        },
        {
            "Metric":            "Countries Represented",
            "Previous Scenario": ", ".join(sorted(prev_ctries)) if prev_ctries else "—",
            "What-If Scenario":  ", ".join(sorted(cur_ctries))  if cur_ctries  else "—",
            "Change":            (
                "No change"
                if sorted(prev_ctries) == sorted(cur_ctries)
                else f"{len(prev_ctries)} → {len(cur_ctries)} countries"
            ),
        },
    ]

    # ── Coverage rows (expedite runs only) ────────────────────────────────────
    coverage_rows = _build_coverage_rows(current_raw, prev_entry) if is_expedite else []

    # For expedite runs: coverage rows first, then economics rows
    rows = coverage_rows + econ_rows

    all_no_change = all(r["Change"] in ("No change", "—") for r in rows)

    # ── Summary caption ────────────────────────────────────────────────────────
    if is_expedite:
        primary_caption = (
            f"What-if scenario detected: {scenario_desc} improves near-term supply coverage "
            f"for **{product_label}**."
        )
        secondary_caption = (
            "This rerun reduces the immediate uncovered window and brings replenishment forward. "
            "Compared against the previous approved scenario for the same product."
        )
    else:
        primary_caption   = f"What-if scenario detected: {scenario_desc} for **{product_label}**."
        secondary_caption = "Compared against the previous approved scenario for the same product."

    with st.expander("**What-If Scenario Impact**", expanded=True):
        st.caption(primary_caption)
        st.caption(secondary_caption)
        if all_no_change:
            st.info(
                "What-if modification did not change the supplier allocation "
                "or summary economics."
            )
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )


def _render_lp_result(raw: dict) -> None:
    """
    Render one LP optimization result dict as structured Streamlit output.

    Sections (in order):
      1. Requirement Summary
      2. Supplier Allocation  (DataFrame, top 4 rows, no Top Risk Drivers column)
      3. Procurement & Risk Summary
      3b. What-If Scenario Impact (only when a prior same-product approved run exists)
      4. Supply Urgency & Lead Time Assessment (only when shortfall detected)
      5. "Tell me more about the selected suppliers" expander
      6. "How was this decision made?" expander
      7. Excluded Suppliers expander (after explanation)

    Does NOT render the approve/discard buttons — that is handled by the caller.
    """
    import pandas as pd

    status = (
        raw.get("constraint_diagnostics", {}).get("lp_status")
        or raw.get("lp_status", "Unknown")
    )

    if status != "Optimal":
        reason = raw.get("reason") or raw.get("executive_summary") or "No feasible solution found."
        st.error(f"LP Status: {status}  —  {reason}")
        return

    recap   = raw.get("params_recap", {})
    req     = raw.get("requirement", {})
    pool    = raw.get("supplier_pool", {})
    alloc   = raw.get("allocation", [])
    cost    = raw.get("cost_summary", {})
    diag    = raw.get("constraint_diagnostics", {})
    excl    = raw.get("excluded_suppliers", [])
    base    = raw.get("baseline", {})

    product_label = recap.get("product", "").replace("_", " ").title()

    # ── 1. Requirement Summary ────────────────────────────────────────────────
    st.markdown("**Requirement Summary**")
    fac_bd = req.get("facility_breakdown", [])
    req_rows = []
    for fb in fac_bd:
        req_rows.append({
            "Facility":             fb.get("facility_id", ""),
            "Net Requirement":      f"{fb.get('net_req', 0):,.0f}",
            "Share of Total (%)":   f"{fb.get('share_pct', 0):.1f}",
            "Allocated (units)":    f"{fb.get('allocated_qty', 0):,.0f}",
        })
    if req_rows:
        st.dataframe(
            pd.DataFrame(req_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        net = req.get("adjusted_requirement", req.get("total_net_requirement", 0))
        st.markdown(f"Total net procurement requirement: **{net:,} units**")

    n_fac    = req.get("n_facilities_included", len(fac_bd))
    adj_req  = req.get("adjusted_requirement", 0)
    svc_pct  = int(recap.get("service_level_target", 1.0) * 100)
    st.caption(
        f"{n_fac} facilit{'y' if n_fac == 1 else 'ies'} included  ·  "
        f"Demand floor: {adj_req:,} units  ·  Service-level target: {svc_pct}%"
    )

    # ── 2. Supplier Allocation ────────────────────────────────────────────────
    st.markdown("**Supplier Allocation**")
    if alloc:
        alloc_rows = []
        for r in alloc[:4]:  # cap at 4 rows
            alloc_rows.append({
                "Supplier":           r.get("supplier_id", ""),
                "Country":            r.get("country_code", ""),
                "Tier":               r.get("decision_tier", "—"),
                "Allocated (units)":  f"{r.get('allocated_qty', 0):,}",
                "Share (%)":          f"{r.get('share_pct', 0):.1f}",
                "Unit Cost (USD)":    f"${r.get('landed_unit_cost', 0):.4f}",
                "Total Cost (USD)":   f"${r.get('total_cost', 0):,.0f}",
                "Risk Penalty":       f"{r.get('risk_penalty_norm', 0):.4f}",
            })
        st.dataframe(
            pd.DataFrame(alloc_rows),
            use_container_width=True,
            hide_index=True,
            height=min(200 + 40 * len(alloc_rows), 360),
        )
        if len(alloc) > 4:
            st.caption(f"Showing top 4 of {len(alloc)} allocated suppliers.")
    else:
        st.warning("No suppliers were allocated.")

    # ── 3. Procurement & Risk Summary ─────────────────────────────────────────
    st.markdown("**Procurement & Risk Summary**")
    total_cost  = cost.get("total_cost_usd", 0)
    avg_cost    = cost.get("avg_landed_unit_cost", 0)
    avg_risk    = cost.get("avg_risk_penalty_norm", 0)
    n_selected  = pool.get("n_selected_by_lp", len(alloc))
    n_eligible  = pool.get("n_eligible_post_compliance", 0)
    countries   = diag.get("countries_selected", [])
    total_units = sum(r.get("allocated_qty", 0) for r in alloc)

    # Baseline delta
    base_cost   = base.get("baseline_total_cost") if base else None
    if base_cost and base_cost > 0:
        delta     = total_cost - base_cost
        delta_pct = delta / base_cost * 100
        delta_str = f"${delta:+,.0f} ({delta_pct:+.1f}% vs cost-only baseline)"
    else:
        delta_str = None  # will be hidden when unavailable

    cost_summary_rows = [
        {"Metric": "Total Units Procured",           "Value": f"{total_units:,}"},
        {"Metric": "Total Procurement Cost",         "Value": f"${total_cost:,.2f}"},
        {"Metric": "Average Unit Cost",              "Value": f"${avg_cost:.4f}"},
        {"Metric": "Weighted Avg Risk Penalty",      "Value": f"{avg_risk:.4f}  (0 = lowest risk, 1 = riskiest)"},
        {"Metric": "Suppliers Selected / Eligible",  "Value": f"{n_selected} / {n_eligible}"},
        {"Metric": "Countries Represented",          "Value": ", ".join(countries) if countries else "—"},
    ]
    if delta_str is not None:
        cost_summary_rows.append({"Metric": "Cost vs Cost-Only Baseline", "Value": delta_str})
    bud_util = cost.get("budget_utilization_pct")
    if bud_util is not None:
        cost_summary_rows.append(
            {"Metric": "Budget Utilization", "Value": f"{bud_util:.1f}%"}
        )
    st.dataframe(
        pd.DataFrame(cost_summary_rows),
        use_container_width=True,
        hide_index=True,
    )

    # ── 3b. What-If Scenario Impact ───────────────────────────────────────────
    # Only shown when a prior approved LP run exists for the same product.
    _prev_run = _find_prev_same_product_run(
        recap.get("product"),
        st.session_state.get("approved_lp_runs", []),
    )
    if _prev_run is not None:
        _render_whatif_comparison(raw, _prev_run)

    # ── 4. Supply Urgency & Lead Time Assessment ──────────────────────────────
    # Source: query_triggered_rows_structured() — weekly-trigger semantics only.
    # Only rows where net_requirement > 0 are included (procurement actually required).
    # Row scope: limited to the "immediate gap" — weeks before the selected supplier
    # can realistically begin replenishing, derived from dim_supplier lead_time_mean.
    exec_summary = raw.get("executive_summary", "")
    _sf_match = _re.search(r'Early shortfall begins Week (\d+)', exec_summary)
    if _sf_match:
        shortfall_week = int(_sf_match.group(1))
        st.markdown("**Supply Urgency & Lead Time Assessment**")

        _product_key = recap.get("product", "")
        _sel_sup_ids = [r.get("supplier_id", "") for r in alloc if r.get("supplier_id")]

        # Step 1 — Resolve selected-supplier lead times → first coverable week.
        # dim_supplier.lead_time_mean (days); same formula LP uses: round(lt / 7).
        _min_selected_lead_weeks: int | None = None
        _sel_lt_map: dict[str, float] = {}
        try:
            from tools.pipeline_queries import query_supplier_lead_times
            _sel_lt_map = query_supplier_lead_times(_product_key, _sel_sup_ids)
            if _sel_lt_map:
                _min_lt_days = min(_sel_lt_map.values())
                _min_selected_lead_weeks = max(1, round(_min_lt_days / 7.0))
        except Exception:
            pass

        # Step 2 — Fetch weekly-trigger rows (net_requirement > 0 only).
        _all_trig_rows: list[dict] = []
        try:
            from tools.pipeline_queries import query_triggered_rows_structured
            _trig = query_triggered_rows_structured()
            _all_trig_rows = [
                r for r in _trig.get("rows", [])
                if r["Component"] == _product_key
            ]
        except Exception:
            pass  # don't crash render if DB unavailable

        # Step 3 — Separate immediate-gap rows from covered rows.
        # Gap: triggered weeks BEFORE selected supplier can first deliver.
        # Conservative fallback: shortfall_week + 3 when lead time is unknown.
        if _min_selected_lead_weeks is not None:
            _gap_rows = [r for r in _all_trig_rows if r["Forecast Week"] < _min_selected_lead_weeks]
        else:
            _gap_rows = [r for r in _all_trig_rows if r["Forecast Week"] <= shortfall_week + 3]

        # Step 4 — Assign each gap row to an urgency band.
        # SS Utilization = (safety_stock - available_inventory) / safety_stock × 100
        # True value (not capped): avail < 0 → util > 100% → Critical.
        # Bands: Low < 50%, Moderate 50–74%, High 75–99%, Critical ≥ 100%.
        _urgency_bands: dict[str, list] = {
            "Low": [], "Moderate": [], "High": [], "Critical": [],
        }
        _cum_pressure: dict[tuple, float] = {}  # running sum per (facility, component)

        for _r in sorted(_gap_rows, key=lambda x: x["Forecast Week"]):
            _ss   = _r["Safety Stock Reserve"]
            _need = _r["Procurement Need"]

            # Cumulative pressure must be updated before computing SS utilization
            _fc_key = (_r["Facility"], _r["Component"])
            _cum_pressure[_fc_key] = _cum_pressure.get(_fc_key, 0.0) + _need
            _cum = _cum_pressure[_fc_key]

            # SS Utilization = (Cumulative Procurement Pressure / Safety Stock) × 100
            # True value — not capped. Exceeds 100% when cumulative need exceeds SS floor.
            _ss_util = (_cum / _ss * 100) if _ss > 0 else 100.0

            if _ss_util >= 100:
                _band = "Critical"
            elif _ss_util >= 75:
                _band = "High"
            elif _ss_util >= 50:
                _band = "Moderate"
            else:
                _band = "Low"

            _urgency_bands[_band].append({
                "Forecast Week":                   _r["Forecast Week"],
                "Facility":                        _r["Facility"],
                "Component":                       _r["Component"].replace("_", " ").title(),
                "Direct Procurement Needed":       f"{_need:,.0f}",
                "Cumulative Procurement Pressure": f"{_cum:,.0f}",
                "Safety Stock":                    f"{_ss:,.0f}",
                "Safety Stock Utilization (%)":    f"{_ss_util:.1f}%",
            })

        # Step 5 — Render bands: Low → Moderate → High → Critical
        _df_opts: dict = {"use_container_width": True, "hide_index": True}

        if _urgency_bands["Low"]:
            st.success("**Low** — Less than 50% of safety stock being utilized to cover demand.")
            st.dataframe(pd.DataFrame(_urgency_bands["Low"]), **_df_opts,
                         height=min(150 + 35 * len(_urgency_bands["Low"]), 300))
        if _urgency_bands["Moderate"]:
            st.info("**Moderate** — 50% or more of safety stock being utilized to cover demand needs; monitor closely.")
            st.dataframe(pd.DataFrame(_urgency_bands["Moderate"]), **_df_opts,
                         height=min(150 + 35 * len(_urgency_bands["Moderate"]), 300))
        if _urgency_bands["High"]:
            st.warning("**High** — 75% or more of safety stock being utilized; inventory critically low.")
            st.dataframe(pd.DataFrame(_urgency_bands["High"]), **_df_opts,
                         height=min(150 + 35 * len(_urgency_bands["High"]), 300))
        if _urgency_bands["Critical"]:
            st.error("**Critical** — Safety stock fully exhausted or exceeded; immediate replenishment action required.")
            st.dataframe(pd.DataFrame(_urgency_bands["Critical"]), **_df_opts,
                         height=min(150 + 35 * len(_urgency_bands["Critical"]), 300))

        if not any(_urgency_bands.values()):
            # Fallback: DB unavailable or no gap rows in any band
            if "Faster alternative(s) in pool:" in exec_summary:
                _alt_m = _re.search(r'Faster alternative\(s\) in pool: (.+?)(?:\.|$)', exec_summary)
                alts_str = (_alt_m.group(1).strip()) if _alt_m else ""
                st.warning(
                    f"**Shortfall Risk — Week {shortfall_week}:** Selected supplier lead times "
                    f"cannot deliver before first demand peaks. "
                    f"Faster eligible alternatives: {alts_str}."
                )
            else:
                st.error(
                    f"**Critical — Week {shortfall_week}:** No eligible supplier can cover this "
                    f"window. Emergency domestic or spot sourcing required."
                )

        # Step 6 — Compliance-excluded suppliers with fast enough lead times.
        # Shown if their lead_weeks ≤ shortfall_week (could cover the early gap if threshold relaxed).
        _excl_compliance_fast: list[tuple[str, int, float]] = []
        _excl_all = raw.get("excluded_suppliers", [])
        _excl_comp_ids = [
            e["supplier_id"] for e in _excl_all
            if "compliance" in e.get("exclusion_reason", "")
        ]
        if _excl_comp_ids and _gap_rows:
            try:
                from tools.pipeline_queries import query_supplier_lead_times
                _excl_lt_map = query_supplier_lead_times(_product_key, _excl_comp_ids)
                for _sup_id, _lt_days in _excl_lt_map.items():
                    _sup_lt_wks = max(1, round(_lt_days / 7.0))
                    if _sup_lt_wks <= shortfall_week:
                        _comp_elig = next(
                            (e.get("compliance_eligibility", 0.0)
                             for e in _excl_all if e["supplier_id"] == _sup_id),
                            0.0,
                        )
                        _excl_compliance_fast.append((_sup_id, _sup_lt_wks, float(_comp_elig)))
            except Exception:
                pass

        # ── Recommendation bullets ──────────────────────────────────────────────
        _top_supplier = alloc[0].get("supplier_id", "primary supplier") if alloc else "primary supplier"

        # Parse faster alternatives (Case A) from exec_summary
        _alt_list: list[tuple[str, int]] = []
        _alt_raw_m = _re.search(r'Faster alternative\(s\) in pool: (.+?)(?:\.|$)', exec_summary)
        if _alt_raw_m:
            for _am in _re.finditer(r'\d+\)\s*(\S+)\s*\((\d+)\s*d\)', _alt_raw_m.group(1)):
                _alt_days = int(_am.group(2))
                _alt_list.append((_am.group(1).strip(), max(1, round(_alt_days / 7.0))))

        _has_alternatives = bool(_alt_list)
        _no_eligible_in_time = "Recommend emergency domestic / spot sourcing" in exec_summary

        # Facilities impacted — highest-urgency first
        _fac_seen: list[str] = []
        for _bname in ("Critical", "High", "Moderate", "Low"):
            for _br in _urgency_bands[_bname]:
                _f = _br.get("Facility", "")
                if _f and _f not in _fac_seen:
                    _fac_seen.append(_f)
        if not _fac_seen:
            for _fb in req.get("facility_breakdown", []):
                _f = _fb.get("facility_id", "")
                if _f and _f not in _fac_seen:
                    _fac_seen.append(_f)
        _fac_str = ", ".join(_fac_seen) if _fac_seen else "all affected facilities"

        # Emergency forecast weeks — only weeks where SS utilization ≥ 50%
        # (Moderate, High, or Critical band). Low-urgency weeks with minor
        # procurement need are excluded from emergency sourcing recommendations.
        _emergency_weeks = sorted({
            r["Forecast Week"]
            for _bname in ("Moderate", "High", "Critical")
            for r in _urgency_bands[_bname]
        })
        # Fallback: if no week reaches Moderate threshold, use all triggered weeks
        # so the recommendation is never silently empty when gap rows exist.
        _gap_weeks = _emergency_weeks if _emergency_weeks else (
            sorted({r["Forecast Week"] for r in _gap_rows}) if _gap_rows else []
        )
        _gap_weeks_str = ", ".join(str(w) for w in _gap_weeks)
        _week_plural = "Weeks" if len(_gap_weeks) != 1 else "Week"

        _rec_bullets: list[str] = []

        # Bullet 1 — selected supplier with actual first-coverable week (from DB lead time)
        if _min_selected_lead_weeks is not None:
            _fastest_sel = (
                min(_sel_lt_map, key=_sel_lt_map.get) if _sel_lt_map else _top_supplier
            )
            _rec_bullets.append(
                f"Selected suppliers (**{_fastest_sel}**) are expected to begin replenishing "
                f"inventory around Forecast Week {_min_selected_lead_weeks}, based on current "
                f"lead-time expectations. Orders placed now will support demand from that "
                f"window onwards."
            )
        elif _has_alternatives:
            _rec_bullets.append(
                f"Place purchase orders with **{_top_supplier}** immediately to support "
                f"replenishment in later weeks of the planning horizon — current lead-time "
                f"expectations indicate this supplier cannot cover the initial shortfall "
                f"window at Forecast Week {shortfall_week}."
            )
        else:
            _rec_bullets.append(
                f"Place purchase orders with **{_top_supplier}** immediately. "
                f"Current lead-time expectations position this supplier to support "
                f"replenishment in later planning horizon weeks rather than the initial "
                f"shortfall window at Forecast Week {shortfall_week}."
            )

        # Bullet 2 (Case A only) — faster alternatives for early window
        if _alt_list:
            _alt_names = ", ".join(f"**{s}** ({w}w lead)" for s, w in _alt_list)
            _rec_bullets.append(
                f"For earlier coverage, consider spot orders with {_alt_names} — "
                f"their lead times are consistent with delivery by or before "
                f"Forecast Week {shortfall_week} for {_fac_str}."
            )

        # Bullet 3 — compliance-excluded suppliers with short enough lead times
        if _excl_compliance_fast:
            _comp_thr_val = recap.get("compliance_threshold", 0.5)
            _excl_lines = [
                f"**{sid}** ({wk}w lead, {elig:.0%} compliance eligibility)"
                for sid, wk, elig in _excl_compliance_fast
            ]
            _rec_bullets.append(
                f"The following supplier(s) were excluded under the current compliance "
                f"threshold ({_comp_thr_val:.0%}) but have lead times short enough to "
                f"cover Forecast Week {shortfall_week}: {', '.join(_excl_lines)}. "
                f"Consider relaxing the compliance threshold as a contingency."
            )

        # Bullet 4 — emergency / spot sourcing, split by per-week eligible-pool feasibility.
        # Uses structured urgency_feasibility from LP result (added in run_lp_optimization.py).
        # Distinguishes: weeks eligible suppliers CAN cover (expedite first) vs. weeks
        # nobody in the eligible pool can cover (genuine emergency sourcing needed).
        def _fmt_wk(weeks: list) -> str:
            """'week 2'  /  'weeks 2 and 5'  /  'weeks 2, 5, and 8'"""
            if not weeks:
                return ""
            if len(weeks) == 1:
                return f"week {weeks[0]}"
            if len(weeks) == 2:
                return f"weeks {weeks[0]} and {weeks[1]}"
            return "weeks " + ", ".join(str(w) for w in weeks[:-1]) + f", and {weeks[-1]}"

        _uf            = raw.get("urgency_feasibility") or {}
        _uf_coverable  = _uf.get("coverable_weeks", [])    # eligible pool CAN cover
        # Intersect uncoverable_weeks with _emergency_weeks (SS util ≥ 50%) so
        # the "Contact sales/sourcing" sentence only cites weeks with actual
        # procurement pressure at Moderate or higher urgency.
        _uf_uncoverable = [
            w for w in _uf.get("uncoverable_weeks", [])
            if w in _emergency_weeks
        ]
        _uf_fast_sups  = _uf.get("fast_suppliers", [])

        if _uf:
            # Preferred path: structured per-week data available from LP result.
            # Only show "eligible suppliers available" if Bullet 2 has NOT already named them.
            # Bullet 2 fires when _alt_list is set (Case A: earliest week coverable by pool).
            # If _alt_list is empty but _uf_coverable is non-empty, some LATER gap weeks are
            # coverable — this is the gap the user observed (eligible sups for weeks 5,8 but
            # not week 2, causing misleading "no eligible supplier" wording in old code).
            if _uf_coverable and not _has_alternatives:
                _cov_str = _fmt_wk(_uf_coverable)
                if _uf_fast_sups:
                    _fast_names_str = ", ".join(
                        f"**{s['supplier_id']}** ({s['lead_time_weeks']}w lead)"
                        for s in _uf_fast_sups
                    )
                    _rec_bullets.append(
                        f"Eligible suppliers ({_fast_names_str}) are available to cover "
                        f"{_cov_str} if expedited or reallocated. "
                        f"Consider expediting these suppliers first before pursuing emergency options."
                    )
                else:
                    _rec_bullets.append(
                        f"Some eligible suppliers may be able to cover {_cov_str} "
                        f"if expedited or reallocated. "
                        f"Consider reviewing supplier lead times before pursuing emergency options."
                    )

            if _uf_uncoverable:
                _uncov_str = _fmt_wk(_uf_uncoverable)
                if _has_alternatives:
                    _rec_bullets.append(
                        f"If the alternatives above are not available for spot ordering, "
                        f"contact sales/sourcing for emergency domestic or spot suppliers "
                        f"to cover {_uncov_str} at heightened cost."
                    )
                else:
                    _rec_bullets.append(
                        f"Contact sales/sourcing for emergency domestic or spot suppliers "
                        f"to cover immediate replenishment needs for {_uncov_str} at heightened cost."
                    )
            elif not _uf_coverable:
                # urgency_feasibility present but both lists empty — safe fallback
                _wk_ref = _fmt_wk(_gap_weeks) if _gap_weeks else f"week {shortfall_week}"
                _rec_bullets.append(
                    f"Consider expediting eligible suppliers to cover urgent procurement needs. "
                    f"Otherwise, contact sales/sourcing for emergency domestic or spot suppliers "
                    f"to cover immediate replenishment needs for {_wk_ref} at heightened cost."
                )
        else:
            # Fallback path: old result format without urgency_feasibility key.
            # Replaces misleading "no currently eligible selected supplier" wording.
            if _gap_weeks_str:
                if _no_eligible_in_time:
                    _rec_bullets.append(
                        f"Consider expediting eligible suppliers to cover urgent procurement needs. "
                        f"Otherwise, contact sales/sourcing for emergency domestic or spot suppliers "
                        f"to cover immediate replenishment needs for Forecast {_week_plural} "
                        f"{_gap_weeks_str} at heightened cost."
                    )
                elif _has_alternatives:
                    _rec_bullets.append(
                        f"If the faster alternatives above are not available for spot ordering, "
                        f"contact sales/sourcing for emergency domestic suppliers to cover "
                        f"Forecast {_week_plural} {_gap_weeks_str} at heightened cost."
                    )
            elif _no_eligible_in_time:
                _rec_bullets.append(
                    f"Consider expediting eligible suppliers to cover urgent procurement needs. "
                    f"Otherwise, contact sales/sourcing for emergency domestic or spot suppliers "
                    f"to cover immediate replenishment needs for Forecast Week {shortfall_week} "
                    f"at heightened cost."
                )

        for _rb in _rec_bullets:
            st.markdown(f"- {_rb}")

    # ── Supplier Deep Dive ─────────────────────────────────────────────────────
    if alloc:
        _pk        = recap.get("product", "")
        _Q         = int(adj_req) if adj_req else int(req.get("total_net_requirement", 5000))
        _lam       = recap.get("lambda_risk", 0.5)
        _comp_thr  = recap.get("compliance_threshold", 0.5)
        _sup_ids   = [r.get("supplier_id", "") for r in alloc if r.get("supplier_id")]
        _bd_key    = f"_lp_bd_{_pk}_{_Q}_{_lam}"   # session_state cache key

        with st.expander("Tell me more about the selected suppliers"):
            if _bd_key in st.session_state:
                st.image(base64.b64decode(st.session_state[_bd_key]))
                st.caption(
                    f"Score breakdown — {product_label}  ·  "
                    f"Q = {_Q:,} units  ·  λ = {_lam}  ·  "
                    f"{len(_sup_ids)} allocated supplier(s)"
                )
            else:
                st.markdown(
                    "Cost and risk score breakdown for every allocated supplier, "
                    "using the exact LP parameters from this run."
                )
                if st.button("Load supplier analysis", key=f"_load_bd_{_bd_key}"):
                    with st.spinner("Generating score breakdown..."):
                        try:
                            from tools.chart_tools import plot_score_breakdown
                            _res = plot_score_breakdown(
                                supplier_ids=_sup_ids,
                                product=_pk,
                                Q=_Q,
                                lambda_risk=_lam,
                                compliance_threshold=_comp_thr,
                            )
                            st.session_state[_bd_key] = _res["image"]
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Could not generate analysis: {_e}")

    # ── Decision Explanation ──────────────────────────────────────────────────
    with st.expander("How was this decision made?"):
        _render_lp_decision_explanation(raw)

    # ── Excluded Suppliers (expander, shown after explanation) ────────────────
    if excl:
        _excl_label = f"Excluded Suppliers ({len(excl)})"
        with st.expander(_excl_label):
            excl_rows = []
            for e in excl:
                reason_raw  = e.get("exclusion_reason", "")
                comp_elig   = e.get("compliance_eligibility", 0)
                if reason_raw == "zero_allocation":
                    reason_disp = "Eligible — not selected by optimizer"
                elif reason_raw == "excluded_by_user_scenario":
                    reason_disp = "Manually excluded for this scenario"
                elif reason_raw == "gate:compliance_gate":
                    reason_disp = f"Below compliance threshold ({comp_elig:.0%} eligibility)"
                elif reason_raw == "null_policy_drop_row":
                    reason_disp = "Excluded — missing required data fields"
                elif reason_raw == "avoid_tier_filter":
                    reason_disp = "Eligible — excluded by Avoid-tier safeguard (non-Avoid suppliers sufficient)"
                else:
                    reason_disp = reason_raw or "Excluded (reason unspecified)"
                excl_rows.append({
                    "Supplier": e.get("supplier_id", ""),
                    "Country":  e.get("country_code", ""),
                    "Reason":   reason_disp,
                })
            st.dataframe(
                pd.DataFrame(excl_rows),
                use_container_width=True,
                hide_index=True,
            )


def _render_procurement_status_bar(pending_products: list | None = None) -> None:
    """Render a persistent procurement status panel with the Complete button.

    Shows which products have been approved in this session and (optionally)
    which are still pending.  The "Complete Procurement Plan" button is shown
    as soon as at least one product is approved; clicking it is the ONLY way
    to trigger the final executive summary.

    Args:
        pending_products: Optional list of human-readable product names that are
            currently pending approval (passed from render_lp_approval so the
            panel can distinguish approved vs. in-progress).
    """
    approved = st.session_state.get("approved_lp_runs", [])
    if not approved:
        return

    approved_names = [
        r.get("product", "unknown").replace("_", " ").title()
        for r in approved
    ]

    with st.container(border=True):
        st.markdown("### Procurement Status")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Procured**")
            for name in approved_names:
                st.markdown(f"- {name}")
        with col_b:
            if pending_products:
                st.markdown("**Pending Approval**")
                for name in pending_products:
                    st.markdown(f"- {name}")
            else:
                st.markdown("**Pending Approval**")
                st.markdown("*None queued — run another LP to add a product*")

        st.markdown("")
        if st.button(
            "Complete Procurement Plan",
            type="primary",
            key="complete_plan_btn",
            help="Generate the final executive summary for all approved runs",
        ):
            st.session_state.show_executive_summary = True
            st.session_state._pending_scroll = "exec_summary"
            st.rerun()
