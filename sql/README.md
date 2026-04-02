# SQL Warehouse Build Order and Planning Layer Documentation

## Full rebuild order

Run the SQL files in this order:

1. `sql/dimensions.sql`
2. `sql/facts.sql`
3. `sql/load/stage.sql`
4. `sql/load/copy_staging.sql`
5. `sql/load/load_dimensions.sql`
6. `sql/load/load_facts.sql`
7. `sql/load/load_bom.sql`
8. `sql/views.sql`

## Why this order matters

- `dimensions.sql` and `facts.sql` create the warehouse tables
- `stage.sql` creates the staging tables required by `copy_staging.sql`
- `copy_staging.sql` loads raw CSV data into staging
- `load_dimensions.sql` and `load_facts.sql` populate the warehouse
- `load_bom.sql` seeds the BOM bridge after dimensions are loaded
- `views.sql` should run last because the views depend on the underlying tables already existing

---

## Core completed layers

### Historical finished-goods demand
`fact_semiconductor_demand`

Stores historical finished-good semiconductor demand.

**Grain**
- `week_date × facility_id × semiconductor_id`

### Production forecast metadata
`dim_forecast_run`

Stores one row per production forecast batch.

### Forward finished-goods forecasts
`fact_semiconductor_demand_forecast`

Stores forward demand forecasts generated from the production model.

**Grain**
- `forecast_run_id × facility_id × semiconductor_id × target_week_date`

### BOM bridge
`dim_bom`

Maps finished semiconductor SKUs to procurement-side components.

**Grain**
- `semiconductor_id × product_key`

### BOM-exploded forecast views
`vw_component_requirement_detail`
- SKU-level exploded component requirement view
- **Grain:** `forecast_run_id × target_week_date × facility_id × semiconductor_id × product_key`
- Joins `fact_semiconductor_demand_forecast` to `dim_bom`; computes `gross_component_requirement = predicted_demand × units_per_sku`
- Used for BOM translation explainability; feeds `vw_component_requirement_lp`

`vw_component_requirement_lp`
- Aggregated LP-ready component requirement view
- **Grain:** `forecast_run_id × target_week_date × facility_id × product_key`
- SKU dimension collapsed; sums `gross_component_requirement` across all finished-good SKUs
- **LP input:** the LP optimizer queries this view directly to obtain horizon gross demand, then applies the inventory offset once per facility to compute the demand floor

---

## Supplier analytics layer

### Supplier dimension
`dim_supplier`

One row per supplier. Contains all supplier-level risk and logistics attributes.

**Grain**
- `supplier_key` (one row per supplier)

**Key columns**
- `supplier_id` — supplier identifier
- `country_code` — supplier country (used for diversification and country-risk context)
- `product_key` — procurement component this supplier provides
- `lead_time_mean` — average lead time in days (required for scoring)
- `lead_time_stddev` — standard deviation of lead time in days (required for scoring)
- `lead_time_variance` — variance of lead time (optional; explainability only)
- `disruption_probability` — synthetic probability of supply disruption `[0,1]`
- `compliance_eligibility` — governance/customs-derived compliance score `[0,1]`; suppliers below 0.60 are excluded before LP runs
- `logistics_reliability` — weighted LPI-derived reliability score `[0,1]`

**Pipeline role:** feeds `vw_supplier_complete_profile`; not used directly by LP demand computation

---

### Supplier product profile
`fact_supplier_product_profile`

One row per supplier. Contains product-level commercial and quality attributes.

**Grain**
- `supplier_key` (one row per supplier)

**Key columns**
- `probability_of_defect` — manufacturing defect probability `[0,1]`
- `baseline_price` — base unit price (USD)
- `price_volatility` — price volatility score `[0,1]`
- `bulk_discount` — fractional discount when order quantity ≥ `bulk_units`
- `bulk_units` — minimum order quantity to activate bulk pricing (units)
- `hts8` — HTS-8 tariff code for tariff lookup (optional)

**Pipeline role:** feeds `vw_supplier_complete_profile`; not used directly by LP demand computation

---

### Supplier scoring views
`vw_supplier_complete_profile`

Canonical scoring input. Joins `dim_supplier`, `fact_supplier_product_profile`, and tariff data into a single flat table at the supplier–product grain.

**LP input:** the LP optimizer queries this view to build the eligible supplier pool and pass it to the scoring layer (`analytics/scoring.py`). This is the supplier-side LP input; `vw_component_requirement_lp` is the demand-side LP input.

`vw_supplier_pricing_profile`
- Debug view for cost, tariff, and bulk pricing fields. Not used by LP or scoring directly.

`vw_supplier_risk_profile`
- Debug view for risk and logistics fields. Not used by LP or scoring directly.

---

### Analytics context views
`vw_product_price_history`
- Monthly product–country price history for charting, price trend analysis, and cost explainability. Not used by LP.

`vw_commodity_price_history`
- Monthly commodity price history for indirect cost driver context. Not used by LP.

`vw_country_risk_snapshot`
- Country-level WGI and LPI indicators for risk annotation and supplier-country context visualizations. Not used by LP.

---

## New inventory / planning objects

### Historical component inventory
`fact_component_inventory_history`

Stores weekly benchmark component inventory by facility and product.

**Grain**
- `week_date × facility_id × product_key`

**Purpose**
- represents historical inventory state for procurement components
- derived from historical BOM-implied component demand
- includes inventory quantities and historical cost

