# Setup Guide — Procurement Intelligence Agent

This guide covers everything required to get the full system running from scratch: database, Python environments, forecasting pipeline, inventory layer, and the demo UI.

---

## System Requirements

| Requirement | Version / Notes |
|-------------|-----------------|
| Python | 3.12+ |
| PostgreSQL | Running locally — verify with `psql --version` |
| Azure OpenAI API key | For LLM calls in the demo (GPT-4o-mini) |
| Tavily API key | Free tier at tavily.com — used for geopolitical risk search |

---

## Repository Structure

```
procurement_agent/               ← project root
├── sql/                         # Database DDL and load scripts
│   ├── dimensions.sql
│   ├── facts.sql
│   ├── views.sql
│   └── load/                    # Must be run in order (see below)
│       ├── stage.sql
│       ├── copy_staging.sql
│       ├── load_dimensions.sql
│       ├── load_facts.sql
│       └── load_bom.sql
├── cleaned_data/                # Source CSV files for staging
├── forecasting/                 # HGB demand forecasting model + helpers
├── inventory/                   # Inventory policy + procurement planning helpers
├── optimization/                # LP supplier allocation optimizer
├── analytics/                   # Supplier scoring engine + chart rendering
│   ├── scoring.py
│   ├── metric_contract.yaml
│   └── charts/
├── artifacts/                   # Output artifacts from forecasting pipeline
├── scripts/                     # Data cleaning scripts
├── requirements.txt             # Root-level Python dependencies
└── demo/                        # Streamlit/FastAPI multi-agent UI
    ├── streamlit_app.py         # Primary entry point
    ├── main.py                  # FastAPI alternative
    ├── requirements.txt         # Demo-specific dependencies
    ├── .env                     # API keys (create this — not committed)
    ├── .streamlit/config.toml   # UI theme
    ├── graph/                   # LangGraph agent definitions
    └── tools/                   # Tool wrappers for agents
```

---

## Step 1 — Create and Load the Database

All commands run from the **project root** (`procurement_agent/`).

**If a `procurement_agent` database already exists, drop it first:**
```bash
# Terminate any open connections, then drop
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'procurement_agent';"
sudo -u postgres psql -c "DROP DATABASE procurement_agent;"
```

**Create the database:**
```bash
sudo -u postgres psql -c "CREATE DATABASE procurement_agent;"
```

**Run SQL files in this exact order** — order matters due to foreign key dependencies:

```bash
sudo -u postgres psql -d procurement_agent -f sql/dimensions.sql
sudo -u postgres psql -d procurement_agent -f sql/facts.sql
sudo -u postgres psql -d procurement_agent -f sql/load/stage.sql
sudo -u postgres psql -d procurement_agent -f sql/load/copy_staging.sql
sudo -u postgres psql -d procurement_agent -f sql/load/load_dimensions.sql
sudo -u postgres psql -d procurement_agent -f sql/load/load_facts.sql
sudo -u postgres psql -d procurement_agent -f sql/load/load_bom.sql
sudo -u postgres psql -d procurement_agent -f sql/views.sql
```

**Verify the database loaded correctly:**
```bash
sudo -u postgres psql -d procurement_agent -c "SELECT COUNT(*) FROM vw_supplier_complete_profile;"
# Expected: 89

sudo -u postgres psql -d procurement_agent -c "SELECT COUNT(*) FROM dim_bom;"
# Expected: > 0
```

See `sql/README.md` for full schema documentation.

---

## Step 2 — Python Environment (Root)

The root environment is used for the forecasting pipeline, inventory layer, and optimization module. Install from the project root:

```bash
cd procurement_agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Root `requirements.txt` includes:**
- `pandas`, `numpy`, `scikit-learn` — forecasting and data processing
- `matplotlib` — chart rendering (also used by `analytics/charts/`)
- `psycopg2-binary` — PostgreSQL driver
- `pulp` — LP solver (CBC backend)
- `pydantic`, `python-dotenv`, `PyYAML`
- `langchain-core`, `langgraph`, `langchain-openai` — agent framework

---

## Step 3 — Run the Forecasting Pipeline

The forecasting module trains a HistGradientBoosting model on historical semiconductor demand and generates a 20-week forward forecast. **This must be run before the inventory layer and LP optimizer can work.**

All commands from the **project root** with the root venv active:

```bash
# 1. Run validation pipeline: GridSearchCV + holdout evaluation + artifact generation
python -m forecasting.run_pipeline

