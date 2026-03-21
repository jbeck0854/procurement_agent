"""
LangChain tool that wraps the teammate's SupplierScorer.
Queries the database, runs the scoring engine, and returns ranked results.
"""

import sys
import os

# Add the procurement_agent directory to Python's path
# so we can import the teammate's analytics module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import logging
import time

import pandas as pd
from langchain_core.tools import tool

from config import DATABASE_URL, METRIC_CONTRACT_PATH
from analytics.scoring import SupplierScorer, load_contract

logger = logging.getLogger(__name__)


@tool
def score_suppliers(
    product: str = "",
    quantity: int = 5000,
    lambda_risk: float = 0.5,
    top_k: int = 5,
) -> str:
    """Score and rank suppliers for a given product based on risk-adjusted cost.

    Args:
        product: Product name to filter by (e.g. "DRAM", "transistors").
                 If empty, scores all products.
        quantity: Order quantity in units. Affects bulk discount pricing.
        lambda_risk: Risk aversion parameter (0 to 1).
                     Higher = prioritize low risk over low cost.
        top_k: Number of top suppliers to return.

    Returns:
        A formatted string with the ranked supplier results.
    """
    import psycopg2

    tool_start = time.perf_counter()

    # 1. Query the database view
    t0 = time.perf_counter()
    conn = psycopg2.connect(DATABASE_URL)
    query = "SELECT * FROM vw_supplier_complete_profile"
    params = None
    if product:
        query += " WHERE product ILIKE %s"
        params = (f"%{product}%",)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    db_elapsed = time.perf_counter() - t0
    logger.info(f"[TIMING] score_suppliers DB query: {db_elapsed:.3f}s ({len(df)} rows)")

    if df.empty:
        return f"No suppliers found for product '{product}'."

    # 2. Load the scoring contract and run the scorer
    t1 = time.perf_counter()
    contract = load_contract(METRIC_CONTRACT_PATH)
    scorer = SupplierScorer(contract)
    result = scorer.score(df, Q=quantity, lambda_risk=lambda_risk, top_k=top_k)
    score_elapsed = time.perf_counter() - t1
    logger.info(f"[TIMING] score_suppliers scoring engine: {score_elapsed:.3f}s")

    # 3. Format the output
    output_parts = []
    if result.warnings:
        output_parts.append("Warnings: " + "; ".join(result.warnings))

    ranked = result.ranked
    header_product = product if product else "all products"
    header = f"## Supplier Ranking ({header_product}, Q={quantity}, λ={lambda_risk}, top {top_k})"
    output_parts.append(header)
    price_col = next((col for col in ("EffectiveUnitPrice", "LandedUnitCost") if col in ranked.columns), None)
    records = ranked.to_dict(orient="records")
    for idx, row in enumerate(records[:top_k], start=1):
        supplier = row.get("SupplierID", "Unknown")
        country = row.get("CountryCode", "N/A")
        score = row.get("RiskAdjustedCost")
        score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "N/A"
        line_header = f"{idx}. **{supplier}** ({country}) — Risk-Adjusted Score: {score_text}"
        price = row.get(price_col)
        pricing = f"${price:,.3f}" if isinstance(price, (int, float)) else "N/A"
        lead_mean = row.get("LeadTimeMean")
        lead_std = row.get("LeadTimeStdDev")
        lead_text = "N/A"
        if isinstance(lead_mean, (int, float)) and isinstance(lead_std, (int, float)):
            lead_text = f"{lead_mean:.1f} ± {lead_std:.1f} days"
        disruption = row.get("DisruptionProbability")
        disruption_text = f"{disruption:.1%}" if isinstance(disruption, (int, float)) else "N/A"
        defect = row.get("ProbabilityOfDefect")
        defect_text = f"{defect:.1%}" if isinstance(defect, (int, float)) else "N/A"
        logistics = row.get("LogisticsReliability")
        logistics_text = f"{logistics:.3f}" if isinstance(logistics, (int, float)) else "N/A"
        compliance = row.get("ComplianceEligibility")
        compliance_text = f"{compliance:.3f}" if isinstance(compliance, (int, float)) else "N/A"
        drivers = row.get("TopRiskDrivers")
        if isinstance(drivers, (list, tuple)):
            drivers_text = ", ".join(str(driver) for driver in drivers)
        else:
            drivers_text = str(drivers) if drivers else "N/A"

        output_parts.append(line_header)
        output_parts.append(f"   - Unit cost: {pricing} | Lead time: {lead_text}")
        output_parts.append(f"   - Disruption risk: {disruption_text} | Defect rate: {defect_text} | Logistics: {logistics_text}")
        output_parts.append(f"   - Compliance: {compliance_text} | Top risk drivers: {drivers_text}")

    if not result.dropped_rows.empty:
        output_parts.append(f"⚠ {len(result.dropped_rows)} suppliers excluded from scoring")

    total = time.perf_counter() - tool_start
    logger.info(f"[TIMING] score_suppliers total: {total:.3f}s")
    output_parts.append(f"\n[Timing: DB {db_elapsed:.3f}s | Scoring {score_elapsed:.3f}s | Total {total:.3f}s]")

    return "\n".join(output_parts)


# Quick test
if __name__ == "__main__":
    print(score_suppliers.invoke({"product": "", "quantity": 5000, "lambda_risk": 0.5, "top_k": 5}))
