## How to read procurement outputs (READ THIS FIRST)

You have inventory on hand when the planning horizon starts. Some of that
inventory is reserved as a safety buffer. The rest — everything **above** the
safety stock floor — is what demand can actually consume week by week.
Once that usable stock runs out, procurement is triggered.

| Term | What it means |
|---|---|
| **Starting OH** | Total on-hand inventory at the start of the horizon. Fixed — same every week. |
| **SS Floor** | Safety stock reserve. Set aside before any demand is counted. Fixed. |
| **Available** | Starting OH − SS Floor = the inventory demand is allowed to consume. Computed once. |
| **Remaining** | How much Available is left at the start of this week. **Decreases each week.** |
| **Gross Req** | This week's component demand (forecast × BOM). Changes every week. |
| **Net Req** | Procurement needed = max(0, Gross Req − Remaining). Zero while stock covers demand. |

**Why Starting OH and SS Floor look constant:** They are point-in-time snapshots
taken once at the start of the planning horizon. Only **Remaining** depletes.

**Example — one facility × one component, 3 weeks**
`Starting OH = 800 · SS Floor = 200 · Available = 600`

| Wk | Gross Req | Remaining (start of week) | Net Req |
|----|-----------|--------------------------|---------|
| 1  | 300       | 600                      | 0       |
| 2  | 300       | 300                      | 0       |
| 3  | 280       | 0                        | **280** |

Week 3 triggers because weeks 1 + 2 consumed the full Available pool (300 + 300 = 600).
Safety stock was never touched — it was reserved from day one.

---

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
Weekly inventory trigger view for explainability

**Grain**
- `forecast_run_id × target_week_date × facility_id × product_key`

Contains:
- gross requirement (BOM-translated demand for this week)
- decision-point inventory state (on_hand, SR, backorder — constant per series)
- safety stock (constant per series)
- remaining_inventory (rolling balance: inventory above SS floor after prior weeks consumed)
- net requirement (demand this week that exceeds remaining_inventory)

**Note:** This view is for planning explainability. The LP uses `vw_component_requirement_lp` and applies the inventory offset once at the horizon level.

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
Week-by-week inventory trigger signal. Applies current on-hand inventory and
safety stock policy to BOM demand on a per-week basis. Shows WHERE and WHEN
procurement is activated across the planning horizon. This is NOT the LP demand
floor — see `format_aggregated_procurement_need()` for that.

**`format_aggregated_procurement_need(conn, forecast_run_id=None, product=None, facility_id=None) -> str`**
Horizon-level procurement need used by the LP optimizer. Applies the inventory
offset (on-hand, safety stock, scheduled receipts) ONCE against the total
horizon gross demand per facility — the same formulation the LP uses internally.
This is the quantity the optimizer allocates across suppliers. Use this to
understand what the LP is actually optimizing, and to verify LP allocation
totals against planning need.

---

### LangChain wrappers

Each wrapper opens and closes its own DB connection. `forecast_run_id=0`
retrieves the most recent run.

| Wrapper | Returns |
|---|---|
| `get_component_requirements_summary_tool(forecast_run_id=0)` | Full-horizon gross BOM demand |
| `get_procurement_status_summary_tool(forecast_run_id=0)` | Week-by-week procurement trigger signal |
| `get_procurement_planning_summary_tool(forecast_run_id=0)` | Both gross demand and weekly trigger signal in sequence |
| `get_aggregated_procurement_need_tool(forecast_run_id=0, product='', facility_id='')` | Horizon-level LP demand floor (the quantity the LP optimizes) |
| `get_bom_translation_tool(semiconductor_id, forecast_run_id=0, facility_id='', target_week_date='')` | BOM translation explainability output |

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

### BOM translation explainability helper

**`format_bom_translation(conn, semiconductor_id, forecast_run_id=None, facility_id=None, target_week_date=None) -> str`**

Explains how a finished-good semiconductor SKU maps to procurement components
via the Bill of Materials. Two modes:

**Mode A — SKU-level BOM recipe** (`semiconductor_id` only, no facility or week):
Shows which components make up one unit of the SKU and how many units of each
are required. Use this to answer: *"What goes into this SKU?"* or *"How does
the BOM for SEMICONDUCTOR_6 break down?"*

**Mode B — Forecast-row explosion** (all arguments provided):
Takes a specific forecast week's finished-good demand for the SKU, applies the
BOM multipliers, and shows the resulting gross component requirement row by row.
Includes a context block (SKU, facility, week, run), the arithmetic walkthrough,
and a note explaining that these figures are gross demand before any inventory
or safety stock offset. Use this to answer: *"Show me how the forecast for
SEMICONDUCTOR_6 at FACILITY_2 translates into component demand for week X."*

