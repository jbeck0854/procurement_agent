import base64
import streamlit as st

from ui.common import _fig_to_b64, _format_facility_label
from ui.inventory_views import _fetch_component_req_data


def _render_executive_summary() -> None:
    """Render the final executive summary page (user-triggered only).

    Sections:
        Procurement Overview
        Product-Level Summary
        Baseline vs Optimized Comparison  (+ expandable risk panels)
        Supply Coverage & Shortfall Summary
        Forward-Looking Outlook
        Executive Assessment
    """
    import pandas as _pd

    # Anchor target — JS scrolls here when _pending_scroll == "exec_summary"
    st.markdown('<div id="exec-summary-top"></div>', unsafe_allow_html=True)

    approved = st.session_state.get("approved_lp_runs", [])
    if not approved:
        st.warning("No approved LP runs in this session. Approve at least one optimization first.")
        return

    st.title("Final Executive Summary")
    st.caption("Session-level procurement plan — approved recommendations only")
    st.divider()

    # ── Consulting-grade section header helper (local) ────────────────────────
    def _section_header(num: str, title: str) -> None:
        st.markdown(
            f"<div style='display:flex; align-items:baseline; gap:12px; margin:1.5rem 0 0.75rem;'>"
            f"<span style='font-family:Inter,sans-serif; font-size:1.8rem; font-weight:300; color:#76b900;'>{num}</span>"
            f"<span style='font-family:Inter,sans-serif; font-size:1rem; font-weight:600; color:#ffffff; letter-spacing:0.02em;'>{title}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    def _rec_box(text: str) -> None:
        st.markdown(
            f"<div style='background:rgba(118,185,0,0.06); border-left:3px solid #76b900; "
            f"border-radius:2px; padding:0.75rem 1rem; margin:0.5rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.75rem; font-weight:600; "
            f"color:#76b900; text-transform:uppercase; letter-spacing:0.1em; margin:0 0 0.3rem;'>Recommendation</p>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.85rem; color:#ffffff; margin:0;'>{text}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    def _risk_box(text: str) -> None:
        st.markdown(
            f"<div style='background:rgba(223,101,0,0.06); border-left:3px solid #df6500; "
            f"border-radius:2px; padding:0.75rem 1rem; margin:0.5rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.75rem; font-weight:600; "
            f"color:#df6500; text-transform:uppercase; letter-spacing:0.1em; margin:0 0 0.3rem;'>Risk Alert</p>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.85rem; color:#ffffff; margin:0;'>{text}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Session-level metrics ─────────────────────────────────────────────────
    total_cost     = sum(r.get("total_cost") or 0.0 for r in approved)
    total_qty      = sum(r.get("allocated_qty") or 0 for r in approved)
    total_baseline = sum(r.get("baseline_cost") or 0.0 for r in approved)
    avg_lambda     = (
        sum(r.get("lambda_risk", 0.5) for r in approved) / len(approved)
        if approved else 0.5
    )
    approved_product_keys  = [r.get("product", "") for r in approved]
    approved_product_names = [k.replace("_", " ").title() for k in approved_product_keys]

    # ── Pre-compute coverage maps once — reused by table and section D ────────
    _coverage_map:     dict[str, int | None] = {}   # optimized earliest replenishment week
    _baseline_cov_map: dict[str, int | None] = {}   # baseline earliest replenishment week
    try:
        from tools.pipeline_queries import query_supplier_lead_times as _qlt
        for _apr in approved:
            _prd = _apr.get("product", "")
            # Optimized suppliers
            _sel_ids = [
                a.get("supplier_id", "")
                for a in (_apr.get("allocation") or [])
                if a.get("supplier_id")
            ]
            if _sel_ids:
                try:
                    _lt = _qlt(_prd, _sel_ids)
                    _coverage_map[_prd] = max(1, round(min(_lt.values()) / 7.0)) if _lt else None
                except Exception:
                    _coverage_map[_prd] = None
            else:
                _coverage_map[_prd] = None

            # Baseline suppliers
            _base_ids = _apr.get("baseline_selected_suppliers") or []
            if _base_ids:
                try:
                    _blt = _qlt(_prd, _base_ids)
                    _baseline_cov_map[_prd] = max(1, round(min(_blt.values()) / 7.0)) if _blt else None
                except Exception:
                    _baseline_cov_map[_prd] = None
    except Exception:
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # 01 — Cost & Allocation Summary
    # ─────────────────────────────────────────────────────────────────────────
    _section_header("01", "Cost & Allocation Summary")
    _ov1, _ov2, _ov3 = st.columns(3)
    _ov1.metric("Products Procured", len(approved))
    _ov2.metric("Total Units", f"{total_qty:,}")
    _ov3.metric("Total Estimated Cost", f"${total_cost:,.2f}")

    _rec_box(f"Products successfully procured: {', '.join(approved_product_names)}")

    # Red band — products in planning horizon not yet approved
    try:
        _comp_data  = _fetch_component_req_data()
        _universe   = {r[0] for r in _comp_data.get("rows", [])}
        _remaining  = _universe - set(approved_product_keys)
        if _remaining:
            _rem_labels = [p.replace("_", " ").title() for p in sorted(_remaining)]
            _risk_box(
                f"<strong>Products Still Requiring Procurement:</strong> {', '.join(_rem_labels)} — "
                f"Run LP optimization for these components to complete the procurement plan."
            )
    except Exception:
        pass

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # (inline — part of section 01, product detail breakdown)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown(
        "<p style='font-family:Inter,sans-serif; font-size:0.75rem; font-weight:600; "
        "color:#76b900; text-transform:uppercase; letter-spacing:0.1em; margin:1.5rem 0 0.5rem;'>"
        "Product Detail</p>",
        unsafe_allow_html=True,
    )
    _rows_b = []
    for r in approved:
        alloc         = r.get("allocation") or []
        supplier_names = [a.get("supplier_name") or a.get("supplier_id", "?") for a in alloc]
        countries     = r.get("countries") or []
        _rows_b.append({
            "Product":     r.get("product", "unknown").replace("_", " ").title(),
            "Units":       f"{r.get('allocated_qty') or 0:,}",
            "Cost (USD)":  f"${r.get('total_cost') or 0.0:,.2f}",
            "Suppliers":   ", ".join(supplier_names) if supplier_names else "—",
            "# Suppliers": r.get("n_suppliers", 0),
            "Countries":   ", ".join(countries) if countries else "—",
            "Risk (λ)":    r.get("lambda_risk", 0.5),
        })
    st.dataframe(_pd.DataFrame(_rows_b), use_container_width=True, hide_index=True)
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # Baseline vs Optimized — sub-section of 01, before section 02 divider
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown(
        "<p style='font-family:Inter,sans-serif; font-size:0.75rem; font-weight:600; "
        "color:#76b900; text-transform:uppercase; letter-spacing:0.1em; margin:1.5rem 0 0.5rem;'>"
        "Baseline vs Optimized Comparison</p>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Baseline: λ = 0, no diversification, cheapest compliant suppliers, "
        "uncapped share. Optimized: risk-adjusted, constrained as configured."
    )

    _rows_c: list[dict] = []
    _has_baseline        = False
    _single_country_prds: list[str] = []
    _single_supplier_prds: list[str] = []

    for r in approved:
        _prd_key   = r.get("product", "unknown")
        _prd_label = _prd_key.replace("_", " ").title()
        cost       = r.get("total_cost") or 0.0
        b_cost     = r.get("baseline_cost")
        b_n_sup    = r.get("baseline_n_suppliers", 0)
        b_n_ctry   = r.get("baseline_country_count", 0)
        n_sup      = r.get("n_suppliers", 0)
        countries  = r.get("countries") or []

        if b_n_sup <= 1:
            _single_supplier_prds.append(_prd_label)
        if b_n_ctry <= 1:
            _single_country_prds.append(_prd_label)

        if b_cost and b_cost > 0:
            _has_baseline = True
            delta_abs  = cost - b_cost
            delta_pct  = (delta_abs / b_cost) * 100
            delta_str  = f"+${delta_abs:,.2f}" if delta_abs >= 0 else f"-${abs(delta_abs):,.2f}"
            pct_str    = f"+{delta_pct:.1f}%" if delta_pct >= 0 else f"{delta_pct:.1f}%"
            sup_delta  = n_sup - b_n_sup
            ctry_delta = len(countries) - b_n_ctry
            sup_str    = f"+{sup_delta}" if sup_delta >= 0 else str(sup_delta)
            ctry_str   = f"+{ctry_delta}" if ctry_delta >= 0 else str(ctry_delta)
        else:
            delta_str  = "—"
            pct_str    = "—"
            sup_str    = "—"
            ctry_str   = "—"

        # Additional weeks of coverage: optimized vs baseline earliest replenishment
        _opt_wk  = _coverage_map.get(_prd_key)
        _base_wk = _baseline_cov_map.get(_prd_key)
        if _opt_wk is not None and _base_wk is not None:
            _wk_delta = _base_wk - _opt_wk  # positive = optimized is faster
            if _wk_delta > 0:
                _cov_col = f"{_wk_delta}w earlier (Wk {_opt_wk} vs Wk {_base_wk})"
            elif _wk_delta == 0:
                _cov_col = f"Same (Wk {_opt_wk})"
            else:
                _cov_col = f"{abs(_wk_delta)}w later (Wk {_opt_wk} vs Wk {_base_wk})"
        elif _opt_wk is not None:
            _cov_col = f"Replenishment by Wk {_opt_wk}"
        else:
            _cov_col = "—"

        _rows_c.append({
            "Product":                      _prd_label,
            "Baseline Cost":                f"${b_cost:,.2f}" if b_cost else "—",
            "Optimized Cost":               f"${cost:,.2f}",
            "Risk Premium ($)":             delta_str,
            "Risk Premium (%)":             pct_str,
            "Supplier Δ vs Base":           sup_str,
            "Country Δ vs Base":            ctry_str,
            "Additional Weeks of Coverage": _cov_col,
        })

    st.dataframe(_pd.DataFrame(_rows_c), use_container_width=True, hide_index=True)

    # ── Baseline concentration warnings ───────────────────────────────────────
    if _single_country_prds:
        _risk_box(
            f"<strong>Single-country sourcing risk (baseline):</strong> For "
            f"{', '.join(_single_country_prds)}, the cost-only baseline routes all procurement "
            f"through a single country — creating full exposure to tariff shocks, port "
            f"disruptions, and geopolitical risk. The optimized plan diversifies this exposure."
        )
    elif _single_supplier_prds:
        _risk_box(
            f"<strong>Single-supplier concentration (baseline):</strong> For "
            f"{', '.join(_single_supplier_prds)}, the cost-only baseline selects a single "
            f"supplier — any disruption halts procurement entirely."
        )

    # ── Session total — metric cards + strong executive bullets ──────────────
    if _has_baseline and total_baseline > 0:
        session_delta_abs = total_cost - total_baseline
        session_delta_pct = (session_delta_abs / total_baseline) * 100

        _sm1, _sm2, _sm3 = st.columns(3)
        _sm1.metric("Optimized Plan Cost",  f"${total_cost:,.2f}")
        _sm2.metric("Cost-Only Baseline",   f"${total_baseline:,.2f}")
        _sm3.metric(
            "Risk Premium Paid",
            f"${abs(session_delta_abs):,.2f}",
            delta=f"{session_delta_pct:+.1f}% vs baseline",
            delta_color="off",
        )

        # Executive justification bullets — built from actual plan data
        _opt_countries = sorted(set(cc for r in approved for cc in (r.get("countries") or [])))

        if abs(session_delta_pct) <= 1.0:
            _prem_sentence = (
                f"The {session_delta_pct:+.1f}% premium is negligible — risk-adjusted supplier "
                f"selection added virtually no cost while materially improving supply chain resilience."
            )
        elif abs(session_delta_pct) <= 10.0:
            _prem_sentence = (
                f"The {session_delta_pct:+.1f}% premium is modest and operationally justified — "
                f"a single supply disruption to the baseline's concentrated sourcing would cost "
                f"more in delays and emergency sourcing than this premium."
            )
        else:
            _prem_sentence = (
                f"The {session_delta_pct:+.1f}% premium is material but defensible — driven by "
                f"active diversification and risk constraints that eliminate single-point "
                f"sourcing failure as a procurement risk."
            )

        if _single_country_prds:
            _baseline_why = (
                f"The baseline concentrates sourcing in a single country for "
                f"{', '.join(_single_country_prds)} — one tariff change, port closure, or "
                f"geopolitical event halts procurement entirely."
            )
        elif _single_supplier_prds:
            _baseline_why = (
                f"The baseline selects a single lowest-cost supplier for "
                f"{', '.join(_single_supplier_prds)} — no redundancy means any disruption "
                f"stops procurement entirely."
            )
        else:
            _baseline_why = (
                "The baseline selects the cheapest compliant suppliers with no regard for "
                "country concentration, lead-time reliability, or disruption history."
            )

        if len(_opt_countries) > 1:
            _opt_why = (
                f"The optimized plan spans {len(_opt_countries)} countries "
                f"({', '.join(_opt_countries)}), distributing risk across independent "
                f"supply chains. No single disruption event can halt procurement."
            )
        else:
            _opt_why = (
                "The optimized plan selects suppliers across risk-adjusted tiers, reducing "
                "dependency on any single sourcing channel even within the same geography."
            )

        st.markdown(f"- {_prem_sentence}")
        _risk_box(f"<strong>Why the baseline is cheaper:</strong> {_baseline_why}")
        _rec_box(
            f"<strong>Why the optimized plan is preferable:</strong> {_opt_why} "
            f"The risk premium is the cost of protection against a disruption event that "
            f"could halt production."
        )
    else:
        st.caption("Baseline comparison unavailable — baseline data not present for this run.")

    # ── Expandable justification panels ──────────────────────────────────────
    with st.expander("Why the Optimized Plan Reduces Supplier Risk", expanded=False):
        for r in approved:
            _prd_label_e = r.get("product", "unknown").replace("_", " ").title()
            st.markdown(f"**{_prd_label_e}**")
            alloc = r.get("allocation") or []
            if alloc:
                _opt_rows = [{
                    "Supplier":   a.get("supplier_id", "?"),
                    "Country":    a.get("country_code", "?"),
                    "Share (%)":  f"{a.get('share_pct', 0):.1f}%",
                    "Unit Cost":  f"${a.get('landed_unit_cost', 0):.4f}",
                    "Total Cost": f"${a.get('total_cost', 0):,.2f}",
                    "Tier":       a.get("decision_tier", "—"),
                } for a in alloc]
                st.caption("Optimized Allocation:")
                st.dataframe(_pd.DataFrame(_opt_rows), use_container_width=True, hide_index=True)

            b_cost_e   = r.get("baseline_cost")
            b_n_sup_e  = r.get("baseline_n_suppliers", 0)
            b_n_ctry_e = r.get("baseline_country_count", 0)
            _b_ids     = r.get("baseline_selected_suppliers") or []
            _b_id_str  = ", ".join(_b_ids) if _b_ids else f"{b_n_sup_e} supplier(s)"
            st.caption(
                f"Cost-only baseline: {_b_id_str} | "
                f"{b_n_ctry_e} countr{'y' if b_n_ctry_e == 1 else 'ies'} | "
                f"Cost: {'${:,.2f}'.format(b_cost_e) if b_cost_e else '—'}"
            )
            countries_e = r.get("countries") or []
            n_sup_e     = r.get("n_suppliers", 0)
            if b_n_ctry_e == 1 and len(set(countries_e)) > 1:
                st.info(
                    f"Optimized: {n_sup_e} suppliers across {len(set(countries_e))} countries "
                    f"({', '.join(sorted(set(countries_e)))}). "
                    f"Baseline routes 100% through one country — "
                    f"the optimized plan eliminates that single-country exposure."
                )
            elif n_sup_e > b_n_sup_e:
                st.info(
                    f"Optimized uses {n_sup_e} suppliers vs {b_n_sup_e} in the baseline — "
                    f"reducing dependency on any single source."
                )
            if r is not approved[-1]:
                st.markdown("---")

    _all_opt_countries = sorted(set(
        cc for r in approved for cc in (r.get("countries") or [])
    ))

    if _all_opt_countries:
        with st.expander("Country Logistics & Governance Comparison", expanded=False):
            st.caption(
                "Logistics Performance Index (LPI) and World Governance Indicators (WGI) "
                f"for countries in the optimized plan: {', '.join(_all_opt_countries)}. "
                "Higher scores indicate stronger logistics infrastructure and governance stability."
            )
            try:
                import sys as _sys_c, os as _os_c
                _parent_c = _os_c.path.join(_os_c.path.dirname(__file__), "..")
                if _parent_c not in _sys_c.path:
                    _sys_c.path.insert(0, _parent_c)
                import psycopg2 as _pg2
                from config import DATABASE_URL as _DB_URL
                import matplotlib.pyplot as _mpl
                from analytics.charts.plot_country_logistics_governance_comparison_panel import (
                    plot_country_indicator_comparison_panel as _plot_lpi,
                )
                _conn_lpi = _pg2.connect(_DB_URL)
                try:
                    _fig_lpi, _, _ = _plot_lpi(_conn_lpi, _all_opt_countries)
                    _b64_lpi = _fig_to_b64(_fig_lpi)
                    _mpl.close(_fig_lpi)
                    st.image(base64.b64decode(_b64_lpi))
                finally:
                    _conn_lpi.close()
            except Exception as _ce:
                st.caption(f"Country comparison chart unavailable: {_ce}")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # 02 — Supply Coverage & Shortfall
    # ─────────────────────────────────────────────────────────────────────────
    _section_header("02", "Supply Coverage & Shortfall")
    _covered_pct_global: float | None = None
    try:
        from tools.pipeline_queries import query_triggered_rows_structured as _qtr
        _trig_data = _qtr()
        _trig_rows = _trig_data.get("rows", [])

        # Classify rows using pre-computed _coverage_map
        _not_covered: list[dict] = []
        _covered:     list[dict] = []
        _cum_nc: dict[tuple, float] = {}
        _cum_cv: dict[tuple, float] = {}

        def _build_section_d_row(row: dict, cum_press: float) -> dict:
            _ss   = row.get("Safety Stock Reserve", 0)
            _need = row.get("Procurement Need", 0)
            _ss_util = (cum_press / _ss * 100) if _ss > 0 else 100.0
            return {
                "Forecast Week":                   row.get("Forecast Week", ""),
                "Facility":                        row.get("Facility", ""),
                "Component":                       row.get("Component", "").replace("_", " ").title(),
                "Direct Procurement Needed":       f"{_need:,.0f}",
                "Cumulative Procurement Pressure": f"{cum_press:,.0f}",
                "Safety Stock":                    f"{_ss:,.0f}",
                "Safety Stock Utilization (%)":    f"{_ss_util:.1f}%",
            }

        for row in sorted(
            (r for r in _trig_rows if r.get("Component", "") in approved_product_keys),
            key=lambda x: x.get("Forecast Week", 0),
        ):
            _prod     = row.get("Component", "")
            _earliest = _coverage_map.get(_prod)
            _fw       = row.get("Forecast Week", 0)
            _fc       = (_prod, row.get("Facility", ""))
            _need     = row.get("Procurement Need", 0)
            if _earliest is None or _fw < _earliest:
                _cum_nc[_fc] = _cum_nc.get(_fc, 0.0) + _need
                _not_covered.append(_build_section_d_row(row, _cum_nc[_fc]))
            else:
                _cum_cv[_fc] = _cum_cv.get(_fc, 0.0) + _need
                _covered.append(_build_section_d_row(row, _cum_cv[_fc]))

        _total_trigger_rows = len(_not_covered) + len(_covered)
        _covered_pct_global = (
            len(_covered) / _total_trigger_rows * 100 if _total_trigger_rows else 100.0
        )

        # Per-product coverage summary
        if _coverage_map:
            _cov_summary = []
            for _prd, _ew in _coverage_map.items():
                _prd_rows = [r for r in _trig_rows if r.get("Component", "") == _prd]
                _prd_cov  = sum(
                    1 for r in _prd_rows
                    if _ew is not None and r.get("Forecast Week", 0) >= _ew
                )
                _prd_tot  = len(_prd_rows)
                _prd_pct  = (_prd_cov / _prd_tot * 100) if _prd_tot else 100.0
                _ew_label = f"Week {_ew}" if _ew is not None else "Unknown (lead time unavailable)"
                _cov_summary.append({
                    "Product":                     _prd.replace("_", " ").title(),
                    "Earliest Replenishment Week": _ew_label,
                    "Trigger Rows Covered":        f"{_prd_cov} / {_prd_tot}",
                    "% Planning Horizon Covered":  f"{_prd_pct:.0f}%",
                })

            if _covered_pct_global >= 100:
                _rec_box(
                    "100% of triggered procurement windows are covered "
                    "by selected supplier replenishment timing."
                )
            elif _covered_pct_global >= 70:
                _risk_box(
                    f"<strong>{_covered_pct_global:.0f}% of triggered procurement windows are covered.</strong> "
                    f"{len(_not_covered)} row(s) require expedited or spot sourcing."
                )
            else:
                _risk_box(
                    f"<strong>{_covered_pct_global:.0f}% of triggered procurement windows are covered.</strong> "
                    f"{len(_not_covered)} row(s) fall before selected-supplier replenishment — "
                    f"emergency sourcing required."
                )
            st.dataframe(_pd.DataFrame(_cov_summary), use_container_width=True, hide_index=True)

        st.markdown(
            "<p style='font-family:Inter,sans-serif; font-size:0.75rem; font-weight:600; "
            "color:#df6500; text-transform:uppercase; letter-spacing:0.1em; margin:1.5rem 0 0.4rem;'>"
            "Uncovered Shortfall — Immediate Procurement Risk</p>",
            unsafe_allow_html=True,
        )
        if _not_covered:
            _risk_box(
                f"<strong>{len(_not_covered)} trigger row(s)</strong> fall before selected suppliers are "
                f"expected to begin replenishing inventory. "
                f"Emergency or spot sourcing is required for these windows."
            )
            st.dataframe(_pd.DataFrame(_not_covered), use_container_width=True, hide_index=True)
        else:
            _rec_box(
                "No uncovered shortfall rows identified. All triggered procurement windows "
                "fall within or after selected-supplier replenishment timing."
            )

        st.markdown(
            "<p style='font-family:Inter,sans-serif; font-size:0.75rem; font-weight:600; "
            "color:#76b900; text-transform:uppercase; letter-spacing:0.1em; margin:1.5rem 0 0.4rem;'>"
            "Covered Demand — Expected to be Fulfilled by Selected Suppliers</p>",
            unsafe_allow_html=True,
        )
        if _covered:
            _rec_box(
                f"<strong>{len(_covered)} trigger row(s)</strong> fall at or after the expected "
                f"selected-supplier replenishment window. These weeks are expected to be "
                f"covered by orders placed in the approved plan."
            )
            st.dataframe(_pd.DataFrame(_covered), use_container_width=True, hide_index=True)
        else:
            st.caption("No covered-demand rows found for approved products in the trigger view.")

    except Exception as _e:
        st.info(f"Supply coverage data unavailable: {_e}")
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # 03 — Strategic Recommendations
    # ─────────────────────────────────────────────────────────────────────────
    _section_header("03", "Strategic Recommendations")

    if _covered_pct_global is not None:
        if _covered_pct_global >= 100:
            _rec_box(
                f"<strong>Coverage status:</strong> 100% of triggered procurement windows are covered. "
                f"No immediate sourcing gaps for {', '.join(approved_product_names)}. "
                f"Issue purchase orders within the next <strong>8–10 weeks</strong> to stay on schedule."
            )
        else:
            _risk_box(
                f"<strong>Coverage status:</strong> {_covered_pct_global:.0f}% of triggered windows are "
                f"covered. Uncovered rows require <strong>expedited or spot-market sourcing</strong> — "
                f"initiate emergency sourcing immediately for the windows identified above."
            )
    else:
        _rec_box(
            f"<strong>Coverage status:</strong> Plan approved for {', '.join(approved_product_names)}. "
            f"Issue purchase orders within the next <strong>8–10 weeks</strong> to stay on schedule."
        )

    _risk_box(
        "<strong>Next-cycle trigger:</strong> Re-run the optimizer when any of the following occur: "
        "on-hand inventory drops toward safety stock levels, a new demand forecast is "
        "published, or a supplier disruption is detected. Do not wait for the planning "
        "cycle boundary."
    )
    _rec_box(
        "<strong>Carryover demand:</strong> This plan covers only the current planning horizon. "
        "Demand is expected to continue beyond this window, especially for multi-quarter production programs. "
        "If procurement needs extend beyond this horizon, rerun the optimization with an updated forecast "
        "to ensure future demand is explicitly planned for. Do not assume current allocations will automatically "
        "carry forward and cover demand needs past the planning horizon."
    )

    _carryover = []
    for r in approved:
        dm = r.get("diversification_mode", "none")
        if dm == "country_diversified":
            _carryover.append(f"{r.get('product','').replace('_',' ').title()} (country-diversified)")
        elif dm == "supplier_share_only":
            _mx = r.get("max_supplier_share", 1.0)
            _carryover.append(f"{r.get('product','').replace('_',' ').title()} (share-capped at {_mx:.0%})")
    if _carryover:
        _rec_box(
            f"<strong>Active constraints to carry forward:</strong> {'; '.join(_carryover)}. "
            f"Re-apply in the next planning run to maintain consistency."
        )
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # 04 — Next Steps
    # ─────────────────────────────────────────────────────────────────────────
    _section_header("04", "Next Steps")

    # What was done
    _rec_box(
        f"<strong>What was done:</strong> Procurement plans approved for "
        f"<strong>{len(approved)} product(s)</strong> "
        f"({', '.join(approved_product_names)}) — "
        f"<strong>{total_qty:,} units</strong> at an estimated cost of "
        f"<strong>${total_cost:,.2f}</strong>."
    )

    if avg_lambda == 0.0:
        _opt_reason = (
            "the optimizer minimized cost across compliant suppliers with no additional risk weighting"
        )
    elif avg_lambda <= 0.25:
        _opt_reason = (
            f"cost was the primary objective with light risk consideration (avg λ = {avg_lambda:.2f})"
        )
    elif avg_lambda <= 0.5:
        _opt_reason = (
            f"cost and supplier risk were jointly minimized (avg λ = {avg_lambda:.2f}), "
            f"favoring a balanced mix of efficiency and resilience"
        )
    elif avg_lambda <= 1.0:
        _opt_reason = (
            f"risk aversion was prioritized over cost minimization (avg λ = {avg_lambda:.2f}), "
            f"selecting more stable suppliers even at a cost premium"
        )
    else:
        _opt_reason = (
            f"supplier risk was the primary decision driver (avg λ = {avg_lambda:.2f}), "
            f"reflecting a risk-first procurement posture"
        )
    _rec_box(f"<strong>Why it is optimal:</strong> Under the configured constraints, {_opt_reason}.")

    _constraint_parts = []
    _div_counts: dict[str, int] = {}
    for r in approved:
        dm = r.get("diversification_mode", "none")
        _div_counts[dm] = _div_counts.get(dm, 0) + 1
    if _div_counts.get("country_diversified"):
        _constraint_parts.append(
            f"country-level diversification enforced on {_div_counts['country_diversified']} product(s)"
        )
    if _div_counts.get("supplier_share_only"):
        _constraint_parts.append(
            f"supplier share caps applied on {_div_counts['supplier_share_only']} product(s)"
        )
    _urgency_runs = [r for r in approved if r.get("urgency")]
    if _urgency_runs:
        _constraint_parts.append(f"urgency mode active on {len(_urgency_runs)} product(s)")

    _tradeoff_parts = []
    if _constraint_parts:
        _tradeoff_parts.append("; ".join(_constraint_parts).capitalize())
    if total_baseline > 0:
        _delta_pct = (total_cost - total_baseline) / total_baseline * 100
        if abs(_delta_pct) <= 1.0:
            _tradeoff_parts.append("cost premium vs unconstrained baseline is negligible (≤1%)")
        elif abs(_delta_pct) <= 10.0:
            _tradeoff_parts.append(
                f"cost premium vs unconstrained baseline is modest ({_delta_pct:.1f}%) — "
                "reflects expected trade-off between efficiency and resilience"
            )
        else:
            _tradeoff_parts.append(
                f"cost premium vs unconstrained baseline is material ({_delta_pct:.1f}%) — "
                "driven by diversification and risk constraints; justifiable as insurance "
                "against concentration risk"
            )
    if _tradeoff_parts:
        _rec_box(f"<strong>Tradeoffs:</strong> {'; '.join(_tradeoff_parts)}.")
    else:
        _rec_box("<strong>Tradeoffs:</strong> No significant cost-risk tradeoffs identified for this session.")

    # Country concentration risk — only flag if ≥2/3 of allocated suppliers share one country
    _country_conc_warnings = []
    for r in approved:
        _alloc_r = r.get("allocation") or []
        _n_alloc = len(_alloc_r)
        if _n_alloc < 2:
            continue
        _cc_counts: dict[str, int] = {}
        for _a in _alloc_r:
            _cc = _a.get("country_code", "?")
            _cc_counts[_cc] = _cc_counts.get(_cc, 0) + 1
        for _cc, _cnt in _cc_counts.items():
            if _cnt >= max(2, round(_n_alloc * 2 / 3)):
                _country_conc_warnings.append(
                    f"{r.get('product','').replace('_',' ').title()}: {_cnt}/{_n_alloc} from {_cc}"
                )

    if _country_conc_warnings:
        _risk_box(
            f"<strong>Country concentration risk:</strong> {'; '.join(_country_conc_warnings)}. "
            f"Consider running with <code>country_diversified</code> mode to reduce single-country exposure."
        )

    _risks = [
        "Lead-time exposure in high-urgency weeks should be monitored through the next planning cycle."
    ]
    if not _country_conc_warnings:
        _risks.append("No significant country concentration detected in the current plan.")
    _risks.append(
        "Supplier-level disruption risk and price volatility should be reviewed before "
        "the next procurement run."
    )
    _risk_box(f"<strong>Risks remaining:</strong> {' '.join(_risks)}")

    st.divider()
    if st.button("← Back to Procurement Agent", key="exit_exec_summary_btn"):
        st.session_state.show_executive_summary = False
        st.rerun()
