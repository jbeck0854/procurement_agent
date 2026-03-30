"""
Thin wrapper around optimization/run_lp_optimization.run().
Accepts user-facing parameters, constructs LPParams, and returns
the structured result dict from the LP solver.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from optimization.run_lp_optimization import run, LPParams

logger = logging.getLogger(__name__)


def run_optimization(
    product: str,
    lambda_risk: float = 0.50,
    max_supplier_share: float = 1.00,
    budget_cap: float | None = None,
    compliance_threshold: float = 0.60,
    service_level_target: float = 1.00,
    order_quantity: int = 5_000,
    urgency: bool = False,
    facility_id: str | None = None,
    exclude_supplier_ids: list[str] | None = None,
) -> dict:
    """Run LP optimization for a single product and return structured result."""
    params = LPParams(
        product=product,
        facility_id=facility_id,
        budget_cap=budget_cap,
        compliance_threshold=compliance_threshold,
        lambda_risk=lambda_risk,
        max_supplier_share=max_supplier_share,
        service_level_target=service_level_target,
        order_quantity=order_quantity,
        urgency=urgency,
        exclude_supplier_ids=exclude_supplier_ids or [],
    )
    logger.info(f"[LP_TOOL] Running optimization for product={product}, lambda={lambda_risk}")
    result = run(params)
    status = result.get("constraint_diagnostics", {}).get("lp_status") or result.get("lp_status", "Unknown")
    logger.info(f"[LP_TOOL] Result status: {status}")
    return result


DIRECT_LP_TOOLS = {
    "run_optimization": run_optimization,
}