This helper is distinct from:
- **Component Requirements** — which aggregates gross demand across all SKUs,
  all facilities, and all weeks into a single horizon-level total per component
- **Procurement Status** — which shows the inventory-adjusted net buy signal

The BOM translation helper explains the *recipe and mapping logic* for a single
SKU, not the aggregated planning totals.

---

### Key conceptual distinctions

| Output | What it represents | LP input? |
|---|---|---|
| **Component Requirements** | Full-horizon gross BOM demand — all weeks, before any inventory offset | No — gross only |
| **Procurement Status** | Week-by-week inventory trigger signal — shows WHERE and WHEN procurement activates | No — weekly signal |
| **Triggered rows** | Subset of weekly rows where `net_requirement > 0` — the specific weeks/facilities driving procurement | No — weekly subset |
| **Aggregated Procurement Need** | Horizon-level net requirement with inventory offset applied ONCE per facility — the LP demand floor | **Yes — this is what the LP optimizes** |
| **BOM Translation (Mode A)** | BOM recipe for one SKU — components and units-per-SKU | No |
| **BOM Translation (Mode B)** | One forecast row exploded through the BOM — gross component demand for a specific SKU × facility × week | No |

**Why the distinction matters:**
The Procurement Status and Triggered Rows views apply `max(0, gross_T + K)`
per forecast week, where K is the (fixed) inventory offset. Summing these
per-week values produces a much smaller number than the correct horizon need
because most weeks show 0 net requirement (inventory is sufficient that week).
The LP must instead apply the inventory offset once against the full horizon
gross demand — which is what the Aggregated Procurement Need helper shows.

Most weeks have gross demand but net requirement = 0. Procurement is triggered
only in the weeks and facilities where on-hand inventory plus safety stock
coverage is insufficient to meet that week's component need.

---

### Usage examples

```python
from inventory.procurement_summary import (
    get_component_requirements_summary_tool,
    get_procurement_status_summary_tool,
    get_aggregated_procurement_need_tool,
    get_procurement_planning_summary_tool,
    get_triggered_procurement_rows,
    get_procurement_requirement_drilldown,
)

# --- LP-facing outputs ---

# Horizon-level LP demand floor — what the LP actually optimizes
# "What is the total procurement need the LP is solving for?"
print(get_aggregated_procurement_need_tool())

# Filtered to one component (matches LP run for transistors)
print(get_aggregated_procurement_need_tool(product='transistors'))

# --- Weekly planning / drill-down outputs ---

# Gross BOM demand (before any inventory offset)
print(get_component_requirements_summary_tool())

# Week-by-week procurement trigger signal (NOT the LP demand floor)
print(get_procurement_status_summary_tool())

# Combined gross + weekly trigger in one output
print(get_procurement_planning_summary_tool())

# All triggered rows across all components and facilities
conn = psycopg2.connect(DATABASE_URL)
print(get_triggered_procurement_rows(conn))

# Drill down: one component, one facility, all forecast weeks
print(get_procurement_requirement_drilldown(conn, product='transistors', facility_id='FACILITY_3'))
conn.close()
```

**NOTE:** What is now being fed into LP:
 - For each product x facility, the LP demand is:
  - `D = max[0, TOTAL_GROSS_DEMAND + BACKORDERS (0) + SAFETY_STOCK − ON_HAND − SCHEDULED_RECEIPTS (0)]`

This is applied ONCE over the entire (20 week) planning horizon.

```python
from inventory.procurement_summary import (
    format_bom_translation,
    get_bom_translation_tool,
)

# Mode A — BOM recipe for a SKU (no connection needed via tool wrapper)
# "How does the BOM for SEMICONDUCTOR_6 break down?"
# "What components does SEMICONDUCTOR_6 require?"
print(get_bom_translation_tool('SEMICONDUCTOR_6'))

# Mode A via direct helper (caller manages connection)
conn = psycopg2.connect(DATABASE_URL)
print(format_bom_translation(conn, semiconductor_id='SEMICONDUCTOR_6'))

# Mode B — forecast-row explosion for a specific SKU × facility × week
# "Show me how the forecast for SEMICONDUCTOR_6 at FACILITY_2 is converted to component demand"
print(format_bom_translation(
    conn,
    semiconductor_id='SEMICONDUCTOR_6',
    facility_id='FACILITY_2',
    target_week_date='2024-03-04',
))
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

Stateful rolling depletion across forecast weeks:

```
Step 1 — Usable inventory above SS floor (computed once per facility × component):
  available_above_ss = max(0, on_hand + SR − BO − safety_stock)

