# Demand Forecasting & Inventory Planning Pipeline — Status Update

## Overview

The demand forecasting and inventory planning pipeline is now fully implemented and validated up to the procurement requirement stage.

The system can now:

> **Forecast demand (finished goods) → Translate that demand into component need (what we procure from suppliers) → Compare against component inventory → Determine what must be procured**

---

## 0. Finished Goods Demand Creation

### Source Data
- Original dataset: Kaggle **food demand dataset**
- Grain:  
  - `week × center_id × meal_id`

### Transformation Overview
Converted a food demand dataset into a semiconductor-style finished-goods demand dataset.

### Key Transformations
- **Meal → Semiconductor SKU**
  - Top-demand meals mapped to semiconductor SKUs (12)
- **Center → Facility**
  - Top centers mapped to manufacturing facilities (4)
- **Category / cuisine → SKU attributes**
  - Used to derive:
    - performance tiers
    - product families
- **Center attributes → Facility descriptors**
  - region, scale, capacity, etc.

### Output Dataset
- Final dataset:
  - `cleaned_data/finished_goods_demand_table.csv`

- Final grain:
  - `week_date × facility_id × finished_sku_id`

### Notebook Reference
All transformations are documented in:
`scripts/data_cleaning/04_FinishedGoods_Demand_Table.ipynb`

This notebook shows:
- filtering logic (top SKUs / facilities)
- feature mapping
- renaming and restructuring
- final dataset generation

---


## Completed Work

### 1. Demand Forecasting
- Built and validated the finished-goods demand forecasting model
- Retrained the model on full historical data
- Generated forward demand forecasts (16–20 week horizon)
- Stored forecasts in the database:
  - `dim_forecast_run`
  - `fact_semiconductor_demand_forecast`

---

### 2. BOM Layer (Demand Translation)
- Built BOM bridge from finished semiconductor SKUs → procurement components. This details how many components/WIP products needed for each particular semiconductor chip we assemble/manufacture.
- Implemented component demand views:
  - Translate finished-good demand into component-level requirements
- Ensures procurement decisions are based on **actual component needs**, not finished goods

---

### 3. Inventory & Procurement Requirement Layer

#### Historical Inventory
- Created realistic historical component inventory:
  - Derived from BOM-implied demand (not random)
  - Uses PPI-aligned cost structure

#### Inventory Policy
- Implemented periodic review (order-up-to) policy:
  - Review period: 8 weeks
  - Service level: 95% (z = 1.65)
  - Stochastic lead time modeled (since lead time varies amongst suppliers. 'Grouped' by product.)

#### Procurement Requirement
- Built `vw_procurement_requirement`:
  - Combines:
    - forecasted demand
    - BOM explosion (the translation into procurement needs)
    - inventory state
    - safety stock
  - Outputs **net procurement requirement** by:
    - facility
    - week
    - component

---

### 4. Critical Fix — Inventory Realism

Fix implemented:
- Adjusted benchmark inventory at decision point to:
  - reflect realistic inventory drawdown
  - remain grounded in historical demand
- Result:
  - system produces a **non-trivial procurement signal**

---

## Current Results

| Metric | Value |
|------|------|
| Total procurement rows | 320 |
| Rows requiring procurement | 49 (15.3%) |
| Rows with no action needed | 271 (84.7%) |

Interpretation:
- Procurement is **selective, not constant**
- System highlights **true gaps**, not noise
- Output is suitable for optimization

---

## What the System Now Does

For each component, facility, and week:

1. Forecasts finished-good demand  
2. Translates demand → component requirements (via BOM)  
3. Compares against:
   - on-hand inventory  
   - scheduled receipts  
   - safety stock  
4. Outputs:

> **Net Procurement Requirement for Each Product Across Each Facility**

---

## Next Step — LP Optimization Layer

We will now build the optimization engine that:

### Objective
Allocate procurement volume across suppliers in a way that:
- minimizes risk-adjusted cost
- satisfies demand requirements
- respects operational constraints

### Constraints to incorporate
- Budget cap
- Compliance threshold
- Risk tolerance (lambda)
- Diversification preferences
- Optional supplier share limits
- Optional/potential service level requirements

---

## Planned Demo Capabilities

The system will support interactive decision-making during demo.

### User Inputs
- Component / product to procure
- Planning horizon
- Budget cap
- Compliance threshold
- Risk tolerance (λ)
- Diversification preference
- Optional disruption scenario

### System Output
- Optimal supplier allocation
- Cost + risk tradeoff
- Feasibility under constraints
- Inventory sufficiency insights

---

## System Capability (Current State)

System now functions as a **procurement decision pipeline**:

Forecast Demand --> BOM Translation --> Inventory Comparison --> Procurement Need (Net Requirement) --> [Next: Optimization Layer]

---

## Summary

- Forecasting is complete and production-ready  
- Inventory logic is realistic and validated  
- Procurement signals are meaningful  
- System is ready for optimization  

> **Next milestone: LP optimization and real-time supplier allocation**