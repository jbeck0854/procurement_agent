# AI Procurement Decision Intelligence Agent — Demo Plan

> **Current as of:** Sprint ending 2026-03-29
> **Status:** All pipeline layers complete and validated. Agent/orchestration integration in progress.

---

## Overview

The demo shows a procurement manager moving from demand uncertainty to an actionable, optimized procurement plan — entirely through a conversational agent interface.

The pipeline the agent orchestrates:

```
Historical Finished-Goods Demand
    ↓
Forward Demand Forecast  (precomputed; triggerable live)
    ↓
BOM Translation → Component Requirements
    ↓
Inventory + Safety Stock Check → Net Procurement Requirement
    ↓
Supplier Comparison + Plots  (live, on demand)
    ↓
LP Optimization → Per-Product Allocation  (live, per product)
    ↓
Optional: Disruption / Urgency Rerun
    ↓
Session-Level Final Procurement Summary  (assembled by synthesizer)
```

---

## Demo Objective

Show that the agent can answer the five core procurement questions a manager actually faces:

1. What demand are we expecting over the planning window?
2. What components will we need to support that demand?
3. Do we already have enough inventory?
4. If not, what do we need to procure and how much?
5. Which suppliers should we use, at what mix, under what constraints?

And show one additional capability that differentiates the system:

6. What happens if a key supplier becomes unavailable?

---

## End-to-End Walkthrough

---

### 0:00–1:00 — Opening and objective framing

**User says:**
> "I need to make sure we can meet the next 12–16 weeks of demand for our semiconductor components. Minimize cost, but keep supplier risk at a moderate level."

**Agent responds:**
> "Understood. I'll walk you through five steps: forecast demand, translate that into component requirements, check inventory coverage, identify what needs to be procured, and recommend an optimized supplier allocation, based on your risk aversion. Let's start."

> (optional addition) Please provide/upload your historical demand csv begin demand forecast.

NOTE: Above is simply so that it is clear to audience that the system has/is working with actual demand
> (if optional route added) AGENT: Demand successfully stored. Here is your input: (shows on screen a few lines of first few weeks x facility x sku and last few week lines)

**On screen:**
A four-step workflow indicator:
1. Forecast demand
2. Translate to components
3. Check inventory
4. Recommend procurement plan

**Business explanation:**
> "The system doesn't just rank suppliers. It starts from assessing historical demand and works forward — so every procurement recommendation is grounded in what we actually need."

**What runs behind the scenes:** Nothing yet. Orientation only.

---

### 1:00–2:30 — Demand forecast

**User action:** "Please provide me a forecast for the upcoming planning horizon."

**Agent action:** Queries the forecast layer ( **forecast summary**). No rerun needed — forecasts are precomputed and stored.

**Behind the scenes:**
- `dim_forecast_run` — identifies latest run
- `fact_semiconductor_demand_forecast` — weekly forward demand by SKU and facility
- `fact_semiconductor_demand` — historical actuals for comparison

**On screen:**
#### 1) Forecast summary
Returns a clean planning-window summary of the latest production forecast, including:
- planning horizon
- total forecasted demand
- facility / SKU coverage
- weekly totals
- forecast metadata

Additional routes that can be taken here (user choice) **SEE THE HELPER FUNCTIONS (within /forecast) FOR IDEAS ON STRUCTURING PROFESSIONAL QUERIES FOR THESE**:
#### 2) Forecast drill-down
Returns week × facility × semiconductor detail for the production forecast, including:
- predicted demand
- lower / upper confidence bounds
- horizon week

This is used when the user wants to inspect:
- which SKUs are needed at which facilities
- where demand is concentrated
- how the forecast behaves across the horizon

NOTE: SOME SORT OF TREND CHART WITH A LEGEND FOR EACH OF THE FOUR FACILITIES MIGHT ACTUALLY BE USEFUL HERE (customer orders on y-axis and time on x)

#### 3) Forecast model assessment / explainability
Returns business-facing summaries and artifacts for:
- validation / training performance
- feature importance
- baseline comparison

This allows the agent to answer questions like:
- “How was the model trained and validated?”
- “What features drove the forecast most?”
- “How does the model compare to baseline approaches?”

### Why this matters

The forecasting layer now supports two distinct user needs:

1. **Operational planning**
   - What demand are we expecting?
   - Where is that demand located?
   - How uncertain is it?

2. **Model understanding**
   - Why should we trust the forecast?
   - What drives the prediction?
   - How much better is the model than simple baselines?

This separation helps the system feel like a real decision-support workflow rather than a single static output.

**Business explanation:**
> "We start by knowing what finished-goods demand looks like over the planning window. Then we convert that demand signal into the specific components we need to procure."

