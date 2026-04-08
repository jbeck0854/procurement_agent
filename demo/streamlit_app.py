import asyncio
import base64
import logging
import os
import uuid

import nest_asyncio
import streamlit as st

from langgraph.types import Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

nest_asyncio.apply()

from graph.builder import build_graph

# Keys that belong to other agents (not pipeline results).
# Used to filter agent_results → pipeline-only items by exclusion.
_NON_PIPELINE_KEYS = frozenset({
    "data_agent", "risk_agent", "pipeline_agent", "pipeline_errors",
    "lp_agent", "lp_agent_errors", "chart_agent",
})

# User inputs that trigger a session-level summary (bypass graph entirely).
_SUMMARY_TRIGGERS = frozenset({
    "final summary", "session summary", "summarize session",
    "summarize all", "full summary", "what did we decide",
})

# ── Opening kickoff detection ──────────────────────────────────────────────────
# Substring signals (lowercase). All four groups must match for kickoff to fire.
_KICKOFF_DEMAND  = ("demand", "planning horizon", "planning", "horizon", "weeks")
_KICKOFF_SUBJECT = ("semiconductor", "semionductor", "procurement", "component")
_KICKOFF_COST    = ("cost", "minim", "efficien", "budget")
_KICKOFF_RISK    = ("risk", "disruption", "reliab", "supplier")

# Responses that confirm the demand data and advance to the pipeline.
_PROCEED_TRIGGERS = frozenset({
    "yes", "yes, proceed", "looks correct", "proceed", "continue", "confirmed", "correct",
})

# Deterministic transition sentence shown immediately after kickoff confirmation.
# Appears before the forecast result so the user sees instant acknowledgement.
_KICKOFF_TRANSITION_SENTENCE = (
    "I will now generate forecasts over the upcoming planning horizon "
    "(20-week period), based on your historical demand data."
)

# ── Fast forecast-layer direct paths ──────────────────────────────────────────
# Context guard — at least one of these must appear for forecast routes to fire.
_FORECAST_CONTEXT = ("forecast", "model", "predict", "planning window", "forecastin")

# Model assessment direction signals (mirrors keywords in forecast_summary.py).
_FORECAST_BASELINE_SIGNALS = (
    "baseline", "benchmark", "compar", "naive", "better than", "versus",
    " vs ", "stack up", "improve",
)
_FORECAST_FEATURES_SIGNALS = (
    "feature", "features", "drove", "importance", "influential", "driver",
    "drivers", "what drives", "signal", "signals", "inputs",
)
_FORECAST_VALIDATE_SIGNALS = (
    "reliable", "how was", "trained", "validated", "validation", "training",
    "performance", "accuracy", "holdout", "trust", "can we trust",
)

# Drill-down signals — detail by facility / SKU / week.
_FORECAST_DRILLDOWN_SIGNALS = (
    "drill", "detail", "by facility", "by sku", "which sku",
    "per facility", "per sku", "breakdown", "where is demand",
    "concentration", "week by week", "week-by-week",
)

# Case B — specific facility chart (e.g. "Show forecast for Facility 2").
_FORECAST_FACILITY_SIGNALS = (
    "facility 1", "facility 2", "facility 3", "facility 4",
    "facility_1", "facility_2", "facility_3", "facility_4",
    "facility1", "facility2", "facility3", "facility4",
    "for facility", "for fac",
)

# Case C — all-facilities comparison chart.
_FORECAST_ALL_FACILITIES_SIGNALS = (
    "all facilit", "four facilit", "each facilit",
    "compare facilit", "across facilit", "facility-level",
    "facility level", "each of the four",
)

# Component requirements route — gross BOM demand before inventory netting.
# Specific enough that no context guard is needed.
_COMPONENT_REQ_SIGNALS = (
    "component requirement", "component demand",
    "gross component", "total component",
    "bom demand", "gross bom",
)
# Combined-match signals: "component(s)" + one of these fires the same route.
_COMPONENT_REQ_HORIZON_SIGNALS = (
    "planning window", "planning horizon", "demand window", "upcoming horizon",
)

# Inventory / procurement summary route — horizon-level net procurement requirement.
# Canonical queries: "Do we need to buy anything?" and inventory-adjusted variants.
# Checked AFTER BOM/component-requirements (those signals are more specific).
_PROC_SUMMARY_SIGNALS = (
    "do we need to buy",
    "need to order",
    "needs to be ordered",
    "inventory is factored",
    "inventory is accounted",
    "still need to buy",
    "inventory-adjusted procurement",
    "net procurement requirement",
    "what do we need to order",
    "what do we need to procure",
    "how much of each component",
    "what components do we need to buy",
)
# Combined guard: "inventory" + buy/order/procure intent fires the same route.
_PROC_SUMMARY_BUY_SIGNALS = ("order", "buy", "procure", "purchase")

# BOM translation explainability route — "how does/is SKU demand translated into component demand?"
# Canonical anchor phrase: "How exactly is forecasted SKU demand translated into component demand?"
# Direct signals must NOT overlap with _COMPONENT_REQ_SIGNALS; checked first in the elif chain.
_BOM_TRANSLATION_SIGNALS = (
    "translated into component",   # canonical anchor phrase (new primary)
    "translate into component",
    "translates into component",
    "bom convert",
    "bom translation",
    "demand becomes component",
    "sku demand translate",
    "explain how finished",
    "finished-goods demand becomes",
    "finished goods demand becomes",
)
# Combined guard: "bom" + any explanation-intent word fires the same route.
_BOM_TRANSLATION_EXPLAIN_SIGNALS = (
    "explain", "how does", "how is", "how do", "convert", "converts",
)

# Weekly trigger signal route — weekly-grain procurement trigger rows.
# Canonical query: "In which weeks and where is procurement actually triggered
# across the planning horizon?"
# Checked AFTER procurement summary (more specific drill-down).
_WEEKLY_TRIGGER_SIGNALS = (
    "triggered across the planning",
    "when is procurement triggered",
    "where and when do we actually need to buy",
    "weekly procurement trigger",
    "weekly trigger signal",
    "triggered procurement rows",
    "triggered rows",
    "which weeks and facilities trigger",
    "which weeks is procurement",
    "in which weeks",
)
# Combined guard: "triggered" + procurement/week/facility context fires the same route.
_WEEKLY_TRIGGER_CONTEXT_SIGNALS = ("procurement", "weeks", "facilities", "orders")


def _is_weekly_trigger_request(text: str) -> bool:
    """True for weekly-grain procurement trigger drill-down queries."""
    t = text.lower()
    if any(s in t for s in _WEEKLY_TRIGGER_SIGNALS):
        return True
    if "triggered" in t and any(s in t for s in _WEEKLY_TRIGGER_CONTEXT_SIGNALS):
        return True
    return False


# Safety stock / inventory policy explainability route.
# Canonical queries: "How is safety stock calculated?", "Explain safety stock policy",
# "How does base stock policy work?"
# Pure text output — no DB query required.
_SS_POLICY_SIGNALS = (
    "how is safety stock calculated",
    "explain safety stock policy",
    "how does base stock policy work",
    "base stock policy",
    "base-stock policy",
    "safety stock formula",
    "how is safety stock computed",
    "safety stock calculation",
    "explain the inventory policy",
)
# Combined guard: "safety stock" + explanation-intent word fires the same route.
_SS_POLICY_EXPLAIN_SIGNALS = (
    "explain", "how is", "how does", "what is", "calculate", "computed", "formula",
)


def _is_ss_policy_request(text: str) -> bool:
    """True for safety stock / inventory policy explainability queries."""
    t = text.lower()
    if any(s in t for s in _SS_POLICY_SIGNALS):
        return True
    if "safety stock" in t and any(s in t for s in _SS_POLICY_EXPLAIN_SIGNALS):
        return True
    return False


# Full inventory planning horizon drilldown route — diagnostic / traceability only.
# Returns ALL horizon rows (triggered + non-triggered) at facility × component × week.
# Canonical queries: "Show full horizon inventory drilldown",
#                    "Show all upcoming demand weeks across each facility for inventory planning"
# Must NOT overlap with: _is_procurement_summary_request (horizon-level net totals)
#                        _is_weekly_trigger_request (triggered rows only)
_FULL_HORIZON_SIGNALS = (
    "full horizon inventory",
    "full inventory planning",
    "full facility-component-week",
    "all upcoming demand weeks",
    "all planning rows for inventory",
    "full horizon drilldown",
    "all demand weeks across",
    "planning horizon drilldown",
    "full planning detail",
    "full horizon planning",
)
# Combined guard: "full" + "inventory" + drill-down-intent fires the same route.
_FULL_HORIZON_CONTEXT_SIGNALS = ("drilldown", "drill-down", "detail", "all weeks", "all rows")


def _is_full_horizon_drilldown_request(text: str) -> bool:
    """True for full-horizon inventory planning diagnostic / traceability queries."""
    t = text.lower()
    if any(s in t for s in _FULL_HORIZON_SIGNALS):
        return True
    if "full" in t and "inventory" in t and any(s in t for s in _FULL_HORIZON_CONTEXT_SIGNALS):
        return True
    return False


# ── LP intent parser ───────────────────────────────────────────────────────────
# Detects procurement optimization intent from BUSINESS language.
# Users will NOT say "optimize" or "run LP". They will say things like:
#   "provide a procurement plan", "ensure we have enough supply",
#   "recommend suppliers", "balance cost and risk", "limit supplier concentration"
#
# Detection requires THREE signals (all checked independently):
#   1. Procurement planning intent — e.g. "procurement plan", "source from"
#   2. Component reference        — e.g. "transistors", "microprocessors"
#   3. Decision framing           — e.g. risk/cost language, constraints, feasibility
#
# If all three are present, extract: product, lambda_risk, max_supplier_share.
# Result is injected as [LP_PARAMS: {...}] into the user message before graph
# invocation so the orchestrator receives exact values instead of inferring them.

# Signal 1 — Procurement planning intent (REQUIRED)
# Business-language triggers. No dependency on "optimize" or "run LP".
_LP_PROCUREMENT_SIGNALS = (
    "procurement plan",
    "sourcing plan",
    "sourcing strategy",
    "supply plan",
    "buying plan",
    "supplier allocation",
    "procurement recommendation",
    "procurement strategy",
    "how should we source",
    "how much should we buy",
    "how much to buy",
    "recommend suppliers",
    "recommend how much",
    "secure supply",
    "ensure we have enough",
    "ensure supply",
    "provide a plan",
    "allocate supply",
    "allocate procurement",
    "source from",
    "where should we buy",
    "who should we buy from",
    # "procure" alone (e.g. "To procure transistors...")
    "procure",
    # fast-path technical terms still accepted
    "optimize", "optimise", "optimization", "optimisation",
    "allocate", "run lp", "run the lp",
)

# Signal 2 — Component (REQUIRED).
# Ordered most-specific → least-specific. Checked via _COMPONENT_CANONICAL (below).

_COMPONENT_CANONICAL: dict[str, str] = {
    # longest phrases first to prevent partial matches
    "integrated_circuit_components":   "integrated_circuit_components",
    "integrated circuit components":   "integrated_circuit_components",
    "integrated circuit":              "integrated_circuit_components",
    "transistors":                     "transistors",
    "transistor":                      "transistors",
    "microprocessors":                 "microprocessors",
    "microprocessor":                  "microprocessors",
    # common misspelling / plural variant — normalize to canonical
    "microprocesses":                  "microprocessors",
    "power_devices":                   "power_devices",
    "power devices":                   "power_devices",
    "power device":                    "power_devices",
}

# Signal 3 — Decision framing (AT LEAST ONE REQUIRED)
# Covers: cost/risk tradeoff, supplier constraints, feasibility language,
# and strategy-intent words.
_LP_DECISION_SIGNALS = (
    # cost / risk tradeoff
    "cost", "risk", "tradeoff", "trade-off",
    # supplier constraints
    "cap", "exceed", "limit", "concentrate", "concentration",
    "no supplier should", "share", "diversif",
    # feasibility / demand coverage
    "meet demand", "meet our demand", "meet upcoming demand",
    "enough supply", "enough", "sufficient",
    "cover demand", "cover our demand",
    # strategy language
    "strategy", "aversion", "averse", "balance", "balanced",
    # optimization-adjacent (still valid framing, just not required)
    "minimize", "minimise", "optimal", "best mix",
)

# Lambda_risk mapping — ordered most-specific → least-specific.
# Exact values; no ranges.
_LAMBDA_MAP: list[tuple[str, float]] = [
    ("very risk averse",   1.5),
    ("very risk-averse",   1.5),
    ("risk first",         1.5),
    ("risk priority",      1.5),
    ("moderate risk aversion", 0.5),  # MUST be before "risk aversion" — is a substring match
    ("risk aversion",      1.0),
    ("risk averse",        1.0),
    ("risk-averse",        1.0),
    ("high risk",          1.0),
    ("heightened",         1.0),      # "heightened state / level / risk aversion"
    ("elevated risk",      1.0),
    ("moderate risk",      0.5),
    ("moderate",           0.5),
    ("balanced",           0.5),
    ("low risk",           0.25),
    ("cost focused",       0.25),
    ("cost-focused",       0.25),
    ("low",                0.25),
    ("cost only",          0.0),
    ("cost-only",          0.0),
    ("no risk",            0.0),
]

import re as _re


def _parse_lp_intent(prompt: str) -> dict | None:
    """
    Detect LP optimization intent from business language and extract parameters.

    Three signals must all be present:
      1. Procurement planning intent  — business-language buy/source/plan phrasing
      2. Component reference          — specific product name
      3. Decision framing             — cost/risk/constraints/feasibility language

    Returns dict with detected params (product, lambda_risk, max_supplier_share),
    or None if the query is not an LP request.

    The caller injects the result as [LP_PARAMS: {...}] into the user message
    before graph invocation.
    """
    t = prompt.lower()

    # ── Signal 2: Component (checked first — cheapest gate) ─────────────────
    detected_product: str | None = None
    _matched_phrase: str | None = None
    for phrase, canonical in _COMPONENT_CANONICAL.items():
        if phrase in t:
            detected_product = canonical
            _matched_phrase  = phrase
            break
    logger.debug(
        "[LP INTENT] matched_phrase=%r | normalized_product=%r | "
        "signal1=%s | signal3=%s",
        _matched_phrase, detected_product,
        any(s in t for s in _LP_PROCUREMENT_SIGNALS),
        any(s in t for s in _LP_DECISION_SIGNALS),
    )
    if not detected_product:
        return None

    # ── Signal 1: Procurement planning intent ────────────────────────────────
    if not any(s in t for s in _LP_PROCUREMENT_SIGNALS):
        return None

    # ── Signal 3: Decision framing ───────────────────────────────────────────
    if not any(s in t for s in _LP_DECISION_SIGNALS):
        return None

    params: dict = {"product": detected_product}

    # ── Extract lambda_risk ──────────────────────────────────────────────────
    # Most-specific match wins (list is ordered).
    for phrase, value in _LAMBDA_MAP:
        if phrase in t:
            params["lambda_risk"] = value
            break

    # ── Extract max_supplier_share ───────────────────────────────────────────
    # Handles all common phrasings:
    #   "40% cap", "40% supplier cap", "40% max share"
    #   "max share 40%", "no supplier should exceed 40%", "limit supplier to 40%"
    cap_m = _re.search(r'(\d+)\s*%\s*(?:supplier\s*)?(?:cap|share|max)', t)
    if not cap_m:
        cap_m = _re.search(
            r'(?:max\s*(?:supplier\s*)?share|supplier\s*cap)\s*(?:of\s*)?(\d+)\s*%', t
        )
    if not cap_m:
        cap_m = _re.search(
            r'(?:no\s+supplier\s+should\s+exceed|limit\s+supplier(?:\s+\w+){0,2}\s+to)\s+(\d+)\s*%',
            t,
        )
    if cap_m:
        pct = int(cap_m.group(1))
        if 0 < pct <= 100:
            params["max_supplier_share"] = round(pct / 100, 2)

    # ── Extract diversification_mode ─────────────────────────────────────────
    _DIVERSIF_PHRASES = (
        "diversif", "different countr", "different country", "3 countries",
        "three countries", "country diversif", "across countries",
        "each from a different country", "different country of origin",
    )
    if any(p in t for p in _DIVERSIF_PHRASES):
        params["diversification_mode"] = "country_diversified"

    # ── Extract urgency ───────────────────────────────────────────────────────
    _URGENCY_PHRASES = ("urgent", "urgency", "emergency sourcing", "expedite")
    if any(p in t for p in _URGENCY_PHRASES):
        params["urgency"] = True

    # ── Extract exclude_supplier_ids ──────────────────────────────────────────
    # Matches explicit supplier IDs like SUP_HKG_38, SUP_CHN_07, etc.
    _excl_ids = _re.findall(r'\bSUP_[A-Z]{3}_\d+\b', prompt)
    _EXCLUSION_CTX = ("exclude", "unavailable", "without supplier", "remove supplier",
                      "can't use", "cannot use", "what if")
    if _excl_ids and any(p in t for p in _EXCLUSION_CTX):
        params["exclude_supplier_ids"] = _excl_ids

    return params


# ── LP follow-up detector ───────────────────────────────────────────────────────
# Handles revision queries that don't use full procurement-planning language.
# Examples: "Keep transistors but lower the cap to 30%"
#           "Same product but make this urgency-focused"
#           "Exclude SUP_HKG_38 and rerun"
#
# Requires: product detected + prior LP context for that product + at least one
# refinement/parameter signal.  Returns fully-merged params (prior base + overrides).
# Returns None if any gate fails.

