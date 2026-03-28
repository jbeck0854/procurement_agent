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

`vw_component_requirement_lp`
- LP-ready aggregated component requirement view

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

Combines forecasted component requirement with inventory state and policy outputs to produce net procurement requirement.

**Grain**
- `forecast_run_id × target_week_date × facility_id × product_key`

**Purpose**
- direct input surface for the LP optimization layer

**Key columns**
- `forecast_run_id`
- `target_week_date`
- `facility_id`
- `product_key`
- `gross_requirement`
- `on_hand_qty`
- `scheduled_receipts_qty`
- `backorder_qty`
- `safety_stock_qty`
- `base_stock_target_qty`
- `net_requirement`

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

### Net procurement requirement
`net_requirement = max(0, gross_requirement + backorder_qty + safety_stock_qty - on_hand_qty - scheduled_receipts_qty)`

---

## How the new planning layer works

1. Forecast finished-good demand
2. Explode that demand through the BOM into component demand
3. Compare component demand against benchmark inventory state
4. Add safety stock / inventory policy outputs
5. Produce net procurement requirement
6. Feed that requirement into the LP optimizer

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