**Precomputed:** Yes — forecasts are already in the database.

---

### 2:30–3:45 — BOM translation to component requirements

**Agent action:** Converts finished-goods forecast into component-level demand.

**Behind the scenes:**
- `dim_bom` — BOM bridge from finished SKUs to procurement components
- `vw_component_requirement_detail` — exploded per-SKU component view
- `vw_component_requirement_lp` — aggregated full-horizon component demand

**Suggested user query #1 (summary):** "Show total component requirements for the next planning window."

**Agent returns:**
Full-horizon gross BOM demand — the raw component volume implied by the finished-goods forecast, before any inventory offset is applied.

| Component | Facilities | Full-Horizon Gross Demand |
|---|---|---|
| transistors | FACILITY_3, FACILITY_4 | large — driven by forecast volume × BOM multiplier |
| power_devices | FACILITY_3, FACILITY_4 | large — driven by forecast volume × BOM multiplier |
| integrated_circuit_components | multiple | large |
| microprocessors | multiple | small |

*Exact figures shown on screen from the helper output. These are gross demand totals — no inventory has been netted out yet.*

**Suggested query #2 (translation explainability):** "How does forecasted SKU demand translate into component demand?"

**Agent returns:**
BOM translation explainer — shows which components make up each finished SKU and the arithmetic that converts forecasted SKU volume into raw component need.

**Business explanation:**
> "This step shows what components we need to build the products our customers are expecting. Every finished unit requires a specific mix of inputs — the BOM tells us exactly how many of each. We now know what we need in total. The next step is whether we already have it."

**Precomputed:** Yes — BOM is loaded; outputs compute on query.

---

### 3:45–5:15 — Inventory sufficiency and net procurement requirement

**Agent action:** Checks projected component demand against current inventory, scheduled receipts, and safety stock — then surfaces the quantity the LP will actually optimize.

**Behind the scenes:**
- `inventory/run_inventory.py` — inventory simulation (already run; outputs in DB)
- `fact_component_inventory_history` — on-hand and pipeline inventory
- `fact_inventory_policy` — safety stock and base-stock targets

**Step 1 — Procurement Status (weekly trigger signal):**

Shows *where* and *when* procurement is activated across the planning horizon — the specific weeks and facilities where existing inventory falls short.

| Component | On-Hand | Safety Stock | Weekly Gross | Weekly Net | Status |
|---|---|---|---|---|---|
| transistors | ~X | ~Y | ~29,006 | ~29,006 | 🔴 Action required |
| power_devices | ~X | ~Y | ~12,815 | ~12,815 | 🔴 Action required |
| integrated_circuit_components | ... | ... | ~2,617 | ~2,617 | 🟡 Monitor |
| microprocessors | ... | ... | ~43 | ~43 | 🟢 Covered |

*These figures reflect triggered weeks only — the subset of the horizon where on-hand coverage is insufficient. Most weeks are covered; these are the gaps.*

> "This tells us which components have inventory shortfalls and which periods they occur. Transistors and power_devices require procurement action this cycle."

---

**Step 2 — Aggregated Procurement Need (LP demand floor):**

**Suggested query:** "Show aggregated procurement need for transistors."

**Agent returns:**
The horizon-level procurement need the LP will actually optimize against. The inventory offset (on-hand stock, safety stock, scheduled receipts) is applied once across the full horizon — not week by week — producing the correct total quantity to source from suppliers.

| Component | Horizon Gross Demand | Inventory Offset | LP Demand Floor |
|---|---|---|---|
| transistors | large | applied once | the optimizer's target |
| power_devices | large | applied once | the optimizer's target |

*Exact figures shown on screen. These are materially larger than the weekly trigger values — because the LP is sizing for the full planning horizon, not a single week.*

> "The LP optimization in the next step will allocate supplier volume to cover this total. The weekly trigger signal told us *where* procurement is needed; this tells us *how much* to buy in total."

**Precomputed:** Yes — inventory simulation already run; outputs compute on query.

---

## Explainability and Summary Helpers

`procurement_summary.py` provides business-facing, formatted outputs for the
inventory and procurement planning layer. It reads from pre-computed tables and
views only — no computational logic is changed. Its purpose is to improve
interpretability for demo delivery and agent integration.

---

### Summary helpers

**`format_component_requirements(conn, forecast_run_id=None) -> str`**
Full-horizon gross BOM demand. Shows the total component volume required to
fulfill the finished-goods forecast, before any inventory or safety stock
adjustment. Use this to understand the raw scale of procurement need.