# 2. (Optional) Run baseline comparison
python -m forecasting.run_baseline

# 3. Run production forecast: retrain on full history + write to database
python -m forecasting.run_production
```

`run_production` writes results to two tables:
- `dim_forecast_run` — one row per forecast batch (upsert, idempotent)
- `fact_semiconductor_demand_forecast` — 20-week forward predictions per facility × SKU

Artifacts (validation plots, metrics JSON, model selection summary) are saved to `artifacts/forecasting/`.

**Verify:**
```bash
sudo -u postgres psql -d procurement_agent -c \
  "SELECT forecast_run_id, forecast_origin_date, n_forecast_rows FROM dim_forecast_run ORDER BY 1 DESC LIMIT 3;"
```

---

## Step 4 — Run the Inventory Layer

The inventory layer derives component-level inventory from BOM-implied demand, computes inventory policy (safety stock, base-stock targets), and generates the week-by-week procurement trigger signal. **Run this after the forecasting pipeline.**

```bash
python -m inventory.run_inventory
```

This populates:
- `fact_component_inventory_history` — weekly benchmark component inventory per facility × product
- `fact_inventory_policy` — safety stock and base-stock targets per forecast run × facility × product
- `vw_procurement_requirement` is a view built on these tables (no separate run needed)

**Verify:**
```bash
sudo -u postgres psql -d procurement_agent -c \
  "SELECT COUNT(*) FROM fact_inventory_policy;"
# Expected: > 0

sudo -u postgres psql -d procurement_agent -c \
  "SELECT product_key, SUM(net_requirement) as total_net
   FROM vw_procurement_requirement GROUP BY 1 ORDER BY 2 DESC;"
```

---

## Step 5 — Demo Environment

The demo has its own virtual environment and `requirements.txt` with additional packages for the agent layer (LangGraph, MCP clients, Streamlit, etc.).

```bash
cd demo
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Demo-specific packages (in addition to root packages):**
- `streamlit` — UI
- `fastapi`, `uvicorn` — REST API alternative
- `mcp`, `langchain-mcp-adapters`, `postgres-mcp`, `mcp-tavily` — MCP clients
- `nest-asyncio` — async compatibility in Streamlit
- `graphviz` — architecture diagram generation

---

## Step 6 — Configure Environment Variables

Create a `.env` file inside the `demo/` folder:

```bash
# demo/.env
AZURE_OPENAI_API_KEY=your-azure-key-here
TAVILY_API_KEY=your-tavily-key-here

# Optional — only needed if your PostgreSQL user or port differs from the default
# DATABASE_URL=postgresql://youruser:@localhost:5432/procurement_agent
# DATABASE_URL=postgresql://matthew:mw78037803!@localhost:5432/procurement_agent
```

| Variable | Required | Source |
|----------|----------|--------|
| `AZURE_OPENAI_API_KEY` | Yes | Azure Portal → OpenAI resource → Keys and Endpoints |
| `TAVILY_API_KEY` | Yes | tavily.com → Dashboard → API Keys |
| `DATABASE_URL` | No | Defaults to `postgresql://localhost:5432/procurement_agent` |

---

## Step 7 — Verify Demo Setup

Run all checks from inside the `demo/` folder with the demo venv active:

```bash
cd demo
source venv/bin/activate

# Database connection
python -c "import psycopg2; conn = psycopg2.connect('postgresql://localhost:5432/procurement_agent'); print('DB OK'); conn.close()"

# LLM connection
python -c "from llm import get_llm; llm = get_llm(); print(llm.invoke('Say hello in one word').content)"

# PostgreSQL MCP tools
python mcp_client.py
# Expected: "Loaded X MCP tools:" followed by tool names

# Tavily MCP tools
python tavily_client.py
# Expected: "Loaded 3 Tavily tools:"

# LangGraph compilation
python -c "from graph.builder import build_graph; app = build_graph(); print('Graph compiled OK')"

# Pipeline tools (10 pre-built query wrappers)
python -c "from tools.pipeline_queries import DIRECT_PIPELINE_TOOLS; print(f'{len(DIRECT_PIPELINE_TOOLS)} pipeline tools loaded')"
# Expected: 10 pipeline tools loaded

# LP optimization
python -c "from tools.optimization import run_optimization; print('LP tools OK')"
```