_LP_FOLLOWUP_SIGNALS = (
    # explicit refinement intent
    "keep", "same", "but", "instead", "lower", "higher", "change",
    "without", "except", "different", "try", "adjust", "rerun", "redo",
    # LP-parameter hints (risk / cost)
    "risk", "cost", "moderate", "balanced", "avers",
    # constraint hints
    "cap", "share", "limit", "exceed", "%",
    # mode hints
    "diversif", "countr", "urgent", "urgency",
    # exclusion hint (explicit ID present)
    "exclude",
)


def _parse_lp_followup(prompt: str, lp_history: dict) -> dict | None:
    """
    Detect LP follow-up / refinement from prior session context + minimal signal.

    Unlike _parse_lp_intent(), this does NOT require the full 3-signal set.
    It triggers when:
      1. A known product is mentioned in the prompt.
      2. Prior LP params for that product exist in lp_history.
      3. At least one LP-parameter hint is present.

    Returns fully-merged params (prior base overridden by current-prompt values),
    or None if any gate fails.
    """
    t = prompt.lower()

    # Gate 1 — product
    detected_product: str | None = None
    for phrase, canonical in _COMPONENT_CANONICAL.items():
        if phrase in t:
            detected_product = canonical
            break
    if not detected_product:
        return None

    # Gate 2 — prior LP context for this product
    prior = lp_history.get(detected_product)
    if not prior:
        return None

    # Gate 3 — at least one refinement / parameter signal
    if not any(s in t for s in _LP_FOLLOWUP_SIGNALS):
        return None

    # Build merged params: prior base → apply current-prompt overrides.
    merged: dict = {
        "product":              prior.get("product", detected_product),
        "lambda_risk":          prior.get("lambda_risk", 0.5),
        "max_supplier_share":   prior.get("max_supplier_share", 1.0),
        "diversification_mode": prior.get("diversification_mode", "none"),
        "urgency":              prior.get("urgency", False),
        "exclude_supplier_ids": list(prior.get("exclude_supplier_ids") or []),
        "budget_cap":           prior.get("budget_cap"),
        "service_level_target": prior.get("service_level_target", 1.0),
        "compliance_threshold": prior.get("compliance_threshold", 0.50),
        "facility_id":          prior.get("facility_id"),
    }

    # Override lambda_risk
    for phrase, value in _LAMBDA_MAP:
        if phrase in t:
            merged["lambda_risk"] = value
            break

    # Override max_supplier_share
    _cap_m = _re.search(r'(\d+)\s*%\s*(?:supplier\s*)?(?:cap|share|max)', t)
    if not _cap_m:
        _cap_m = _re.search(
            r'(?:max\s*(?:supplier\s*)?share|supplier\s*cap)\s*(?:of\s*)?(\d+)\s*%', t
        )
    if not _cap_m:
        _cap_m = _re.search(
            r'(?:no\s+supplier\s+should\s+exceed|limit\s+supplier(?:\s+\w+){0,2}\s+to)\s+(\d+)\s*%', t
        )
    if _cap_m:
        _pct = int(_cap_m.group(1))
        if 0 < _pct <= 100:
            merged["max_supplier_share"] = round(_pct / 100, 2)

    # Override diversification_mode
    _DIV = ("diversif", "different countr", "different country", "3 countries",
            "three countries", "country diversif", "across countries",
            "each from a different country", "different country of origin")
    if any(p in t for p in _DIV):
        merged["diversification_mode"] = "country_diversified"

    # Override urgency
    if any(p in t for p in ("urgent", "urgency", "emergency sourcing", "expedite")):
        merged["urgency"] = True

    # Override exclude_supplier_ids (only when explicit IDs present + exclusion context)
    _xids = _re.findall(r'\bSUP_[A-Z]{3}_\d+\b', prompt)
    if _xids and any(p in t for p in ("exclude", "unavailable", "without supplier",
                                       "remove supplier", "can't use", "cannot use")):
        merged["exclude_supplier_ids"] = _xids

    return merged


# ── LP contextual follow-up detector ───────────────────────────────────────────
# Handles vague urgency / schedule messages that rely on conversational LP context
# rather than an explicit product mention.  Examples:
#   "It appears we are a bit behind schedule this cycle for this particular product"
#   "Let's make this one more urgent"
#   "Speed this product up"
#
# Does NOT require a product name in the prompt.
# Resolves product from the most recent LP result in session state.
# Returns merged params (prior base + urgency=True), or None if no context / no signal.

_LP_CONTEXTUAL_URGENCY_SIGNALS = (
    "behind schedule",
    "a bit behind",
    "falling behind",
    "behind on this",
    "behind this cycle",
    "need this faster",
    "need it faster",
    "tighter timeline",
    "more urgent",
    "make this urgent",
    "make it urgent",
    "make this more urgent",
    "speed this up",
    "speed this product up",
    "accelerate this",
    "this is urgent",
    "becoming urgent",
)

# Contextual references that anchor the message to the current plan/product.
_LP_CONTEXTUAL_REF_SIGNALS = (
    "this particular product",
    "this particular component",
    "this component",
    "this product",
    "this one",
    "this order",
    "this plan",
    "this cycle",
    "for this",
)


def _parse_lp_contextual_followup(
    prompt: str,
    lp_history: dict,
    last_lp_raw: dict,
) -> dict | None:
    """
    Detect vague urgency / schedule follow-ups in the context of the most recent LP run.

    Unlike _parse_lp_followup(), this does NOT require a product name in the prompt.
    It resolves the product from the most recent LP result in session state.

    Requirements:
      1. Recent LP context in session (non-empty lp_history or last_lp_raw).
      2. At least one urgency/schedule signal.
      3. At least one contextual reference signal  OR  a strong schedule phrase alone
         ("behind schedule", "a bit behind", "falling behind").

    Returns fully-merged params (prior base + urgency=True), or None.
    """
    t = prompt.lower()

    # Gate 1 — recent LP context required
    if not lp_history and not last_lp_raw:
        return None

    # Gate 2 — at least one urgency/schedule signal
    has_urgency = any(s in t for s in _LP_CONTEXTUAL_URGENCY_SIGNALS)
    # Also accept bare "urgent" / "urgency" / "expedite" when paired with a context ref
    has_bare_urgency = any(s in t for s in ("urgent", "urgency", "expedite"))

    if not has_urgency and not has_bare_urgency:
        return None

    # Gate 3 — contextual product reference, OR strong schedule phrasing alone
    has_context_ref = any(s in t for s in _LP_CONTEXTUAL_REF_SIGNALS)
    strong_schedule  = any(s in t for s in ("behind schedule", "a bit behind", "falling behind"))

    # Bare urgency ("urgent", "urgency") alone is too broad — require a context ref.
    if has_bare_urgency and not has_urgency and not has_context_ref:
        return None

    # Strong schedule phrasing alone (without context ref) is sufficient.
    if not has_urgency and not strong_schedule and not has_context_ref:
        return None

    # ── Resolve product from most recent LP context ────────────────────────────
    # Priority 1: last_lp_raw_full keys are "lp_{product}" — most recently shown result.
    # Priority 2: last key in lp_history (Python 3.7+ preserves insertion order).
    recent_product: str | None = None
    if last_lp_raw:
        for key in last_lp_raw:
            if key.startswith("lp_"):
                recent_product = key[3:]
                break
    if not recent_product and lp_history:
        recent_product = list(lp_history.keys())[-1]

    if not recent_product:
        return None

    # ── Build merged params: prior base + urgency override ────────────────────
    prior = lp_history.get(recent_product, {})
    merged: dict = {
        "product":              prior.get("product", recent_product),
        "lambda_risk":          prior.get("lambda_risk", 0.5),
        "max_supplier_share":   prior.get("max_supplier_share", 1.0),
        "diversification_mode": prior.get("diversification_mode", "none"),
        "urgency":              True,   # always set for contextual urgency follow-up
        "exclude_supplier_ids": list(prior.get("exclude_supplier_ids") or []),
        "budget_cap":           prior.get("budget_cap"),
        "service_level_target": prior.get("service_level_target", 1.0),
        "compliance_threshold": prior.get("compliance_threshold", 0.50),
        "facility_id":          prior.get("facility_id"),
    }
    return merged


# ── LP direct-route gating ─────────────────────────────────────────────────────
# Signals that indicate params _parse_lp_intent() cannot fully extract.
# Queries matching any of these require the orchestrator to interpret complex
# params (exclude_supplier_ids, diversification_mode, urgency, facility scope,
# budget cap, service-level target).  They use the orchestrator fast path
# (which still bypasses plan-approval) rather than the direct LP route.
_LP_ORCHESTRATOR_REQUIRED_SIGNALS = (
    # Supplier exclusion where ID is NOT matchable by SUP_XXX_NN regex
    "unavailable",          # e.g. "supplier X is unavailable" (no explicit ID)
    "what if",              # disruption / what-if scenario (ambiguous supplier ref)
    "without supplier",     # disruption phrasing without explicit ID
    "reinstate",            # what-if reversal
    # Facility-scoped runs referenced by description (not ID)
    "facility ",            # facility-scoped run
    "single facility",
    # Budget / service level adjustments that require numeric extraction
    "budget cap",
    "budget limit",
    "spending limit",
    "spend cap",
    "service level",
    "buffer stock",
    "extra buffer",
    # NOTE: "diversif", "different countr", "urgent", "urgency", "exclude",
    # "emergency" are now handled deterministically by _parse_lp_intent()
    # and do NOT require the orchestrator.
)


def _needs_orchestrator(prompt: str) -> bool:
    """Return True if the LP query contains params the orchestrator must extract.

    Direct LP route is only safe for queries that _parse_lp_intent() can fully
    interpret: product + lambda_risk + max_supplier_share.  Everything else
    (exclusion IDs, diversification, urgency, facility scope, budget) needs the
    orchestrator LLM to parse the natural language into structured params.
    """
    t = prompt.lower()
    return any(s in t for s in _LP_ORCHESTRATOR_REQUIRED_SIGNALS)


def _run_lp_direct(params: dict) -> None:
    """Execute LP optimization without the orchestrator or LangGraph graph.

    Calls run_optimization() from tools/optimization.py directly, builds the
    LP approval payload, and sets session state so render_lp_approval() renders
    the result immediately on the next Streamlit rerun.

    Args:
        params: dict from _parse_lp_intent() — must contain 'product' key.
                May also contain 'lambda_risk' and 'max_supplier_share'.
                All other LP params use run_optimization() defaults.

    Side-effects:
        Sets st.session_state.waiting_for_lp_approval = True
        Sets st.session_state.pending_lp_result       = LP approval payload
        Sets st.session_state.last_lp_raw_full        = {result_key: result}
        Saves params_recap to st.session_state.lp_params_history for carry-forward
        Calls st.rerun() to surface the LP result page
    """
    import time as _time
    from tools.optimization import run_optimization

    product = params.get("product", "transistors")
    lam     = params.get("lambda_risk", 0.5)
    share   = params.get("max_supplier_share", 1.0)
    div_mode    = params.get("diversification_mode", "none")
    urgency_flg = params.get("urgency", False)
    excl_ids    = params.get("exclude_supplier_ids") or []
    budget_cap  = params.get("budget_cap", None)
    svc_level   = params.get("service_level_target", 1.0)
    compliance  = params.get("compliance_threshold", 0.50)
    facility_id = params.get("facility_id", None)

    t0 = _time.perf_counter()
    logger.info(
        "[LP DIRECT] product=%s | lambda_risk=%s | max_supplier_share=%s | "
        "diversification_mode=%s | urgency=%s | exclude=%s",
        product, lam, share, div_mode, urgency_flg, excl_ids,
    )

    try:
        result = run_optimization(
            product=product,
            lambda_risk=lam,
            max_supplier_share=share,
            diversification_mode=div_mode,
            urgency=urgency_flg,
            exclude_supplier_ids=excl_ids,
            budget_cap=budget_cap,
            service_level_target=svc_level,
            compliance_threshold=compliance,
            facility_id=facility_id,
        )
        t_solve = _time.perf_counter()
        status = (
            result.get("constraint_diagnostics", {}).get("lp_status")
            or result.get("lp_status", "Unknown")
        )
        logger.info(
            "[LP DIRECT] status=%s | solve_elapsed=%.3fs | total=%.3fs",
            status, t_solve - t0, t_solve - t0,
        )
    except Exception as _e:
        logger.error("[LP DIRECT] LP solve failed: %s", _e, exc_info=True)
        st.error(f"LP optimization failed: {_e}")
        return

    result_key = f"lp_{product}"

    # Persist params_recap for carry-forward on subsequent disruption / urgency reruns.
    params_recap = result.get("params_recap", {})
    if "lp_params_history" not in st.session_state:
        st.session_state.lp_params_history = {}
    if params_recap:
        st.session_state.lp_params_history[product] = params_recap

    # Build LP approval payload — identical schema to lp_agent_node interrupt payload.
    # direct_mode=True tells render_lp_approval() to skip graph resume on approve/discard.
    lp_interrupt_payload = {
        "type":        "lp_approval",
        "direct_mode": True,
        "raw":         {result_key: result},
        "formatted":   {result_key: ""},   # _render_lp_result() renders from raw, not formatted
    }

    st.session_state.waiting_for_lp_approval = True
    st.session_state.pending_lp_result       = lp_interrupt_payload
    st.session_state.lp_partial_state        = {}
    st.session_state.last_lp_raw_full        = {result_key: result}
    st.session_state.saved_plan              = {}
    # thread_id intentionally not set — no graph session exists in direct mode.
    st.rerun()


# ── LP decision explanation route ──────────────────────────────────────────────
# "How was this decision made?" — user-triggered structured LP explanation.
_LP_EXPLAIN_SIGNALS = (
    "how was this decision made",
    "how was the decision made",
    "how did you make this decision",
    "explain this decision",
    "explain the decision",
    "explain the recommendation",
    "explain the lp",
    "explain the optimization",
    "how does the optimizer work",
    "how does the optimization work",
    "why did you recommend",
    "why this recommendation",
    "what drove this recommendation",
    "what is the objective",
    "what is the objective function",
    "how was this optimized",
)


def _is_lp_decision_explanation_request(text: str) -> bool:
    """True for 'How was this decision made?' and equivalent phrasings."""
    t = text.lower()
    return any(s in t for s in _LP_EXPLAIN_SIGNALS)


# Transition sentences and section headings for each assessment direction.
_FORECAST_ASSESS_META = {
    "validation": (
        "Yes — I can explain how the forecast model was trained and validated. "
        "Here is the model assessment summary.",
        "📐 Forecast Model — Validation & Training Performance",
    ),
    "features": (
        "Here is a breakdown of which features drove the forecast model most, "
        "based on permutation importance measured on the held-out validation set.",
        "📐 Forecast Model — Feature Importance",
    ),
    "baseline": (
        "Here is how the production forecast compares with the baseline approaches "
        "used for validation.",
        "📐 Forecast Model — Baseline Comparison",
    ),
}

# Project root — one level up from demo/. Used to resolve artifact PNG paths.
_ARTIFACTS_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# Path to the historical demand CSV (relative to this file).
_CSV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "cleaned_data", "finished_goods_demand_table.csv")
)

# Fixed opening response — no variability.
_KICKOFF_OPENING_RESPONSE = """\
Understood. We will:

1. Verify your historical demand across all four facilities and semiconductor SKUs
2. Translate that demand into the exact component requirements needed to support production
3. Assess inventory coverage and identify where procurement is required
4. Optimize supplier allocation to minimize cost while controlling supplier risk and disruption

Your objective balances cost efficiency with supply reliability:
- **Lower emphasis** prioritizes cost minimization
- **Higher emphasis** prioritizes more stable, lower-risk suppliers even if slightly more expensive

Let's begin by validating the historical demand that drives this entire workflow.

Please review the historical demand file below and confirm it looks correct. Once reviewed, \
reply with **'Yes, proceed'** to continue.\
"""

st.set_page_config(page_title="Procurement Agent", layout="wide")
st.title("Procurement Supply Chain Agent")


@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

# ── Core session state ─────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "traces" not in st.session_state:
    st.session_state.traces = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "waiting_for_approval" not in st.session_state:
    st.session_state.waiting_for_approval = False
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "plan_feedback" not in st.session_state:
    st.session_state.plan_feedback = ""

# ── Fast-path visual persistence ──────────────────────────────────────────────
# DataFrames for Case-A drilldown. Stored by index so replay loop can re-render
# them after st.rerun(). Charts are stored as base64 PNG in the message dict.
if "fast_path_dfs" not in st.session_state:
    st.session_state.fast_path_dfs = []

# ── LP approval session state ──────────────────────────────────────────────────
if "waiting_for_lp_approval" not in st.session_state:
    st.session_state.waiting_for_lp_approval = False
if "pending_lp_result" not in st.session_state:
    st.session_state.pending_lp_result = None
if "lp_partial_state" not in st.session_state:
    st.session_state.lp_partial_state = {}
if "saved_plan" not in st.session_state:
    st.session_state.saved_plan = {}

# ── Modify mode — explicit in-place LP refinement ──────────────────────────────
# lp_modify_mode: True when user clicked "Modify" — keeps pending result as the
#   editable baseline; chat input is exposed inside render_lp_approval().
# lp_modify_baseline: dict keyed by product → entry-format snapshot of the result
#   that was displayed when Modify was clicked.  Used by _find_prev_same_product_run()
#   so the what-if comparison table diffs against the pending (not approved) result.
if "lp_modify_mode" not in st.session_state:
    st.session_state.lp_modify_mode = False