**`format_procurement_status(conn, forecast_run_id=None) -> str`**
Week-by-week inventory trigger signal. Applies current on-hand inventory and
safety stock policy to BOM demand on a per-week basis. Shows *where* and *when*
procurement is activated across the planning horizon. This is NOT the LP demand
floor — the LP applies the inventory offset once at the horizon level, not per
week. Use this to understand which weeks and facilities are driving procurement
need.

**`format_aggregated_procurement_need(conn, forecast_run_id=None, product=None, facility_id=None) -> str`**
Horizon-level LP demand floor. Applies the inventory offset (on-hand, safety
stock, scheduled receipts) once against the total horizon gross demand per
facility — the same formulation the LP uses internally. This is the quantity the
optimizer allocates across suppliers. Use this to understand what the LP is
actually optimizing, and to verify LP allocation totals against planning need.

---

### LangChain wrappers

Each wrapper opens and closes its own DB connection. `forecast_run_id=0`
retrieves the most recent run.

| Wrapper | Returns |
|---|---|
| `get_component_requirements_summary_tool(forecast_run_id=0)` | Full-horizon gross BOM demand |
| `get_procurement_status_summary_tool(forecast_run_id=0)` | Week-by-week procurement trigger signal (NOT LP input) |
| `get_procurement_planning_summary_tool(forecast_run_id=0)` | Both gross demand and weekly trigger signal in sequence |
| `get_aggregated_procurement_need_tool(forecast_run_id=0, product='', facility_id='')` | Horizon-level LP demand floor — the quantity the LP optimizes |

---

### Drill-down helpers

**`get_procurement_requirement_drilldown(conn, forecast_run_id=None, product=None, facility_id=None) -> str`**
Full week-by-week planning detail at the component × facility × week level.
Accepts optional filters by product name and facility. Use this to trace the
complete planning math for any component across all forecast weeks.

**`get_triggered_procurement_rows(conn, forecast_run_id=None, product=None, facility_id=None) -> str`**
Only weeks and facilities where net requirement > 0 — the specific gaps where
existing inventory is insufficient. Accepts the same optional filters. Use this
to isolate where and when procurement is triggered.

---

### Key conceptual distinctions

| Output | What it represents | LP input? |
|---|---|---|
| **Component Requirements** | Full-horizon gross BOM demand — all weeks, before any inventory offset | No — gross only |
| **Procurement Status** | Week-by-week trigger signal — shows WHERE and WHEN procurement activates | No — weekly signal |
| **Triggered rows** | Subset of weekly rows where net requirement > 0 | No — weekly subset |
| **Aggregated Procurement Need** | Horizon-level net requirement, inventory offset applied once per facility | **Yes — LP demand floor** |

Most weeks have gross demand but zero net requirement. The weekly trigger signal
shows the shortfall weeks. The LP does not sum these per-week values — it
computes the correct horizon total by applying the inventory offset once against
the full gross demand, which is materially larger than the sum of triggered-week
net values.

---

### Usage examples

```python
from inventory.procurement_summary import (
    get_aggregated_procurement_need_tool,
    get_procurement_planning_summary_tool,
    get_triggered_procurement_rows,
    get_procurement_requirement_drilldown,
)

# LP demand floor — what the optimizer actually allocates against
print(get_aggregated_procurement_need_tool())

# Filtered to one component (matches LP run scope)
print(get_aggregated_procurement_need_tool(product='transistors'))

# Gross demand + weekly trigger signal (planning context, not LP input)
print(get_procurement_planning_summary_tool())

# All triggered rows across all components and facilities
conn = psycopg2.connect(DATABASE_URL)
print(get_triggered_procurement_rows(conn))

# Drill down: one component, one facility, all forecast weeks
print(get_procurement_requirement_drilldown(conn, product='transistors', facility_id='FACILITY_3'))
conn.close()
```
---

### 5:15–6:00 — Side-track: ad hoc supplier comparison (Probably don't need this anymore since these suppliers plot comparison should show for each LP Inventory Optimization run below)

*This segment demonstrates the agent handles interruptions without losing context.*

**User asks:**
> "Before we go further — show me the top suppliers for transistors. I want to see how they compare on price stability and delivery risk."

**Agent responds:**
> "Switching to supplier analysis for transistors. I'll return to the procurement plan after."

**Behind the scenes:**
- `demo/tools/scoring.py` → `score_suppliers(product="transistors")`
- `demo/tools/chart_tools.py` → one or two of:
  - `plot_supplier_comparison(product="transistors")`
  - `plot_score_breakdown(product="transistors")`
  - `plot_price_vs_commodity(product="transistors")`
  - `plot_volatility_trend(product="transistors")`

