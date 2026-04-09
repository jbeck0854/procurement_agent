# Architecture Documentation

This document explains how the Procurement Intelligence Agent is structured — from a user's natural language query all the way to an executive summary with charts and an optimized supplier allocation.

There are two complementary diagrams:

| Diagram | What it shows |
|---------|---------------|
| `architecture_flowchart.png` | The multi-agent orchestration layer (LangGraph state machine, agents, MCP connections) |
| `helpers_diagram.png` | The backend data pipeline (4 sequential steps from raw DB → LP answer) |

---

## System Architecture (`architecture_flowchart.png`)

The system is a **two-phase fan-out LangGraph pipeline** triggered by a natural language query.

```
User (Natural Language)
        │
        ▼
  Streamlit UI
        │
        ▼
  Orchestrator (GPT-4o-mini)
  Intent recognition · Task planning · Parameter extraction
        │
        ▼  "work orders"
    ┌───────┐
    │Approve?│  ◄── Human-in-the-loop interrupt
    └───────┘
        │
        ├─────────────────────────────────────────────────────────┐
        │  PHASE 1 — Data Retrieval (parallel)                    │
        │                                                         │
        ▼  demo queries     ▼  SQL explore     ▼  geopolitical    │
  Pipeline Agent       Data Agent          Risk Agent             │
  (Direct Mode)        (ReAct Loop)        (ReAct Loop)           │
  10 pre-built tools   Free-form SQL       Web search             │
  Forecast|BOM         Postgres MCP        Tavily MCP             │
  Inventory|Procurement     │                   │                 │
        │                   │                   │                 │
        └───────────────────┴───────────────────┘                 │
        │ (all Phase 1 complete)                                   │
        │                                                         │
        ├─────────────────────────────────────────────────┐       │
        │  PHASE 2 — Analysis & Optimization (parallel)   │       │
        │                                                 │       │
        ▼  charts + scores           ▼  allocation + cost │       │
  Chart Agent                   LP Agent                  │       │
  (Direct Mode)                 (Direct Mode)             │       │
  7 chart tools                 Procurement Optimizer     │       │
  Supplier Scoring              PuLP/CBC Solver           │       │
                                Baseline Comparison       │       │
        │                             │                   │       │
        └─────────────────────────────┘                   │       │
        │                                                 │       │
        ▼                                                 │       │
  Synthesizer (GPT-4o-mini)                               │       │
  Executive Summary · Next Steps                          │       │
        │                                                 │       │
        ▼                                                 │       │
  Response (Text + Charts)                                │       │
                                                          │       │
  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─│
  Backend Modules (read-only)              PostgreSQL     │  Tavily
  forecasting/forecast_summary.py          Procurement DB │  API
  inventory/procurement_summary.py              ▲         │   ▲
  optimization/run_lp_optimization.py           │  MCP────┘   │ MCP
  analytics/scoring.py + charts/           ◄───┘             ─┘
```

### Agents

| Agent | Phase | Mode | Purpose |
|-------|-------|------|---------|
| **Orchestrator** | — | LLM only | Parses intent, generates work orders (task structs), triggers the human-in-the-loop interrupt before any data agent runs |
| **Pipeline Agent** | 1 | Direct | Calls the 10 pre-built tool wrappers for forecast, BOM, inventory, and procurement queries. Sub-second; no ReAct loop needed |
| **Data Agent** | 1 | ReAct | Runs free-form exploratory SQL via the PostgreSQL MCP server. Used for ad-hoc questions not covered by the 10 tools |
| **Risk Agent** | 1 | ReAct | Runs web searches via the Tavily MCP server for geopolitical risk, tariff news, and sanctions |
| **Chart Agent** | 2 | Direct | Generates 7 matplotlib visualizations and runs the supplier scoring model using Phase 1 results as input |
| **LP Agent** | 2 | Direct | Runs the PuLP/CBC linear program against the net procurement need from Phase 1 |
| **Synthesizer** | — | LLM only | Combines all agent outputs into a final executive summary with recommended next steps |

### Human-in-the-Loop

After the Orchestrator generates its task plan, the LangGraph graph raises an **interrupt**. The Streamlit UI detects this via `waiting_for_approval` session state and shows the plan to the user. On approval, it resumes the graph with `Command(resume=True)`. The FastAPI server exposes the same pattern via `POST /resume`.

### MCP Connections

- **PostgreSQL MCP** (`mcp_client.py`): managed async session, used by Data Agent for free-form SQL
- **Tavily MCP** (`tavily_client.py`): managed async session, used by Risk Agent for web search
- Both are kept open for the duration of a pipeline run, not per-query

---

## Backend Helper Functions (`helpers_diagram.png`)

The backend is a **sequential 4-step pipeline** that transforms raw database tables into an LP-ready demand number. Each step feeds the next.

