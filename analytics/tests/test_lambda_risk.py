import pandas as pd

from analytics.scoring import SupplierScorer, load_contract

# test is to confirm that increasing `lambda_risk` increases the penalty applied to the risk score, thus increasing the risk-adjusted cost for a given supplier. This ensures that the `lambda_risk` parameter is functioning as intended in the scoring logic, allowing users to adjust the weight of risk in their supplier evaluations.
def test_lambda_risk_increases_penalty_for_risky_supplier():
    contract = load_contract("analytics/metric_contract.yaml")
    scorer = SupplierScorer(contract)

    df = pd.read_csv("analytics/tests/fixtures/test_suppliers.csv")

    low_lambda = scorer.score(df, Q=6000, lambda_risk=0.0, top_k=10)
    high_lambda = scorer.score(df, Q=6000, lambda_risk=1.0, top_k=10)

    low_ranked = low_lambda.ranked
    high_ranked = high_lambda.ranked

    # supplier that survives the compliance gate thus appearing in both results
    supplier_id = "SUP_BEL_7"

    low_row = low_ranked.loc[low_ranked["SupplierID"] == supplier_id].iloc[0]
    high_row = high_ranked.loc[high_ranked["SupplierID"] == supplier_id].iloc[0]

    # Higher lambda_risk should never reduce the penalty from risk
    assert high_row["RiskAdjustedCost"] >= low_row["RiskAdjustedCost"]