import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import AgentState
from llm import get_llm

logger = logging.getLogger(__name__)

SYNTHESIZER_PROMPT = """You are the final synthesizer of a procurement supply-chain analysis system.
You receive the user's original question and pre-formatted summaries from sub-agents.
The sub-agents already presented their detailed findings directly to the user.
If charts were generated, they are displayed visually to the user — reference them but do NOT describe them in detail.
Do NOT repeat the full details; instead:
1. Provide a brief executive summary (2-3 sentences max).
2. Identify cross-cutting insights or conflicts between agent results (e.g., a top-ranked supplier is in a geopolitically risky region).
3. Offer 2-3 actionable next steps.
Keep your response under 150 words and respond in the same language the user used."""


# ── LP session-state helpers ───────────────────────────────────────────────────

def _format_lp_pending_prompt(pending: dict) -> str:
    """
    Append an approval prompt to the synthesizer response when a LP run is
    awaiting user action.  Called only when state['pending_lp_run'] is set.
    """
    params   = pending.get('params_recap', {})
    cs       = pending.get('cost_summary', {})
    cd       = pending.get('constraint_diagnostics', {})
    exec_sum = pending.get('executive_summary', '')

    product  = (params.get('product') or 'N/A').replace('_', ' ')
    cost     = cs.get('total_cost_usd', 0)
    n_sup    = len(pending.get('allocation', []))
    countries = cd.get('countries_selected', [])
    div_mode  = params.get('diversification_mode', 'none')

    lines = [
        '',
        '─' * 68,
        '  LP RUN PENDING APPROVAL',
        f'  Product   : {product}',
        f'  Suppliers : {n_sup}  |  Countries: {", ".join(countries) if countries else "N/A"}',
        f'  Cost      : ${cost:,.2f}  |  Mode: {div_mode}',
    ]
    if exec_sum:
        lines.append(f'  Summary   : {exec_sum}')
    lines += [
        '',
        '  Reply "approve" (or "lock it in", "accept this plan") to add to session.',
        '  Reply "reject" (or "rerun", "try again") to discard.',
        '─' * 68,
    ]
    return '\n'.join(lines)


def _build_session_summary(approved_runs: list) -> str:
    """
    Build a procurement-manager-style wrap-up from all approved LP runs.
    Called when intent == 'session_summary'.
    """
    if not approved_runs:
        return (
            "No LP runs have been approved in this session.\n"
            "Run an LP optimization and approve it to include it in the summary."
        )

    n = len(approved_runs)
    lines = [
        '=' * 70,
        '  PROCUREMENT SESSION SUMMARY',
        f'  {n} approved run{"s" if n != 1 else ""}',
        '=' * 70,
        '',
        'Components secured:',
        f'  {"Product":<38} {"Units":>10}  {"Cost (USD)":>14}',
        '  ' + '-' * 66,
    ]

    total_units = 0
    total_cost  = 0.0
    total_rac   = 0.0
    all_countries: set = set()
    all_suppliers: set = set()
    total_budget = 0.0
    has_budget   = False
    div_modes    = []

    for r in approved_runs:
        prod   = (r.get('product') or 'N/A').replace('_', ' ')
        units  = r.get('total_units_procured', 0)
        cost   = r.get('total_cost', 0.0)
        lines.append(f'  {prod:<38} {units:>10,}  ${cost:>13,.2f}')

        total_units += units
        total_cost  += cost
        total_rac   += r.get('risk_adjusted_total', 0.0)
        all_countries.update(r.get('supplier_countries', []))
        all_suppliers.update(r.get('selected_suppliers', []))
        div_modes.append(r.get('diversification_mode', 'none'))
        if r.get('budget_cap'):
            total_budget += r['budget_cap']
            has_budget    = True

    lines += [
        '  ' + '-' * 66,
        f'  {"TOTAL":<38} {total_units:>10,}  ${total_cost:>13,.2f}',
        '',
        f'  Risk-adjusted total cost      : ${total_rac:>13,.2f}',
    ]

    if has_budget:
        remaining = total_budget - total_cost
        util_pct  = total_cost / total_budget * 100 if total_budget > 0 else 0
        lines += [
            f'  Combined budget cap           : ${total_budget:>13,.2f}',
            f'  Budget remaining              : ${remaining:>13,.2f}  ({100 - util_pct:.1f}% unused)',
        ]

    if total_units > 0:
        lines.append(
            f'  Avg landed unit cost          : ${total_cost / total_units:>13.5f}'
        )

    sorted_countries = sorted(all_countries)
    sorted_suppliers = sorted(all_suppliers)
    lines += [
        '',
        f'  Supplier countries            : {", ".join(sorted_countries)}'
        f'  ({len(sorted_countries)} countries)',
        f'  Suppliers selected            : {", ".join(sorted_suppliers)}'
        f'  ({len(sorted_suppliers)} total)',
    ]

    # Diversification posture
    if all(m == 'country_diversified' for m in div_modes):
        div_summary = 'fully country-diversified across all runs'
    elif all(m == 'none' for m in div_modes):
        div_summary = 'no diversification constraints applied'
    elif any(m != 'none' for m in div_modes):
        div_summary = 'mixed — some runs diversified, some unconstrained'
    else:
        div_summary = 'N/A'
    lines.append(f'  Diversification posture       : {div_summary}')

    # Per-run detail
    lines += ['', 'Run detail:']
    for i, r in enumerate(approved_runs, 1):
        prod    = (r.get('product') or 'N/A').replace('_', ' ')
        sups    = ', '.join(r.get('selected_suppliers', [])) or 'N/A'
        ctries  = ', '.join(r.get('supplier_countries', [])) or 'N/A'
        units   = r.get('total_units_procured', 0)
        cost    = r.get('total_cost', 0.0)
        mode    = r.get('diversification_mode', 'none')
        sl      = r.get('service_level_target', 1.0)
        exec_s  = r.get('executive_summary', '')
        fac     = r.get('facility_scope', 'all facilities')
        lines += [
            f'  Run {i}: {prod}',
            f'    Facility scope : {fac}',
            f'    Suppliers      : {sups}',
            f'    Countries      : {ctries}',
            f'    Units          : {units:,}',
            f'    Cost           : ${cost:,.2f}',
            f'    Div mode       : {mode}',
            f'    Service level  : {int(sl * 100)}%',
        ]
        if exec_s:
            lines.append(f'    Summary        : {exec_s}')
        lines.append('')

    lines += [
        'Key recommendations:',
        '  1. Cross-check supplier countries against current geopolitical risk alerts.',
        '  2. Confirm MOQ compliance for each selected supplier before issuing POs.',
        '  3. Review budget utilization — reallocate unused budget to buffer stock if needed.',
        '',
        '=' * 70,
    ]
    return '\n'.join(lines)