**Key columns**
- `week_date`
- `week_number`
- `facility_id`
- `product_key`
- `bom_implied_demand`
- `scheduled_receipts_qty`
- `on_hand_qty`
- `backorder_qty`
- `order_placed_qty`
- `inventory_position`
- `unit_cost`
- `inventory_value`

---

### Inventory policy output
`fact_inventory_policy`

Stores the policy parameters and computed stock targets used for planning.

**Grain**
- `forecast_run_id × facility_id × product_key`

**Purpose**
- stores demand stats, lead-time stats, safety stock, and base-stock target for each facility-product pair

**Key columns**
- `forecast_run_id`
- `facility_id`
- `product_key`
- `avg_demand_weekly`
- `std_demand_weekly`
- `avg_lead_time_weeks`
- `std_lead_time_weeks`
- `review_period_weeks`
- `service_level_z`
- `safety_stock_qty`
- `base_stock_target_qty`
- `n_eligible_suppliers`
- `compliance_threshold`
- `computed_at`

---

### Procurement requirement
`vw_procurement_requirement`

Week-by-week procurement trigger view. Applies the decision-point inventory state and safety stock policy to each forecast week's gross demand to show where and when procurement is activated.

**Grain**
- `forecast_run_id × target_week_date × facility_id × product_key`

**Purpose**
- weekly inventory trigger signal for explainability and drill-down
- **NOT the LP demand floor** — the LP applies the inventory offset once at the horizon level via `vw_component_requirement_lp`; this view applies it per forecast week and is used only for planning diagnostics and agent-facing helpers

**Key columns**
- `forecast_run_id`
- `target_week_date` — calendar date of the forecast week
- `horizon_week` — sequential week index within the planning horizon (1 = first week, 20 = last); useful for sorting and display
- `facility_id`
- `product_key`
- `gross_requirement` — that week's BOM-exploded component demand
- `on_hand_qty` (**Starting OH**) — decision-point on-hand stock; fixed across all horizon weeks
- `scheduled_receipts_qty` — on-order at decision point; fixed (currently 0)
- `backorder_qty` — unfilled demand at decision point; fixed (currently 0)
- `safety_stock_qty` (**SS Floor**) — policy buffer; fixed across horizon; pre-deducted once in `available_above_ss`
- `base_stock_target_qty` — base-stock target S from inventory policy
- `available_above_ss` — `max(0, on_hand + SR − BO − SS)`; usable inventory above the SS floor; computed once per series
- `remaining_inventory` — `max(0, available_above_ss − cumulative gross from prior weeks)`; decreases each week
- `net_requirement` — `max(0, gross_N − remaining_inventory_N)`; stateful rolling depletion; SS pre-deducted once, NOT added per week

**Formula validation note:** `net_requirement = gross − remaining` (not `gross + SS − on_hand`). SS is pre-deducted in `available_above_ss`, so adding it again per week would double-count it. When `on_hand ≥ SS`, `SUM(net_requirement over all weeks) = LP demand floor`.

---

## Main formulas

### Inventory policy
Periodic review, order-up-to policy:

- review period `r = 8 weeks`
- service level `z = 1.65`

For each `facility_id × product_key`:

`S = μ_D (r + μ_L) + z * sqrt((r + μ_L) * σ_D² + μ_D² * σ_L²)`

Where:
- `μ_D` = average weekly component demand
- `σ_D` = std dev of weekly component demand
- `μ_L` = average lead time in weeks
- `σ_L` = std dev of lead time in weeks

### Net procurement requirement (weekly stateful depletion)
```
available_above_ss = max(0, on_hand + SR − BO − SS)   [once per series]
remaining_N        = max(0, available_above_ss − cumulative_gross_{weeks 1..N−1})
net_requirement_N  = max(0, gross_N − remaining_N)
```
SS is pre-deducted once in `available_above_ss`. It is NOT added per week.
When `on_hand ≥ SS`: `SUM(net_requirement_N) = LP demand floor`.

---

## How the new planning layer works

1. Forecast finished-good demand
2. Explode that demand through the BOM into component demand (`vw_component_requirement_lp`)
3. Compare component demand against benchmark inventory state (`fact_component_inventory_history` decision point)
4. Add safety stock / inventory policy outputs (`fact_inventory_policy`)
5. Produce weekly procurement trigger signal (`vw_procurement_requirement`) for explainability
6. LP computes horizon-level demand floor directly from `vw_component_requirement_lp` + inventory snapshot (offset applied once per facility); LP also loads eligible suppliers from `vw_supplier_complete_profile`

---

## Important separation of layers

### Forecasting layer
Forecasts finished-good demand.

### BOM layer
Translates finished-good demand into procurement component demand.

### Inventory / planning layer
Evaluates whether existing inventory plus policy coverage is enough.

### LP layer
Decides how to allocate procurement across suppliers.

**Demand-side inputs (what the LP optimizes against):**
- `vw_component_requirement_lp` — horizon gross demand by facility × product × week
- `fact_component_inventory_history` — decision-point on-hand, scheduled receipts, backorder
- `fact_inventory_policy` — safety stock per facility × product

The LP applies the inventory offset once at the horizon level (not per forecast week) to compute the demand floor per facility, then sums across facilities to get total D.

**Supplier-side input:**
- `vw_supplier_complete_profile` — eligible supplier pool with cost, risk, compliance, and lead-time data

**Not used by LP for demand:**
- `vw_procurement_requirement` — week-by-week trigger view; used only for planning explainability