if "lp_modify_baseline" not in st.session_state:
    st.session_state.lp_modify_baseline = {}

# ── Session-level approved LP runs ─────────────────────────────────────────────
if "approved_lp_runs" not in st.session_state:
    st.session_state.approved_lp_runs = []

# Full raw LP result dict from the most recent LP interrupt, keyed by product_key.
# Used by the "How was this decision made?" explanation route after approval.
if "last_lp_raw_full" not in st.session_state:
    st.session_state.last_lp_raw_full = {}

# Flag: user clicked "Complete Procurement Plan" — show final executive summary.
# Only set by explicit user action; never auto-triggered.
if "show_executive_summary" not in st.session_state:
    st.session_state.show_executive_summary = False

# ── Opening kickoff state ──────────────────────────────────────────────────────
if "historical_demand_verification_pending" not in st.session_state:
    st.session_state.historical_demand_verification_pending = False


# ── Session-level helpers ──────────────────────────────────────────────────────

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
        "baseline_cost":        baseline.get("total_cost_usd"),
        "baseline_n_suppliers": len(baseline.get("baseline_selected_suppliers") or []),
        "baseline_country_count": baseline.get("baseline_country_count", 0),
    }


def _store_approved_run(result: dict) -> None:
    """Append one approved LP result dict to the session-level approved_lp_runs store."""
    st.session_state.approved_lp_runs.append(_build_run_entry(result))


def _apply_modify_overrides(prompt: str, base_params: dict) -> dict:
    """Apply LP parameter overrides from a modify-mode user message.

    Used exclusively in modify mode — Gates 1 and 2 (product detection, prior
    context) are skipped because base_params come directly from the displayed
    pending LP result.  Applies any detectable overrides on top of that base.

    Handles the full range of modification intents:
      - risk level    ("more risk averse", "cost only", …)
      - supplier cap  ("40% cap", "no supplier should exceed 35%", …)
      - diversification ("different countries", "diversify portfolio", …)
      - urgency       ("expedite", "urgent", …)
      - exclusion     ("SUP_HKG_38 unavailable", "what if SUP_X …", "exclude SUP_Y", …)
      - compliance    ("lower compliance to 45%", …)
      - budget cap    ("budget cap of $500,000", …)
    """
    t      = prompt.lower()
    merged = dict(base_params)

    # Override lambda_risk
    for phrase, value in _LAMBDA_MAP:
        if phrase in t:
            merged["lambda_risk"] = value
            break

    # Override max_supplier_share
    _cap_m = _re.search(r'(\d+)\s*%\s*(?:supplier\s*)?(?:cap|share|max)', t)
    if not _cap_m:
        _cap_m = _re.search(
            r'(?:max\s*(?:supplier\s*)?share|supplier\s*cap)\s*(?:of\s*)?(\d+)\s*%', t
        )
    if not _cap_m:
        _cap_m = _re.search(
            r'(?:no\s+supplier\s+should\s+exceed|limit\s+supplier(?:\s+\w+){0,2}\s+to)\s+(\d+)\s*%',
            t,
        )
    if _cap_m:
        _pct = int(_cap_m.group(1))
        if 0 < _pct <= 100:
            merged["max_supplier_share"] = round(_pct / 100, 2)

    # Override diversification_mode
    _DIV = (
        "diversif", "different countr", "different country", "3 countries",
        "three countries", "country diversif", "across countries",
        "each from a different country", "different country of origin",
    )
    if any(p in t for p in _DIV):
        merged["diversification_mode"] = "country_diversified"

    # Override urgency
    if any(p in t for p in ("urgent", "urgency", "emergency sourcing", "expedite")):
        merged["urgency"] = True

    # Override exclude_supplier_ids — expanded exclusion context for modify mode
    # (includes "unavailable" and "what if" phrasing beyond what _parse_lp_followup handles)
    _xids = _re.findall(r'\bSUP_[A-Z]{3}_\d+\b', prompt)
    if _xids and any(
        p in t for p in (
            "exclude", "unavailable", "without supplier", "remove supplier",
            "can't use", "cannot use", "becomes unavailable", "not available",
            "what if", "if supplier",
        )
    ):
        merged["exclude_supplier_ids"] = _xids

    # Override compliance_threshold
    _comp_m = _re.search(r'compliance\s*(?:threshold|to|at|=)?\s*(\d+)\s*%', t)
    if not _comp_m:
        _comp_m = _re.search(r'(\d+)\s*%\s*compliance', t)
    if _comp_m:
        _pct = int(_comp_m.group(1))
        if 0 < _pct <= 100:
            merged["compliance_threshold"] = round(_pct / 100, 2)

    # Override budget_cap
    _budget_m = _re.search(r'budget\s*(?:cap|limit|of)?\s*\$?([\d,]+)', t)
    if _budget_m:
        try:
            merged["budget_cap"] = float(_budget_m.group(1).replace(",", ""))
        except ValueError:
            pass

    return merged


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


# ── Opening kickoff helpers ────────────────────────────────────────────────────

def _is_first_user_turn() -> bool:
    """True when no assistant message has been rendered yet in this session."""
    return not any(m.get("role") == "assistant" for m in st.session_state.messages)


def _is_opening_kickoff(text: str) -> bool:
    """True when first user message signals a broad planning + cost + risk objective.

    Uses substring matching so minor misspellings (e.g. 'semionductor', 'plannning')
    are handled without NLP. All four signal groups must be present.
    """
    t = text.lower()
    return (
        any(s in t for s in _KICKOFF_DEMAND)
        and any(s in t for s in _KICKOFF_SUBJECT)
        and any(s in t for s in _KICKOFF_COST)
        and any(s in t for s in _KICKOFF_RISK)
    )


def _is_proceed_response(text: str) -> bool:
    """True when user confirms the demand data and wants to advance."""
    t = text.lower().strip()
    return any(trigger in t for trigger in _PROCEED_TRIGGERS)


def _forecast_assessment_direction(text: str) -> str | None:
    """Return the assessment direction ('validation', 'features', 'baseline') or None.

    Requires at least one _FORECAST_CONTEXT signal. Among the three directions,
    baseline is checked first (most specific phrase), then features, then validation.
    Returns None if no forecast-context + direction signal is found.
    """
    t = text.lower()
    if not any(s in t for s in _FORECAST_CONTEXT):
        return None
    if any(s in t for s in _FORECAST_BASELINE_SIGNALS):
        return "baseline"
    if any(s in t for s in _FORECAST_FEATURES_SIGNALS):
        return "features"
    if any(s in t for s in _FORECAST_VALIDATE_SIGNALS):
        return "validation"
    return None


def _is_forecast_drilldown_request(text: str) -> bool:
    """True when the user asks for forecast detail by facility/SKU/week."""
    t = text.lower()
    return (
        any(s in t for s in _FORECAST_CONTEXT)
        and any(s in t for s in _FORECAST_DRILLDOWN_SIGNALS)
    )


def _is_all_facilities_forecast(text: str) -> bool:
    """True when the user asks for a cross-facility forecast comparison.

    Checked BEFORE _forecast_assessment_direction so that queries containing
    'compare' (e.g. 'Compare forecast demand across all facilities') are not
    misrouted to the model-baseline assessment route, which also matches 'compar'.
    Requires at least one _FORECAST_CONTEXT signal plus one all-facilities signal.
    """
    t = text.lower()
    return (
        any(s in t for s in _FORECAST_CONTEXT)
        and any(s in t for s in _FORECAST_ALL_FACILITIES_SIGNALS)
    )


def _is_component_requirements_request(text: str) -> bool:
    """True when the user asks for full-horizon gross component demand (pre-inventory).

    Fires on direct signals (e.g. 'component requirement', 'gross bom') or on the
    combined pattern: 'component(s)' + a horizon/window context term.

    LP PRECEDENCE: If _parse_lp_intent() detects a procurement-allocation query,
    this function returns False so LP routing is not shadowed.  This prevents queries
    like "Provide a procurement plan ... for this particular component ... demand window"
    from firing via the combined 'component' + 'demand window' match.
    """
    t = text.lower()
    # ── LP allocation intent takes priority over BOM routing ─────────────────
    if _parse_lp_intent(text) is not None:
        logger.debug(
            "[ROUTE ARBITRATION] LP intent detected — suppressing BOM/component-req route "
            "| bom_signal_would_have_fired=%s",
            any(s in t for s in _COMPONENT_REQ_SIGNALS)
            or ("component" in t and any(s in t for s in _COMPONENT_REQ_HORIZON_SIGNALS)),
        )
        return False
    if any(s in t for s in _COMPONENT_REQ_SIGNALS):
        return True
    # Combined: 'component' + planning horizon / window context
    if "component" in t and any(s in t for s in _COMPONENT_REQ_HORIZON_SIGNALS):
        return True
    return False


def _is_bom_translation_request(text: str) -> bool:
    """True when the user asks how finished-good SKU demand converts to component demand.

    Fires on direct phrasing (e.g. 'translated into component', 'bom translation')
    or on the combined pattern: 'bom' + an explanation-intent word.
    Must be checked BEFORE _is_component_requirements_request() in the elif chain
    so that queries containing 'component demand' in a translation context route here
    and not to the component totals summary.
    """
    t = text.lower()
    if any(s in t for s in _BOM_TRANSLATION_SIGNALS):
        return True
    # Combined: BOM mentioned + explanation intent (excludes pure demand-total queries)
    if "bom" in t and any(s in t for s in _BOM_TRANSLATION_EXPLAIN_SIGNALS):
        return True
    return False


def _is_procurement_summary_request(text: str) -> bool:
    """True for horizon-level inventory-adjusted procurement need queries.

    Catches 'Do we need to buy anything?', 'What is our net procurement
    requirement?', and similar. Fires AFTER BOM/component-requirements routes
    so those more specific signals are not shadowed.

    LP PRECEDENCE: Same guard as _is_component_requirements_request() — if LP
    allocation intent is detected, LP routing wins.
    """
    t = text.lower()
    # ── LP allocation intent takes priority ───────────────────────────────────
    if _parse_lp_intent(text) is not None:
        return False
    if any(s in t for s in _PROC_SUMMARY_SIGNALS):
        return True
    # "procurement" + requirement/need intent
    if "procurement" in t and any(s in t for s in ("requirement", "need", "needed")):
        return True
    # "inventory" + buy/order/procure intent
    if "inventory" in t and any(s in t for s in _PROC_SUMMARY_BUY_SIGNALS):
        return True
    return False


def _extract_facility_id(text: str) -> str | None:
    """Extract FACILITY_N from free text (e.g. 'Facility 2' → 'FACILITY_2')."""
    import re
    m = re.search(r'facilit(?:y|_)?[\s_]?(\d)', text.lower())
    return f"FACILITY_{m.group(1)}" if m else None


def _format_facility_label(facility_id: str) -> str:
    """Convert DB-format 'FACILITY_1' to business-facing 'Facility 1'."""
    import re
    m = re.match(r'FACILITY_(\d+)', facility_id, re.IGNORECASE)
    return f"Facility {m.group(1)}" if m else facility_id


def _fetch_component_req_data() -> dict:
    """Fetch structured component requirement data for DataFrame rendering.

    Queries the same source as format_component_requirements() but returns
    structured dicts/lists instead of formatted text — used by the demo render
    block to build proper DataFrames. No computation is changed.
    """
    import psycopg2
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
    from config import DATABASE_URL

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Resolve latest forecast run (matches _resolve_run_id contract)
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "ORDER BY forecast_run_id DESC LIMIT 1"
            )
            row = cur.fetchone()
            run_id = int(row[0]) if row else 0

            # Planning window metadata
            cur.execute(
                """
                SELECT MIN(target_week_date), MAX(target_week_date),
                       COUNT(DISTINCT target_week_date),
                       COUNT(DISTINCT facility_id),
                       COUNT(DISTINCT product_key)
                FROM vw_component_requirement_lp
                WHERE forecast_run_id = %s
                """,
                (run_id,),
            )
            start_date, end_date, n_weeks, n_fac, n_comp = cur.fetchone()

            # Per-component totals, ordered by descending volume
            cur.execute(
                """
                SELECT p.product, SUM(lp.total_component_requirement) AS total_gross
                FROM vw_component_requirement_lp lp
                JOIN dim_product p ON p.product_key = lp.product_key
                WHERE lp.forecast_run_id = %s
                GROUP BY p.product
                ORDER BY total_gross DESC
                """,
                (run_id,),
            )
            comp_rows = cur.fetchall()
    finally:
        conn.close()

    return {
        "run_id":       run_id,
        "start_date":   str(start_date),
        "end_date":     str(end_date),
        "n_weeks":      int(n_weeks),
        "n_facilities": int(n_fac),
        "n_components": int(n_comp),
        "rows":         [(r[0], float(r[1])) for r in comp_rows],
    }


def _render_csv_button() -> None:
    """Compact summary line + download button for historical demand CSV.

    Shows dataset shape and key dimensions without rendering the full table inline.
    """
    try:
        import pandas as pd
        df = pd.read_csv(_CSV_PATH)
        n_rows, n_cols = df.shape
        facilities = df["facility_id"].nunique() if "facility_id" in df.columns else "?"
        skus       = df["semiconductor_id"].nunique() if "semiconductor_id" in df.columns else "?"
        weeks      = df["week"].nunique() if "week" in df.columns else "?"
        st.caption(
            f"Historical demand file: **{n_rows:,} rows** · **{n_cols} columns** · "
            f"**{facilities} facilities** · **{skus} SKUs** · **{weeks} weeks**"
        )
        st.download_button(
            label="📥 Download Historical Demand CSV",
            data=df.to_csv(index=False).encode(),
            file_name="finished_goods_demand_table.csv",
            mime="text/csv",
            key="kickoff_csv_download",
        )
    except Exception:
        st.caption("Historical demand file: `cleaned_data/finished_goods_demand_table.csv`")


def _render_kickoff_response() -> None:
    """Render the deterministic opening assistant message and CSV button (first turn only)."""
    with st.chat_message("assistant"):
        st.markdown(_KICKOFF_OPENING_RESPONSE)
        _render_csv_button()
    st.session_state.messages.append({
        "role": "assistant",
        "content": _KICKOFF_OPENING_RESPONSE,
        "has_trace": False,
        "summary": "",
    })


def _render_demand_verification_banner() -> None:
    """Persistent info banner + CSV button shown on every rerender while verification is pending."""
    st.info(
        "Waiting for your confirmation on the historical demand data. "
        "Reply **'Yes, proceed'** when ready to begin the analysis pipeline.",
        icon="📋",
    )
    _render_csv_button()
    st.divider()


def _fig_to_b64(fig) -> str:
    """Serialize a matplotlib Figure to base64-encoded PNG string.

    Used by fast-path drill-down handlers to persist charts across st.rerun().
    The b64 string is stored in the message dict under 'chart_b64' and decoded
    by the replay loop with st.image(base64.b64decode(msg['chart_b64'])).
    """
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _plot_facility_faceted(df, facility_id: str):
    """6×2 faceted figure — one subplot per semiconductor SKU for a single facility.

    Each panel shows the 20-week predicted demand line with a lightly shaded 90% CI.
    SKUs are sorted alphabetically so the layout is deterministic across facilities.
    """
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import pandas as pd

    fac_df = df[df["facility_id"] == facility_id].copy()
    # Coerce numeric columns — psycopg2 returns Decimal, pandas stores as object.
    for col in ("predicted_demand", "interval_lower_90", "interval_upper_90"):
        fac_df[col] = pd.to_numeric(fac_df[col], errors="coerce").fillna(0.0)
    fac_df["target_week_date"] = fac_df["target_week_date"].astype(str)
    skus = sorted(fac_df["semiconductor_id"].unique())
    n_skus = len(skus)
    ncols = 2
    nrows = (n_skus + 1) // 2  # ceil division — handles odd counts cleanly
    palette = [cm.tab10(i / 10) for i in range(min(n_skus, 10))]

    fig, axes = plt.subplots(nrows, ncols, figsize=(12, nrows * 3), sharey=False)
    axes = axes.flatten()

    for i, sku in enumerate(skus):
        ax = axes[i]
        s = fac_df[fac_df["semiconductor_id"] == sku].sort_values("target_week_date")
        color = palette[i % len(palette)]
        ax.plot(s["target_week_date"], s["predicted_demand"],
                color=color, linewidth=1.8)
        ax.fill_between(
            s["target_week_date"],
            s["interval_lower_90"], s["interval_upper_90"],
            alpha=0.12, color=color,
        )
        ax.set_title(sku, fontsize=9, pad=4)
        ax.tick_params(axis="x", rotation=45, labelsize=6)
        ax.tick_params(axis="y", labelsize=7)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

    # Hide any unused subplot panels (if SKU count is odd)
    for j in range(n_skus, len(axes)):
        axes[j].set_visible(False)

    label = _format_facility_label(facility_id)
    fig.suptitle(
        f"Production Demand Forecast — {label} by SKU",
        fontsize=12, y=1.005,
    )
    fig.tight_layout()
    return fig


