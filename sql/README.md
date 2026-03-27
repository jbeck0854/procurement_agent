# SQL Warehouse Build Order and New Forecast/BOM Objects

## Full rebuild order (from scratch)

Run the SQL files in this order:

1. `sql/dimensions.sql`
2. `sql/facts.sql`
3. `sql/load/stage.sql`
4. `sql/load/copy_staging.sql`
5. `sql/load/load_dimensions.sql`
6. `sql/load/load_facts.sql`
7. `sql/load/load_bom.sql`
8. `sql/views.sql`

### Why this order matters

- `dimensions.sql` and `facts.sql` create the core warehouse tables
- `stage.sql` creates the staging tables required by `copy_staging.sql`
- `copy_staging.sql` loads raw CSV data into staging
- `load_dimensions.sql` and `load_facts.sql` populate warehouse dimensions and facts
- `load_bom.sql` must run **after** `load_dimensions.sql` because dimension reloads can truncate and cascade into `dim_bom`
- `views.sql` should run last because the views depend on the underlying tables and BOM seed data existing

---

## Key demand / forecast tables

### `fact_semiconductor_demand`
Historical finished-good semiconductor demand

**Grain**
- `week_date × facility_id × semiconductor_id`

**Purpose**
- stores historical finished-good demand used for forecasting

### `dim_forecast_run`
Forecast run metadata

**Purpose**
- one record per production forecast batch

### `fact_semiconductor_demand_forecast`
Stored forward-looking demand forecasts

**Grain**
- `forecast_run_id × facility_id × semiconductor_id × target_week_date`

**Purpose**
- stores the production forecast output used downstream for BOM explosion

---

## BOM bridge table

### `dim_bom`
Structural mapping between finished SKUs and procurement-side components

**Grain**
- `semiconductor_id × product_key`

**Purpose**
- maps each finished semiconductor SKU to the procurement components required to support one unit of forecasted demand

**Core columns**
- `semiconductor_id`
- `product_key`
- `units_per_sku`

**Important**
- this is curated seed data, not a staging-table load
- do not load this through `load_dimensions.sql`
- use `sql/load/load_bom.sql`

---

## BOM-driven component requirement views

### `vw_component_requirement_detail`
Explodes finished-good forecast rows into SKU-level component requirements

**Grain**
- `forecast_run_id × target_week_date × facility_id × semiconductor_id × product_key`

**Key fields**
- `predicted_demand`
- `units_per_sku`
- `gross_component_requirement`

**Use**
- debugging
- tracing which finished SKU is driving which component need

### `vw_component_requirement_lp`
Aggregated component requirement surface for optimization

**Grain**
- `forecast_run_id × target_week_date × facility_id × product_key`

**Key field**
- `total_component_requirement`

**Use**
- direct LP input
- procurement planning by component, week, and facility

**Important**
- the LP should consume this aggregated view, not the detail view

---

## Modeling and semantic separation

### Procurement layer
These names remain untouched and represent procured input components:
- `microprocessors`
- `integrated_circuit_components`
- `power_devices`
- `transistors`

### Finished-goods demand layer
These represent forecasted finished semiconductor SKUs:
- `semiconductor_id`
- `finished_family`
- `sku_performance_tier`

### BOM layer
This is the bridge that converts:
- finished-good demand
into
- component procurement requirements

Do not collapse these layers together.