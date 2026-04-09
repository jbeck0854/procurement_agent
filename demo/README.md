# Procurement Supply Chain Agent — Demo

An AI-powered procurement intelligence platform that moves from demand forecasting to optimized supplier allocation through a conversational multi-agent interface.

## Architecture

```
User Query
    |
Streamlit UI  (streamlit_app.py)
    |
Orchestrator (GPT-5 Mini) --- intent recognition, task planning, param extraction
    |                          human-in-the-loop approval (interrupt)
    |
Phase 1 --- Data Retrieval (parallel):
+-----------------------------------------------------------------------+
|  pipeline_agent  |  10 direct-mode tools: forecast, BOM, inventory,   |
|                  |  procurement status, drill-downs (sub-second)       |
|  data_agent      |  Free-form SQL exploration via MCP PostgreSQL      |
|  risk_agent      |  Geopolitical risk search via Tavily MCP           |
+-----------------------------------------------------------------------+
    |  (phase2_router --- waits for Phase 1)
    |
Phase 2 --- Analysis & Optimization (parallel):
+-----------------------------------------------------------------------+
|  chart_agent     |  7 chart tools + supplier scoring (direct mode)    |
|  lp_agent        |  LP procurement optimization via PuLP/CBC solver   |
+-----------------------------------------------------------------------+
    |
Synthesizer (GPT-5 Mini) --- executive summary + actionable next steps
    |
Streamed Response (text + charts + allocation tables)
```

See `architecture/architecture_flowchart.png` for a visual diagram.

### Agent Responsibilities

| Agent | Phase | Mode | Tools | When Triggered |
|-------|-------|------|-------|----------------|
| **pipeline_agent** | 1 | Direct | 10 pipeline tools | Forecast, BOM, inventory, procurement queries (demo main flow) |
| **data_agent** | 1 | ReAct | MCP PostgreSQL | Exploratory SQL queries ("how many suppliers?", "list products") |
| **risk_agent** | 1 | ReAct | Tavily MCP | User asks about geopolitical risks, tariffs, sanctions, news |
| **chart_agent** | 2 | Direct | 7 chart tools + scoring | Supplier ranking, scoring, any visualization request |
| **lp_agent** | 2 | Direct | LP optimizer | "Optimize transistors", "what if supplier X unavailable?" |

### Pipeline Tools (pipeline_agent)

| Tool | Description |
|------|-------------|
| `query_forecast_summary` | Production demand forecast summary (planning horizon, weekly totals) |
| `query_forecast_drilldown` | Week x facility x SKU detail with confidence bounds |
| `query_forecast_model_assessment` | Model explainability (validation / features / baseline) |
| `query_component_requirements` | Full-horizon gross BOM demand across all components |
| `query_bom_translation` | BOM recipe: how finished-good SKU maps to procurement components |
| `query_procurement_status` | Week-by-week inventory-adjusted procurement trigger signal |
| `query_procurement_planning_summary` | Combined gross demand + weekly trigger signal |
| `query_aggregated_procurement_need` | Horizon-level LP demand floor (what optimizer allocates against) |
| `query_procurement_drilldown` | Week-by-week detail at component x facility x week grain |
| `query_triggered_procurement_rows` | Only weeks/facilities where net requirement > 0 |

### Chart Tools (chart_agent)

| Tool | Description |
|------|-------------|
| `plot_score_breakdown` | 4-panel score decomposition (final score, cost, risk penalty, risk components) |
| `plot_supplier_comparison` | Side-by-side supplier cost/risk comparison |
| `plot_country_comparison` | Country logistics (LPI) and governance (WGI) indicators |
| `plot_price_trend` | Product price trend over time |
| `plot_volatility_trend` | Rolling price volatility |
| `plot_cross_country_volatility` | Cross-country volatility comparison |
| `plot_price_vs_commodity` | Product price vs commodity baselines |