def _narrative_facility_bullets(df, facility_id: str) -> str:
    """Markdown bullet summary for a single-facility faceted forecast view.

    Covers: total/avg demand, peak + lowest week, SKU concentration, and a
    cross-SKU comparative insight (highest-volume SKUs + most/least volatile).
    Returned string is passed directly to st.markdown().
    """
    import pandas as pd
    fac_df = df[df["facility_id"] == facility_id].copy()
    # Coerce to numeric — psycopg2 returns Decimal, which groupby().sum() keeps as
    # object dtype, causing nlargest() / arithmetic to fail.
    fac_df["predicted_demand"] = pd.to_numeric(fac_df["predicted_demand"], errors="coerce").fillna(0.0)
    weekly = fac_df.groupby("target_week_date")["predicted_demand"].sum()
    total     = weekly.sum()
    avg       = weekly.mean()
    n_weeks   = weekly.nunique()
    peak_week = str(weekly.idxmax())
    peak_val  = weekly.max()
    low_week  = str(weekly.idxmin())
    low_val   = weekly.min()

    by_sku = fac_df.groupby("semiconductor_id")["predicted_demand"].sum()
    top_sku   = by_sku.idxmax()
    top_share = by_sku.max() / by_sku.sum() * 100
    n_skus    = by_sku.nunique()

    if top_share > 40:
        concentration = (
            f"Demand is concentrated — **{top_sku}** accounts for "
            f"**{top_share:.0f}%** of facility volume"
        )
    else:
        concentration = (
            f"Demand is broadly distributed across {n_skus} SKUs "
            f"(top SKU: **{top_sku}** at **{top_share:.0f}%**)"
        )

    # Top 3 by total volume and SKU-level coefficient of variation (volatility proxy)
    top3 = by_sku.nlargest(3).index.tolist()
    top3_str = ", ".join(f"**{s}**" for s in top3)
    sku_cv = (
        fac_df.groupby("semiconductor_id")["predicted_demand"]
        .apply(lambda x: x.std() / x.mean() if x.mean() > 0 else 0.0)
    )
    most_volatile  = sku_cv.idxmax()
    least_volatile = sku_cv.idxmin()
    cross_sku = (
        f"{top3_str} lead in total volume; "
        f"**{most_volatile}** shows the highest week-to-week variability "
        f"while **{least_volatile}** is the most stable"
    )

    return "\n".join([
        f"- **Total horizon demand:** {total:,.0f} units across {n_weeks} weeks",
        f"- **Average weekly demand:** {avg:,.0f} units/week",
        f"- **Peak week:** {peak_week} → {peak_val:,.0f} units",
        f"- **Lowest week:** {low_week} → {low_val:,.0f} units",
        f"- **SKU concentration:** {concentration}",
        f"- **Cross-SKU insight:** {cross_sku}",
    ])