# ── Synthesizer node ───────────────────────────────────────────────────────────

async def synthesizer_node(state: AgentState) -> dict:
    start  = time.perf_counter()
    intent = state.get('intent') or ''

    prev_timings = state.get('timings') or {}

    def _done(content: str) -> dict:
        elapsed = time.perf_counter() - start
        logger.info(f'[TIMING] synthesizer: {elapsed:.3f}s')
        return {
            'final_response': content,
            'timings': {**prev_timings, 'synthesizer': round(elapsed, 3)},
        }

    # ── LP approval confirmation ───────────────────────────────────────────────
    if intent == 'lp_approved':
        approved = state.get('approved_lp_runs') or []
        last     = approved[-1] if approved else {}
        product  = (last.get('product') or 'N/A').replace('_', ' ')
        cost     = last.get('total_cost', 0)
        n        = len(approved)
        msg = (
            f'LP run approved and locked into session.\n'
            f'  Product: {product}  |  Cost: ${cost:,.2f}  |  '
            f'Session total: {n} approved run{"s" if n != 1 else ""}.\n\n'
            f'Say "session summary" when ready for the final procurement wrap-up, '
            f'or run another LP optimization.'
        )
        logger.info('[SYNTHESIZER] LP run confirmed as approved')
        return _done(msg)

    # ── LP rejection confirmation ──────────────────────────────────────────────
    if intent == 'lp_rejected':
        msg = (
            'LP run discarded — not included in session summary.\n'
            'You can run a new LP optimization with adjusted parameters at any time.'
        )
        logger.info('[SYNTHESIZER] LP run confirmed as rejected')
        return _done(msg)

    # ── Session summary ────────────────────────────────────────────────────────
    if intent == 'session_summary':
        approved = state.get('approved_lp_runs') or []
        logger.info(f'[SYNTHESIZER] Building session summary from {len(approved)} approved run(s)')
        return _done(_build_session_summary(approved))

    # ── Normal flow (LLM synthesis) ────────────────────────────────────────────
    llm           = get_llm()
    agent_results = state.get('agent_results') or {}
    chart_results = state.get('chart_results') or {}

    parts = [f'## {name}\n{value}' for name, value in agent_results.items()]
    if chart_results:
        chart_names = ', '.join(chart_results.keys())
        parts.append(
            f'## Charts Generated\n'
            f'The following charts are displayed to the user: {chart_names}'
        )

    formatted = '\n\n'.join(parts)
    response = await llm.ainvoke([
        SystemMessage(content=SYNTHESIZER_PROMPT),
        *state['messages'],
        HumanMessage(content=f'Sub-agent results:\n\n{formatted}'),
    ])

    content = response.content

    # Append LP pending prompt if a run is awaiting approval
    pending = state.get('pending_lp_run')
    if pending:
        logger.info('[SYNTHESIZER] Appending LP pending-approval prompt')
        content = content + '\n\n' + _format_lp_pending_prompt(pending)

    elapsed = time.perf_counter() - start
    logger.info(f'[TIMING] synthesizer: {elapsed:.3f}s')
    return {
        'final_response': content,
        'timings': {**prev_timings, 'synthesizer': round(elapsed, 3)},
    }
