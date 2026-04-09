# Procurement Agent — Current Demo Architecture

**Speed-First System Documentation**

This document describes the current state of the procurement agent demo after the speed-first refactor. It covers what has changed, why, and how the system is structured to support optional traceable agent execution in a planned future mode.

---

## 1. Overview — Fast Demo Architecture

The current demo is a **speed-optimized procurement decision system** designed for live presentation, minimal latency, and deterministic outputs.

> "This version prioritizes responsiveness and clarity over full agent trace visibility."

### Design goals

| Goal | Implementation |
|---|---|
| Sub-second layer transitions | Direct-query pipeline tools — no LLM call for data retrieval |
| Deterministic UI rendering | Prebuilt render helpers per layer; no runtime formatting decisions |
| Minimal user typing | Dropdown-driven exploration; typed queries reserved for optimization |
| Executive-ready outputs | Structured tables, metric cards, collapsible expanders — no ASCII |
| Stable approval flow | LP results persist through approval, modification, and session summary |

### What was removed

The prior version routed most queries through the full LangGraph orchestrator — including forecasting, BOM, and inventory queries that had deterministic answers. This introduced:
- unnecessary LLM calls for queries with known results
- visible reasoning traces that slowed down the UI
- inconsistent output formatting across layers

These are now replaced with fast paths (described below).

---

## 2. Core Pipeline — End-to-End Flow

The system moves through five layers sequentially. Most layers are **retrieval + formatting**. Only the LP layer involves runtime optimization.

```
1. Forecasting
   └── query_forecast_summary (precomputed DB view)
   └── Expanders: forecast drilldown, model validation, baseline comparison

2. BOM Translation
   └── query_component_requirements (precomputed DB view)
   └── Expander: BOM recipe translation (how SKUs map to components)

3. Inventory / Procurement Requirement
   └── query_procurement_planning_summary (precomputed DB view)
   └── Expanders: trigger detail, base-stock policy, full horizon drilldown

4. LP Optimization
   └── run_optimization (PuLP/CBC solver — runtime)
   └── Approval: Approve / Modify / Discard
   └── What-if: exclude suppliers, urgency mode, country diversification

5. Session + Executive Summary
   └── Aggregates all approved LP runs
   └── Baseline comparison per product (cost-only vs optimized)
   └── Final narrative exported on "Complete Procurement Plan"
```

**Layers 1–3 are entirely retrieval-driven.** The database views are precomputed during the data pipeline runs (`run_forecast.py`, `run_inventory.py`). The demo queries them directly — there is no runtime forecasting or inventory recalculation.

**Layer 4 (LP) is the only true runtime computation.** The solver runs on each new optimization request, which takes ~1–3 seconds.

**Layer 5 (session summary) is aggregation only** — no additional LLM calls or optimization. It reads from approved LP run results stored in session state.

---

## 3. Speed Optimizations Implemented

### Output rendering

| Before | After |
|---|---|
| ASCII-style text tables | `st.dataframe()` with formatted columns |
| Plain-text metric lists | Metric cards + section headers |
| Raw reasoning trace blocks | Collapsed `st.expander()` sections |
| Repeated explanatory paragraphs | Module-level constants; rendered once per expander |

### Query routing

| Before | After |
|---|---|
| All queries → orchestrator LLM → agent | Forecast/BOM/inventory queries → direct pipeline tools |
| Orchestrator generates task plan for every message | Fast path intercepts known query patterns before LLM |
| Data agent invoked for structured pipeline queries | `pipeline_agent` handles all structured queries (sub-second) |

### UI interaction

| Before | After |
|---|---|
| User types follow-up questions for each layer | Collapsed expanders pre-loaded with downstream detail |
| Full page refresh on every new message | Scroll position managed via session state + JS anchor injection |
| LP results disappear after approval interaction | LP result panel persists through approval; accumulated in session |

### Parameter propagation

| Before | After |
|---|---|
| What-if scenarios lost prior run parameters | `[LP_PARAMS: ...]` injection copies all params to new run |
| Risk weight not consistently propagated to charts | `lambda_risk` explicitly passed to scoring visualization |

