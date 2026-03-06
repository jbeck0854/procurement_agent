# Supplier Scoring Engine `scoring.py`

This document explains how the contract-driven supplier scoring engine works, how to run it, and how each part of the system contributes to deterministic, transparent supplier ranking.

The **Supplier Scoring Engine** consists of two core files:

 - `scoring.py` - the deterministic scoring engine
 - `metric_contract.yaml` - the configuration contract defining all scoring rules

Together, they form a fully auditable, reproducible, and explainable supplier scoring framework.

## 1. System Overview
 The scoring engine evaluates suppliers using a fully configuration-driven architecture:

  - All scoring rules live in `metric_contract.yaml`
  - All logic in `scoring.py` reads directly from the contract
  - No scoring behavior is hard-coded
  - Changing the contract changes the scoring behavior without touching Python

  This ensures:

   - **Determinism -** same inputs -> same outputs
   - **Transparency -** every metric, weight, and rule is visible in YAML
   - **Auditability -** dropped rows, warnings, and explainability are returned
   - **Reproducibility -** every output can be traced back to the contract

## 2. The Metric Contract (`metric_contract.yaml`)
The contract defines *everything* about scoring. It is the single source of truth for:

 ### Data Reqirements
Specifies:
 - Required columns
 - Optional explainability-only columns
 - Null-handling rules
 - Compliance gate thresholds

 Rows missing required fields are dropped with an audit reason.

 ### Normalization Rules
 Defines how metrics are scaled to 0-1:

 - Method: min-max
 - Scope: by-product (suppliers only compared to peers producing the same product)
 - Optional clipping to remove outliers

 ### Base Metrics
 Raw or derived fields such as:
 - `risk_disruption` (higher is worse)
 - `risk_logistics` (higher is worse)
 - `risk_quality` (higher is worse)
 - `risk_cost_instability` (higher is worse)
 - `risk_leadtime` (higher is worse)
 - `effective_unit_price` (lower is better)
 - `landed_unit_cost` (lower is better)
 These are computed exactly as defined in the contract.

 ### Composite Metrics

 **risk_score**
 Weighted combination of five risk components:

  - disruption
  - lead-time
  - logistics
  - cost instablility
  - quality

  Scaled to 0-100 for interpretability. Higher is worse.

  **risk_adjusted_cost**
  Defined as:
  `normalized_landed_cost + λ * normalized_risk_score`

  Where λ (risk aversion):
  - Comes from the contract
  - Can be overriden at runtime.

  A lower `risk_adjusted_score` is better.

### Ranking Rules
Defines:
 - Primary metric (risk_adjusted_cost)
 - Sort direction
 - Tie-breakers
 - Default top-K (best suppliers based on risk aversion)

### Explainability Rules
The contract specifics
- Whether explainability is enabled
- How many top drivers to return
- Which explainability method to use
- Which fields to return in the final output

Two explainability modes run simultaneously:

1. **TopDrivers -** drivers of risk_adjusted_cost -> sorted(list[str])
2. **TopRiskDrivers -** drivers of risk_score -> sorted(list[str])

Both are contract driven.

## 4. Scoring Logic (`scoring.py`)
The scorer performs the full pipeline and answers the question **Which suppliers provide the best balance between cost and risk?**

The system evaluates each supplier, by product, using:
 - Cost signals
 - Lead-time reliability
 - Logistics performance
 - Disruption probability
 - Product quality risk
 - Tariff exposure

This system allows procurement managers to select suppliers that minimize expected cost while controlling supply chain risk.

### Input Data
The scoring exine expects a dataset at the following grain:
`1 row per supplier_id per product`

Primary source view: `vw_supplier_complete_profile`
This SQL view combines supplier attributes from several datasets, icluding:
 - supplier_id (supplier identifier)
 - product (semiconductor component)
 - lead_time_mean (expected lead time)
 - lead_time_variance (lead time variability)
 - disruption_probability (probability of disruption)
 - logistics_reliability (logistics reliability score)
 - baseline_price (base supplier price)
 - bulk_discount( discount when ordering large volumes)
 - bulk_units (minimum units required for bulk pricing)
 - price_volatility (price volatility metric)
 - probability_of_defect (probability of defective components)
 - mfn_text_rate_pct (tariff rate)

### Schema Validation
Ensures all required fields exist.
Optional explainability fields do not block scoring.

### Null Policy
Rows missing critical fields are dropped.
Dropped rows are returned with reasons.

