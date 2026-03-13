"""
LangChain tool that wraps the teammate's SupplierScorer.
Queries the database, runs the scoring engine, and returns ranked results.
"""

import sys
import os

# Add the procurement_agent directory to Python's path
# so we can import the teammate's analytics module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
from langchain_core.tools import tool

from config import DATABASE_URL, METRIC_CONTRACT_PATH
from analytics.scoring import SupplierScorer, load_contract


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

    # 1. Query the database view
    conn = psycopg2.connect(DATABASE_URL)
    query = "SELECT * FROM vw_supplier_complete_profile"
    if product:
        query += f" WHERE product ILIKE '%{product}%'"
    df = pd.read_sql(query, conn)
    conn.close()

    if df.empty:
        return f"No suppliers found for product '{product}'."

    # 2. Load the scoring contract and run the scorer
    contract = load_contract(METRIC_CONTRACT_PATH)
    scorer = SupplierScorer(contract)
    result = scorer.score(df, Q=quantity, lambda_risk=lambda_risk, top_k=top_k)

    # 3. Format the output
    output_parts = []
    if result.warnings:
        output_parts.append("Warnings: " + "; ".join(result.warnings))

    output_parts.append(result.ranked.to_string(index=False))

    if not result.dropped_rows.empty:
        output_parts.append(f"\n({len(result.dropped_rows)} suppliers excluded from scoring)")

    return "\n".join(output_parts)


# Quick test
if __name__ == "__main__":
    print(score_suppliers.invoke({"product": "", "quantity": 5000, "lambda_risk": 0.5, "top_k": 5}))