---

## 4. UI Interaction Model

The demo is designed to behave like a **decision tool**, not a chatbot. The user is guided through a procurement analysis workflow, not a free-form conversation.

### Interaction structure

```
Forecast summary
  └── [Dropdown] Forecast detail by facility / SKU
  └── [Dropdown] Model validation
  └── [Dropdown] Baseline comparison

Component requirements
  └── [Dropdown] How SKU demand translates to component demand

Procurement summary
  └── [Dropdown] Triggered procurement rows (where and when)
  └── [Dropdown] Base-stock policy explanation
  └── [Dropdown] Full horizon drilldown

LP optimization
  └── [Interactive] Product, risk weight, constraints → run
  └── [Buttons] Approve / Modify / Discard
  └── [Modify flow] Adjust params → rerun → compare
  └── [What-if] Exclude supplier, add urgency, diversify

Final summary
  └── [Button] "Complete Procurement Plan"
  └── Aggregated table + baseline comparison + narrative
```

All dropdowns are pre-loaded during the initial query response — expanding them does not trigger a new DB query or LLM call.

The LP panel is the only interactive section where the user specifies parameters at runtime. Everything above it is driven by the current forecast and inventory state.

---

## 5. Current Limitation (Intentional)

The following are **deliberate tradeoffs** in the current system, not gaps:

- **Agent trace visibility is minimized.** The orchestrator still runs for LP and chart queries, but its task plan is not displayed in the UI. The user sees outputs, not reasoning steps.
- **Background routing is not exposed.** The two-phase agent graph (orchestrator → pipeline/chart/lp agents) executes silently. The user cannot observe which agent handled their request.
- **Orchestration is simplified for common paths.** Forecast, BOM, and inventory queries bypass the orchestrator entirely via fast path matching in `streamlit_app.py`.

These choices were made deliberately to maximize demo speed and reduce confusion during live presentation. They are reversible — the full LangGraph graph remains intact and is the execution path for LP, chart, and exploratory queries.

---

## 6. Planned Enhancement — Traceable Agent Execution

The next major enhancement reintroduces a **traceable execution layer** that makes the system's AI-driven behavior visible without sacrificing speed.

### What it will show

When enabled, a collapsible trace panel will display:

```
Orchestrator
  Intent: Optimize transistors with moderate risk, 40% supplier cap
  Task 1 → lp_agent
    Tool: run_optimization
    Params: {product: transistors, lambda_risk: 0.5, max_supplier_share: 0.4}

Router
  Phase 1: (none)
  Phase 2: lp_agent dispatched

lp_agent
  Status: Solved
  Solver: PuLP/CBC
  Duration: 1.2s

Synthesizer
  Output: LP result rendered
```

This surface will be implemented as a collapsed `st.expander` labeled **"Show execution trace"** — visible by default on first run, collapsed after.

### Why this matters

- Proves the system is LLM-driven, not a scripted pipeline
- Shows real task decomposition and routing decisions
- Differentiates from static dashboards in a capstone context
- Aligns with feedback requesting more visible agent reasoning

### Implementation path

The LangGraph graph already emits timing data and task metadata (`state["tasks"]`, `state["timings"]`, `state["intent"]`). The trace layer reads from this state and renders it after the primary result — no changes to the agent execution logic are needed.

---

## 7. Model Strategy

The current system uses a single LLM (Azure OpenAI GPT-5-mini) for all orchestration and synthesis. The planned enhancement introduces a **two-model split**:

| Role | Model | Responsibilities |
|---|---|---|
| Orchestration / reasoning | gpt-5.1-codex | Intent parsing, task planning, what-if parameter extraction, multi-step reasoning |
| UI responses / synthesis | gpt-5.3-chat | Fast structured outputs, executive summaries, expander content, synthesis narration |

### Why split

- Reasoning tasks (intent → task plan → parameter extraction) benefit from a stronger model that can hold complex context across multi-turn modifications
- UI-facing outputs (summaries, explanations, expander text) benefit from a faster, lower-latency model
- The split preserves demo speed for the user-facing path while enabling deeper reasoning in the background

