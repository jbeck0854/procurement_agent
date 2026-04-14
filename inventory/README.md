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

## Demo-Facing Routes

The Streamlit demo (`demo/streamlit_app.py`) exposes three primary inventory-layer routes, backed by query helpers in `demo/tools/pipeline_queries.py`. These are the entry points for all live demo interaction with the inventory and procurement planning layer.

---

### Primary demo routes

#### Route 1 — Horizon-level procurement summary

**Trigger phrases:** "What is the total procurement need?", "How much do we need to procure?", "Show me the aggregated procurement need", "LP demand floor"

**Backend:** `query_procurement_summary_data()` → `vw_component_requirement_lp`

Returns a structured table with one row per facility × component. Columns:

| Column | Meaning |
|---|---|
| Facility | Facility ID |
| Component | Procurement component name |
| Total Gross Demand | Sum of BOM-translated finished-good demand across the 20-week horizon |
| On-Hand Inventory | Usable on-hand at the decision point (OH − SS already offset in LP formula) |
| Safety Stock (+) | Policy-computed SS reserve added back to LP demand |
| LP Net Requirement | Horizon-level procurement quantity the LP optimizes (`max(0, gross + SS − OH − SR + BO)`) |
| Action | `BUY` / `HOLD` |

This is the quantity the LP optimizer allocates across suppliers. Use this to answer: *"How much do we need to buy?"*

---

#### Route 2 — Weekly procurement trigger view

**Trigger phrases:** "When is procurement triggered?", "Which weeks trigger procurement?", "Where and when do we actually need to buy?", "Weekly procurement trigger", "Triggered rows"

**Backend:** `query_triggered_rows_structured()` → `vw_procurement_requirement WHERE net_requirement > 0`

Returns only the weeks where procurement is actually required (`net_requirement > 0`). Columns displayed:

| Column | Meaning |
|---|---|
| Forecast Week | Horizon position (1–20), sourced from `horizon_week` in `vw_procurement_requirement` |
| Week | Calendar date of the planning week |
| Component | Procurement component |
| Facility | Facility ID |
| Gross Requirement | BOM-translated demand for this week |
| Available Inventory Before Demand | `remaining_inventory` — how much usable stock was left at the start of this week (rolling: decreases each week as prior demand is consumed) |
| Direct Procurement Needed | `net_requirement` — demand that exceeded remaining usable stock |
| Cumulative Procurement Pressure | Running sum of Direct Procurement Needed per facility × component |
| Safety Stock Utilization (%) | Cumulative Procurement Pressure ÷ Safety Stock Reserve × 100 |
| Urgency Level | Critical (≥100%) / High (≥75%) / Moderate (≥50%) / Low (<50%) |

A companion safety stock context block shows the protected SS floor per facility × component.

**Filterable** by Facility and Component via multiselect widgets.

---

#### Route 3 — Safety stock / base-stock policy explainability

**Trigger phrases:** "How is safety stock calculated?", "Explain safety stock policy", "How does base stock policy work?", "Safety stock formula", "Explain the inventory policy"

**Backend:** Pure-text route (no DB query). Returns a structured explanation of:
- Policy type (periodic review / order-up-to)
- Safety stock formula and parameters
- Base-stock target formula
- Decision-point snapshot design choices
- How SS feeds into the weekly trigger and LP demand floor

---

#### Route 4 — Full horizon drilldown (diagnostic)

**Trigger phrases:** "Full horizon drilldown", "Full planning detail", "Full inventory planning", "All demand weeks across", "Planning horizon drilldown"

**Backend:** `query_full_horizon_drilldown()` → `vw_procurement_requirement` (all rows, no filter)

Returns all 20-week horizon rows — both triggered and non-triggered — for every facility × component. Includes a `Triggered?` column (`Yes`/`No`) and the `Safety Stock (Protected Floor)` reference column. Use this for tracing the full rolling depletion math, not as a primary demo output.

---

### Key conceptual distinctions

| Demo output | What it represents | LP input? |
|---|---|---|
| **BOM Translation** | How a finished-good SKU maps to procurement components; gross demand for a specific SKU × facility × week | No — gross recipe |
| **Component Requirements** | Full-horizon gross BOM demand summed across all SKUs — before any inventory offset | No — gross only |
| **Weekly Trigger View** | Specific weeks and facilities where `net_requirement > 0`; shows rolling depletion with urgency signals | No — weekly timing signal |
| **Horizon Procurement Summary** | LP demand floor: inventory offset applied ONCE per facility over the full 20-week horizon | **Yes — this is what the LP optimizes** |
| **LP Allocation** | Supplier-level allocation of the LP demand floor, produced by `run_lp_optimization.py` | Output |