```
PostgreSQL Procurement Database
  dim_forecast_run · fact_semiconductor_demand_forecast
  dim_bom · vw_component_requirement_lp
  fact_component_inventory_history · fact_inventory_policy
  vw_procurement_requirement · vw_supplier_complete_profile
        │
        │ historical demand
        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1 — Demand Forecasting                            │
│  forecasting/forecast_summary.py                        │
│  "Future 13–20 weeks, how much semiconductor demand     │
│   do we expect?"                                        │
├─────────────────────────────────────────────────────────┤
│ get_forecast_summary_tool()     → planning horizon,     │
│   Reads dim_forecast_run +        total demand,         │
│   fact_semiconductor_demand_forecast  weekly totals,    │
│                                   peak/lowest week,     │
│                                   model metadata        │
│                                                         │
│ get_forecast_drilldown_tool()   → week × facility × SKU │
│                                   detail with 90% CI    │
│                                   bounds; CSV export    │
│                                                         │
│ get_forecast_model_assessment() → model validation,     │
│                                   feature importance,   │
│                                   baseline comparison,  │
│                                   artifact path         │
└─────────────────────────────────────────────────────────┘
        │ finished-good forecast (weekly × facility × SKU)
        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 2 — BOM Translation                               │
│  inventory/procurement_summary.py                       │
│  "Finished goods → What raw components do we need?"     │
├─────────────────────────────────────────────────────────┤
│ format_component_requirements() → gross BOM demand per  │
│   Reads vw_component_requirement_lp  component type     │
│                                   across ALL facilities  │
│                                   × ALL weeks           │
│                                   (before inventory     │
│                                    offset)              │
│                                                         │
│ format_bom_translation()        Mode A: BOM recipe      │
│                                   e.g. 1 SEMICONDUCTOR_6│
│                                   = 3 transistors +     │
│                                     2 power_devices     │
│                                 Mode B: forecast-row    │
│                                   explosion for a       │
│                                   specific week ×       │
│                                   facility              │
└─────────────────────────────────────────────────────────┘
        │ gross component demand (BOM-exploded)
        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 3 — Inventory Check & Procurement Need            │
│  inventory/procurement_summary.py                       │
│  "We need 3 000 transistors total, but have 500 in      │
│   stock. How much do we actually need to BUY?"          │
├─────────────────────────────────────────────────────────┤
│ format_procurement_status()     → week-by-week rolling  │
│                                   inventory depletion;  │
│                                   shows WHERE and WHEN  │
│                                   procurement triggers  │
│                                   (NOT the LP input)    │
│                                                         │
│ format_aggregated_procurement_need()                    │
│                                 → horizon-level LP      │
│                                   demand floor:         │
│   net = gross_demand                                    │
│       + safety_stock + backorder                        │
│       - on_hand - scheduled_recv                        │
│   Applied ONCE per facility.                            │
│   THIS is what the LP optimizes against.                │
│                                                         │
│ get_procurement_requirement_drilldown()                 │
│ get_triggered_procurement_rows()                        │
│                                 → week × facility ×     │
│                                   component detail;     │
│                                   "triggered" = only    │
│                                   rows where net > 0    │
└─────────────────────────────────────────────────────────┘
        │ net procurement need (inventory-adjusted)
        ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 4 — LP Optimization                               │
│  optimization/run_lp_optimization.py                    │
│  "We need to buy 2 400 transistors.                     │
│   Which suppliers? How much from each?"                 │
├─────────────────────────────────────────────────────────┤
│ run(LPParams) → dict                                    │
│                                                         │
│   Objective:                                            │
│     min  Σ cost × (1 + λ × risk) × qty                 │
│   Subject to:                                           │
│     total qty ≥ demand                                  │
│     per-supplier share ≤ max_share                      │
│     compliance score ≥ threshold                        │
│                                                         │
│   Returns: allocation table, cost summary,              │
│            executive summary, formula description,      │
│            baseline comparison                          │
│                                                         │
│ Key user parameters:                                    │
│   product            — which component type            │
│   lambda_risk        — 0 = cost-only, 1 = risk-only    │
│   max_supplier_share — per-supplier cap (fraction)     │
│   urgency            — penalise slow-lead-time suppliers│
│   exclude_supplier_ids — force-exclude for what-if     │
│   diversification_mode — none | share_only | country   │
└─────────────────────────────────────────────────────────┘
        │
        ▼
  Final Output Example
  ══════════════════════════════════════
  SUP_CAN_10 (CAN) — 505 520 units (40%)
  SUP_HKG_38 (HKG) — 505 520 units (40%)
  SUP_HKG_35 (HKG) — 252 760 units (20%)
  Total: $133 046  |  Avg risk: 0.277
  ══════════════════════════════════════
```

### Key distinction: procurement status vs. aggregated procurement need

These two helpers are easy to confuse:

- **`format_procurement_status()`** — simulates week-by-week inventory depletion. Useful for showing *when* and *where* stock runs out. It is **not** the number fed to the LP.
- **`format_aggregated_procurement_need()`** — computes a single horizon-level net figure per facility (`gross - on_hand - scheduled_recv + safety_stock + backorder`). This is the **LP demand floor** that the optimizer must satisfy.

---

## How the Two Layers Connect

The backend helpers (Steps 1–4) are called by the **demo tools layer** (`tools/pipeline_queries.py`, `tools/optimization.py`) which wraps them as LangChain `Tool` objects. The agents in the orchestration layer call these tools directly — they never import the backend modules themselves.

```
LangGraph agents (graph/)
      │  call tools
      ▼
Tool wrappers (tools/)
      │  import and call
      ▼
Backend helpers (../forecasting/, ../inventory/, ../optimization/, ../analytics/)
      │  query
      ▼
PostgreSQL Procurement Database
```

The split means the backend business logic is testable independently of the agent layer, and the tool wrappers are the only translation boundary between them.