### Implementation

The split is additive — `llm.py` will expose two client factories (`get_reasoning_llm()` / `get_response_llm()`). No changes to agent logic are needed; only the LLM client each agent calls is swapped.

---

## 8. Design Principle — Dual-Mode System

The system is designed to support two operating modes. The mode can be toggled via session state (a settings toggle in the UI) without restarting the app.

### Mode A — Fast Demo Mode (default)

```
- Orchestrator runs silently
- Fast-path routes bypass LLM for pipeline queries
- No trace panel
- Minimal latency end-to-end
- Clean, executive-ready outputs
```

Use for: live presentations, demos to external stakeholders, time-constrained walkthroughs.

### Mode B — Trace Mode (planned)

```
- Orchestrator intent + task plan displayed
- Agent routing decisions visible
- Execution timing per agent shown
- Structured reasoning steps in collapsible panel
- Slightly slower (extra render step after result)
```

Use for: class presentations, professor reviews, demos where the AI architecture itself is the subject of evaluation.

The two modes share the same execution graph, the same tool implementations, and the same LP solver. Only the rendering layer changes.

---

## 9. Why This Matters — Capstone Framing

Most student demos are dashboards: static visualizations over a fixed dataset. This system is different in three ways.

**It executes decisions, not just analysis.** Every LP run solves a real optimization problem at runtime against live inventory and supplier data. The output is not a chart — it is a procurement allocation with supplier names, quantities, costs, and risk tradeoffs.

**It explains its reasoning.** The baseline comparison quantifies the cost of risk management in dollars. The formula description explains why the optimizer chose each supplier. The executive summary is generated from actual run parameters, not a template.

**It is architecturally honest.** The trace layer will make the LangGraph multi-agent execution visible — showing orchestrator intent, task routing, agent dispatch, and solver timing. This is not a scripted demo pipeline. It is a real AI system making real decisions.

That combination — optimization + explanation + transparent AI execution — is what distinguishes this from a data science project with a Streamlit front end.

---

## Appendix — Quick Reference

### Agent responsibilities (current)

| Agent | Phase | Mode | When used |
|---|---|---|---|
| `pipeline_agent` | 1 | Direct | Forecast, BOM, inventory, procurement queries |
| `data_agent` | 1 | ReAct (SQL) | Exploratory DB queries ("how many suppliers in China?") |
| `risk_agent` | 1 | ReAct (Tavily) | Explicit geopolitical / tariff / news requests |
| `chart_agent` | 2 | Direct | Supplier scoring, ranking, visualization |
| `lp_agent` | 2 | Direct | Procurement optimization (all variants) |

### Fast-path bypass (no LLM call)

The following query patterns are intercepted in `streamlit_app.py` before reaching the orchestrator:

- Forecast summary / drilldown / model assessment
- Component requirements
- BOM translation
- Procurement planning summary / status / trigger rows / aggregated need
- Safety stock policy explanation

### Session state keys (relevant to demo flow)

| Key | Purpose |
|---|---|
| `messages` | Full chat history (replay loop source) |
| `fast_path_dfs` | DataFrame cache for replay (avoids DB re-query on rerun) |
| `forecast_expander_cache` | Pre-loaded expander data (drilldown, validation, baseline) |
| `lp_approved_runs` | Accumulated approved LP runs for final summary |
| `_pending_scroll` | One-time anchor scroll target (`"exec_summary"` / `"lp_result_top"`) |
| `_scroll_msg_count` | Gates scroll-to-bottom to new messages only |

### Related files

| File | Purpose |
|---|---|
| `demo/streamlit_app.py` | Main UI — all rendering, session management, fast paths |
| `demo/graph/orchestrator.py` | LangGraph orchestrator with LLM task planning |
| `demo/graph/builder.py` | LangGraph topology (two-phase fan-out) |
| `optimization/run_lp_optimization.py` | LP solver, baseline comparison, result dict |
| `optimization/README.md` | Full LP layer documentation |
| `team_docs/updates/tentative_planned_demo_precomputed_version.md` | Full demo script |
