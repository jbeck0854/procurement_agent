# AI Procurement Decision Intelligence Agent — Demo Plan

> **Current as of:** Sprint ending 2026-04-08
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

**IMPORTANT:**

Before kickstarting demo and initializing streamlit, in terminal (after all database schemas loaded), must run in order:

```bash
# 0. activate venv
source demo/venv/bin/activate

# 1 for model-trust and explainability routes (from project root)
python -m forecasting.run_pipeline
python -m forecasting.run_baseline

# 2. generate forecasts (from project root)
python -m forecasting.run_production

# 3. build inventory / procurement layer (from project root)
python -m inventory.run_inventory

# 4. THEN start demo
cd demo
streamlit run streamlit_app.py
```


---

### 0:00–1:00 — Opening and objective framing

**User says:**
> "I need to make sure we can meet the next 12–16 weeks of demand for our semiconductor components. Minimize cost, but keep supplier risk at a moderate level."

**Other acceptable user variations:**
> "Help me plan procurement for the upcoming 20 week planning horizon with a balance between cost and reliability."

**Agent responds:**
> "Understood. We will:
> 1. Verify your historical demand across all four facilities and semiconductor SKUs
> 2. Translate that demand into the exact component requirements needed to support production
> 3. Assess inventory coverage and identify where procurement is required
> 4. Optimize supplier allocation to minimize cost while controlling supplier risk and disruption

> Your objective balances cost efficiency with supply reliability:
> - lower emphasis prioritizes cost minimization
> - higher emphasis prioritizes more stable, lower-risk suppliers even if slightly more expensive

> Let's begin by validating the historical demand that drives this workflow.

> Please review the historical demand file below and confirm it looks correct. Once reviewed, reply with 'Yes, proceed' to continue."

NOTE: Above is simply so that it is clear to audience that the system has/is working with actual demand

**Business explanation (subject to change):**
> "The system doesn't just rank suppliers. It starts from assessing historical demand and works forward — so every procurement recommendation is grounded in what we actually need."

**What runs behind the scenes:** Nothing yet. Orientation only.

---

### 1:00–2:30 — Demand forecast

**User action:** "Yes, proceed."

**Agent Response:** "I will now generate forecasts over the upcoming planning horizon (20-week period), based on your historical demand data."

**Agent action:** Queries the forecast layer ( **forecast summary**). No rerun needed — forecasts are precomputed and stored.

**NOTE:** Here is where I am considering implementing a returned table that shows average forecasted demand for each facility over the 20-week period.

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

Additional routes that can be taken here (user choice) 

**(Optional) CALLS FOR MODEL ASSESSMENT AND VALIDATION OF FORECASTS**:
> **User:** "Show me the forecast detail by facility and SKU."

> **User:** "Show me the forecast detail for Facility 1"

> **User:** "Compare forecast demand across all facilities"

> **User:** "Are these forecasts reliable? How was the model trained and validated?"

> **User:** "How does this model stack up against a baseline model?" 

**SEE THE HELPER FUNCTIONS (within /forecast) FOR IDEAS ON STRUCTURING PROFESSIONAL QUERIES FOR THESE**:
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

**NOTE:** The system implicitly adopts a two-layer risk handling strategy:

 - Inventory layer handles demand uncertainty via safety stock (σ_D-based buffering)
 - Optimization layer assumes deterministic demand and focuses on supplier-side risk


---

### 2:30–3:45 — BOM translation to component requirements

**Agent action:** Converts finished-goods forecast into component-level demand.

**Behind the scenes:**
- `dim_bom` — BOM bridge from finished SKUs to procurement components
- `vw_component_requirement_detail` — exploded per-SKU component view
- `vw_component_requirement_lp` — aggregated full-horizon component demand

**Suggested user query #1 (summary):** "Show total component requirements for the upcoming demand window."

**Agent returns:**
Full-horizon gross BOM demand — the raw component volume implied by the finished-goods forecast, before any inventory offset is applied.

| Component | Facilities | Full-Horizon Gross Demand |
|---|---|---|
| transistors | FACILITY_3, FACILITY_4 | large — driven by forecast volume × BOM multiplier |
| power_devices | FACILITY_3, FACILITY_4 | large — driven by forecast volume × BOM multiplier |
| integrated_circuit_components | multiple | large |
| microprocessors | multiple | small |

*Exact figures shown on screen from the helper output. These are gross demand totals — no inventory has been netted out yet.*

**Suggested query #2 (translation explainability):** "How exactly is forecasted SKU demand translated into component demand?"

**Agent returns:**
BOM translation explainer — shows which components make up each finished SKU and the arithmetic that converts forecasted SKU volume into raw component need.

