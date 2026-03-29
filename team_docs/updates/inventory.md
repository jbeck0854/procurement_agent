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

## 1. Demand Forecasting

### Completed
- built and validated finished-goods demand forecasting model
- retrained on full observed history
- generated forward demand forecasts for the planning horizon
- stored forecasts in database

### Main forecast objects
- `fact_semiconductor_demand`
- `dim_forecast_run`
- `fact_semiconductor_demand_forecast`

---

## 2. BOM Layer

### Completed
- built BOM bridge from finished semiconductor SKUs to procurement-side components
- created component-demand views

### Purpose
Translate finished-good demand into the actual input components that must be procured.

### Main objects
- `dim_bom`
- `vw_component_requirement_detail`
- `vw_component_requirement_lp`

---

## 3. Inventory & Procurement Requirement Layer

### Historical inventory
Implemented realistic historical component inventory:
- derived from BOM-implied component demand
- grounded in historical planning assumptions
- includes cost structure aligned with the upstream pricing logic

### Inventory policy
Implemented periodic review policy:
- review period = 8 weeks
- service level = 95%
- z = 1.65
- stochastic lead time included

### Procurement requirement
Built procurement requirement output that compares:
- forecasted component demand
- inventory
- scheduled receipts
- safety stock

and returns:
- net procurement requirement

### Main objects
- `inventory/run_inventory.py`
- `fact_component_inventory_history`
- `fact_inventory_policy`
- `vw_procurement_requirement`

---

## 4. Inventory Realism Fix

### Problem
Initial benchmark inventory assumptions made the system appear universally overstocked, which produced zero procurement signal everywhere.

### Fix
Benchmark decision-point inventory was adjusted so it remained:
- plausible
- conservative
- grounded in historical demand
- not perfectly stocked

### Result
The system now produces a meaningful procurement signal.

---

## 5. Procurement Requirement Output

### Current results
- total procurement rows: 320
- rows requiring procurement action: 49
- rows with no action needed: 271

Interpretation:
- procurement is selective
- the system highlights real gaps rather than always recommending action
- output is suitable for optimization

This aligns with the prior validated status update.

---

## 6. LP Optimization Layer

### Completed
LP procurement allocation layer is now implemented and validated.

### Purpose
Allocate procurement volume across suppliers while balancing:
- cost
- risk
- compliance
- diversification
- optional urgency
- optional budget constraint
- optional service-level buffer

### Main optimization file
- `optimization/run_lp_optimization.py`

### Validated behaviors
Confirmed:
- lambda sensitivity works
- budget infeasibility is handled cleanly
- service-level buffer scales requirement correctly
- facility filter works
- urgency mode is reflected in the objective and validated in notebook

### Validation notebook
- `analytics/analysis/optimization_validation.ipynb`

---

## 7. Optimization Output Contract

The LP module now returns a structured result for one optimization run.

### Includes
- requirement summary
- supplier pool summary
- allocation output
- excluded suppliers
- cost summary
- constraint diagnostics
- formula description
- executive summary

Important:
- `executive_summary` is scoped to one LP run only
- final multi-product / session-level summary belongs in the agent layer, not inside the LP module 

---

## 8. What the System Now Does

For each selected product / component:

1. forecast finished-good demand  
2. translate demand into component need via BOM  
3. compare against inventory and safety stock  
4. determine procurement requirement  
5. optimize supplier allocation under business constraints  

The system can now answer:

> “What do we need to buy, and who should we buy it from?”

---

## 9. Planned Demo Capability

The updated demo should show that the system can:

- start from historical demand
- forecast the planning horizon
- convert finished demand into component need
- compare against inventory
- determine what must be procured
- compare supplier options
- run LP optimization
- support side-track supplier questions
- rerun under urgency or disruption scenarios

This is aligned with the current demo plan.

---

## 10. Remaining Work

### Main remaining work
- agent-side integration of optimization layer
- final session-level summary across multiple LP runs
- demo orchestration polish

### Not needed right now
- no new SQL views
- no LP redesign
- no separate formatter module
- no changes to scoring / forecasting / BOM logic

---

## Summary

The demand forecasting and inventory planning route is now complete through optimization.

The system is able to:

> **Forecast demand → translate demand into procurement-side component need → compare against inventory → determine procurement gaps → recommend supplier allocation**

The main remaining work is now:
- demo integration
- session-level aggregation
- final presentation polish