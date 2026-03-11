# Supplier Decision Intelligence Metric Contract  
**Version:** 1.0  
**File:** `metric_contract.yaml`  
**Folder:** `/analytics`

---

## Overview

This document explains the purpose, structure, and usage of the **Supplier Decision Intelligence Metric Contract**, which defines how suppliers are scored, normalized, and ranked for procurement recommendations. It serves as the authoritative reference for anyone working with supplier analytics, scoring logic, or downstream decision‑intelligence components.

The goal is to make the YAML contract easy to understand across the team—especially as more analytics files are added to this folder.

---

## What This Contract Does

The metric contract provides:

- A **deterministic scoring framework** for evaluating suppliers at the *supplier–product* level.
- A **standardized set of required inputs**, ensuring all scoring pipelines use consistent fields.
- A **normalization strategy** that keeps comparisons fair by normalizing *within product groups*.
- A **set of derived and composite metrics** that combine risk, cost, logistics, and quality signals.
- A **ranking policy** that determines the top recommended suppliers.
- An **explainability schema** that ensures transparency in how scores were produced.

This contract is the backbone of supplier scoring and is used by the analytics engine, SQL views, and any LLM‑based reasoning layer.

---

## Why This Document Is Useful

This documentation helps teammates quickly understand:

- **What inputs the scoring pipeline expects**
- **How each metric is calculated and why it matters**
- **How normalization and constraints affect supplier eligibility**
- **How final rankings are produced**
- **What fields are returned for explainability**

It reduces onboarding time, prevents misinterpretation of the YAML, and ensures consistent implementation across the team.

---

## Data Requirements

### Primary and Supporting Views
The contract expects data from the following SQL views:

- **`vw_supplier_complete_profile`**  
  Canonical input view containing risk, value, tariff, and logistics fields at the supplier–product grain.

- **`vw_supplier_pricing_profile`**  
  Debugging view for cost, tariff, and pricing fields.

- **`vw_supplier_risk_profile`**  
  Debugging view for risk‑related fields.

**Grain:**  
`vw_supplier_complete_profile` must return **one row per supplier per product**.

### Required Columns
The scoring pipeline requires the following fields:

- Supplier identity: `supplier_id`, `country_code`, `product`
- Logistics & disruption: `lead_time_mean`, `lead_time_variance`, `disruption_probability`, `compliance_eligibility`, `logistics_reliability`
- Cost/value: `baseline_price`, `bulk_discount`, `bulk_units`, `price_volatility`
- Quality & tariff: `probability_of_defect`, `mfn_text_rate_pct`
- Optional explainability fields: `hts8`, `tariff_description`, `how_measured`

### Null Policy
If any of the following fields are null, the supplier is **dropped from scoring**:

- `probability_of_defect`
- `bulk_discount`
- `bulk_units`
- `baseline_price`
- `price_volatility`

This ensures scoring stability and prevents partial or misleading results.

### Tariff Policy
Tariffs are applied only when `assumptions.tariff.enabled == true`.

- Tariff rate field: `mfn_text_rate_pct`
- Missing tariff rate defaults to **0.0%** for demo stability.

---

## Normalization Strategy

Normalization is performed **by product**, not globally.  
This ensures fairness: suppliers are compared only against others producing the same product.

- Method: **min‑max normalization**
- Epsilon: `1e-9` to avoid division by zero
- Optional clipping: trims extreme outliers using 1st and 99th percentiles

---

## Constraints

### Compliance Gate
Suppliers must meet a minimum compliance threshold:

- Field: `compliance_eligibility`
- Threshold: **0.60**
- Rule: supplier must satisfy `>= threshold`

This prevents recommending suppliers unlikely to meet governance or customs requirements.

---

## Assumptions

- **Quantity units:** interpreted as “units” for bulk pricing logic  
- **Currency:** all prices are in **USD**  
- **Tariffs:** applied as ad valorem percentages to effective unit price  

These assumptions ensure consistent interpretation across the analytics pipeline.

---

## Metric Definitions

The contract defines several categories of metrics:

### Base / Helper Metrics
- **Lead time coefficient of variation (`lead_time_cv`)**  
  Measures variability relative to mean lead time.

- **Disruption risk (`risk_disruption`)**  
  Probability of disruption based on WGI + LPI‑derived synthetic features.

- **Logistics risk (`risk_logistics`)**  
  Inverse of logistics reliability.

- **Quality risk (`risk_quality`)**  
  Probability of defect.

- **Cost instability risk (`risk_cost_instability`)**  
  Volatility of product pricing blended with disruption probability.

- **Lead‑time risk (`risk_leadtime`)**  
  Composite of mean lead time and lead time variability.

### Commercial Metrics
- **Effective unit price (`effective_unit_price`)**  
  Applies bulk discounts when quantity ≥ MOQ.

- **Landed unit cost (`landed_unit_cost`)**  
  Effective price adjusted by MFN tariff rate.

### Composite Scoring Metrics
- **Risk score (`risk_penalty`)**  
  Weighted combination of disruption, lead‑time, logistics, cost instability, and quality risks.

- **Risk‑adjusted cost (`risk_adjusted_cost`)**  
  Normalized landed cost + λ × normalized risk score.  
  This is the **primary ranking metric**.

---

## Ranking Logic

- Ranking is **enabled**.
- Primary metric: **`risk_adjusted_cost`** (ascending = better).
- Default top‑K: **5 suppliers**.
- Tie‑breakers (in order):
  1. `risk_disruption`
  2. `risk_leadtime`
  3. `risk_logistics`
  4. `landed_unit_cost`

This ensures deterministic and explainable ordering.

---

## Explainability

Explainability is **enabled** and returns:

- Raw input fields (supplier ID, country, product, cost fields, risk fields, tariff fields)
- Derived metrics (lead time CV, risk metrics, effective price, landed cost, composite scores)
- Top **2 drivers** of the final score, `risk_adjusted_score`, based on weighted component contributions and, separately, the **top 3 drivers** of the `risk_score`

This makes the scoring transparent and judge‑friendly.

---

## How This File Fits Into the Analytics Folder

The metric contract is one of the core documents in `/analytics` because:

- It defines the **rules** that all scoring logic must follow.
- It ensures **consistency** across SQL, Python, and LLM‑based reasoning.
- It acts as a **single source of truth** for supplier scoring.
- It supports **future extensibility** (e.g., adding SHAP‑based explainability, new metrics, or new constraints).

As more analytics files are added, each will have its own documentation page in this folder, following the same structure.

---

## Summary

The `metric_contract.yaml` file is the central specification for supplier scoring and ranking. This documentation provides a clear, accessible explanation of how the contract works, what inputs it expects, how metrics are calculated, and how final recommendations are produced. It ensures that every team member can confidently understand and extend the analytics layer.