All checks must pass before running the UI.

---

## Step 8 — Run the Demo

```bash
cd demo
source venv/bin/activate
streamlit run streamlit_app.py
```

Opens at **http://localhost:8501**.

The UI will show a landing screen. Type a query, review the orchestrator's plan, click **Approve & Execute**, and watch results stream in phase by phase.

**Alternative — FastAPI server:**
```bash
python main.py
# Runs at http://localhost:8000
# POST /chat   → submit query, get thread_id + plan
# POST /resume → resume after approval
```

---

## Full Pipeline Execution Order (Summary)

For a clean setup from scratch, run steps in this order:

```
1. Create PostgreSQL database
2. Load SQL schema and data (8 SQL files in order)
3. Install root Python environment
4. Run forecasting pipeline (run_pipeline → run_production)
5. Run inventory layer (run_inventory)
6. Install demo Python environment
7. Create demo/.env with API keys
8. Verify all demo checks pass
9. streamlit run streamlit_app.py
```

---

## Module Overview

### `forecasting/`
Trains a HistGradientBoosting Regressor on 145 weeks of historical semiconductor demand across 4 facilities × 12 SKUs. Generates a 20-week recursive forward forecast with 90% confidence intervals. Writes results to `dim_forecast_run` and `fact_semiconductor_demand_forecast`.

### `inventory/`
Derives component-level inventory from BOM-implied demand. Computes inventory policy (periodic review, order-up-to, z=1.65 service level). Generates `fact_component_inventory_history`, `fact_inventory_policy`, and powers `vw_procurement_requirement`.

### `optimization/`
LP supplier allocation optimizer (PuLP/CBC). Takes the horizon-level net procurement requirement and eligible supplier pool, solves `min Σ cost × (1 + λ_risk × risk) × qty` subject to demand, budget, compliance, and diversification constraints. Supports three diversification modes: `none`, `supplier_share_only`, `country_diversified`.

### `analytics/`
Contract-driven supplier scoring engine (`scoring.py` + `metric_contract.yaml`). Scores suppliers on risk-adjusted cost using five risk dimensions (disruption, lead-time, logistics, cost instability, quality). Chart rendering functions used by the demo's `chart_agent`.

### `demo/`
LangGraph multi-agent UI. Two-phase fan-out pipeline: Phase 1 runs pipeline_agent (10 tools), data_agent (PostgreSQL MCP), and risk_agent (Tavily MCP) in parallel; Phase 2 runs chart_agent and lp_agent in parallel after Phase 1 completes. Human-in-the-loop approval interrupt between orchestration and execution.

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| `psql: error: database "procurement_agent" does not exist` | DB not created | Run the `CREATE DATABASE` step |
| SQL load fails with foreign key error | Wrong execution order | Re-run all 8 SQL files in the documented order |
| `ModuleNotFoundError: pulp` | Root venv not active or incomplete install | `source venv/bin/activate && pip install -r requirements.txt` |
| `ModuleNotFoundError` in demo | Demo venv not active | `cd demo && source venv/bin/activate` |
| Database connection fails | PostgreSQL not running | `brew services start postgresql` (macOS) / `sudo service postgresql start` (Linux) |
| LLM returns 401 | Expired or wrong API key | Check `AZURE_OPENAI_API_KEY` in `demo/.env` |
| MCP tools fail to load | MCP packages missing | `pip install postgres-mcp mcp-tavily mcp langchain-mcp-adapters` |
| Tavily returns no results | API key missing | Check `TAVILY_API_KEY` in `demo/.env` |
| `[Errno 48] address already in use` | Port 8501 occupied | `lsof -i :8501` then `kill <PID>` |
| LP returns zero demand | Inventory layer not run | Run `python -m inventory.run_inventory` |
| Forecast table empty | Production forecast not run | Run `python -m forecasting.run_production` |
| USA supplier prices ~$0.03 | Stale data in DB | Re-run all SQL load files in order |
| `Graph compiled OK` fails | LangGraph import error | Check `langgraph>=0.2` is installed in demo venv |