**On screen:**
- Supplier comparison panel (cost, risk, compliance, lead time)
- Score breakdown panel if time permits

**Agent explains:**
> "SUP_HKG_38 is the lowest unit cost. SUP_CAN_10 is competitive on cost and well-balanced on risk. Several suppliers were excluded by the compliance threshold. I can now return to the procurement plan."

**Then agent says:**
> "Returning to the optimization workflow."

**Why this matters:** Shows the system is conversational and context-aware, not a rigid pipeline.

**Precomputed:** No — scored live, charts rendered live. Fast enough for demo.

---

### 6:00–7:30 — LP optimization: transistors

**User says:**
> "Optimize transistors procurement with moderate risk and a 40% supplier cap."

**Agent action:** Runs LP optimization for transistors using the net procurement requirement from the inventory layer and the scored supplier universe.

**Behind the scenes:**
- Horizon-level aggregated procurement need (computed from full-horizon gross demand with inventory offset applied once) — the LP demand floor
- `vw_supplier_complete_profile` + `analytics/scoring.py` — supplier scoring layer
- `optimization/run_lp_optimization.py` → `run(LPParams(product="transistors", lambda_risk=0.50, max_supplier_share=0.40))`

The LP solves: minimize total cost weighted by risk exposure, subject to demand coverage, compliance filter, and concentration limit. It is not a ranking — it determines how much to buy from each supplier. The demand it covers is the full horizon procurement need, not the weekly triggered signal from the inventory step.

**Parameter explainability (shown to audience):**

| Parameter | Value | Business meaning |
|---|---|---|
| `lambda_risk` | 0.50 | Balanced — cost and supplier risk weighted equally |
| `max_supplier_share` | 40% | No single supplier may supply more than 40% of volume |
| `service_level_target` | 1.00 | Procure exactly what the net requirement specifies |
| `compliance_threshold` | 60% | Suppliers below this score are excluded before the LP runs |
| `budget_cap` | none | No hard spend ceiling applied this run |

`lambda_risk` is not a math formula — it is a business dial. At 0, the optimizer picks the cheapest option regardless of risk. At 1, it treats risk penalty as equal in weight to cost. At 0.5, it balances both. The audience does not need to see the formula.

**On screen:**
- Supplier allocation table: supplier ID, country, quantity allocated, share %, landed unit cost, risk score, total cost contribution
- Supplier pool summary: total eligible → compliance excluded → LP selected
- Cost summary: total cost, avg landed unit cost, avg risk penalty, risk-adjusted total
- LP `executive_summary` field (surfaced directly from result dict — no LLM call)
- Formula description: plain-language explanation of the optimization run

**Agent explanation:**
> "The LP allocated transistors volume across three suppliers. The 40% cap prevents overconcentration — no single country or supplier absorbs the full order. Two suppliers were excluded by compliance threshold before the LP ran; they were never eligible. The allocation reflects the lowest-cost mix that also meets your risk tolerance."

**Live run:** Yes — CBC solver is sub-second for this problem size.

---

**Additional user queries the agent handles here (show one or two live):**

- > "Optimize for FACILITY_3 only" → reruns LP with `facility_id="FACILITY_3"` scope
- > "Limit any supplier to 30% of volume" → reruns with `max_supplier_share=0.30`
- > "Increase risk aversion slightly" → reruns with `lambda_risk=0.70`
- > "Exclude SUP_HKG_38" → reruns with `exclude_supplier_ids=["SUP_HKG_38"]`
- > "Diversify across countries" → reruns with `diversification_mode="country_diversified"` (MIP: exactly 3 suppliers, each from a different country, ~33% each)

Each rerun is a one-parameter change — the audience sees that the system is responsive, not a static report.

---

**Session-state behavior (important for the transition ahead):**

Each LP run result is stored in the agent session under `approved_lp_runs`. The agent prompts the user to approve or discard each run before it is committed. Only approved runs are carried forward.

This means the demo can now hold:
- the baseline transistors run (moderate risk, 40% cap)
- an optional disruption rerun (SUP_HKG_38 excluded)
- an optional power_devices run

All approved runs will be aggregated in the final session summary — alongside a baseline comparison showing how much additional cost the diversification and risk constraints added over the cheapest feasible unconstrained plan.

---

### 7:30–8:00 — Disruption / what-if scenario

**User asks:**
> "What if SUP_HKG_38 becomes unavailable next quarter?"

**Agent action:** Reruns the transistors LP with `exclude_supplier_ids=["SUP_HKG_38"]`.