**Why the distinction matters:**
`vw_procurement_requirement` uses stateful rolling depletion — inventory is consumed week by week until exhausted, then procurement is triggered. Most weeks show `net_requirement = 0` because inventory covers demand. Summing weekly net requirements equals the LP demand floor when `on_hand ≥ SS` (proven by formula). The LP applies this offset once at the horizon level; the weekly trigger view shows the timing of when that demand pressure materializes.

---

### Cross-layer flow

```
Finished-goods forecast
    ↓  (BOM explosion: finished-good demand × component qty-per-unit)
Gross component demand  [vw_component_requirement_detail / _lp]
    ↓  (inventory offset: on_hand + SR − BO − SS, applied ONCE per facility)
LP demand floor  [vw_component_requirement_lp → horizon procurement summary]
    ↓  (rolling depletion week-by-week: remaining_N decrements)
Weekly trigger timing  [vw_procurement_requirement WHERE net_req > 0]
    ↓
LP optimization  [run_lp_optimization.py]
    ↓
Supplier allocation
```

---

### LP demand floor formula

Applied ONCE over the 20-week planning horizon, per facility × product:

```
LP demand floor = max(0,
    SUM(gross_requirement across forecast horizon)
  + backorder_qty  +  safety_stock_qty
  − on_hand_qty    −  scheduled_receipts_qty
)

available_above_ss = max(0, on_hand + SR − BO − safety_stock)
LP demand floor    = max(0, SUM(gross) − available_above_ss)
```

At the decision point: `BO = 0`, `SR = 0`, `OH = SS + 8×μ_D`. LP demand floor = `max(0, SUM(gross) − 8×μ_D)`.

---

### BOM translation explainability helper

**`format_bom_translation(conn, semiconductor_id, forecast_run_id=None, facility_id=None, target_week_date=None) -> str`**

Two modes:

**Mode A — SKU-level BOM recipe** (`semiconductor_id` only): shows which components make up one unit of the SKU and the required quantity per unit.

**Mode B — Forecast-row explosion** (all args provided): takes one forecast week's finished-good demand, applies BOM multipliers, shows resulting gross component requirement. Output is gross demand before any inventory or SS offset.

---

### Diagnostic helpers (not primary demo routes)

These helpers exist in `inventory/procurement_summary.py` and remain available for validation and deep-dive analysis. They are not invoked in the primary demo flow.

| Helper | Returns |
|---|---|
| `format_procurement_recommendation(conn)` | One-screen buy/no-buy status per component (LP net req + triggered week count) |
| `format_procurement_status(conn)` | Full week-by-week inventory trigger signal for all components |
| `format_procurement_planning_summary(conn)` | Gross demand + weekly trigger signal in sequence |
| `format_component_requirements(conn)` | Raw gross BOM demand before any inventory offset |
| `get_procurement_requirement_drilldown(conn)` | All horizon rows (triggered + non-triggered) at facility × component × week grain |

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
  `SS + 8 × μ_D` (safety stock floor plus one full review period of average
  demand), providing roughly 8 weeks of usable inventory above the SS floor
  before procurement is triggered
- **scheduled_receipts_qty** — quantity already on order and inbound; currently
  zero by design at the decision point
- **backorder_qty** — unfilled demand carried forward; currently zero by design
  at the decision point

These are **point-in-time values**. They do not change as the forecast advances
week by week — they capture the starting inventory position at the beginning of
the planning window.

**Why `SS + 8 × μ_D` is used at the decision point:**
The formula represents a controlled but not overstocked planning state:
- `SS` is the protected safety buffer (never consumed during planning)
- `8 × μ_D` is one full review period (`r = 8 weeks`) of average weekly demand
- Usable inventory above the SS floor = `8 × μ_D`

This initialization means the first ~8 weeks of the forecast horizon are covered
by existing inventory, and procurement is triggered in later weeks where demand
exhausts that usable pool. It produces nontrivial LP demand without the
artificial extreme of triggering procurement immediately in week 1.

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

The historical simulation begins with on_hand initialized at **95% of the
base-stock target** — a near-steady-state assumption that avoids artificial
early procurement triggers in the historical inventory trace.

The planning horizon uses a **separate decision-point snapshot** that overrides
the final week of the historical simulation. These are two distinct concepts:

| | What it is | Used for |
|---|---|---|
| Cold-start (95% × S) | Historical simulation warm-up | Generating representative inventory history |
| Decision-point snapshot (SS + 8 × μ_D) | Starting inventory at the planning horizon | Driving procurement requirements and LP demand floor |

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