import pandas as pd

from analytics.scoring import SupplierScorer, load_contract

# test is to confirm that increasing the quantity (Q) in the scoring function leads to a decrease in the effective unit price for suppliers that qualify for bulk discounts. This ensures that the scoring logic correctly applies bulk discount rules based on the quantity threshold defined in the contract, allowing users to see the cost benefits of purchasing larger quantities from suppliers that offer such discounts.

def test_quantity_changes_effective_unit_price_when_bulk_threshold_crossed():
    contract = load_contract("analytics/metric_contract.yaml")
    scorer = SupplierScorer(contract)

    df = pd.read_csv("analytics/tests/fixtures/test_suppliers.csv")

    low_q = scorer.score(df, Q=1000, lambda_risk=0.5, top_k=10)
    high_q = scorer.score(df, Q=6000, lambda_risk=0.5, top_k=10)

    low_ranked = low_q.ranked
    high_ranked = high_q.ranked

    supplier_id = "SUP_AUS_5"

    low_row = low_ranked.loc[low_ranked["SupplierID"] == supplier_id].iloc[0]
    high_row = high_ranked.loc[high_ranked["SupplierID"] == supplier_id].iloc[0]

    # At low Q, supplier should not qualify for bulk pricing.
    # At high Q, supplier should qualify and unit price should fall.
    assert high_row["EffectiveUnitPrice"] < low_row["EffectiveUnitPrice"]