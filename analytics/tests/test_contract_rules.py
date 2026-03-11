import pandas as pd
import pytest

from analytics.scoring import SupplierScorer, load_contract

# test is to check contract enforcement behavior.
# 1) missing required columns should raise a ValueError and prevent scoring from proceeding, ensuring that the input data meets the minimum requirements defined in the contract.
# 2) compliance gate should exclude suppliers that are not compliant, confirming that the compliance criteria defined in the contract are correctly applied to filter out ineligible suppliers.
# 3) null policy should drop rows with null values in protected fields, validating that the null handling strategy specified in the contract is correctly implemented to maintain data integrity during scoring.
# 4) top_k should limit the number of ranked results returned, ensuring that the scoring function respects the configuration for how many top suppliers to return based on their risk-adjusted scores.


def test_missing_required_column_raises_value_error():
    contract = load_contract("analytics/metric_contract.yaml")
    scorer = SupplierScorer(contract)

    df = pd.read_csv("analytics/tests/fixtures/test_suppliers.csv")
    df = df.drop(columns=["baseline_price"])

    with pytest.raises(ValueError, match="Missing required columns for scoring"):
        scorer.score(df, Q=6000, lambda_risk=0.5, top_k=10)


def test_compliance_gate_excludes_ineligible_supplier():
    contract = load_contract("analytics/metric_contract.yaml")
    scorer = SupplierScorer(contract)

    df = pd.read_csv("analytics/tests/fixtures/test_suppliers.csv")
    result = scorer.score(df, Q=6000, lambda_risk=0.5, top_k=10)

    dropped = result.dropped_rows

    assert "SUP_BRA_8" in dropped["supplier_id"].values
    assert "gate:compliance_gate" in dropped["drop_reason"].values


def test_null_policy_drops_row_with_null_protected_field():
    contract = load_contract("analytics/metric_contract.yaml")
    scorer = SupplierScorer(contract)

    df = pd.read_csv("analytics/tests/fixtures/test_suppliers.csv").copy()

    # Introduce a null in a protected column for one row that would otherwise be eligible
    df.loc[df["supplier_id"] == "SUP_CAN_10", "lead_time_mean"] = pd.NA

    result = scorer.score(df, Q=6000, lambda_risk=0.5, top_k=10)
    dropped = result.dropped_rows

    assert "SUP_CAN_10" in dropped["supplier_id"].values
    assert "null_policy_drop_row" in dropped["drop_reason"].values


def test_top_k_limits_number_of_ranked_results():
    contract = load_contract("analytics/metric_contract.yaml")
    scorer = SupplierScorer(contract)

    df = pd.read_csv("analytics/tests/fixtures/test_suppliers.csv")
    result = scorer.score(df, Q=6000, lambda_risk=0.5, top_k=2)

    ranked = result.ranked

    assert len(ranked) == 2