## Purpose

`run_inventory.py` builds the inventory and procurement planning layer that sits between:

- the BOM-exploded component demand layer
- and the LP optimization layer

It does **not** forecast demand and it does **not** score suppliers.

Its job is to:

1. derive historical component inventory from BOM-implied demand
2. compute inventory policy values (safety stock and base-stock target)
3. generate the procurement requirement signal that the LP optimizer will consume

---

## What this script produces

### 1) `fact_component_inventory_history`
Weekly benchmark historical component inventory

**Grain**
- `week_date × facility_id × product_key`

Contains:
- BOM-implied historical demand
- on-hand inventory
- scheduled receipts
- backorders
- order placed quantity
- inventory position
- unit cost
- inventory value

---

### 2) `fact_inventory_policy`
Inventory policy outputs by forecast run

**Grain**
- `forecast_run_id × facility_id × product_key`

Contains:
- average weekly demand
- demand volatility
- average lead time
- lead time volatility
- review period
- service level
- safety stock
- base-stock target

---

### 3) `vw_procurement_requirement`
LP-ready procurement requirement view

**Grain**
- `forecast_run_id × target_week_date × facility_id × product_key`

Contains:
- gross requirement
- inventory state at the decision point
- safety stock
- net requirement

---

## Explainability and Summary Helpers

`procurement_summary.py` provides business-facing, formatted outputs for the
inventory and procurement planning layer. It reads from pre-computed tables and
views only — no computational logic is changed. Its purpose is to improve
interpretability for demo delivery and agent integration.

---

### Summary helpers

**`format_component_requirements(conn, forecast_run_id=None) -> str`**
Full-horizon BOM-exploded demand. Shows the gross component volume required to
fulfill the finished-goods forecast, before any inventory or safety stock
adjustment. Use this to understand the raw scale of procurement need.

**`format_procurement_status(conn, forecast_run_id=None) -> str`**
Inventory-adjusted buy signal. Applies current on-hand inventory and safety
stock policy to BOM demand to derive net procurement requirement. This is the
direct input to the LP optimizer. Use this to see what actually needs to be
purchased.

---

### LangChain wrappers

Each wrapper opens and closes its own DB connection. `forecast_run_id=0`
retrieves the most recent run.

| Wrapper | Returns |
|---|---|
| `get_component_requirements_summary_tool(forecast_run_id=0)` | Component requirements output |
| `get_procurement_status_summary_tool(forecast_run_id=0)` | Procurement buy signal output |
| `get_procurement_planning_summary_tool(forecast_run_id=0)` | Both outputs in sequence |

---

### Drill-down helpers

**`get_procurement_requirement_drilldown(conn, forecast_run_id=None, product=None, facility_id=None) -> str`**
All rows (triggered and non-triggered) at the grain `facility × component × week`.
Accepts optional filters by product name and facility. Use this to trace the
full week-by-week planning math for any component.

**`get_triggered_procurement_rows(conn, forecast_run_id=None, product=None, facility_id=None) -> str`**
Only rows where `net_requirement > 0` — the specific weeks and facilities where
procurement is actually required. Accepts the same optional filters. Use this
to isolate where and when the buy signal is active.

---

### Key conceptual distinctions

| Output | What it represents |
|---|---|
| **Component Requirements** | Full-horizon gross BOM demand — all 320 rows, all weeks, before any inventory offset |
| **Procurement Status** | Inventory-adjusted buy signal — net requirement after on-hand and safety stock are applied |
| **Triggered rows** | The subset of rows where `net_requirement > 0` — the actual procurement signal |

Most weeks have gross demand but net requirement = 0. Procurement is triggered
only in the weeks and facilities where on-hand inventory plus safety stock
coverage is insufficient to meet that week's component need.

---

### Usage examples

```python
from inventory.procurement_summary import (
    get_procurement_planning_summary_tool,
    get_triggered_procurement_rows,
    get_procurement_requirement_drilldown,
)

# Combined planning summary (no connection needed — wrapper manages it)
print(get_procurement_planning_summary_tool())

# All triggered rows across all components and facilities
conn = psycopg2.connect(DATABASE_URL)
print(get_triggered_procurement_rows(conn))

# Drill down: one component, one facility, all forecast weeks
print(get_procurement_requirement_drilldown(conn, product='transistors', facility_id='FACILITY_3'))
conn.close()
```

---

## Logic flow

### Step 1 — Historical finished-good demand
Read historical demand from:
- `fact_semiconductor_demand`

### Step 2 — BOM explosion
Translate finished-good demand into component demand using:
- `dim_bom`

This creates BOM-implied historical component demand.

### Step 3 — Historical component inventory simulation
Simulate benchmark historical inventory by week and facility-product pair.

This benchmark is:
- demand-aware
- BOM-consistent
- not random

### Step 4 — Historical cost assignment
Assign historical component cost using:
- `cleaned_data/combined_products_UPDATED.csv`

Cost uses:
- global-average `real_price` across all countries
- grouped by product × year × month
- mapped to `product_key` via `dim_product`

This is more defensible than a single-country price because the firm sources
globally, and averaging across all countries maximises year-month coverage,
reducing the risk of zero-cost fallbacks in the valuation history.

If a `(product_key, year, month)` combination is still missing after averaging,
the pipeline logs a warning and defaults `unit_cost` to 0.0 for that row.

These cost fields (`unit_cost`, `inventory_value`) are for inventory valuation
reporting only. They do **not** affect safety stock, base-stock targets,
net procurement requirements, or LP optimization inputs.

### Step 5 — Inventory policy calculation
For each `facility_id × product_key`, compute:

- average weekly component demand
- standard deviation of component demand
- average lead time
- standard deviation of lead time
- safety stock
- base-stock target

### Step 6 — Procurement requirement generation
Join:
- forecasted component demand
- decision-point inventory state
- policy outputs

to produce:
- `net_requirement`

---

## Inventory policy assumptions

### Policy type
Periodic review / order-up-to

### Parameters
- `review_period_weeks = 8`
- `service_level_z = 1.65`

### Formula
`S = μ_D (r + μ_L) + z * sqrt((r + μ_L) * σ_D² + μ_D² * σ_L²)`

Where:
- `μ_D` = average weekly component demand
- `σ_D` = std dev of weekly component demand
- `μ_L` = average lead time in weeks
- `σ_L` = std dev of lead time in weeks

---

## Procurement requirement formula

`net_requirement = max(0, gross_requirement + backorder_qty + safety_stock_qty - on_hand_qty - scheduled_receipts_qty)`

---

## Important design rules

- Inventory is derived from historical BOM-implied component demand
- Inventory is **not** directly forecasted
- This script does **not** change supplier scoring logic
- This script does **not** change the forecasting model
- This script prepares the input for LP optimization

---

## Output role in the full system

This script enables the workflow:

historical demand  
→ forward forecast  
→ BOM explosion  
→ inventory comparison  
→ net procurement requirement  
→ LP optimization

---

## Why this matters

Without this layer, the system can forecast demand but cannot answer:

- do we already have enough inventory?
- how much do we actually need to buy?
- which supplier mix should we choose?

This script is the bridge between demand forecasting and procurement optimization.