### LP Optimization (lp_agent)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `product` | (required) | transistors, microprocessors, integrated_circuit_components, power_devices |
| `lambda_risk` | 0.5 | Risk aversion: 0 = pure cost, 1 = pure risk |
| `max_supplier_share` | 1.0 | Max fraction of volume per supplier |
| `budget_cap` | None | Optional USD budget cap |
| `urgency` | false | Penalize slow suppliers with lead-time premium |
| `exclude_supplier_ids` | [] | Force-exclude suppliers (what-if scenarios) |
| `diversification_mode` | "none" | "none" / "supplier_share_only" / "country_diversified" |

**Key technologies:** LangGraph, Azure OpenAI, PostgreSQL (via MCP), Tavily Web Search (via MCP), PuLP (LP solver), Streamlit, matplotlib

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Python | 3.12+ |
| PostgreSQL | Running locally. `psql --version` to verify |
| Azure OpenAI API key | For LLM calls (GPT-5-mini) |
| Tavily API key | Free tier at [tavily.com](https://tavily.com) |

## Quick Start

### 1. Set up the database

Run SQL files **in this exact order** from the **project root** (`procurement_agent/`):

```bash
sudo -u postgres psql -c "CREATE DATABASE procurement_agent;"

sudo -u postgres psql -d procurement_agent -f sql/dimensions.sql
sudo -u postgres psql -d procurement_agent -f sql/facts.sql
sudo -u postgres psql -d procurement_agent -f sql/load/stage.sql
sudo -u postgres psql -d procurement_agent -f sql/load/copy_staging.sql
sudo -u postgres psql -d procurement_agent -f sql/load/load_dimensions.sql
sudo -u postgres psql -d procurement_agent -f sql/load/load_facts.sql
sudo -u postgres psql -d procurement_agent -f sql/load/load_bom.sql
sudo -u postgres psql -d procurement_agent -f sql/views.sql
```

Verify:

```bash
sudo -u postgres psql -d procurement_agent -c "SELECT COUNT(*) FROM vw_supplier_complete_profile;"
# Expected: 89
```

See `sql/README.md` for full schema documentation.

### 2. Install dependencies

```bash
cd demo
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the `demo/` folder:

```
AZURE_OPENAI_API_KEY=your-azure-key-here
TAVILY_API_KEY=your-tavily-key-here
# Optional — override if your PostgreSQL user/port differs:
# DATABASE_URL=postgresql://youruser:@localhost:5432/procurement_agent
```

| Variable | Required | Where to get it |
|----------|----------|----------------|
| `AZURE_OPENAI_API_KEY` | Yes | Azure Portal -> OpenAI resource -> Keys |
| `TAVILY_API_KEY` | Yes | [tavily.com](https://tavily.com) -> Overview -> API Keys |
| `DATABASE_URL` | No | Defaults to `postgresql://localhost:5432/procurement_agent` |

### 4. Verify setup

Run each command from the `demo/` folder — all must pass before proceeding.

```bash
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

# Graph compilation
python -c "from graph.builder import build_graph; app = build_graph(); print('Graph compiled OK')"

# Pipeline tools (backend helpers)
python -c "from tools.pipeline_queries import DIRECT_PIPELINE_TOOLS; print(f'{len(DIRECT_PIPELINE_TOOLS)} pipeline tools loaded')"
# Expected: 10 pipeline tools loaded

# LP optimization
python -c "from tools.optimization import run_optimization; print('LP tools OK')"
```

### 5. Run the application

```bash
streamlit run streamlit_app.py
```

Open http://localhost:8501. Type a query, review the plan, click **Approve Plan**, and watch results stream in.

## Demo Flow (Presentation)

The demo walks through a complete procurement decision pipeline:

| Step | Question | Tool |
|------|----------|------|
| 1 | "Show forecast for the upcoming planning horizon" | query_forecast_summary |
| 2 | "Show total component requirements for the planning window" | query_component_requirements |
| 3 | "Do we have enough inventory? Show procurement status" | query_procurement_status |
| 4 | "Show aggregated procurement need for transistors" | query_aggregated_procurement_need |
| 5 | "Show me the top suppliers for transistors" | plot_score_breakdown |
| 6 | "Optimize transistors with moderate risk and 40% supplier cap" | run_optimization |
| 7 | "What if SUP_HKG_38 becomes unavailable?" | run_optimization (exclude) |
| 8 | "Diversify across countries" | run_optimization (country_diversified) |

See `team_docs/updates/tentative_planned_demo_precomputed_version.md` for the full demo script.

### Side questions (can be asked at any point)

| Query | Agent |
|-------|-------|
| "How many suppliers are in China?" | data_agent (SQL) |
| "Check recent semiconductor tariff news" | risk_agent (Tavily) |
| "Compare price volatility across China, Taiwan, USA" | chart_agent |

### Available products

`transistors` · `microprocessors` · `integrated_circuit_components` · `power_devices`

## Project Structure

```
demo/
├── streamlit_app.py          # Streamlit UI (main entry point)
├── main.py                   # FastAPI server (alternative)
├── config.py                 # Environment variables, DB URL, API keys
├── llm.py                    # Azure OpenAI client (GPT-5-mini)
├── mcp_client.py             # PostgreSQL MCP session management
├── tavily_client.py          # Tavily MCP session management
├── timing.py                 # Performance profiling utilities
├── .env                      # API keys (create this — see step 3)
├── requirements.txt          # Python dependencies
│
├── graph/
│   ├── builder.py            # LangGraph topology (two-phase fan-out)
│   ├── state.py              # AgentState schema
│   ├── orchestrator.py       # LLM task planning + human-in-the-loop
│   ├── pipeline_agent.py     # Direct-mode pipeline queries (10 tools)
│   ├── data_agent.py         # SQL exploration via MCP (ReAct)
│   ├── risk_agent.py         # Geopolitical risk via Tavily (ReAct)
│   ├── chart_agent.py        # Scoring + charts (direct mode)
│   ├── lp_agent.py           # LP procurement optimization (direct mode)
│   └── synthesizer.py        # Final executive summary
│
├── tools/
│   ├── pipeline_queries.py   # 10 direct-mode query wrappers (forecast, BOM, inventory)
│   ├── optimization.py       # LP optimization wrapper (-> optimization/run_lp_optimization.py)
│   ├── scoring.py            # Supplier scoring wrapper (-> analytics/scoring.py)
│   └── chart_tools.py        # 7 chart wrappers (-> analytics/charts/)
│
└── architecture/
    ├── generate_flowchart.py         # System architecture diagram generator
    ├── generate_helpers_diagram.py   # Helper functions diagram generator
    ├── architecture_flowchart.png    # System architecture (pre-generated)
    └── helpers_diagram.png           # Helper functions pipeline (pre-generated)
```

### Backend modules (outside demo/, read-only)

| Module | Purpose |
|--------|---------|
| `forecasting/forecast_summary.py` | Demand forecast helpers (summary, drilldown, model assessment) |
| `inventory/procurement_summary.py` | BOM translation, procurement status, aggregated need helpers |
| `optimization/run_lp_optimization.py` | LP solver (PuLP/CBC), supplier allocation optimizer |
| `analytics/scoring.py` | Supplier risk-adjusted scoring engine |
| `analytics/charts/` | matplotlib chart rendering functions |

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: pulp` | LP dependency missing | `pip install pulp` or `pip install -r requirements.txt` |
| `ModuleNotFoundError` (other) | venv not activated | `source venv/bin/activate && pip install -r requirements.txt` |
| Database connection fails | PostgreSQL not running | `brew services start postgresql` (macOS) |
| LLM returns 401 | API key expired or wrong | Check `AZURE_OPENAI_API_KEY` in `.env` |
| MCP tools fail to load | MCP packages not installed | `pip install postgres-mcp mcp-tavily` |
| Tavily search returns nothing | API key missing | Check `TAVILY_API_KEY` in `.env` |
| `[Errno 48] address already in use` | Port occupied | `lsof -i :8501` then `kill <PID>` |
| Query returns empty results | Product not in DB | Use one of the four products listed above |
| USA supplier prices look wrong (~$0.03) | DB not reloaded | Re-run SQL files in order (step 1) |
