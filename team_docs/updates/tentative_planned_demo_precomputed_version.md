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

**On screen:**
A four-step workflow indicator:
1. Forecast demand
2. Translate to components
3. Check inventory
4. Recommend procurement plan

**Business explanation:**
> "The system doesn't just rank suppliers. It starts from demand and works forward — so every procurement recommendation is grounded in what we actually need."

**What runs behind the scenes:** Nothing yet. Orientation only.

---

### 1:00–2:30 — Demand forecast

**User action:** "Use the latest forecast already in the system."

**Agent action:** Queries the forecast layer. No rerun needed — forecasts are precomputed and stored.

**Behind the scenes:**
- `dim_forecast_run` — identifies latest run
- `fact_semiconductor_demand_forecast` — weekly forward demand by SKU and facility
- `fact_semiconductor_demand` — historical actuals for comparison

**On screen:**
- Historical demand trend (aggregate, system level)
- Forward forecast for the planning window (16–20 weeks)
- One representative SKU-level example if useful for context

**Business explanation:**
> "We start by knowing what finished-goods demand looks like over the planning window. Then we convert that demand signal into the specific components we need to procure."

**Precomputed:** Yes — forecasts are already in the database.
**NOTE:** Could potentially assess viability of giving the system the "appearance" of having upload csv capability so this seems done in real time.

---

### 2:30–3:45 — BOM translation to component requirements

**Agent action:** Converts finished-goods forecast into component-level demand.

**Behind the scenes:**
- `dim_bom` — BOM bridge from finished SKUs to procurement components
- `vw_component_requirement_detail` — exploded per-SKU component view
- `vw_component_requirement_lp` — LP-ready aggregated component demand

**On screen:**
Component requirement summary by product type:

| Component | Facility | Gross Requirement |
|---|---|---|
| transistors | FACILITY_3, FACILITY_4 | ~29,000 units |
| power_devices | FACILITY_3, FACILITY_4 | ~12,800 units |
| integrated_circuit_components | ... | ~2,600 units |
| microprocessors | ... | ~43 units |

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

---

### 5:15–6:00 — Side-track: ad hoc supplier comparison

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
> "Proceed. Budget cap is flexible but keep per-product spend reasonable. Moderate risk tolerance. Don't overconcentrate on one supplier."

**Agent action:** Runs LP optimization for transistors with user parameters.

**Behind the scenes:**
- `vw_procurement_requirement` — net requirement input
- `vw_supplier_complete_profile` + `analytics/scoring.py` — supplier scoring
- `optimization/run_lp_optimization.py` → `run(LPParams(product="transistors", lambda_risk=0.50, max_supplier_share=0.40))`

**User-adjustable parameters shown:**
- Product: transistors
- Lambda (risk weight): 0.50
- Max supplier share: 40%
- Service-level target: 100%
- Compliance threshold: 60%
- Budget cap: optional

**On screen:**
- Supplier allocation table: supplier, quantity, share %, unit cost, risk score
- Cost summary: total cost, avg unit cost, avg risk penalty
- Supplier pool: total eligible → selected → excluded (with reasons)
- LP executive_summary string (from result dict, surfaced directly)

**Agent explanation:**
> "Given moderate risk weighting and a 40% diversification cap, the LP allocated volume across three suppliers. SUP_CAN_10 leads at 40% of volume — it balances cost and risk well. Two suppliers were excluded by compliance threshold."

**Live run:** Yes — this runs in real time during demo.

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

---

### 8:00–8:30 — Optional: urgency mode

*Run this only if time permits. Can be shown as a quick toggle.*

**User asks:**
> "What if we need this faster — we're behind schedule on this cycle?"

**Agent action:** Reruns transistors LP with `urgency=True`.

**Behind the scenes:**
- Same LP pipeline
- Objective coefficient gets lead-time penalty: `+$0.002 × lead_time_mean per unit`

**On screen:**
- Updated allocation (may shift toward faster suppliers if the penalty is large enough to change ranking)
- formula_description noting urgency mode active
- executive_summary with urgency flag

**Agent explanation:**
> "In urgency mode, the optimizer adds a cost penalty proportional to each supplier's lead time. Slower suppliers become relatively less attractive. This doesn't exclude anyone — it lets cost decide whether speed is worth paying for."

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

**Note:** The LP-level `executive_summary` for each product is passed through as-is into the session summary table. The session narrative is the only new LLM-generated text at this stage.

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

