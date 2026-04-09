# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This System Does

An end-to-end **semiconductor procurement decision system** for a business analytics capstone. It covers:

1. **Demand Forecasting** — HGB model forecasting weekly semiconductor SKU demand across 4 facilities × 12 SKUs
2. **BOM Translation** — Explodes finished-goods demand into component procurement need via Bill of Materials
3. **Inventory Planning** — Safety stock policy (periodic review, order-up-to) computes net procurement requirement
4. **LP Optimization** — PuLP/CBC solves supplier allocation (minimize risk-adjusted cost subject to budget, diversification, compliance)
5. **Supplier Scoring** — Contract-driven YAML scoring engine ranks suppliers by `risk_adjusted_cost = normalized_landed_cost + λ × risk_penalty`
6. **LangGraph Agent Demo** — Streamlit UI backed by a multi-agent orchestration system

## Repository Layout

```
procurement_agent/
├── forecasting/        # HGB demand forecasting model and pipeline
├── inventory/          # Inventory policy and procurement requirement computation
├── optimization/       # LP supplier allocation (PuLP/CBC)
├── analytics/          # Supplier scoring engine + matplotlib charts
│   └── metric_contract.yaml  # Single source of truth for all scoring weights/rules
├── sql/                # PostgreSQL star schema DDL + load scripts
├── cleaned_data/       # Raw CSVs (PPI, tariffs, LPI, WGI, supplier data)
├── demo/               # LangGraph multi-agent demo (Streamlit + FastAPI)
│   ├── graph/          # LangGraph node definitions and state machine
│   ├── tools/          # LangChain tool wrappers calling backend modules
│   └── streamlit_app.py
└── artifacts/forecasting/  # Auto-generated model evaluation outputs
```

## Running the Pipeline (Backend)

All commands run from project root. Use the root `venv`:

```bash
source venv/bin/activate

# 1. Validate forecast model (GridSearchCV + holdout eval + plots → artifacts/forecasting/)
python -m forecasting.run_pipeline

# 2. Run baseline comparison (requires artifacts/forecasting/holdout_predictions.csv)
python -m forecasting.run_baseline

# 3. Generate production forecast and write to DB (retrains on full history)
python -m forecasting.run_production

# 4. Build inventory state and procurement requirement (run after forecast)
python -m inventory.run_inventory

# 5. Run LP optimization
python -m optimization.run_lp_optimization
```

**Pipeline dependency order:** `run_production` → `run_inventory` → `run_lp_optimization`. Regenerating the forecast requires re-running inventory before LP to keep the inventory snapshot aligned.

## Running the Demo

```bash
cd demo
source venv/bin/activate

# Primary UI
streamlit run streamlit_app.py     # http://localhost:8501

# Alternative REST API
python main.py                     # http://localhost:8000
```

### Demo Environment

Create `demo/.env`:
```
AZURE_OPENAI_API_KEY=...
TAVILY_API_KEY=...
# DATABASE_URL defaults to postgresql://localhost:5432/procurement_agent
```

### Demo Verification

```bash
cd demo
python -c "import psycopg2; conn = psycopg2.connect('postgresql://localhost:5432/procurement_agent'); print('DB OK'); conn.close()"
python -c "from llm import get_llm; llm = get_llm(); print(llm.invoke('Say hello in one word').content)"
python -c "from graph.builder import build_graph; app = build_graph(); print('Graph compiled OK')"
python -c "from tools.pipeline_queries import DIRECT_PIPELINE_TOOLS; print(f'{len(DIRECT_PIPELINE_TOOLS)} tools loaded')"
```

## Running Tests (Analytics)

```bash
# From project root
pytest analytics/tests/
```

## Database Setup

Run SQL files **in this exact order** from `psql` connected to `procurement_agent`:

1. `sql/dimensions.sql`
2. `sql/facts.sql`
3. `sql/load/stage.sql`
4. `sql/load/copy_staging.sql`
5. `sql/load/load_dimensions.sql`
6. `sql/load/load_facts.sql`
7. `sql/load/load_bom.sql`
8. `sql/views.sql`

## Architecture: LangGraph Multi-Agent Demo

The demo uses a **two-phase fan-out** pattern:

```
User Query
  → orchestrator (intent + task plan + human-in-the-loop interrupt)
  ↓
Phase 1 (parallel):
  ├── pipeline_agent   — 10 direct-mode tools (forecast, BOM, inventory)
  ├── data_agent       — ReAct loop via PostgreSQL MCP
  └── risk_agent       — ReAct loop via Tavily MCP
  ↓
Phase 2 (parallel, after Phase 1):
  ├── chart_agent      — 7 matplotlib chart tools + supplier scoring
  └── lp_agent         — LP optimization via PuLP/CBC
  ↓
synthesizer → executive summary streamed to Streamlit
```

**Human-in-the-loop:** The orchestrator calls a LangGraph `interrupt()` before dispatching agents. `streamlit_app.py` tracks `waiting_for_approval` in session state; on user approval it resumes via `graph.invoke(Command(resume=True), config)`.

**Shared state** (`demo/graph/state.py` — `AgentState`): `messages`, `intent`, `tasks`, `agent_results`, `chart_results`, `raw_data`, `final_response`, `timings`.

**LLM:** Azure OpenAI GPT-4o-mini, configured in `demo/config.py`, instantiated via `demo/llm.py`.

**MCP connections:** `demo/mcp_client.py` (PostgreSQL MCP) and `demo/tavily_client.py` (Tavily MCP) manage async MCP sessions for the ReAct agents.

**Tools bridge:** `demo/tools/` wrappers call backend modules outside `demo/`:
- `tools/pipeline_queries.py` → `forecasting/forecast_summary.py` + `inventory/procurement_summary.py`
- `tools/optimization.py` → `optimization/run_lp_optimization.py`
- `tools/scoring.py` → `analytics/scoring.py`
- `tools/chart_tools.py` → `analytics/charts/`

## Key Domain Concepts

**Inventory math:** `available_above_ss = max(0, on_hand + SR − BO − SS)` computed **once** per facility × component. `remaining_N` depletes each week. `net_requirement_N = max(0, gross_N − remaining_N)`. Safety stock is pre-deducted once — never added per week.

**LP demand floor** (`vw_component_requirement_lp`): inventory offset applied **once** at horizon level — not summed from the weekly `vw_procurement_requirement` view (which applies the offset per-week and produces a much smaller, incorrect total).

**Supplier scoring** (`analytics/scoring.py` + `analytics/metric_contract.yaml`): all weights, normalization rules, and ranking rules live in the YAML. Changing the contract changes behavior without touching Python. `risk_adjusted_cost = normalized_landed_unit_cost + λ × normalized_risk_penalty`. Normalization is per-product (suppliers compared only to peers producing the same component).

**LP products:** `"transistors"`, `"microprocessors"`, `"integrated_circuit_components"`, `"power_devices"`.

**Diversification modes:** `"none"`, `"supplier_share_only"`, `"country_diversified"` (MIP: exactly 3 suppliers, each from a different country, ~1/3 volume each).
