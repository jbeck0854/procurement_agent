# ensuring scoring.py runs on real fixture of data and the fixture loads correcter
# Test is meant to ensure scorer produces the expected columns

import pandas as pd
from analytics.scoring import SupplierScorer, load_contract

def test_real_supplier_fixture_runs():
    # Load the contract
    contract = load_contract('analytics/metric_contract.yaml')
    # Initialize the scorer with the contract
    scorer = SupplierScorer(contract)

    df = pd.read_csv('analytics/tests/fixtures/test_suppliers.csv')
    result = scorer.score(df, Q=6000, lambda_risk=0.5, top_k=10)

    ranked = result.ranked

    print(ranked.head())  # Print the top rows of the ranked DataFrame to visually confirm scoring worked

    assert not ranked.empty
    assert 'RiskPenalty' in ranked.columns
    assert 'RiskAdjustedCost' in ranked.columns