| Stage | Python / pipeline | Database objects |
|---|---|---|
| Demand forecast | `forecasting/run_production.py` (precomputed) | `dim_forecast_run`, `fact_semiconductor_demand_forecast`, `fact_semiconductor_demand` |
| BOM translation | — (view-based) | `dim_bom`, `vw_component_requirement_detail`, `vw_component_requirement_lp` |
| Inventory check | `inventory/run_inventory.py` (precomputed) | `fact_component_inventory_history`, `fact_inventory_policy`, `vw_procurement_requirement` |
| Supplier comparison | `demo/tools/scoring.py`, `demo/tools/chart_tools.py` | `vw_supplier_complete_profile` |
| LP optimization | `optimization/run_lp_optimization.py` | `vw_procurement_requirement`, `vw_supplier_complete_profile` |
| Session summary | `demo/graph/synthesizer.py` | Reads from `agent_results` dict in `AgentState` |

---

## Recommended Hybrid Setup

### Precomputed before demo (reliability-critical)
| Item | Why |
|---|---|
| Forecasts stored in DB | Avoids model retraining during demo |
| Inventory simulation run | `run_inventory.py` takes time; output already in DB |
| BOM loaded | `dim_bom` seed data already in DB |
| Procurement requirement view live | `vw_procurement_requirement` queries in <1s |

### Run live during demo (fast, high-impact)
| Item | Why live |
|---|---|
| `score_suppliers()` + chart renders | Shows the system is active, not static |
| LP optimization run (transistors) | Sub-second solve; demonstrates real computation |
| Disruption rerun (exclude supplier) | One-line param change; visually compelling |
| Urgency mode rerun (optional) | Same |

### Pre-staged but surfaced as if live
| Item |
|---|
| Inventory status table (pre-queried, displayed on trigger) |
| Component requirement summary (pre-queried, displayed on trigger) |

---

## Agent Integration Notes

### `AgentState` fields used
- `agent_results` — accumulates LP result dicts keyed as `lp_{product}` (e.g. `lp_transistors`)
- `chart_results` — accumulates chart base64 images from chart_agent
- `raw_data` — holds requirement and inventory query results from data_agent
- `final_response` — session-level summary text from synthesizer

### LP result fields surfaced directly in demo
- `executive_summary` — per-product, surfaced as-is in the allocation step
- `formula_description` — shown in urgency/disruption scenarios to explain what changed
- `allocation` list — rendered as the supplier allocation table
- `cost_summary.total_cost_usd` — shown in session summary totals
- `constraint_diagnostics.lp_status` — used to flag Optimal vs. Infeasible

### Session-level summary (synthesizer's job)
The synthesizer iterates over all `agent_results["lp_*"]` entries and:
1. Aggregates `total_cost_usd`, `adjusted_requirement`, `n_suppliers_selected` across products
2. Flags any Infeasible product
3. Generates `session_narrative` via LLM given the structured aggregated fields
4. Does **not** call `run()` again — reads only already-computed results

### Agents that need to exist (for teammate integration)
| Agent | Status | What it does |
|---|---|---|
| `data_agent` | Exists | Queries DB for demand, inventory, requirement data |
| `risk_agent` | Exists | Supplier risk scoring |
| `chart_agent` | Exists | Calls chart_tools functions |
| `lp_agent` | **Needs to be created** | Calls `optimization/run_lp_optimization.run()` per product |
| `synthesizer` | Exists | Needs update to handle `lp_*` keys and produce session summary |

### New files needed for agent integration
| File | What it contains |
|---|---|
| `demo/tools/optimization.py` | LangChain `@tool` wrapping `run(LPParams(...))` |
| Updates to `demo/graph/orchestrator.py` | Register `lp_agent` in AVAILABLE SUB-AGENTS |
| Updates to `demo/graph/builder.py` | Add `lp_agent` node and routing |
| Updates to `demo/graph/synthesizer.py` | Handle `lp_*` result keys, produce session summary |

---

## Demo Success Criteria

The demo succeeds if the audience can clearly see:

- [ ] The system starts from historical demand, not from a static supplier list
- [ ] Forecasted demand drives component requirements (not manually entered)
- [ ] Inventory coverage is checked before any procurement action is recommended
- [ ] The LP produces a real, explainable supplier allocation — not a ranking
- [ ] The agent handles a side question (supplier comparison) without losing context
- [ ] A disruption scenario reruns instantly and produces a revised plan
- [ ] The session ends with a clean, complete procurement recommendation covering all components

**The system should feel like a workflow, not a lookup tool.**
