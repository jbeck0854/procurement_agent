"""
Parameter extraction and completion for LP optimization tasks.

Extracts LP parameters (lambda_risk, max_supplier_share, diversification_mode,
urgency, exclude_supplier_ids) from user text using deterministic rules.
Reuses logic originally written by Jonathan in streamlit_app.py.

Used by the Orchestrator node to supplement LLM intent classification with
fast, deterministic parameter extraction.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Product name normalization — longest phrases first to prevent partial matches.
COMPONENT_CANONICAL: dict[str, str] = {
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

# Risk language → lambda_risk value. Ordered most-specific → least-specific.
LAMBDA_MAP: list[tuple[str, float]] = [
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
    ("cost only",          0.0),
    ("cost-only",          0.0),
    ("no risk",            0.0),
]

# Short ambiguous keywords that need word-boundary matching to avoid false positives
# (e.g. "low" inside "lower", "follow"). Checked after LAMBDA_MAP fails.
_SHORT_RISK_KEYWORDS: list[tuple[str, float]] = [
    (r"\blow\b", 0.25),
]

# LP parameter defaults
LP_DEFAULTS: dict = {
    "lambda_risk": 0.5,
    "max_supplier_share": 1.0,
    "diversification_mode": "none",
    "urgency": False,
    "exclude_supplier_ids": [],
    "budget_cap": None,
    "compliance_threshold": 0.5,
    "service_level_target": 1.0,
    "facility_id": None,
}


def extract_lp_params(prompt: str) -> dict:
    """Extract LP parameters from user text. Returns only non-default params.

    Extracts: lambda_risk, max_supplier_share, diversification_mode,
              urgency, exclude_supplier_ids

    Does NOT detect intent or product — that's the Orchestrator's job.
    This function only extracts parameter VALUES from text.
    """
    t = prompt.lower()
    params = {}

    # Extract lambda_risk from risk language
    for phrase, value in LAMBDA_MAP:
        if phrase in t:
            params["lambda_risk"] = value
            break
    else:
        # Fallback: check short keywords with word-boundary regex
        for pattern, value in _SHORT_RISK_KEYWORDS:
            if re.search(pattern, t):
                params["lambda_risk"] = value
                break

    # Extract max_supplier_share from percentage patterns.
    # Handles all common phrasings:
    #   "40% cap", "40% supplier cap", "40% max share"
    #   "max share 40%", "no supplier should exceed 40%", "limit supplier to 40%"
    #   "cap to 30%", "share to 30%"
    cap_m = re.search(r'(\d+)\s*%\s*(?:supplier\s*)?(?:cap|share|max)', t)
    if not cap_m:
        cap_m = re.search(
            r'(?:max\s*(?:supplier\s*)?share|supplier\s*cap)\s*(?:of\s*)?(\d+)\s*%', t
        )
    if not cap_m:
        cap_m = re.search(
            r'(?:no\s+supplier\s+should\s+exceed|limit\s+supplier(?:\s+\w+){0,2}\s+to)\s+(\d+)\s*%',
            t,
        )
    if not cap_m:
        # "cap to 30%", "share to 30%", "lower ... to 30%"
        cap_m = re.search(r'(?:cap|share|limit)\s+(?:\w+\s+)*?to\s+(\d+)\s*%', t)
    if cap_m:
        pct = int(cap_m.group(1))
        if 0 < pct <= 100:
            params["max_supplier_share"] = round(pct / 100, 2)

    # Extract diversification_mode
    _DIVERSIF_PHRASES = (
        "diversif", "different countr", "different country", "3 countries",
        "three countries", "country diversif", "across countries",
        "each from a different country", "different country of origin",
    )
    if any(p in t for p in _DIVERSIF_PHRASES):
        params["diversification_mode"] = "country_diversified"

    # Extract urgency
    _URGENCY_PHRASES = ("urgent", "urgency", "emergency sourcing", "expedite")
    if any(p in t for p in _URGENCY_PHRASES):
        params["urgency"] = True

    # Extract exclude_supplier_ids
    # Matches explicit supplier IDs like SUP_HKG_38, SUP_CHN_07, etc.
    _excl_ids = re.findall(r'\bSUP_[A-Z]{3}_\d+\b', prompt)
    _EXCLUSION_CTX = ("exclude", "unavailable", "without supplier", "remove supplier",
                      "can't use", "cannot use", "what if")
    if _excl_ids and any(p in t for p in _EXCLUSION_CTX):
        params["exclude_supplier_ids"] = _excl_ids

    return params


def merge_with_prior(prompt: str, prior_params: dict) -> dict:
    """Merge prior LP run params with overrides extracted from current prompt.

    Used for what-if/urgency reruns where the user modifies one parameter
    but wants to keep the rest from the previous run.

    Args:
        prompt: Current user message text
        prior_params: Parameters from the most recent LP run for this product

    Returns:
        Complete merged parameter dict (prior base + current overrides)
    """
    # Start from prior params as base
    merged = {
        "product": prior_params.get("product", ""),
        "lambda_risk": prior_params.get("lambda_risk", 0.5),
        "max_supplier_share": prior_params.get("max_supplier_share", 1.0),
        "diversification_mode": prior_params.get("diversification_mode", "none"),
        "urgency": prior_params.get("urgency", False),
        "exclude_supplier_ids": list(prior_params.get("exclude_supplier_ids") or []),
        "budget_cap": prior_params.get("budget_cap"),
        "service_level_target": prior_params.get("service_level_target", 1.0),
        "compliance_threshold": prior_params.get("compliance_threshold", 0.50),
        "facility_id": prior_params.get("facility_id"),
    }

    # Apply overrides from current prompt
    t = prompt.lower()

    # Override lambda_risk (only if explicit risk language is present)
    _risk_matched = False
    for phrase, value in LAMBDA_MAP:
        if phrase in t:
            merged["lambda_risk"] = value
            _risk_matched = True
            break
    if not _risk_matched:
        for pattern, value in _SHORT_RISK_KEYWORDS:
            if re.search(pattern, t):
                merged["lambda_risk"] = value
                break

    # Override max_supplier_share
    cap_m = re.search(r'(\d+)\s*%\s*(?:supplier\s*)?(?:cap|share|max)', t)
    if not cap_m:
        cap_m = re.search(
            r'(?:max\s*(?:supplier\s*)?share|supplier\s*cap)\s*(?:of\s*)?(\d+)\s*%', t
        )
    if not cap_m:
        cap_m = re.search(
            r'(?:no\s+supplier\s+should\s+exceed|limit\s+supplier(?:\s+\w+){0,2}\s+to)\s+(\d+)\s*%', t
        )
    if not cap_m:
        cap_m = re.search(r'(?:cap|share|limit)\s+(?:\w+\s+)*?to\s+(\d+)\s*%', t)
    if cap_m:
        pct = int(cap_m.group(1))
        if 0 < pct <= 100:
            merged["max_supplier_share"] = round(pct / 100, 2)

    # Override diversification_mode
    _DIV = ("diversif", "different countr", "different country", "3 countries",
            "three countries", "country diversif", "across countries",
            "each from a different country", "different country of origin")
    if any(p in t for p in _DIV):
        merged["diversification_mode"] = "country_diversified"

    # Override urgency
    if any(p in t for p in ("urgent", "urgency", "emergency sourcing", "expedite")):
        merged["urgency"] = True

    # Override exclude_supplier_ids (only when explicit IDs present + exclusion context).
    # Note: "what if" is intentionally omitted here — it is only valid as an exclusion
    # context for fresh extraction (extract_lp_params), not for follow-up merges.
    xids = re.findall(r'\bSUP_[A-Z]{3}_\d+\b', prompt)
    if xids and any(p in t for p in ("exclude", "unavailable", "without supplier",
                                     "remove supplier", "can't use", "cannot use")):
        merged["exclude_supplier_ids"] = xids

    return merged


def fill_defaults(params: dict) -> dict:
    """Fill missing parameters with defaults. Ensures output is a complete LP params dict."""
    result = dict(LP_DEFAULTS)
    result.update({k: v for k, v in params.items() if v is not None or k in ("budget_cap", "facility_id")})
    return result