### Compliance Gate
Suppliers failing minimum governance and reglatory compliance requirements are removed.

These rows are also returned for audit.

### Metric Computation
The scorer computes:

**Lead Time Coefficient of Variation**
Measures relative variability in delivery time.

`lead_time_cv = lead_time_variance / lead_time_mean`

Higher values indicate less predictable delivery.

**Logistics Risk**
Logistics risk is defined as the inverse of logistics reliability.

`risk_logistics = 1 - logistics_reliability`

**Cost Instability Risk**
Derived from price volatility metrics.

Higher volatility indicates increased procurement risk.

**Quality Risk**
Represents probability of manufacturing defects.

`risk_quality = probability_of_defect`

**Lead-Time Risk**
Lead-time risk combines two factors:
 - average delivery time
 - variability in delivery

Formula:
 `risk_leadtime = 0.70 * normalized(lead_time_mean) + 0.3 * normalized(lead_time_cv)`

 Normalization ensures fair comparisons across suppliers by product.

 ### Cost Calculations

 **Bulk Pricing**
 If the order quantity exceeds the supplier's bulk threshold:
 `effective_unit_price = baseline_price * (1 - bulk_discount)

 Otherwise:
 `effective_unit_price = baseline_price`

 **Landed Cost**
 Tariffs are applied when:
 `landed_unit_cost = effective_unit_price * (1 + tariff_rate)

 If the tariff data is missing, the rate defaults to 0.

 ### Composite Scores

 **Risk Score**
 The system aggregates multiple risk dimensions.

 `risk_score = 0.3 * disruption_risk + 0.25 * leadtime_risk + 0.2 * logistics_risk + 0.15 * cost_instability + 0.1 * quality_risk

 The final score is then scaled to be in the (0, 100) range, where a higher score indicates higher supply chain risk.

 **Risk-Adjusted Cost**
 The final primary supplier ranking metric is:
 `risk_adjusted_cost = normalized(landed_unit_cost) + λ × normalized(risk_score)`

 Where:
 - λ is a risk tolerance parameter.
    - smaller lambda = prioritize cost
    - larger lambda = prioritize reliability (minimize risk)

This allows procurement manager to fine-tune decisions based on risk tolerance.

### Normalizaiton Strategy
Metrics are normalized using **min-max scaling.**

`normalized(x) = (x - min) / (max - min + epsilon)`

normalization occurs within each product group, rather than globally, to ensure suppliers are compared only against suppliers that produce the same product.

### Ranking
Suppliers are ranked by:
1. Primary metric (risk_adjusted_cost), ascending.
2. Tie-breakers:
    - disruption risk 
    - lead-time risk
    - logistics risk
    - landed unit cost

Top-K suppliers are returned.

### Explainability
Explainability is contract-driven and produces two independent columns:

#### 1.TopDrivers (Risk Adjusted Cost-level explainability)
Shows which components most influenced the **risk_adjusted_cost** metric.

Since RAC has two components:
- landed_unit_cost
- risk_score

This columns shows which one contributed most for each supplier.

#### 2. TopRiskDrivers (nested explainability)
Breaks down **risk_score** into its five components and then returns the top N contributers per supplier. In other words, which components most contributed to a "poor" `risk_score`

## 5. Running the Scorer
From the project root:

```Python
from scoring import SupplierScorer, load_contract
import pandas as pd

contract = load_contract("analytics/metric_contract.yaml")
scorer = SupplierScorer(contract)

df = pd.read_csv("debug_join_output.csv")   # or load from SQL
result = scorer.score(df, Q=6000, lambda_risk=0.6, top_k=5)

print(result.warnings)
print(result.ranked)
print(result.dropped_rows)
```

**Runtime overrides:**

- `Q` - order quantity (affects bulk pricing)
- `lambda_risk` - risk aversion
- `top_k` - number of suppliers to return

## 6. Determinism & Transparency
The system is deterministic because:
- All formulas come from the contract
- All weights are explicitly defined
- All normalization rules are explicitly defined
- All ranking rules are explicitly defined
- No randomness is used anywhere
- Every dropped row is returned with a reason
- Every score can be traced back to its raw inputs

## 7. Summary
The scoring engine is:
- **Contract-driven -** YAML defines all behavior
- **Deterministic -** same inputs -> same outputs
- **Transparent -** every metric and weight isvisible
- **Explainable -** top drivers for cost and risk
- **Modular -** easy to extend

The system provides a compelte, end-to-end, reproducible supplier evaluation pipeline.