**Business explanation:**
> "This step shows what components we need to build the products our customers are expecting. Every finished unit requires a specific mix of inputs — the BOM tells us exactly how many of each. We now know what we need in total. The next step is whether we already have it."

**Precomputed:** Yes — BOM is loaded; outputs compute on query.

---

### 3:45–5:15 — Inventory sufficiency and net procurement requirement

**User:** "After our inventory is factored in, what is the total amount that needs to be ordered for each component to meet our upcoming demand?"

**Agent:** Returns a clean horizon-level net procurement summary table.

--

**User:** "In which weeks and where is procurement actually triggered across the planning horizon?"

**Agent:** 
Shows *where* and *when* procurement is activated across the planning horizon using stateful rolling depletion.

--

**User:** "How does the base stock policy work"

**Agent:** Details Safety Stock and Base-Stock Logic set in place

--

*optional transparency full-horizon drilldown query*
**User:** "Show all upcoming demand weeks across each facility for inventory planning"

**Agent:** returns filterable table for inventory planning. All week x facility x component combinations, with trigger indicator.

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
> "From our available suppliers, provide a procurement plan to ensure we have enough integrated circuit components across all facilities to meet our upcoming demand window. Implement a moderate risk aversion supply strategy. No supplier should exceed 40% of total supply volume for this order."

**Agent action:** Runs LP optimization for integrated circuit components using the net procurement requirement from the inventory layer and the scored supplier universe.

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
> "The LP allocated integrated circuit component volume across three suppliers. The 40% cap prevents overconcentration — no single country or supplier absorbs the full order. X suppliers were excluded by compliance threshold before the LP ran; they were never eligible. The allocation reflects the lowest-cost mix that also meets your risk tolerance."

**Live run:** Yes — CBC solver is sub-second for this problem size.

---

*Users sees that some weeks arent covered*

**User:** "We need to expedite this component"

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

This run is a one-parameter (other modifications possible) change — the audience sees that the system is responsive, not a static report.

---

**Session-state behavior (important for the transition ahead):**

Each LP run result is stored in the agent session under `approved_lp_runs`. The agent prompts the user to approve, modify or discard each run before it is committed. Only approved runs are carried forward towards final executive summary.

This means the demo can now hold:
- the baseline transistors run (moderate risk, 40% cap)
- an optional disruption rerun (SUP_HKG_38 excluded)
- an optional power_devices run

All approved runs will be aggregated in the final session summary — alongside a baseline comparison showing how much additional cost the diversification and risk constraints added over the cheapest feasible unconstrained plan.

---

### 7:30–8:30 — Disruption / what-if scenario

**User first asks:** From our available suppliers, provide a procurement plan to ensure we have enough transistors across all facilities to meet our upcoming demand window. Implement a moderate risk aversion supply strategy. No supplier should exceed 35% of total supply volume for this order

**User then asks:**
> "What if SUP_HKG_38 becomes unavailable next quarter?"

**Agent action:** Reruns the transistors LP with `exclude_supplier_ids=["SUP_HKG_38"]`.

**Behind the scenes:**
- Same LP pipeline as above
- `LPParams(product="transistors", exclude_supplier_ids=["SUP_HKG_38"], lambda_risk=0.50, max_supplier_share=0.35)`

**On screen:**
- Updated allocation table (SUP_HKG_38 absent)
- Change in total cost vs. baseline run
- Any binding constraint changes (e.g. share constraint now forces different mix)
- LP executive_summary reflecting exclusion

**Agent explanation:**
> "With SUP_HKG_38 excluded, volume redistributes to the remaining eligible suppliers. Total cost increases by approximately X%. The plan remains feasible — no stockout risk — but the risk profile shifts slightly."

**Live run:** Yes — fast rerun, CBC solver is sub-second for this problem size.

--

### 8:30–9:30 — Session-level final summary

**Agent action:** After all LP runs are complete (integrated circuit components, transistors, and potentially one other), the synthesizer assembles the session-level summary.

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
> "We forecast 20 weeks of finished-goods demand, translated that into component requirements, and confirmed that transistors and power_devices require procurement action this cycle. The LP optimizer allocated the full horizon procurement need across suppliers under moderate risk weighting with diversification enforced. Total estimated procurement spend is $X,XXX,XXX across X suppliers."

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
> "The system moved from historical demand to an optimized, feasible procurement plan — accounting for inventory, supplier risk, compliance, and resilience constraints — in a single session to help guide and steer risk-minimized forward looking procurement decision making."

---

## Behind-the-Scenes Objects by Stage

see relevant */README.md files in forecasting/, inventory/, and optimization/.