def show_trace(trace):
    with st.expander("Execution Trace"):
        # --- Timing breakdown ---
        timings = trace.get("timings") or {}
        if timings:
            st.subheader("Performance")
            top_level = ["orchestrator", "data_agent", "risk_agent", "pipeline_agent", "chart_agent", "lp_agent", "synthesizer"]
            active = [name for name in top_level if timings.get(name) is not None]
            if active:
                cols = st.columns(len(active))
                for col, name in zip(cols, active):
                    col.metric(name, f"{timings[name]:.2f}s")
            total = sum(timings.get(k, 0) for k in top_level)
            st.caption(f"Total pipeline time: **{total:.2f}s**")

            sub_steps = {k: v for k, v in timings.items() if "." in k}
            if sub_steps:
                detail_lines = [f"- {k}: {v:.3f}s" for k, v in sub_steps.items()]
                st.markdown("**Step breakdown:**\n" + "\n".join(detail_lines))
            st.divider()

        st.subheader("Orchestrator")
        st.write(f"**Intent:** {trace['intent']}")
        for i, task in enumerate(trace["tasks"]):
            st.write(f"**Task {i+1}**")
            st.write(f"- Agent: {task['agent']}")
            st.write(f"- Objective: {task['objective']}")
            st.write(f"- Context: {task['context']}")
            st.write(f"- Instructions: {task['instructions']}")

        st.subheader("Router")
        if trace["tasks"]:
            routed_agents = list({task["agent"] for task in trace["tasks"]})
            st.write(f"Routed to: **{', '.join(routed_agents)}**")

        pipeline_results = {k: v for k, v in trace["agent_results"].items()
                           if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")}
        if pipeline_results:
            st.subheader("Pipeline Agent")
            for key, content in pipeline_results.items():
                st.caption(key.replace("_", " ").title())
                st.code(content)

        for agent_name, label in [("data_agent", "Data Agent"), ("risk_agent", "Risk Agent")]:
            raw = trace["agent_results"].get(agent_name)
            if raw:
                st.subheader(label)
                display = raw[:500] + "..." if len(raw) > 500 else raw
                st.code(display)

        lp_results = {k: v for k, v in trace["agent_results"].items() if k.startswith("lp_")}
        if lp_results:
            st.subheader("LP Optimization Agent")
            for key, content in lp_results.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                st.caption(f"Product: {product}")
                st.code(content)

        chart_results = trace.get("chart_results") or {}
        if chart_results:
            st.subheader("Chart Agent")
            for chart_name, b64_img in chart_results.items():
                st.caption(chart_name)
                st.image(base64.b64decode(b64_img))

        st.subheader("Synthesizer")
        st.write("Final response generated")


# ── Message history replay ─────────────────────────────────────────────────────

assistant_index = 0
for _msg_loop_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        # ── Fast-path chart replay (Case B / Case C drilldown) ────────────
        # Assessment routes set chart_first=True so the plot renders before
        # the text summary (transition + result_text are stored together in
        # content, so the only way to get image-first is to render the chart
        # before calling st.markdown on content).
        _b64 = msg.get("chart_b64", "")
        if _b64 and msg.get("chart_first"):
            st.image(base64.b64decode(_b64))
        if msg.get("content"):
            st.markdown(msg["content"])
        if _b64 and not msg.get("chart_first"):
            if msg.get("chart_scroll"):
                # Case B: render inside a scrollable HTML div so the chart
                # area scrolls independently and the summary stays fixed above.
                st.markdown(
                    f'<div style="height:640px;overflow-y:auto;'
                    f'border:1px solid #e6e9ef;border-radius:6px;padding:4px;">'
                    f'<img src="data:image/png;base64,{_b64}"'
                    f' style="width:100%;display:block;" /></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.image(base64.b64decode(_b64))
        # ── Fast-path dataframe replay (Case A drilldown) ─────────────────
        df_idx = msg.get("df_index")
        if df_idx is not None and df_idx < len(st.session_state.fast_path_dfs):
            _replay_df = st.session_state.fast_path_dfs[df_idx]
            st.dataframe(
                _replay_df.style.format({
                    "Forecast":   "{:,.0f}",
                    "Lower 90%":  "{:,.0f}",
                    "Upper 90%":  "{:,.0f}",
                }),
                use_container_width=True,
            )
        # ── Fast-path component-requirements replay ────────────────────────
        _comp_req_dfs = msg.get("comp_req_dfs")
        if _comp_req_dfs:
            import pandas as _pd
            for _spec in _comp_req_dfs:
                st.caption(_spec["caption"])
                _cdf = _pd.DataFrame(_spec["records"])
                if "Units Required" in _cdf.columns:
                    st.dataframe(
                        _cdf.style.format({"Units Required": "{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.dataframe(_cdf, use_container_width=True, hide_index=True)
        # ── Fast-path BOM translation replay ──────────────────────────────
        _bom_xlate = msg.get("bom_xlate_df")
        if _bom_xlate:
            import pandas as _pd
            _bdf = _pd.DataFrame(_bom_xlate)
            st.dataframe(
                _bdf.style.format({
                    "Units / SKU":            "{:,.2f}",
                    "Forecast (units)":       "{:,.0f}",
                    "Gross Component Demand": "{:,.0f}",
                }),
                height=420,
                use_container_width=True,
                hide_index=True,
            )
        # ── Fast-path procurement summary replay ──────────────────────────
        _proc_rows = msg.get("proc_summary_df")
        if _proc_rows:
            import pandas as _pd
            _proc_df = _pd.DataFrame(_proc_rows)
            _proc_fmt = {
                c: "{:,.0f}" for c in _proc_df.columns if c != "Component"
            }
            st.dataframe(
                _proc_df.style.format(_proc_fmt),
                use_container_width=True,
                hide_index=True,
            )
        # ── Fast-path weekly trigger replay ───────────────────────────────
        _trig_rows = msg.get("weekly_trigger_df")
        if _trig_rows:
            import pandas as _pd
            _trig_df = _pd.DataFrame(_trig_rows)
            # Filters — applied in-memory on the stored unfiltered rows
            _fac_opts  = sorted(_trig_df["Facility"].unique().tolist())  if "Facility"  in _trig_df.columns else []
            _comp_opts = sorted(_trig_df["Component"].unique().tolist()) if "Component" in _trig_df.columns else []
            _col_f, _col_c = st.columns(2)
            with _col_f:
                _sel_fac = st.multiselect(
                    "Filter by Facility",
                    options=_fac_opts,
                    default=_fac_opts,
                    key=f"trig_fac_{_msg_loop_idx}",
                )
            with _col_c:
                _sel_comp = st.multiselect(
                    "Filter by Component",
                    options=_comp_opts,
                    default=_comp_opts,
                    key=f"trig_comp_{_msg_loop_idx}",
                )
            if _sel_fac:
                _trig_df = _trig_df[_trig_df["Facility"].isin(_sel_fac)]
            if _sel_comp:
                _trig_df = _trig_df[_trig_df["Component"].isin(_sel_comp)]
            # Safety Stock context block (above primary table)
            _ss_ctx = msg.get("ss_context", [])
            if _ss_ctx:
                _ss_ctx_df = _pd.DataFrame(_ss_ctx)
                # Apply facility filter to context block if active
                if _sel_fac and "Facility" in _ss_ctx_df.columns:
                    _ss_ctx_df = _ss_ctx_df[_ss_ctx_df["Facility"].isin(_sel_fac)]
                if _sel_comp and "Component" in _ss_ctx_df.columns:
                    _ss_ctx_df = _ss_ctx_df[_ss_ctx_df["Component"].isin(_sel_comp)]
                st.dataframe(
                    _ss_ctx_df.style.format({"Safety Stock (Protected Floor)": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "This value represents the inventory buffer required to maintain the "
                    "target service level. It is preserved in all inventory calculations "
                    "and not consumed by demand. The table below shows how procurement "
                    "pressure accumulates relative to this buffer."
                )
            _trig_fmt = {
                "Forecast Week":                  "{:,.0f}",
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Cumulative Procurement Pressure":"{:,.0f}",
                "Safety Stock Utilization (%)":   "{:.1f}%",
            }
            _trig_fmt = {c: v for c, v in _trig_fmt.items() if c in _trig_df.columns}
            st.caption(f"{len(_trig_df):,} rows shown")
            st.dataframe(
                _trig_df.style.format(_trig_fmt),
                use_container_width=True,
                hide_index=True,
                height=500,
            )
        # ── Full horizon drilldown replay (diagnostic) ────────────────────
        _fh_rows_replay = msg.get("full_horizon_df")
        if _fh_rows_replay:
            import pandas as _pd
            _fh_df = _pd.DataFrame(_fh_rows_replay)
            _fh_fac_opts  = sorted(_fh_df["Facility"].unique().tolist())  if "Facility"  in _fh_df.columns else []
            _fh_comp_opts = sorted(_fh_df["Component"].unique().tolist()) if "Component" in _fh_df.columns else []
            _fh_col_a, _fh_col_b = st.columns(2)
            with _fh_col_a:
                _fh_sel_fac = st.multiselect(
                    "Filter by Facility",
                    options=_fh_fac_opts,
                    default=_fh_fac_opts,
                    key=f"fh_fac_{_msg_loop_idx}",
                )
            with _fh_col_b:
                _fh_sel_comp = st.multiselect(
                    "Filter by Component",
                    options=_fh_comp_opts,
                    default=_fh_comp_opts,
                    key=f"fh_comp_{_msg_loop_idx}",
                )
            if _fh_sel_fac:
                _fh_df = _fh_df[_fh_df["Facility"].isin(_fh_sel_fac)]
            if _fh_sel_comp:
                _fh_df = _fh_df[_fh_df["Component"].isin(_fh_sel_comp)]
            _fh_fmt = {
                "Forecast Week":                  "{:,.0f}",
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Safety Stock (Protected Floor)": "{:,.0f}",
            }
            _fh_fmt = {c: v for c, v in _fh_fmt.items() if c in _fh_df.columns}
            st.caption(f"{len(_fh_df):,} rows shown")
            st.dataframe(
                _fh_df.style.format(_fh_fmt),
                use_container_width=True,
                hide_index=True,
                height=600,
            )
        # ── Trace-backed chart replay (graph execution path) ──────────────
        if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
            chart_results = st.session_state.traces[assistant_index].get("chart_results") or {}
            for chart_name, b64_img in chart_results.items():
                st.caption(chart_name.replace("_", " ").title())
                st.image(base64.b64decode(b64_img))
            if msg.get("summary"):
                st.markdown(msg["summary"])
    if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
        show_trace(st.session_state.traces[assistant_index])
        assistant_index += 1


# ── Graph execution helpers ────────────────────────────────────────────────────

def extract_plan(state):
    interrupts = []
    for task in state.tasks or []:
        interrupts.extend(task.interrupts or [])
    return interrupts[0].value if interrupts else None


def stream_graph(command, config):
    placeholder = st.empty()
    final_state = {"agent_results": {}}

    def _render_streaming(placeholder):
        with placeholder.container():
            pipeline_results = final_state.get("pipeline_results") or {}
            if pipeline_results:
                st.subheader("📊 Pipeline Results")
                for key, content in pipeline_results.items():
                    st.caption(key.replace("_", " ").title())
                    st.code(content)
            if final_state.get("latest_data_agent"):
                st.subheader("📊 Data Query")
                st.markdown(final_state["latest_data_agent"])
            if final_state.get("latest_risk_agent"):
                st.divider()
                st.subheader("🌐 Geopolitical Risk Analysis")
                st.markdown(final_state["latest_risk_agent"])
            lp_results = final_state.get("lp_results") or {}
            if lp_results:
                st.divider()
                st.subheader("⚙️ LP Optimization Results")
                for key, content in lp_results.items():
                    product = key.replace("lp_", "").replace("_", " ").title()
                    st.caption(f"Product: {product}")
                    st.code(content)
            charts = final_state.get("chart_results") or {}
            if charts:
                st.divider()
                st.subheader("📈 Visualizations")
                for chart_name, b64_img in charts.items():
                    st.caption(chart_name.replace("_", " ").title())
                    st.image(base64.b64decode(b64_img))
            if final_state.get("final_response"):
                st.divider()
                st.subheader("📋 Summary & Recommendations")
                st.markdown(final_state["final_response"])

    async def stream_results():
        async for event in graph.astream(command, config=config):
            for node_name, node_output in event.items():
                # ── LP approval interrupt detection ──────────────────────────
                # Must precede the isinstance(dict) check: node_output is a
                # tuple of Interrupt objects here, not a dict.
                if node_name == "__interrupt__":
                    interrupts = node_output
                    if interrupts:
                        intr = interrupts[0]
                        intr_val = intr.value if hasattr(intr, "value") else {}
                        if isinstance(intr_val, dict) and intr_val.get("type") == "lp_approval":
                            final_state["__interrupt__"] = intr_val
                    return final_state  # graph is paused — stop streaming

                # ── Normal event handling ────────────────────────────────────
                if not isinstance(node_output, dict):
                    continue
                if "intent" in node_output:
                    final_state["intent"] = node_output["intent"]
                if "tasks" in node_output:
                    final_state["tasks"] = node_output["tasks"]
                if "agent_results" in node_output:
                    final_state.setdefault("agent_results", {}).update(node_output["agent_results"] or {})
                if node_name == "pipeline_agent" and node_output.get("agent_results"):
                    pipeline_items = {k: v for k, v in node_output["agent_results"].items()
                                     if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")}
                    if pipeline_items:
                        final_state.setdefault("pipeline_results", {}).update(pipeline_items)
                if node_name == "data_agent" and node_output.get("agent_results"):
                    data_text = node_output["agent_results"].get("data_agent")
                    if data_text:
                        final_state["latest_data_agent"] = data_text
                if node_name == "risk_agent" and node_output.get("agent_results"):
                    risk_text = node_output["agent_results"].get("risk_agent")
                    if risk_text:
                        final_state["latest_risk_agent"] = risk_text
                if node_name == "lp_agent" and node_output.get("agent_results"):
                    lp_items = {k: v for k, v in node_output["agent_results"].items() if k.startswith("lp_")}
                    if lp_items:
                        final_state.setdefault("lp_results", {}).update(lp_items)
                if node_name == "chart_agent" and node_output.get("chart_results"):
                    final_state.setdefault("chart_results", {}).update(node_output["chart_results"])
                if node_name == "synthesizer" and "final_response" in node_output:
                    final_state["final_response"] = node_output["final_response"]
                    final_state["timings"] = node_output.get("timings", {})
                final_state[node_name] = node_output
        return final_state

    result = asyncio.run(stream_results())
    # Skip rendering if LP interrupt fired — render_lp_approval() handles display.
    if not result.get("__interrupt__"):
        _render_streaming(placeholder)
    return result


def finalize_execution(final_state, fallback_plan=None):
    plan = fallback_plan or {}
    trace = {
        "intent": final_state.get("intent") or plan.get("intent", ""),
        "tasks": final_state.get("tasks") or plan.get("tasks", []),
        "agent_results": final_state.get("agent_results", {}),
        "chart_results": final_state.get("chart_results") or {},
        "timings": final_state.get("timings") or plan.get("timings", {}),
    }
    st.session_state.traces.append(trace)

    parts = []
    pipeline_items = {k: v for k, v in trace["agent_results"].items()
                     if k not in _NON_PIPELINE_KEYS and not k.startswith("lp_")}
    if pipeline_items:
        pip_parts = []
        for key, content in pipeline_items.items():
            title = key.replace("_", " ").title()
            pip_parts.append(f"**{title}**\n\n```\n{content}\n```")
        parts.append("**📊 Pipeline Results**\n\n" + "\n\n".join(pip_parts))
    data_result = trace["agent_results"].get("data_agent", "")
    if data_result:
        parts.append(data_result)
    risk_result = trace["agent_results"].get("risk_agent", "")
    if risk_result:
        parts.append("---\n\n**🌐 Geopolitical Risk Analysis**\n\n" + risk_result)
    lp_items = {k: v for k, v in trace["agent_results"].items() if k.startswith("lp_")}
    is_lp_flow = bool(lp_items)
    # For LP flows, suppress the verbose formatted LP text and synthesizer summary.
    # The structured result was already shown in render_lp_approval(); repeating it
    # here would create a confusing duplicate in the message history.
    final_response = final_state.get("final_response", "")
    summary_text = ""
    if final_response and not is_lp_flow:
        summary_text = "---\n\n**📋 Summary & Recommendations**\n\n" + final_response
    combined = "\n\n".join(parts)

    with st.chat_message("assistant"):
        if is_lp_flow:
            # Minimal acknowledgement — the full result lives in the approval panel above.
            products = [k.replace("lp_", "").replace("_", " ").title() for k in lp_items]
            st.markdown(
                f"Procurement plan for **{', '.join(products)}** has been processed. "
                "Review the result above and approve or discard."
            )
        else:
            if combined:
                st.markdown(combined)
            for chart_name, b64_img in trace["chart_results"].items():
                st.caption(chart_name.replace("_", " ").title())
                st.image(base64.b64decode(b64_img))
            if summary_text:
                st.markdown(summary_text)

    st.session_state.messages.append({
        "role": "assistant",
        "content": combined if not is_lp_flow else f"LP optimization completed for: {', '.join(lp_items.keys())}",
        "summary": summary_text,
        "has_trace": True,
    })
    show_trace(trace)
    return combined


def render_pending_plan():
    plan = st.session_state.pending_plan or {}
    tasks = plan.get("tasks", [])

    lp_tasks    = [t for t in tasks if t.get("agent") == "lp_agent"]
    other_tasks = [t for t in tasks if t.get("agent") not in ("lp_agent", "chart_agent")]
    is_lp_only  = len(lp_tasks) > 0 and len(other_tasks) == 0

    if is_lp_only:
        # ── Lean LP approval UI — skip verbose work-order breakdown ──────────
        st.subheader("Procurement Optimization — Ready to Run")
        for t in lp_tasks:
            params = t.get("params") or {}
            prod   = (params.get("product") or "").replace("_", " ").title()
            lam    = params.get("lambda_risk", 0.5)
            share  = params.get("max_supplier_share", 1.0)
            div    = params.get("diversification_mode", "none")
            urg    = params.get("urgency", False)
            cap    = params.get("budget_cap")
            parts_lp = [f"**{prod}**  ·  λ = {lam}  ·  Max share: {share:.0%}"]
            if div != "none":
                parts_lp.append(f"  ·  Diversification: {div}")
            if urg:
                parts_lp.append("  ·  Urgency mode: on")
            if cap:
                parts_lp.append(f"  ·  Budget cap: ${cap:,.0f}")
            st.markdown("  ".join(parts_lp))
    else:
        # ── Standard verbose plan display for non-LP or mixed plans ─────────
        st.write("## Pending Plan")
        st.write(f"**Intent:** {plan.get('intent')}")
        if plan.get("question"):
            st.info(plan["question"])
        for i, task in enumerate(tasks):
            st.write(f"### Task {i+1}")
            st.write(f"- Agent: {task.get('agent')}")
            st.write(f"- Objective: {task.get('objective')}")
            st.write(f"- Context: {task.get('context')}")
            st.write(f"- Instructions: {task.get('instructions')}")

    st.text_input("Modify the plan (optional)", key="plan_feedback")
    if st.button("Approve Plan", key="approve_plan"):
        with st.spinner("Executing approved plan..."):
            feedback = st.session_state.plan_feedback.strip() or "ok"
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            final_state = stream_graph(Command(resume=feedback), config=config)
        # ── Check whether the LP agent raised an approval interrupt ────────
        lp_interrupt = final_state.get("__interrupt__")
        if lp_interrupt and lp_interrupt.get("type") == "lp_approval":
            st.session_state.waiting_for_lp_approval = True
            st.session_state.pending_lp_result = lp_interrupt
            st.session_state.lp_partial_state = final_state
            # Cache full raw dict for the "How was this decision made?" explanation.
            st.session_state.last_lp_raw_full = lp_interrupt.get("raw", {})
            st.session_state.saved_plan = plan
            st.session_state.waiting_for_approval = False
            st.session_state.pending_plan = None
            st.rerun()
        else:
            state = asyncio.run(graph.aget_state(config=config))
            next_plan = extract_plan(state)
            if state.next and next_plan:
                st.session_state.pending_plan = next_plan
                st.session_state.messages.append(
                    {"role": "assistant", "content": "Plan updated. Review the new work orders below."}
                )
                st.rerun()
            else:
                finalize_execution(final_state, fallback_plan=plan)
                st.session_state.waiting_for_approval = False
                st.session_state.pending_plan = None
                st.rerun()


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
    """
    cur_uf  = current_raw.get("urgency_feasibility") or {}
    prev_uf = prev_entry.get("urgency_feasibility") or {}

    # If neither run has urgency_feasibility, no coverage rows are possible.
    if not cur_uf and not prev_uf:
        return []

    rows: list[dict] = []

    # ── Earliest Replenishment Week ───────────────────────────────────────────
    # The first week the selected supplier pool can begin delivering.
    # Available in urgency_feasibility only when a shortfall exists.
    cur_min_wk  = cur_uf.get("min_selected_lead_weeks")
    prev_min_wk = prev_uf.get("min_selected_lead_weeks")
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

    # ── Immediate Uncovered Weeks ─────────────────────────────────────────────
    # Weeks where NO eligible supplier can deliver on time.
    # Current run has no shortfall (urgency_feasibility=None) → 0 uncovered.
    cur_uncov  = cur_uf.get("uncoverable_weeks", [])
    prev_uncov = prev_uf.get("uncoverable_weeks", [])
    # Only show if previous run had coverage data.
    if prev_uf:
        cur_uncov_n  = len(cur_uncov)
        prev_uncov_n = len(prev_uncov)
        cur_val      = str(cur_uncov_n) if cur_uncov_n > 0 else "None"
        prev_val     = str(prev_uncov_n) if prev_uncov_n > 0 else "None"
        diff         = cur_uncov_n - prev_uncov_n
        chg = (
            "No change" if diff == 0
            else ("Gap closed ✓" if cur_uncov_n == 0 and prev_uncov_n > 0
                  else f"{diff:+d} weeks")
        )
        rows.append({
            "Metric":            "Immediate Uncovered Weeks",
            "Previous Scenario": prev_val,
            "What-If Scenario":  cur_val,
            "Change":            chg,
        })

    # ── Weeks Now Covered ─────────────────────────────────────────────────────
    # Gap weeks that were present in the previous run but are gone in the current run.
    # "Covered" means: selected suppliers in the current run can reach them on time
    # (i.e., the week is no longer in gap_weeks at all).
    prev_gap = set(prev_uf.get("gap_weeks", []))
    cur_gap  = set(cur_uf.get("gap_weeks", []))
    newly_covered = sorted(prev_gap - cur_gap)
    # Only show this row when the previous run actually had gap weeks.
    if prev_gap:
        n_cov    = len(newly_covered)
        cur_val  = f"{n_cov} week(s)" if n_cov > 0 else "—"
        prev_val = "—"
        chg      = f"+{n_cov} covered" if n_cov > 0 else "No change"
        rows.append({
            "Metric":            "Weeks Now Covered by Selection",
            "Previous Scenario": prev_val,
            "What-If Scenario":  cur_val,
            "Change":            chg,
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
        d = cur - prev
        return "No change" if abs(d) < 0.01 else f"${d:+,.2f}"

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
            "Change":            _delta_currency(cur_avg_cost, prev_avg_cost),
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
    base_cost   = base.get("total_cost_usd") if base else None
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

        # Explicit uncovered forecast weeks for emergency bullet
        _gap_weeks = sorted({r["Forecast Week"] for r in _gap_rows}) if _gap_rows else []
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
        _uf_uncoverable= _uf.get("uncoverable_weeks", [])  # nobody in eligible pool can cover
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
            st.rerun()


def _render_executive_summary() -> None:
    """Render the final executive summary page (user-triggered only).

    This function is the single source of truth for the session-level summary.
    It is NEVER called automatically — only when the user clicks
    "Complete Procurement Plan".

    Sections:
        A  Procurement Overview
        B  Product-Level Summary Table
        C  Baseline Comparison
        D  Supply Coverage / Shortfall Summary
        E  Forward-Looking Note
        F  Final Narrative
    """
    import pandas as _pd

    approved = st.session_state.get("approved_lp_runs", [])
    if not approved:
        st.warning("No approved LP runs in this session. Approve at least one optimization first.")
        return

    st.title("Final Executive Summary")
    st.caption("Session-level procurement plan — approved recommendations only")
    st.divider()

    # ── Derived session-level metrics ─────────────────────────────────────────
    total_cost      = sum(r.get("total_cost") or 0.0 for r in approved)
    total_qty       = sum(r.get("allocated_qty") or 0 for r in approved)
    total_baseline  = sum(r.get("baseline_cost") or 0.0 for r in approved)
    avg_lambda      = (
        sum(r.get("lambda_risk", 0.5) for r in approved) / len(approved)
        if approved else 0.5
    )
    if avg_lambda == 0.0:
        risk_profile_label = "Cost-only (no risk weighting)"
    elif avg_lambda <= 0.25:
        risk_profile_label = f"Cost-focused (avg λ = {avg_lambda:.2f})"
    elif avg_lambda <= 0.5:
        risk_profile_label = f"Balanced (avg λ = {avg_lambda:.2f})"
    elif avg_lambda <= 1.0:
        risk_profile_label = f"Risk-averse (avg λ = {avg_lambda:.2f})"
    else:
        risk_profile_label = f"Risk-priority (avg λ = {avg_lambda:.2f})"

    approved_product_names = [
        r.get("product", "unknown").replace("_", " ").title() for r in approved
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # A. Procurement Overview
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("A  Procurement Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Products Procured", len(approved))
    col2.metric("Total Units", f"{total_qty:,}")
    col3.metric("Total Estimated Cost", f"${total_cost:,.2f}")
    col4.metric("Avg Risk Profile", risk_profile_label)

    st.markdown(
        f"**Products successfully procured:** {', '.join(approved_product_names)}"
    )
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # B. Product-Level Summary Table
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("B  Product-Level Summary")
    _rows_b = []
    for r in approved:
        product_label = r.get("product", "unknown").replace("_", " ").title()
        alloc = r.get("allocation") or []
        supplier_names = [
            a.get("supplier_name") or a.get("supplier_id", "?") for a in alloc
        ]
        countries = r.get("countries") or []
        div_mode  = r.get("diversification_mode", "none")
        div_label = (
            "Country-diversified" if div_mode == "country_diversified"
            else "Share-capped" if div_mode == "supplier_share_only"
            else "None"
        )
        _rows_b.append({
            "Product":          product_label,
            "Units":            f"{r.get('allocated_qty') or 0:,}",
            "Cost (USD)":       f"${r.get('total_cost') or 0.0:,.2f}",
            "Suppliers":        ", ".join(supplier_names) if supplier_names else "—",
            "# Suppliers":      r.get("n_suppliers", 0),
            "Countries":        ", ".join(countries) if countries else "—",
            "Risk (λ)":         r.get("lambda_risk", 0.5),
            "Diversification":  div_label,
        })
    st.dataframe(
        _pd.DataFrame(_rows_b),
        use_container_width=True,
        hide_index=True,
    )
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # C. Baseline Comparison
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("C  Baseline Comparison")
    st.caption(
        "Each approved plan is compared to the cheapest feasible unconstrained plan "
        "(λ = 0, no diversification, max share = 100%) for the same demand level."
    )

    _rows_c = []
    for r in approved:
        product_label = r.get("product", "unknown").replace("_", " ").title()
        cost      = r.get("total_cost") or 0.0
        b_cost    = r.get("baseline_cost")
        b_n_sup   = r.get("baseline_n_suppliers", 0)
        b_n_ctry  = r.get("baseline_country_count", 0)
        n_sup     = r.get("n_suppliers", 0)
        countries = r.get("countries") or []

        if b_cost and b_cost > 0:
            delta_abs = cost - b_cost
            delta_pct = (delta_abs / b_cost) * 100
            if abs(delta_pct) <= 1.0:
                classification = "Negligible"
            elif abs(delta_pct) <= 10.0:
                classification = "Modest"
            else:
                classification = "Material"
            delta_str = f"+${delta_abs:,.2f}" if delta_abs >= 0 else f"-${abs(delta_abs):,.2f}"
            pct_str   = f"+{delta_pct:.1f}%" if delta_pct >= 0 else f"{delta_pct:.1f}%"
            sup_delta = n_sup - b_n_sup
            ctry_delta = len(countries) - b_n_ctry
        else:
            delta_str = "N/A"
            pct_str   = "N/A"
            classification = "N/A"
            sup_delta = "N/A"
            ctry_delta = "N/A"

        _rows_c.append({
            "Product":           product_label,
            "Approved Cost":     f"${cost:,.2f}",
            "Baseline Cost":     f"${b_cost:,.2f}" if b_cost else "N/A",
            "Cost Delta":        delta_str,
            "Delta %":           pct_str,
            "Premium Class":     classification,
            "Supplier Δ vs Base": f"+{sup_delta}" if isinstance(sup_delta, int) and sup_delta >= 0 else str(sup_delta),
            "Country Δ vs Base":  f"+{ctry_delta}" if isinstance(ctry_delta, int) and ctry_delta >= 0 else str(ctry_delta),
        })
    st.dataframe(
        _pd.DataFrame(_rows_c),
        use_container_width=True,
        hide_index=True,
    )

    if total_baseline > 0:
        session_delta_abs = total_cost - total_baseline
        session_delta_pct = (session_delta_abs / total_baseline) * 100
        if abs(session_delta_pct) <= 1.0:
            session_class = "negligible"
        elif abs(session_delta_pct) <= 10.0:
            session_class = "modest"
        else:
            session_class = "material"
        direction = "above" if session_delta_abs >= 0 else "below"
        st.info(
            f"**Session total risk/diversification premium:** "
            f"${abs(session_delta_abs):,.2f} ({abs(session_delta_pct):.1f}% {direction} "
            f"the cost-only baseline) — **{session_class}**"
        )
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # D. Supply Coverage / Shortfall Summary
    # ─────────────────────────────────────────────────────────────────────────
    # Classification uses the same logic as the urgency section in _render_lp_result():
    #   earliest_replenishment_week = max(1, round(min_selected_lead_time_days / 7))
    # Rows with Forecast Week < earliest → NOT COVERED (true immediate risk)
    # Rows with Forecast Week >= earliest → COVERED (expected supplier fulfillment)
    # Source rows: query_triggered_rows_structured() — net_requirement > 0 only.
    st.subheader("D  Supply Coverage & Shortfall Summary")
    try:
        from tools.pipeline_queries import (
            query_triggered_rows_structured as _qtr,
            query_supplier_lead_times as _qlt,
        )
        _trig_data = _qtr()
        _trig_rows = _trig_data.get("rows", [])

        # Step 1 — Build coverage map: product → earliest_replenishment_week
        # Uses selected supplier IDs stored in the approved run's allocation list.
        _coverage_map: dict[str, int | None] = {}
        for _apr in approved:
            _prd = _apr.get("product", "")
            _sel_ids = [
                a.get("supplier_id", "")
                for a in (_apr.get("allocation") or [])
                if a.get("supplier_id")
            ]
            if _sel_ids:
                try:
                    _lt_map = _qlt(_prd, _sel_ids)
                    if _lt_map:
                        _min_days = min(_lt_map.values())
                        _coverage_map[_prd] = max(1, round(_min_days / 7.0))
                    else:
                        _coverage_map[_prd] = None  # conservative: unknown → all uncovered
                except Exception:
                    _coverage_map[_prd] = None
            else:
                _coverage_map[_prd] = None

        approved_products_keys = [r.get("product", "") for r in approved]

        # Step 2 — Filter to approved products and classify each row
        _not_covered: list[dict] = []
        _covered:     list[dict] = []

        def _build_section_d_row(row: dict, cum_press: float) -> dict:
            _ss   = row.get("Safety Stock Reserve", 0)
            _need = row.get("Procurement Need", 0)
            # SS Utilization = (Cumulative Procurement Pressure / Safety Stock) × 100
            # Same formula as urgency section — true value, no cap.
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

        # Accumulate cumulative procurement pressure per (component, facility) — separate
        # accumulators for uncovered and covered tracks to reflect their distinct windows.
        _cum_nc: dict[tuple, float] = {}
        _cum_cv: dict[tuple, float] = {}

        for row in sorted(
            (r for r in _trig_rows if r.get("Component", "") in approved_products_keys),
            key=lambda x: x.get("Forecast Week", 0),
        ):
            _prod = row.get("Component", "")
            _earliest = _coverage_map.get(_prod)
            _fw = row.get("Forecast Week", 0)
            _fc = (_prod, row.get("Facility", ""))
            _need = row.get("Procurement Need", 0)

            if _earliest is None or _fw < _earliest:
                # NOT COVERED — true immediate risk
                _cum_nc[_fc] = _cum_nc.get(_fc, 0.0) + _need
                _not_covered.append(_build_section_d_row(row, _cum_nc[_fc]))
            else:
                # COVERED — expected to be fulfilled by selected supplier replenishment
                _cum_cv[_fc] = _cum_cv.get(_fc, 0.0) + _need
                _covered.append(_build_section_d_row(row, _cum_cv[_fc]))

        # Step 3 — Render Table A: Uncovered Shortfall
        st.markdown("##### Uncovered Shortfall — Immediate Procurement Risk")
        if _not_covered:
            st.error(
                f"**{len(_not_covered)} trigger row(s)** fall before selected suppliers are "
                f"expected to begin replenishing inventory. "
                f"Emergency or spot sourcing is required for these windows."
            )
            st.dataframe(
                _pd.DataFrame(_not_covered),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success(
                "No uncovered shortfall rows identified. All triggered procurement windows "
                "fall within or after selected-supplier replenishment timing."
            )

        # Step 4 — Render Table B: Covered Demand
        st.markdown("##### Covered Demand — Expected to be Fulfilled by Selected Suppliers")
        if _covered:
            st.info(
                f"**{len(_covered)} trigger row(s)** fall at or after the expected "
                f"selected-supplier replenishment window. These weeks are expected to be "
                f"covered by orders placed in the approved plan."
            )
            st.dataframe(
                _pd.DataFrame(_covered),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No covered-demand rows found for approved products in the trigger view.")

        # Step 5 — Coverage week summary per product
        if _coverage_map:
            _cov_summary = []
            for _prd, _ew in _coverage_map.items():
                _ew_label = f"Week {_ew}" if _ew is not None else "Unknown (lead time unavailable)"
                _cov_summary.append({
                    "Product": _prd.replace("_", " ").title(),
                    "Earliest Supplier Replenishment": _ew_label,
                })
            st.caption("**Coverage reference — earliest_replenishment_week per product:**")
            st.dataframe(_pd.DataFrame(_cov_summary), use_container_width=True, hide_index=True)

    except Exception as _e:
        st.info(f"Supply coverage data unavailable: {_e}")
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # E. Forward-Looking Note
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("E  Forward-Looking Note")
    _fwd_products = ", ".join(approved_product_names)
    st.markdown(
        f"- **Coverage:** The approved plan covers the current planning horizon "
        f"for **{_fwd_products}**.\n"
        f"- **Lead times:** Supplier lead times were embedded in the LP objective, "
        f"ensuring orders placed now arrive within the urgency window.\n"
        f"- **Next cycle:** Demand beyond the current planning horizon should be "
        f"re-evaluated using updated forecasts and refreshed inventory positions.\n"
        f"- **Constraints:** Any active diversification constraints (country-diversified "
        f"or share-capped) should be carried forward to subsequent planning runs."
    )
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # F. Final Narrative
    # ─────────────────────────────────────────────────────────────────────────
    st.subheader("F  Executive Assessment")

    # Build constraint summary
    _constraint_parts = []
    _div_counts = {}
    for r in approved:
        dm = r.get("diversification_mode", "none")
        _div_counts[dm] = _div_counts.get(dm, 0) + 1
    if _div_counts.get("country_diversified"):
        _constraint_parts.append(
            f"country-level diversification enforced on "
            f"{_div_counts['country_diversified']} product(s)"
        )
    if _div_counts.get("supplier_share_only"):
        _constraint_parts.append(
            f"supplier share caps applied on "
            f"{_div_counts['supplier_share_only']} product(s)"
        )
    _urgency_runs = [r for r in approved if r.get("urgency")]
    if _urgency_runs:
        _constraint_parts.append(f"urgency mode active on {len(_urgency_runs)} product(s)")

    # What was done
    st.markdown(
        f"- **What was done:** Procurement plans approved for "
        f"**{len(approved)} product(s)** ({', '.join(approved_product_names)}) — "
        f"**{total_qty:,} units** at an estimated cost of **${total_cost:,.2f}**."
    )

    # Why it is optimal
    _opt_reason = (
        "the optimizer minimized cost across compliant suppliers with no additional weighting"
        if avg_lambda == 0.0
        else f"cost and supplier risk were jointly minimized (avg λ = {avg_lambda:.2f}), "
             f"favoring a more stable supplier mix over the cheapest available options"
    )
    st.markdown(f"- **Why it is optimal:** Under the configured constraints, {_opt_reason}.")

    # Tradeoffs
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
                "driven by diversification and risk constraints; justifiable as insurance against concentration risk"
            )
    if _tradeoff_parts:
        st.markdown(f"- **Tradeoffs:** {'; '.join(_tradeoff_parts)}.")
    else:
        st.markdown("- **Tradeoffs:** No significant cost-risk tradeoffs identified for this session.")

    # Risks remaining
    st.markdown(
        "- **Risks remaining:** Lead-time exposure in high-urgency weeks, "
        "potential country concentration, and supplier-level disruption risk "
        "should be monitored through the next planning cycle."
    )

    st.divider()
    if st.button("← Back to Procurement Agent", key="exit_exec_summary_btn"):
        st.session_state.show_executive_summary = False
        st.rerun()


def render_lp_approval():
    """Show LP results and present Approve / Modify / Discard actions to the user.

    Three distinct actions:
      Approve  — stores the run in approved_lp_runs; included in session summary.
      Modify   — sets lp_modify_mode=True and snapshots current result as the
                 what-if baseline; exposes a chat input so the user can describe
                 a refinement (e.g. "exclude SUP_HKG_38", "expedite this component").
                 The next message re-runs LP on the direct fast path and replaces the
                 pending result.  Does NOT add the current run to approved_lp_runs.
      Discard  — clears the pending result and all modify state.  The run is never
                 stored and cannot be used as a what-if comparison baseline.
    """
    lp_interrupt = st.session_state.pending_lp_result or {}
    raw          = lp_interrupt.get("raw", {})
    partial      = st.session_state.get("lp_partial_state") or {}
    is_direct    = lp_interrupt.get("direct_mode", False)
    in_modify    = st.session_state.get("lp_modify_mode", False)

    # ── Heading ───────────────────────────────────────────────────────────────
    if in_modify:
        st.subheader("LP Optimization Results — Modify Mode")
        st.info(
            "✏️ **Modify mode active.** Describe your change in the input below "
            "and the scenario will rerun immediately. "
            "Click **Approve** when you are satisfied, or **Discard** to cancel."
        )
    else:
        st.subheader("LP Optimization Results — Pending Your Approval")

    _pending_labels = [
        k.replace("lp_", "").replace("_", " ").title() for k in raw.keys()
    ]
    _render_procurement_status_bar(pending_products=_pending_labels)

    # ── LP result content — one block per product ──────────────────────────────
    for product_key, result_dict in raw.items():
        product_label = product_key.replace("lp_", "").replace("_", " ").title()
        st.markdown(f"### {product_label}")
        _render_lp_result(result_dict)

    # ── Action buttons — Approve | Modify | Discard ───────────────────────────
    st.divider()
    if not in_modify:
        st.info(
            "Review the optimization results above. "
            "**Approve** to include in the session plan, "
            "**Modify** to refine and rerun, or **Discard** to exclude."
        )
    col1, col2, col3 = st.columns(3)

    # ── Approve ───────────────────────────────────────────────────────────────
    with col1:
        if st.button("✅ Approve Recommendation", key="approve_lp_btn"):
            for result_dict in raw.values():
                _store_approved_run(result_dict)

            if is_direct:
                _approved_products = [
                    k.replace("lp_", "").replace("_", " ").title() for k in raw
                ]
                st.session_state.messages.append({
                    "role":      "assistant",
                    "content":   f"Procurement plan for **{', '.join(_approved_products)}** approved and added to session.",
                    "has_trace": False,
                    "summary":   "",
                })
            else:
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                with st.spinner("Finalizing recommendation..."):
                    second_state = stream_graph(Command(resume="approve"), config=config)
                merged = _merge_final_states(partial, second_state)
                finalize_execution(merged, fallback_plan=st.session_state.get("saved_plan", {}))

            st.session_state.waiting_for_lp_approval = False
            st.session_state.pending_lp_result       = None
            st.session_state.lp_partial_state        = {}
            st.session_state.saved_plan              = {}
            st.session_state.lp_modify_mode          = False
            st.session_state.lp_modify_baseline      = {}
            st.rerun()

    # ── Modify ────────────────────────────────────────────────────────────────
    with col2:
        if st.button("✏️ Modify Recommendation", key="modify_lp_btn"):
            # Snapshot the CURRENT pending result as the what-if comparison baseline
            # so the next rerun's What-If Scenario Impact table diffs against THIS run.
            if "lp_modify_baseline" not in st.session_state:
                st.session_state.lp_modify_baseline = {}
            for result_dict in raw.values():
                entry   = _build_run_entry(result_dict)
                product = entry["product"]
                st.session_state.lp_modify_baseline[product] = entry

            st.session_state.lp_modify_mode = True
            st.rerun()

    # ── Discard ───────────────────────────────────────────────────────────────
    with col3:
        if st.button("❌ Discard", key="discard_lp_btn"):
            if not is_direct:
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                with st.spinner("Discarding..."):
                    second_state = stream_graph(Command(resume="discard"), config=config)
                merged = _merge_final_states(partial, second_state)
                finalize_execution(merged, fallback_plan=st.session_state.get("saved_plan", {}))
            st.session_state.waiting_for_lp_approval = False
            st.session_state.pending_lp_result       = None
            st.session_state.lp_partial_state        = {}
            st.session_state.saved_plan              = {}
            st.session_state.lp_modify_mode          = False
            st.session_state.lp_modify_baseline      = {}
            st.rerun()

    # ── Modify-mode chat input ────────────────────────────────────────────────
    # Only shown after user has clicked Modify.  Routes directly to _run_lp_direct()
    # using the displayed params as the base — no orchestrator or plan-approval page.
    if in_modify:
        st.divider()
        _modify_prompt = st.chat_input(
            "Describe your modification (e.g. 'exclude SUP_HKG_38', 'expedite this', 'diversify across countries')…",
            key="lp_modify_chat_input",
        )
        if _modify_prompt:
            # Resolve base params from the currently displayed pending result.
            # Use the first (and usually only) product in the pending raw payload.
            _base_params: dict = {}
            for _rv in raw.values():
                _base_params = dict(_rv.get("params_recap") or {})
                break

            if _base_params:
                _merged = _apply_modify_overrides(_modify_prompt, _base_params)
                # Record the modify message in chat history for replay.
                st.session_state.messages.append({
                    "role":      "user",
                    "content":   _modify_prompt,
                    "has_trace": False,
                })
                with st.spinner("Rerunning optimization…"):
                    _run_lp_direct(_merged)
                # _run_lp_direct() calls st.rerun() — unreachable below.


# ── Main rendering logic ───────────────────────────────────────────────────────

# Show demand verification banner while awaiting first-turn confirmation.
# Only fires after the kickoff response has been rendered — not before.
if st.session_state.historical_demand_verification_pending:
    _render_demand_verification_banner()

# ── Executive summary page — exclusive view, user-triggered only ───────────────
if st.session_state.get("show_executive_summary"):
    _render_executive_summary()

elif st.session_state.waiting_for_lp_approval and st.session_state.pending_lp_result:
    render_lp_approval()

elif st.session_state.waiting_for_approval and st.session_state.pending_plan:
    render_pending_plan()

elif not st.session_state.waiting_for_approval and not st.session_state.waiting_for_lp_approval:
    # ── Persistent procurement status bar — visible between LP runs ───────────
    # Shown whenever the user has approved at least one LP run and is back in
    # the normal chat view.  This is the persistent "Complete" entry point.
    _render_procurement_status_bar()
    prompt = st.chat_input("Ask about suppliers...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # ── Session summary shortcut — bypass graph entirely ───────────────
        if any(t in prompt.lower() for t in _SUMMARY_TRIGGERS):
            summary = _format_session_summary(st.session_state.get("approved_lp_runs", []))
            with st.chat_message("assistant"):
                st.markdown(summary)
            st.session_state.messages.append({
                "role": "assistant",
                "content": summary,
                "has_trace": False,
                "summary": "",
            })
            st.rerun()

        # ── Opening kickoff: first-turn planning + cost + risk objective ───
        elif _is_first_user_turn() and _is_opening_kickoff(prompt):
            st.session_state.historical_demand_verification_pending = True
            _render_kickoff_response()
            st.rerun()

        # ── Proceed after demand verification ──────────────────────────────
        elif st.session_state.historical_demand_verification_pending and _is_proceed_response(prompt):
            st.session_state.historical_demand_verification_pending = False
            # Direct fast path — bypasses orchestrator AND synthesizer entirely.
            # query_forecast_summary() reads pre-computed DB tables; no LLM involved.
            # Saves ~12–15s of orchestrator + synthesizer round-trip latency.
            with st.spinner("Retrieving forecast summary..."):
                from tools.pipeline_queries import query_forecast_summary
                forecast_result = query_forecast_summary()
                forecast_text = forecast_result.get("content", "")
            combined = (
                f"{_KICKOFF_TRANSITION_SENTENCE}\n\n"
                f"---\n\n"
                f"**📊 Production Demand Forecast**\n\n"
                f"```\n{forecast_text}\n```"
            )
            with st.chat_message("assistant"):
                st.markdown(_KICKOFF_TRANSITION_SENTENCE)
                st.divider()
                st.subheader("📊 Production Demand Forecast")
                st.code(forecast_text)
            st.session_state.messages.append({
                "role": "assistant",
                "content": combined,
                "has_trace": False,
                "summary": "",
            })
            st.rerun()

        # ── Fast all-facilities forecast comparison ────────────────────────
        # Must precede _forecast_assessment_direction: queries like
        # "Compare forecast demand across all facilities" contain 'compar' which
        # matches _FORECAST_BASELINE_SIGNALS. Checking all-facilities signals first
        # prevents misrouting to the model-baseline assessment route.
        elif _is_all_facilities_forecast(prompt):
            import matplotlib.pyplot as plt
            with st.spinner("Retrieving forecast data..."):
                from tools.pipeline_queries import (
                    get_forecast_drilldown_df,
                    _plot_all_facilities_forecast,
                    _narrative_all_facilities,
                )
                df = get_forecast_drilldown_df()
            transition = (
                "Here is the forecasted demand trend across all four "
                "facilities over the planning horizon."
            )
            narrative = _narrative_all_facilities(df)
            fig = _plot_all_facilities_forecast(df)
            chart_b64 = _fig_to_b64(fig)
            plt.close(fig)
            with st.chat_message("assistant"):
                st.markdown(transition)
                st.divider()
                st.subheader("📊 Forecast — All Facilities")
                st.image(base64.b64decode(chart_b64))
                st.markdown(narrative)
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"{transition}\n\n{narrative}",
                "has_trace": False,
                "summary": "",
                "chart_b64": chart_b64,
            })
            st.rerun()

        # ── Fast forecast model assessment ────────────────────────────────
        elif _forecast_assessment_direction(prompt) is not None:
            direction = _forecast_assessment_direction(prompt)
            transition, label = _FORECAST_ASSESS_META[direction]
            with st.spinner("Retrieving forecast model assessment..."):
                from tools.pipeline_queries import query_forecast_model_assessment
                result = query_forecast_model_assessment(direction=direction)
                result_text = result.get("content", "")
                artifact_path = result.get("artifact_path", "")
            # Read artifact PNG → base64 so the replay loop can redisplay it
            # after st.rerun() clears the current render (same pattern as drill-down).
            chart_b64 = ""
            if artifact_path:
                abs_path = os.path.join(_ARTIFACTS_BASE, artifact_path)
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as _f:
                        chart_b64 = base64.b64encode(_f.read()).decode()
            with st.chat_message("assistant"):
                st.subheader(label)
                if chart_b64:
                    st.image(base64.b64decode(chart_b64))
                st.markdown(result_text)
            combined = f"**{label}**\n\n{result_text}"
            st.session_state.messages.append({
                "role": "assistant",
                "content": combined,
                "has_trace": False,
                "summary": "",
                "chart_b64": chart_b64,
                "chart_first": True,  # replay loop renders image before text content
            })
            st.rerun()

        # ── Fast forecast drill-down (Cases A / B / C) ────────────────────
        elif _is_forecast_drilldown_request(prompt):
            import matplotlib.pyplot as plt
            t_low = prompt.lower()
            is_all = any(s in t_low for s in _FORECAST_ALL_FACILITIES_SIGNALS)
            facility_id = _extract_facility_id(prompt)

            with st.spinner("Retrieving forecast data..."):
                from tools.pipeline_queries import (
                    get_forecast_drilldown_df,
                    _plot_all_facilities_forecast,
                    _narrative_all_facilities,
                )
                df = get_forecast_drilldown_df()

            if is_all:
                # ── Case C: all-facilities trend chart ─────────────────────
                # Render fig → base64 before rerun so replay loop can redisplay it.
                transition = (
                    "Here is the forecasted demand trend across all four "
                    "facilities over the planning horizon."
                )
                narrative = _narrative_all_facilities(df)
                fig = _plot_all_facilities_forecast(df)
                chart_b64 = _fig_to_b64(fig)
                plt.close(fig)
                with st.chat_message("assistant"):
                    st.markdown(transition)
                    st.divider()
                    st.subheader("📊 Forecast — All Facilities")
                    st.image(base64.b64decode(chart_b64))
                    st.markdown(narrative)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"{transition}\n\n{narrative}",
                    "has_trace": False,
                    "summary": "",
                    "chart_b64": chart_b64,
                })

            elif facility_id:
                # ── Case B: single-facility faceted SKU chart (6×2) ─────────
                # Uses business-facing label ("Facility 1" not "FACILITY_1").
                # Bullets above the chart; chart rendered in a scrollable
                # container so the summary stays pinned at the top.
                # Figure → base64 before rerun so replay loop can redisplay it.
                fac_label  = _format_facility_label(facility_id)
                transition = (
                    f"Here is the production demand forecast for **{fac_label}** "
                    f"across each semiconductor SKU over the planning horizon."
                )
                bullets    = _narrative_facility_bullets(df, facility_id)
                fig        = _plot_facility_faceted(df, facility_id)
                chart_b64  = _fig_to_b64(fig)
                plt.close(fig)
                # Scrollable chart HTML — browser-native overflow so only the
                # chart area scrolls; intro + bullets stay fixed above it.
                _scroll_html = (
                    f'<div style="height:640px;overflow-y:auto;'
                    f'border:1px solid #e6e9ef;border-radius:6px;padding:4px;">'
                    f'<img src="data:image/png;base64,{chart_b64}"'
                    f' style="width:100%;display:block;" /></div>'
                )
                with st.chat_message("assistant"):
                    st.markdown(transition)       # fixed above scroll region
                    st.markdown(bullets)          # fixed above scroll region
                    st.divider()
                    st.subheader(f"📊 Forecast — {fac_label} by SKU")
                    st.markdown(_scroll_html, unsafe_allow_html=True)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"{transition}\n\n{bullets}",
                    "has_trace": False,
                    "summary": "",
                    "chart_b64": chart_b64,
                    "chart_scroll": True,  # tells replay loop to use scrollable div
                })

            else:
                # ── Case A: full tabular drill-down ─────────────────────────
                # Store display_df in fast_path_dfs so replay loop can re-render
                # the dataframe widget after st.rerun() clears the current render.
                transition = (
                    "Here is the detailed production forecast by week, "
                    "facility, and semiconductor SKU."
                )
                display_df = df[[
                    "target_week_date", "facility_id", "semiconductor_id",
                    "predicted_demand", "interval_lower_90", "interval_upper_90",
                    "horizon_weeks",
                ]].rename(columns={
                    "target_week_date": "Week",
                    "facility_id": "Facility",
                    "semiconductor_id": "SKU",
                    "predicted_demand": "Forecast",
                    "interval_lower_90": "Lower 90%",
                    "interval_upper_90": "Upper 90%",
                    "horizon_weeks": "Horizon Wk",
                })
                df_idx = len(st.session_state.fast_path_dfs)
                st.session_state.fast_path_dfs.append(display_df)
                _fmt = {"Forecast": "{:,.0f}", "Lower 90%": "{:,.0f}", "Upper 90%": "{:,.0f}"}
                with st.chat_message("assistant"):
                    st.markdown(transition)
                    st.divider()
                    st.subheader("📊 Forecast Drill-Down")
                    st.dataframe(
                        display_df.style.format(_fmt),
                        use_container_width=True,
                    )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": (
                        f"{transition}\n\n"
                        f"*(Showing {len(display_df):,} rows — "
                        f"{df['facility_id'].nunique()} facilities × "
                        f"{df['semiconductor_id'].nunique()} SKUs × "
                        f"{df['target_week_date'].nunique()} weeks)*"
                    ),
                    "has_trace": False,
                    "summary": "",
                    "df_index": df_idx,
                })
            st.rerun()

        # ── BOM translation explainability — SKU demand → component demand ──
        # Checked BEFORE component requirements: queries like "...translated into
        # component demand" contain "component demand" which would otherwise match
        # the component-requirements route first and shadow this route entirely.
        elif _is_bom_translation_request(prompt):
            with st.spinner("Building BOM translation view..."):
                from tools.pipeline_queries import query_bom_translation_explainer
                result = query_bom_translation_explainer()

            import pandas as pd
            _rows = result.get("rows", [])
            df_bom = pd.DataFrame(_rows)

            _BOM_EXEC_NOTE = (
                "- This step shows what components are required to build the products "
                "our customers are expecting.\n"
                "- Every finished unit requires a specific mix of inputs — the BOM "
                "defines how many units of each component are needed per SKU.\n"
                "- Multiplying that recipe by the forecasted demand yields the gross "
                "component requirements shown below.\n"
                "- These totals are calculated before any inventory has been considered."
            )
            with st.chat_message("assistant"):
                st.subheader("BOM Translation — How Finished Demand Becomes Component Demand")
                st.caption(
                    "How each finished SKU's forecasted demand converts to gross "
                    "component demand across all facilities and forecast weeks"
                )
                if not df_bom.empty:
                    st.dataframe(
                        df_bom.style.format({
                            "Units / SKU":            "{:,.2f}",
                            "Forecast (units)":       "{:,.0f}",
                            "Gross Component Demand": "{:,.0f}",
                        }),
                        height=420,
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown(_BOM_EXEC_NOTE)
            st.session_state.messages.append({
                "role":        "assistant",
                "content":     (
                    "**BOM Translation — How Finished Demand Becomes Component Demand**\n\n"
                    + _BOM_EXEC_NOTE
                ),
                "has_trace":   False,
                "summary":     "",
                "bom_xlate_df": _rows,
            })
            st.rerun()

        # ── Component requirements — gross BOM demand (no inventory netting) ─
        # NOTE: _is_component_requirements_request() contains an LP-priority guard.
        # If the query has LP allocation intent, it returns False and LP routing wins.
        elif _is_component_requirements_request(prompt):
            logger.debug("[ROUTE ARBITRATION] route_chosen=bom_component_req | lp_intent=False")
            with st.spinner("Retrieving component requirements..."):
                data = _fetch_component_req_data()

            import pandas as pd
            df_window = pd.DataFrame([{
                "Forecast Start":  data["start_date"],
                "Forecast End":    data["end_date"],
                "Horizon Weeks":   data["n_weeks"],
                "Forecast Run ID": data["run_id"],
            }])
            df_scope = pd.DataFrame([{
                "Facilities":      data["n_facilities"],
                "Component Types": data["n_components"],
                "Aggregation":     (
                    f"All {data['n_facilities']} facilities "
                    f"\u00d7 {data['n_weeks']} forecast weeks"
                ),
            }])
            _comp_data = list(data["rows"])
            _total = sum(v for _, v in _comp_data)
            _comp_data.append(("TOTAL", _total))
            df_components = pd.DataFrame(_comp_data, columns=["Component", "Units Required"])

            _EXEC_NOTE = (
                "These totals represent BOM-implied component demand required to "
                "fulfill the finished-goods forecast across the planning horizon. "
                "Each finished unit consumes a defined mix of components, aggregated "
                "here across all facilities and forecast weeks. "
                "Inventory has not yet been netted out."
            )
            _dfs_payload = [
                {"caption": "Planning Window",
                 "records": df_window.to_dict("records")},
                {"caption": "Aggregation Scope",
                 "records": df_scope.to_dict("records")},
                {"caption": "Full-Horizon Gross Requirement by Component",
                 "records": df_components.to_dict("records")},
            ]
            with st.chat_message("assistant"):
                st.subheader("Component Requirements — Full Horizon Gross Demand")
                st.caption("Planning Window")
                st.dataframe(df_window, use_container_width=True, hide_index=True)
                st.caption("Aggregation Scope")
                st.dataframe(df_scope, use_container_width=True, hide_index=True)
                st.caption("Full-Horizon Gross Requirement by Component")
                st.dataframe(
                    df_components.style.format({"Units Required": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                )
                st.markdown(_EXEC_NOTE)
            st.session_state.messages.append({
                "role":         "assistant",
                "content":      (
                    "**Component Requirements — Full Horizon Gross Demand**\n\n"
                    + _EXEC_NOTE
                ),
                "has_trace":    False,
                "summary":      "",
                "comp_req_dfs": _dfs_payload,
            })
            st.rerun()

        # ── Inventory-adjusted procurement requirement summary ─────────────
        # Direct fast-path — no orchestrator. Aligned to README "start here"
        # entry point (format_procurement_recommendation / aggregated need).
        elif _is_procurement_summary_request(prompt):
            with st.spinner("Computing inventory-adjusted procurement requirement..."):
                from tools.pipeline_queries import query_procurement_summary_data
                data = query_procurement_summary_data()

            import pandas as pd
            _proc_rows = data.get("rows", [])
            df_proc = pd.DataFrame(_proc_rows)

            # Rename columns for calculation-flow clarity (sign convention in label)
            df_proc = df_proc.rename(columns={
                "Starting On-Hand":              "Starting On-Hand (\u2212)",
                "Safety Stock Reserve (\u2212)": "Safety Stock Reserve (+)",
            })
            # Reorder left → right as a calculation: Gross − OnHand + SR − BO + SS = Net
            df_proc = df_proc[[
                "Component",
                "Gross Component Demand",
                "Starting On-Hand (\u2212)",
                "Scheduled Receipts (+)",
                "Backorders (\u2212)",
                "Safety Stock Reserve (+)",
                "Net Procurement Requirement",
            ]]
            _PROC_FMT = {c: "{:,.0f}" for c in df_proc.columns if c != "Component"}
            # Store renamed records so replay renders identical columns
            _proc_display_rows = df_proc.to_dict("records")

            _PROC_BULLETS = (
                "- **This table starts from the current inventory position — "
                "Starting On-Hand — at the beginning of the planning horizon.**\n"
                "- **Gross Component Demand** represents total required component "
                "volume based on forecasted production.\n"
                "- **Starting On-Hand**, **Scheduled Receipts**, and **Backorders** "
                "adjust available inventory over the planning horizon.\n"
                "- **Safety Stock Reserve** represents required buffer inventory to "
                "maintain the target service level and must be procured if not "
                "already available.\n"
                "- **Net Procurement Requirement** is the remaining quantity that "
                "must be ordered after accounting for all inventory and policy "
                "constraints."
            )
            _DATA_DICT = {
                "Gross Component Demand": (
                    "Total BOM-implied component volume required to fulfill the "
                    "finished-goods forecast across all facilities and the full "
                    "planning horizon."
                ),
                "Starting On-Hand (\u2212)": (
                    "Total component stock physically on hand at the start of the "
                    "planning horizon, summed across all facilities."
                ),
                "Scheduled Receipts (+)": (
                    "The firm currently assumes no scheduled receipts are due "
                    "within this planning snapshot."
                ),
                "Backorders (\u2212)": (
                    "Backorders are currently zero in this planning view."
                ),
                "Safety Stock Reserve (+)": (
                    "The minimum inventory buffer required to meet the 95% service "
                    "level target. This reserve must be available at all times and "
                    "is added to the procurement requirement if not already covered "
                    "by on-hand stock."
                ),
                "Net Procurement Requirement": (
                    "The quantity that must be procured. Calculated per facility as: "
                    "max(0, Gross Demand \u2212 On-Hand + Scheduled Receipts "
                    "\u2212 Backorders + Safety Stock Reserve), "
                    "then summed across all facilities."
                ),
            }

            with st.chat_message("assistant"):
                st.subheader("Net Component Procurement Requirement — Planning Horizon")
                st.caption(
                    f"Horizon: {data['horizon_start']} \u2192 {data['horizon_end']}"
                    f"  \u00b7  {data['n_weeks']} weeks"
                    f"  \u00b7  Forecast run {data['run_id']}"
                )
                st.caption("All values are aggregated across the full planning horizon.")
                if not df_proc.empty:
                    st.dataframe(
                        df_proc.style.format(_PROC_FMT),
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown(_PROC_BULLETS)
                with st.expander("Click to view data dictionary"):
                    for col, desc in _DATA_DICT.items():
                        st.markdown(f"**{col}:** {desc}")
            st.session_state.messages.append({
                "role":           "assistant",
                "content":        (
                    "**Net Component Procurement Requirement — Planning Horizon**\n\n"
                    f"Horizon: {data['horizon_start']} \u2192 {data['horizon_end']}"
                    f" ({data['n_weeks']} weeks)\n\n"
                    "All values are aggregated across the full planning horizon.\n\n"
                    + _PROC_BULLETS
                ),
                "has_trace":      False,
                "summary":        "",
                "proc_summary_df": _proc_display_rows,
            })
            st.rerun()

        # ── Safety stock / inventory policy explainability ────────────────
        elif _is_ss_policy_request(prompt):
            _SS_FORMULA = (
                "**S = \u03bc\u1d05 (r + \u03bc\u2097) + z \u00b7 "
                "\u221a((r + \u03bc\u2097) \u03c3\u1d05\u00b2 + \u03bc\u1d05\u00b2 \u03c3\u2097\u00b2)**"
            )
            _SS_TERMS = (
                "| Symbol | Definition |\n"
                "|---|---|\n"
                "| \u03bc\u1d05 | Average weekly component demand |\n"
                "| \u03c3\u1d05 | Demand standard deviation |\n"
                "| \u03bc\u2097 | Average lead time (weeks) |\n"
                "| \u03c3\u2097 | Lead time standard deviation |\n"
                "| r | Review period \u2014 **8 weeks** |\n"
                "| z | Service level factor \u2014 **\u22481.65** for 95% target |"
            )
            _SS_BUSINESS = (
                "- The formula computes the **base-stock level (S)** \u2014 the total inventory "
                "required to meet demand across the review period and lead time under uncertainty.\n"
                "- **Safety stock** is the buffer component embedded within this level, covering "
                "demand and lead-time variability.\n"
                "- In this system, safety stock is enforced as a **protected inventory floor** "
                "per facility \u00d7 component. It is not consumed during planning.\n"
                "- Only inventory **above** this floor is used to satisfy weekly demand."
            )
            _SS_CYCLE_STOCK = (
                "The base-stock level (S) has two distinct components:\n\n"
                "**1. Cycle Stock** \u2014 \u03bc\u1d05 \u00d7 (r + \u03bc\u2097)\n"
                "- Covers **expected demand** over the review period and lead time\n"
                "- This is the primary driver of inventory volume\n\n"
                "**2. Safety Stock** \u2014 z \u00b7 \u221a((r + \u03bc\u2097)\u03c3\u1d05\u00b2 "
                "+ \u03bc\u1d05\u00b2\u03c3\u2097\u00b2)\n"
                "- Covers **uncertainty** in demand and lead time\n"
                "- This is a buffer \u2014 NOT intended to cover expected demand\n\n"
                "On-hand inventory at the start of planning is anchored at "
                "**S = Cycle Stock + Safety Stock**. "
                "Safety stock alone will often appear small relative to weekly demand \u2014 "
                "this is expected and correct."
            )
            _SS_PLANNING = (
                "- Weekly procurement is triggered when **usable inventory** (above the safety "
                "stock floor) reaches zero.\n"
                "- Safety stock is already accounted for before any weekly demand calculations "
                "begin \u2014 it does not appear as a deduction in the weekly trigger table.\n"
                "- The weekly trigger table reflects how demand consumes usable inventory, "
                "not safety stock itself."
            )
            _ss_content = (
                "**Inventory Policy \u2014 Safety Stock and Base-Stock Logic**\n\n"
                "**Base-Stock Formula**\n\n"
                + _SS_FORMULA + "\n\n"
                "**Term Definitions**\n\n"
                + _SS_TERMS + "\n\n"
                "**How It Works**\n\n"
                + _SS_BUSINESS + "\n\n"
                "**Cycle Stock vs Safety Stock (Key Distinction)**\n\n"
                + _SS_CYCLE_STOCK + "\n\n"
                "**Connection to Planning Outputs**\n\n"
                + _SS_PLANNING
            )
            with st.chat_message("assistant"):
                st.subheader("Inventory Policy \u2014 Safety Stock and Base-Stock Logic")
                st.markdown("**Base-Stock Formula**")
                st.markdown(_SS_FORMULA)
                st.markdown("**Term Definitions**")
                st.markdown(_SS_TERMS)
                st.markdown("**How It Works**")
                st.markdown(_SS_BUSINESS)
                st.markdown("**Cycle Stock vs Safety Stock (Key Distinction)**")
                st.markdown(_SS_CYCLE_STOCK)
                st.markdown("**Connection to Planning Outputs**")
                st.markdown(_SS_PLANNING)
            st.session_state.messages.append({
                "role":      "assistant",
                "content":   _ss_content,
                "has_trace": False,
                "summary":   "",
            })
            st.rerun()

        # ── Full inventory planning horizon drilldown (diagnostic) ───────────
        elif _is_full_horizon_drilldown_request(prompt):
            with st.spinner("Loading full inventory planning horizon..."):
                from tools.pipeline_queries import query_full_horizon_drilldown
                fh_data = query_full_horizon_drilldown()

            import pandas as pd
            _fh_rows = fh_data.get("rows", [])
            df_fh = pd.DataFrame(_fh_rows)

            if not df_fh.empty and "Facility" in df_fh.columns:
                df_fh["Facility"] = df_fh["Facility"].apply(_format_facility_label)

            _FH_COL_ORDER = [
                "Forecast Week", "Week", "Facility", "Component",
                "Gross Requirement", "Usable Inventory Before Demand",
                "Direct Procurement Needed", "Triggered?",
                "Safety Stock (Protected Floor)",
            ]
            if not df_fh.empty:
                df_fh = df_fh[[c for c in _FH_COL_ORDER if c in df_fh.columns]]

            _FH_FMT = {
                "Forecast Week":                  "{:,.0f}",
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Safety Stock (Protected Floor)": "{:,.0f}",
            }
            _fh_display_rows = df_fh.to_dict("records")

            _n_triggered = int((df_fh["Triggered?"] == "Yes").sum()) if not df_fh.empty else 0
            _FH_NOTE = (
                "All planning weeks are shown — including weeks where inventory covers demand "
                "(Triggered? = No) and weeks where procurement is required (Triggered? = Yes). "
                "Use filters to isolate a specific facility or component."
            )

            with st.chat_message("assistant"):
                st.subheader("Inventory Planning Horizon \u2014 Full Facility \u00d7 Component \u00d7 Week Detail")
                st.caption(
                    f"Forecast run {fh_data['run_id']}"
                    f"  \u00b7  {fh_data['horizon_start']} \u2192 {fh_data['horizon_end']}"
                    f"  \u00b7  {fh_data['n_weeks']} weeks"
                    f"  \u00b7  {len(_fh_rows):,} rows total"
                    f"  \u00b7  {_n_triggered} triggered"
                )
                st.markdown(_FH_NOTE)
                if not df_fh.empty:
                    st.dataframe(
                        df_fh.style.format(_FH_FMT),
                        use_container_width=True,
                        hide_index=True,
                        height=600,
                    )
                else:
                    st.info("No planning rows found for this forecast run.")
            st.session_state.messages.append({
                "role":          "assistant",
                "content":       (
                    "**Inventory Planning Horizon \u2014 Full Facility \u00d7 Component \u00d7 Week Detail**\n\n"
                    f"Forecast run {fh_data['run_id']} \u00b7 "
                    f"{fh_data['horizon_start']} \u2192 {fh_data['horizon_end']} "
                    f"({fh_data['n_weeks']} weeks) \u00b7 {len(_fh_rows):,} rows\n\n"
                    + _FH_NOTE
                ),
                "has_trace":     False,
                "summary":       "",
                "full_horizon_df": _fh_display_rows,
            })
            st.rerun()

        # ── Weekly procurement trigger drill-down ──────────────────────────
        elif _is_weekly_trigger_request(prompt):
            with st.spinner("Fetching triggered procurement rows..."):
                from tools.pipeline_queries import query_triggered_rows_structured
                trig_data = query_triggered_rows_structured()

            import pandas as pd
            _trig_rows = trig_data.get("rows", [])
            df_trig = pd.DataFrame(_trig_rows)

            # Apply readable facility labels (raw facility_id → label)
            if not df_trig.empty and "Facility" in df_trig.columns:
                df_trig["Facility"] = df_trig["Facility"].apply(_format_facility_label)

            # ── Presentation-layer renames ──────────────────────────────────
            df_trig = df_trig.rename(columns={
                "Available Inventory Before Demand": "Usable Inventory Before Demand",
                "Procurement Need":                  "Direct Procurement Needed",
            })

            # ── Extract SS context BEFORE dropping Safety Stock Reserve ────
            # Used for the context block — stored separately in the message dict.
            _ss_context = []
            if not df_trig.empty and "Safety Stock Reserve" in df_trig.columns:
                _ss_context = (
                    df_trig[["Facility", "Component", "Safety Stock Reserve"]]
                    .drop_duplicates()
                    .sort_values(["Facility", "Component"])
                    .rename(columns={"Safety Stock Reserve": "Safety Stock (Protected Floor)"})
                    .to_dict("records")
                )

            # ── Presentation-layer derived columns ─────────────────────────
            # All computed from existing fetched values — no inventory logic change.
            if not df_trig.empty and "Safety Stock Reserve" in df_trig.columns:
                # Ensure correct per-series cumsum order (date within each series)
                df_trig = df_trig.sort_values(["Component", "Facility", "Week"])
                df_trig["Cumulative Procurement Pressure"] = (
                    df_trig.groupby(["Facility", "Component"])["Direct Procurement Needed"]
                    .cumsum()
                )
                df_trig["Safety Stock Utilization (%)"] = (
                    df_trig["Cumulative Procurement Pressure"]
                    / df_trig["Safety Stock Reserve"]
                    * 100
                ).round(1)
                df_trig["Urgency Level"] = df_trig["Safety Stock Utilization (%)"].apply(
                    lambda u: "Critical" if u >= 100 else
                              "High"     if u >= 75  else
                              "Medium"   if u >= 50  else
                              "Low"
                )

            # ── Enforce display column order (Safety Stock Reserve excluded) ─
            # Forecast Week comes from r.horizon_week (true planning horizon index).
            _TRIG_COL_ORDER = [
                "Forecast Week", "Week", "Component", "Facility",
                "Gross Requirement", "Usable Inventory Before Demand",
                "Direct Procurement Needed", "Cumulative Procurement Pressure",
                "Safety Stock Utilization (%)", "Urgency Level",
            ]
            if not df_trig.empty:
                df_trig = df_trig[[c for c in _TRIG_COL_ORDER if c in df_trig.columns]]

            # Store unfiltered rows (Forecast Week = r.horizon_week from DB, not a counter)
            _trig_display_rows = df_trig.to_dict("records")

            _TRIG_FMT = {
                "Gross Requirement":              "{:,.0f}",
                "Usable Inventory Before Demand": "{:,.0f}",
                "Direct Procurement Needed":      "{:,.0f}",
                "Cumulative Procurement Pressure":"{:,.0f}",
                "Safety Stock Utilization (%)":   "{:.1f}%",
                "Forecast Week":                  "{:,.0f}",
            }

            _TRIG_BULLETS = (
                "- **Gross Requirement:** forecast-driven component demand for that week.\n"
                "- **Usable Inventory Before Demand:** inventory available after preserving "
                "the safety stock floor.\n"
                "- **Direct Procurement Needed:** portion of demand not covered by usable "
                "inventory.\n"
                "- **Cumulative Procurement Pressure:** total procurement required up to that "
                "week, per facility \u00d7 component.\n"
                "- **Safety Stock Utilization (%):** how much of the safety buffer is being "
                "matched by cumulative procurement demand.\n"
                "- **Urgency Level:** qualitative indicator \u2014 Low / Medium / High / "
                "Critical \u2014 based on how close cumulative pressure is to the safety "
                "buffer.\n"
                "- Procurement is triggered when usable inventory reaches zero."
            )

            with st.chat_message("assistant"):
                st.subheader("Weekly Procurement Trigger \u2014 Where and When Procurement Is Required")
                st.caption(
                    f"Forecast run {trig_data['run_id']}"
                    f"  \u00b7  {len(_trig_rows)} triggered week\u2013facility\u2013component rows"
                    "  \u00b7  Use filters to drill down by facility or component"
                )
                # ── Safety Stock context block ──────────────────────────────
                if _ss_context:
                    _ss_ctx_df = pd.DataFrame(_ss_context)
                    st.dataframe(
                        _ss_ctx_df.style.format({"Safety Stock (Protected Floor)": "{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(
                        "This value represents the inventory buffer required to maintain the "
                        "target service level. It is preserved in all inventory calculations "
                        "and not consumed by demand. The table below shows how procurement "
                        "pressure accumulates relative to this buffer."
                    )
                # ── Primary trigger table ───────────────────────────────────
                if not df_trig.empty:
                    st.dataframe(
                        df_trig.style.format(_TRIG_FMT),
                        use_container_width=True,
                        hide_index=True,
                        height=500,
                    )
                else:
                    st.info("No triggered procurement rows found \u2014 all inventory positions appear sufficient.")
                st.markdown(_TRIG_BULLETS)
            st.session_state.messages.append({
                "role":    "assistant",
                "content": (
                    "**Weekly Procurement Trigger \u2014 Where and When Procurement Is Required**\n\n"
                    f"Forecast run {trig_data['run_id']} \u00b7 {len(_trig_rows)} triggered rows\n\n"
                    + _TRIG_BULLETS
                ),
                "has_trace":         False,
                "summary":           "",
                "weekly_trigger_df": _trig_display_rows,
                "ss_context":        _ss_context,
            })
            st.rerun()

        elif _is_lp_decision_explanation_request(prompt):
            # ── LP decision explanation ────────────────────────────────────
            _last_raw = st.session_state.get("last_lp_raw_full") or {}
            if not _last_raw:
                with st.chat_message("assistant"):
                    st.info(
                        "No LP run has been completed in this session yet. "
                        "Run a procurement plan first, then ask again and I will explain how "
                        "the decision was made."
                    )
                st.session_state.messages.append({
                    "role":      "assistant",
                    "content":   "No LP run available yet. Run a procurement plan first.",
                    "has_trace": False,
                    "summary":   "",
                })
                st.rerun()
            else:
                with st.chat_message("assistant"):
                    for _pk, _raw in _last_raw.items():
                        _plabel = _pk.replace("lp_", "").replace("_", " ").title()
                        st.subheader(f"How Was This Decision Made — {_plabel}")
                        _render_lp_decision_explanation(_raw)
                st.session_state.messages.append({
                    "role":      "assistant",
                    "content":   "LP decision explanation rendered. See structured breakdown above.",
                    "has_trace": False,
                    "summary":   "",
                })
                st.rerun()

        else:
            # ── Query routing ──────────────────────────────────────────────────
            import time as _time
            _t0 = _time.perf_counter()
            _lp_history  = st.session_state.get("lp_params_history", {})
            _last_lp_raw = st.session_state.get("last_lp_raw_full", {})

            # Step 1 — try full 3-signal LP detection.
            _lp_detected    = _parse_lp_intent(prompt)
            _is_lp_followup = False
            _is_contextual  = False

            # Step 2 — if that failed, try explicit follow-up detection (product
            # must be mentioned + prior context + any parameter hint).
            if not _lp_detected:
                _followup = _parse_lp_followup(prompt, _lp_history)
                if _followup:
                    _lp_detected    = _followup
                    _is_lp_followup = True

            # Step 3 — if still not detected, try contextual urgency follow-up.
            # Fires for vague schedule / urgency statements that rely on recent
            # LP session context rather than an explicit product mention.
            # Example: "It appears we are a bit behind schedule this cycle for
            #           this particular product"
            if not _lp_detected:
                _ctx = _parse_lp_contextual_followup(prompt, _lp_history, _last_lp_raw)
                if _ctx:
                    _lp_detected    = _ctx
                    _is_lp_followup = True
                    _is_contextual  = True
                    logger.info(
                        "[LP CONTEXTUAL] contextual_lp_followup_detected=True | "
                        "recent_lp_context_exists=True | "
                        "resolved_current_product=%s | mapped_urgency_override=True",
                        _ctx.get("product"),
                    )
                else:
                    logger.info(
                        "[LP CONTEXTUAL] contextual_lp_followup_detected=False | "
                        "recent_lp_context_exists=%s",
                        bool(_lp_history or _last_lp_raw),
                    )

            # ── Debug logging ──────────────────────────────────────────────────
            _dbg_product = (_lp_detected or {}).get("product", "")
            _dbg_has_prior = bool(_lp_history.get(_dbg_product))
            _dbg_new_product = bool(_lp_detected and not _dbg_has_prior)
            _dbg_needs_orch  = _needs_orchestrator(prompt) if _lp_detected else False
            _dbg_route = (
                "direct_lp_contextual" if _is_contextual else
                "direct_lp"            if (_lp_detected and not _dbg_needs_orch) else
                "followup_lp"          if _is_lp_followup else
                "orch_lp"              if _lp_detected else
                "non_lp"
            )
            logger.info(
                "[LP ROUTE] parsed_product=%r | prior_context=%s | same_product=%s | "
                "new_product_lp_query=%s | lp_intent_detected=%s | "
                "same_product_followup=%s | contextual_lp_followup=%s | "
                "needs_orch=%s | route_chosen=%s",
                _dbg_product,
                _dbg_has_prior,
                bool(_dbg_product and _dbg_product in _lp_history),
                _dbg_new_product,
                bool(_lp_detected),
                _is_lp_followup,
                _is_contextual,
                _dbg_needs_orch,
                _dbg_route,
            )

            if _lp_detected and not _needs_orchestrator(prompt):
                # ── DIRECT LP ROUTE — no orchestrator, no LangGraph graph ─────
                # Follow-up queries: _parse_lp_followup() already merged prior
                #   params + current overrides → use as-is.
                # First-run queries:  apply carry-forward from lp_params_history
                #   (covers same-product re-runs after a previous approve/discard).
                if _is_lp_followup:
                    # Already merged — no additional carry-forward needed.
                    _final_params = _lp_detected
                else:
                    _prior_params = _lp_history.get(_dbg_product) or {}
                    if _prior_params:
                        _merged = {
                            "product":              _prior_params.get("product", _dbg_product),
                            "lambda_risk":          _prior_params.get("lambda_risk", 0.5),
                            "max_supplier_share":   _prior_params.get("max_supplier_share", 1.0),
                            "diversification_mode": _prior_params.get("diversification_mode", "none"),
                            "urgency":              _prior_params.get("urgency", False),
                            "exclude_supplier_ids": _prior_params.get("exclude_supplier_ids") or [],
                            "budget_cap":           _prior_params.get("budget_cap"),
                            "service_level_target": _prior_params.get("service_level_target", 1.0),
                            "compliance_threshold": _prior_params.get("compliance_threshold", 0.50),
                            "facility_id":          _prior_params.get("facility_id"),
                        }
                        for _k, _v in _lp_detected.items():
                            _merged[_k] = _v
                        _final_params = _merged
                    else:
                        _final_params = _lp_detected

                logger.info(
                    "[LP DIRECT] direct_rerun_path=True | intermediate_plan_page=False | "
                    "is_followup=%s | params=%s | t0=%.3fs",
                    _is_lp_followup, _final_params, _t0,
                )
                with st.spinner("Optimizing..."):
                    _run_lp_direct(_final_params)
                # _run_lp_direct() calls st.rerun() — code below is unreachable
                # for this branch.

            elif _lp_detected:
                # ── ORCHESTRATOR FAST PATH — LP with complex params ────────────
                # Query has signals (_needs_orchestrator=True) that require the
                # orchestrator LLM to extract: exclusion IDs, diversification,
                # urgency, facility scope, budget cap, etc.
                # Auto-resume the orchestrator interrupt; no plan page shown.
                _graph_prompt = prompt
                _params_note = ", ".join(f"{k}={v!r}" for k, v in _lp_detected.items())
                _graph_prompt = f"{prompt}\n\n[LP_PARAMS: {{{_params_note}}}]"

                logger.info(
                    "[LP ORCH FAST PATH] direct_rerun_path=False | intermediate_plan_page=False | "
                    "needs_orchestrator=True | params=%s", _lp_detected,
                )
                with st.spinner("Optimizing..."):
                    thread_id = str(uuid.uuid4())
                    st.session_state.thread_id = thread_id
                    config = {"configurable": {"thread_id": thread_id}}

                    result = asyncio.run(
                        graph.ainvoke({"messages": [("user", _graph_prompt)]}, config=config)
                    )
                    state = asyncio.run(graph.aget_state(config=config))
                    _t_orch = _time.perf_counter()
                    plan = extract_plan(state)
                    logger.info(
                        "[LP ORCH FAST PATH] orch_elapsed=%.3fs | tasks=%s",
                        _t_orch - _t0,
                        [t.get("agent") for t in (plan or {}).get("tasks", [])],
                    )

                    second_state = stream_graph(Command(resume="ok"), config=config)
                    _t_lp = _time.perf_counter()
                    lp_interrupt = second_state.get("__interrupt__")
                    logger.info(
                        "[LP ORCH FAST PATH] lp_interrupt=%s | lp_elapsed=%.3fs | total=%.3fs",
                        lp_interrupt.get("type") if lp_interrupt else None,
                        _t_lp - _t_orch,
                        _t_lp - _t0,
                    )

                if lp_interrupt and lp_interrupt.get("type") == "lp_approval":
                    st.session_state.waiting_for_lp_approval = True
                    st.session_state.pending_lp_result = lp_interrupt
                    st.session_state.lp_partial_state  = second_state
                    st.session_state.last_lp_raw_full  = lp_interrupt.get("raw", {})
                    st.session_state.saved_plan        = plan or {}
                else:
                    logger.warning("[LP ORCH FAST PATH] No LP interrupt — finalizing as normal.")
                    finalize_execution(second_state, fallback_plan=plan or {})
                st.rerun()

            else:
                # ── NORMAL (non-LP) orchestrator path ─────────────────────────
                _graph_prompt = prompt
                with st.spinner("Thinking..."):
                    thread_id = str(uuid.uuid4())
                    st.session_state.thread_id = thread_id
                    config = {"configurable": {"thread_id": thread_id}}
                    result = asyncio.run(
                        graph.ainvoke({"messages": [("user", _graph_prompt)]}, config=config)
                    )
                    state = asyncio.run(graph.aget_state(config=config))

                _t_orch = _time.perf_counter()
                plan = extract_plan(state)

                if state.next and plan:
                    logger.info(
                        "[NORMAL PATH] lp_detected=False | entered_pending_plan=True | "
                        "tasks=%s | orch_elapsed=%.3fs",
                        [t.get("agent") for t in plan.get("tasks", [])],
                        _t_orch - _t0,
                    )
                    st.session_state.waiting_for_approval = True
                    st.session_state.pending_plan = plan
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "I have a plan ready. Review the work orders below and approve when ready.",
                    })
                    st.rerun()
