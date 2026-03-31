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
- `vw_component_requirement_lp` — LP-ready aggregated component demand

**Suggested user query #1 (summary): "Show total component requirements for the next planning window:"**

**Agent Returns:**
Component requirement summary by product type:

| Component | Facility | Gross Requirement |
|---|---|---|
| transistors | FACILITY_3, FACILITY_4 | ~29,000 units |
| power_devices | FACILITY_3, FACILITY_4 | ~12,800 units |
| integrated_circuit_components | ... | ~2,600 units |
| microprocessors | ... | ~43 units |

**Suggested Query type 2 (translation explainability):** "How does forecasted SKU demand translate into component demand?"

**Agent returns**:
BOM translation explainer helper

**Business explanation:**
> "This step converts finished-good demand into the specific input components we actually buy from suppliers. We now know what we need — the next step is whether we already have it."

**Precomputed:** Yes — BOM is loaded; views compute on query.

---

### 3:45–5:15 — Inventory sufficiency and net procurement requirement

**Agent action:** Checks projected component demand against current inventory, scheduled receipts, and safety stock.

**Behind the scenes:**
- `inventory/run_inventory.py` — generates inventory simulation (already run; outputs in DB)
- `fact_component_inventory_history` — on-hand and pipeline inventory
- `fact_inventory_policy` — safety stock and base-stock targets
- `vw_procurement_requirement` — net procurement requirement view

**On screen:**
For the top two components (transistors, power_devices):

| Component | On-Hand | Safety Stock | Gross Req | Net Req | Status |
|---|---|---|---|---|---|
| transistors | ~X | ~Y | ~29,006 | ~29,006 | 🔴 Action required |
| power_devices | ~X | ~Y | ~12,815 | ~12,815 | 🔴 Action required |
| integrated_circuit_components | ... | ... | ~2,617 | ~2,617 | 🟡 Monitor |
| microprocessors | ... | ... | ~43 | ~43 | 🟢 Covered |

**Business explanation:**
> "This is where the forecast becomes a procurement signal. The system compares what we need against what we have — including safety stock buffers — and tells us what must actually be purchased. Only transistors and power_devices require significant procurement action this cycle."

**Precomputed:** Yes — inventory simulation already run; `vw_procurement_requirement` queries live.

ADDITIONS FOR MORE EXPLAINABLE OUTPUT (JUST NEED TO FIGURE OUT HOW TO SMOOTHLY INTEGRATE INTO DEMO RUN AND PROPER QUERIES):

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
- `vw_procurement_requirement` — net requirement input (already computed upstream)
- `vw_supplier_complete_profile` + `analytics/scoring.py` — supplier scoring layer
- `optimization/run_lp_optimization.py` → `run(LPParams(product="transistors", lambda_risk=0.50, max_supplier_share=0.40))`

The LP solves: minimize total cost weighted by risk exposure, subject to demand coverage, compliance filter, and concentration limit. It is not a ranking — it determines how much to buy from each supplier.

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
- Aggregates: total cost, total units, products with action, products infeasible
- Generates `session_narrative` — a 2–3 sentence plain-language wrap-up

**On screen:**

```
FINAL PROCUREMENT PLAN — PLANNING WINDOW: WEEKS 146–158

Components requiring action:      2 of 4
Total units to procure:           ~41,821
Total estimated cost:             $X,XXX
Average risk penalty (norm):      0.XXX

TRANSISTORS    29,006 units  $3,054  3 suppliers  Optimal
POWER_DEVICES  12,815 units  $X,XXX  X suppliers  Optimal

Inventory posture after plan:     Covered at 95% SL
Compliance posture:               All allocations above 60% threshold
Single-source risk:               0 products (diversification active)
```

**Session narrative (generated by synthesizer LLM):**
> "We forecast 12–16 weeks of finished-goods demand, translated that into component requirements, and confirmed that transistors and power_devices require procurement action this cycle. An optimized supplier allocation plan has been generated for both components under moderate risk weighting with diversification enforced. Total estimated procurement spend is $X,XXX across X suppliers."

**Note:** The LP-level `executive_summary` for each product is passed through as-is into the session summary table. The session narrative is the only new LLM-generated text at this stage. **Also compares a baseline optimization that prioritizes complete cost minimization against a more diversified and risk-minimized run.** (see optimization/README.md for this exact augmentation if needed for agent integration)

---

### 9:30–10:00 — Closing

**Agent presents final output.** One screen showing:
- Demand covered: ✓
- Components identified: ✓
- Inventory checked: ✓
- Procurement requirement quantified: ✓
- Supplier allocations recommended: ✓
- Disruption scenario tested: ✓

**Closing line:**
> "The system moved from historical demand to an optimized, feasible procurement plan — accounting for inventory, supplier risk, compliance, and resilience constraints — in a single session."

---

## Behind-the-Scenes Objects by Stage

see relevant */README.md files in forecasting/, inventory/, and optimization/.