Step 2 — Remaining usable inventory at the start of week N:
  remaining_N = max(0, available_above_ss − cumulative_gross_{weeks 1..N−1})
  Decreases each week as prior gross demand consumes the usable pool.

Step 3 — Net procurement requirement for week N:
  net_requirement_N = max(0, gross_N − remaining_N)
```

### Why safety stock is NOT added in Step 3

Safety stock is pre-deducted in Step 1 when computing `available_above_ss`. The semantics of `remaining_N = 0` are "the SS floor has been reached — no usable inventory remains above it." At that point `net_req = gross_N`, meaning all of this week's demand must be procured. Adding SS again per week would inflate requirements by `SS × (triggered weeks)` — SS is a one-time reserve, not a weekly target.

**Proof via LP reconciliation:**
When `on_hand >= SS`: `SUM(net_requirement_N) = SUM(gross) − available_above_ss = LP demand floor`. SS cancels identically.

### Planning week / horizon week

`horizon_week` in `vw_procurement_requirement` is a sequential integer (1 = first forecast week, up to 20 = last). It is computed as `ROW_NUMBER() OVER (PARTITION BY forecast_run_id, facility_id, product_key ORDER BY target_week_date)`. Shown alongside the calendar date in all weekly drill-down outputs.

---

## Interpreting On-Hand Inventory and Safety Stock in Planning Outputs

The values for on-hand inventory, safety stock, scheduled receipts, and backorders
behave differently from gross demand across the planning horizon. Understanding
this distinction prevents misreading the weekly drill-down outputs.

---

### Decision-point inventory snapshot

At the end of the historical simulation, a single **decision-point** inventory
state is recorded for each facility × component. This represents what is
available at the moment the planning horizon begins:

- **on_hand_qty** — stock physically on hand at the decision point; set to
  `safety_stock + one week of average demand (SS + μ_D)`
- **scheduled_receipts_qty** — quantity already on order and inbound; currently
  zero by design at the decision point
- **backorder_qty** — unfilled demand carried forward; currently zero by design
  at the decision point

These are **point-in-time values**. They do not change as the forecast advances
week by week — they capture the starting inventory position at the beginning of
the planning window.

---

### Safety stock

**safety_stock_qty** is a policy-computed buffer derived from historical demand
and lead-time statistics per facility × component. It represents the minimum
inventory cushion required to achieve the 95% service level target.

It is computed once per forecast run — not separately for each future week.
In all planning outputs it appears as a **fixed threshold** for a given facility
× component pair, identical across every row of the horizon.

---

### Why Starting OH and SS Floor look constant in weekly outputs

`on_hand_qty` (labelled **Starting OH**) and `safety_stock_qty` (labelled
**SS Floor**) do not change from week to week for a given facility × component.
**This is intentional** — both are decision-point snapshots taken once at the
beginning of the planning horizon.

The rolling depletion is captured in **Remaining** (`remaining_inventory`),
which decreases each week as gross demand consumes the usable pool above the SS
floor. `Starting OH` and `SS Floor` are shown as fixed reference context, not
as running balances.

**What changes week to week:**
- `gross_requirement` — the BOM-translated demand for that specific week
- `remaining_inventory` — how much usable stock is left at the start of this week
- `net_requirement` — demand that exceeds remaining (0 until the usable pool is exhausted)

---

### How the LP uses these values differently

The LP does not subtract on-hand inventory separately for each forecast week.
Instead, it applies the inventory offset **once** against the total horizon
gross demand per facility:

```
LP demand floor = max(0,
    SUM(gross_requirement across all forecast weeks)
  + backorder_qty  +  safety_stock_qty
  − on_hand_qty    −  scheduled_receipts_qty
)
```

When `on_hand >= SS` at the decision point, the **Aggregated Procurement Need**
(LP demand floor) equals `SUM(weekly net_requirement)` from Procurement Status
exactly — both formulas resolve to the same horizon total. If `on_hand < SS`,
the LP additionally captures the SS deficit, making LP D slightly larger.

---

### Cold-start vs decision-point (for reference)

The historical simulation begins with on_hand initialized at **65% of the
base-stock target** — a warm-up assumption to seed realistic early replenishment
behavior in the historical inventory trace.

The planning horizon uses a **separate decision-point snapshot** taken from the
final week of the historical simulation, where on_hand is anchored at
`SS + μ_D`. These are two distinct concepts that should not be confused:

| | What it is | Used for |
|---|---|---|
| Cold-start (65% × S) | Historical simulation warm-up | Generating representative inventory history |
| Decision-point snapshot (SS + μ_D) | Starting inventory at the planning horizon | Driving procurement requirements and LP demand floor |

All planning helpers and the LP use the **decision-point snapshot**, not the
cold-start value.

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