**Behind the scenes:**
- Same LP pipeline as above
- `LPParams(product="transistors", exclude_supplier_ids=["SUP_HKG_38"], lambda_risk=0.50, max_supplier_share=0.40)`

**On screen:**
- Updated allocation table (SUP_HKG_38 absent)
- Change in total cost vs. baseline run
- Any binding constraint changes (e.g. share constraint now forces different mix)
- LP executive_summary reflecting exclusion

**Agent explanation:**
> "With SUP_HKG_38 excluded, volume redistributes to the remaining eligible suppliers. Total cost increases by approximately X%. The plan remains feasible — no stockout risk — but the risk profile shifts slightly."

**Live run:** Yes — fast rerun, CBC solver is sub-second for this problem size.

### 8:00 - 8:30 - Optional: urgency mode
*Run only if time permits. Can be shown as a quick toggle*

**User asks:**

"What if we need this faster — we're behind schedule on this cycle?"

**Agent action:** Reruns transistors LP with urgency=True.

**Behind the scenes:**

 - Same LP pipeline
 - Objective coefficient applies an additional normalized lead-time premium:
    - `cost × (1 + λ_risk × risk_norm + λ_urgency × lead_time_mean_norm)`
    - where λ_urgency = 0.25
 - lead_time_mean_norm ∈ [0,1] (0 = fastest supplier, 1 = slowest in the eligible pool)
 - No suppliers are removed — urgency only adjusts relative attractiveness

**On screen:**

- Updated allocation (shifts toward faster suppliers if lead-time differences are meaningful)
- formula_description noting urgency mode active and showing λ_urgency
- executive_summary with urgency flag and explanation of speed tradeoff

**Agent explanation:**

> "In urgency mode, we apply a delivery-speed premium on top of cost and risk. Faster suppliers are unaffected, while slower suppliers become relatively more expensive — up to about 25% higher for the slowest option. This keeps all suppliers feasible, but makes the tradeoff between cost and speed explicit in the optimization."

---

### 8:30–9:30 — Session-level final summary

**Agent action:** After all LP runs are complete (transistors, and optionally power_devices), the synthesizer assembles the session-level summary.

**Behind the scenes:**
- `demo/graph/synthesizer.py` reads all `agent_results["lp_*"]` entries
- Aggregates: total cost, total LP-allocated units, products with action, products infeasible
- Generates `session_narrative` — a 2–3 sentence plain-language wrap-up

**On screen:**

```
FINAL PROCUREMENT PLAN — PLANNING WINDOW: WEEKS 146–158

Components requiring action:      2 of 4
Total units to procure:           ~X,XXX,XXX  (horizon-level LP allocation)
Total estimated cost:             $X,XXX,XXX
Average risk penalty (norm):      0.XXX

TRANSISTORS    ~X,XXX,XXX units  $X,XXX,XXX  3 suppliers  Optimal
POWER_DEVICES  ~X,XXX,XXX units  $X,XXX,XXX  X suppliers  Optimal

Inventory posture after plan:     Covered at 95% SL
Compliance posture:               All allocations above 60% threshold
Single-source risk:               0 products (diversification active)
```

*Note: unit totals reflect the horizon-level LP demand floor — the full planning period quantity the optimizer allocated across suppliers, not the weekly trigger signal shown in the inventory step.*

**Session narrative (generated by synthesizer LLM):**
> "We forecast 12–16 weeks of finished-goods demand, translated that into component requirements, and confirmed that transistors and power_devices require procurement action this cycle. The LP optimizer allocated the full horizon procurement need across suppliers under moderate risk weighting with diversification enforced. Total estimated procurement spend is $X,XXX,XXX across X suppliers."

**Note:** The LP-level `executive_summary` for each product is passed through as-is into the session summary table. The session narrative is the only new LLM-generated text at this stage. **Also compares a baseline optimization that prioritizes complete cost minimization against a more diversified and risk-minimized run** — showing how much the active constraints added in cost and how many more suppliers or countries they introduced. (see optimization/README.md for this exact augmentation if needed for agent integration)

---

### 9:30–10:00 — Closing

**Agent presents final output.** One screen showing:
- Demand covered: ✓
- Components identified: ✓
- Inventory checked: ✓
- Procurement requirement quantified: ✓
- Supplier allocations recommended: ✓
- Disruption scenario tested: ✓
- Selected Suppliers (a plot call)

NOTE: This section is essentially merged/works in with the final exectuive summary.

**Closing line:**
> "The system moved from historical demand to an optimized, feasible procurement plan — accounting for inventory, supplier risk, compliance, and resilience constraints — in a single session."

---

## Behind-the-Scenes Objects by Stage

see relevant */README.md files in forecasting/, inventory/, and optimization/.