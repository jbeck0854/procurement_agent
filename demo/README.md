# Procurement Supply Chain Agent — Demo

An AI-powered procurement analysis system that ranks suppliers by risk-adjusted cost and cross-references real-time geopolitical news to surface supply chain risks.

## Architecture

```
User Query
    ↓
Orchestrator (LLM) ─── generates structured tasks + human-in-the-loop approval
    ↓
Phase 1 — Data & Risk Intelligence (parallel):
┌────────────────────────────────────────────────────┐
│  data_agent  │  SQL exploration via MCP PostgreSQL  │  (conditional)
│  risk_agent  │  Geopolitical risk via Tavily MCP    │  (conditional)
└────────────────────────────────────────────────────┘
    ↓  (phase2_router — waits for Phase 1 to complete)
Phase 2 — Scoring & Visualization:
┌────────────────────────────────────────────────────┐
│  chart_agent │  Self-contained: queries DB, scores  │
│              │  suppliers, renders matplotlib charts │
└────────────────────────────────────────────────────┘
    ↓
Synthesizer (LLM) ─── cross-analysis & actionable recommendations
    ↓
Streamed Response (charts + summary, progressive output)
```

### Agent Responsibilities

| Agent | Phase | Tools | When Triggered |
|-------|-------|-------|----------------|
| **data_agent** | 1 | MCP PostgreSQL (ReAct) | Exploratory SQL queries ("how many suppliers?", "list products") |
| **risk_agent** | 1 | Tavily MCP (ReAct) | User explicitly asks about geopolitical risks, tariffs, sanctions, news |
| **chart_agent** | 2 | 7 chart tools + internal scoring (direct mode) | Supplier ranking, scoring, any visualization request |

### Chart Tools (chart_agent)

| Tool | Description | Data Source |
|------|-------------|-------------|
| `plot_score_breakdown` | 4-panel score decomposition (final score, cost, risk penalty, risk components) | vw_supplier_complete_profile + SupplierScorer |
| `plot_supplier_comparison` | Side-by-side supplier cost/risk comparison | vw_supplier_complete_profile |
| `plot_country_comparison` | Country logistics (LPI) & governance (WGI) indicators | vw_country_risk_snapshot |
| `plot_price_trend` | Product price trend over time | vw_product_price_history |
| `plot_volatility_trend` | Rolling price volatility | vw_product_price_history |
| `plot_cross_country_volatility` | Cross-country volatility comparison | vw_product_price_history |
| `plot_price_vs_commodity` | Product price vs commodity baselines | vw_product_price_history + vw_commodity_price_history |

**Key technologies:** LangGraph, Azure OpenAI, PostgreSQL (via MCP), Tavily Web Search (via MCP), Streamlit, matplotlib

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Python | 3.12+ |
| PostgreSQL | `psql --version` to verify |
| Azure OpenAI API key | For LLM calls (GPT-5-mini) |
| Tavily API key | Free tier — 1,000 credits/month, no credit card required. Sign up at [tavily.com](https://tavily.com) |

## Quick Start

### 1. Set up the database

See `sql/README.md` for full instructions. Quick summary from the **project root**:

```bash
psql -U postgres -c "CREATE DATABASE procurement_agent;"
psql -U postgres -d procurement_agent -f sql/load/stage.sql
psql -U postgres -d procurement_agent -f sql/load/copy_staging.sql
psql -U postgres -d procurement_agent -f sql/dimensions.sql
psql -U postgres -d procurement_agent -f sql/load/load_dimensions.sql
psql -U postgres -d procurement_agent -f sql/facts.sql
psql -U postgres -d procurement_agent -f sql/load/load_facts.sql
psql -U postgres -d procurement_agent -f sql/views.sql
```

Verify:

```bash
psql -U postgres -d procurement_agent -c "SELECT COUNT(*) FROM vw_supplier_complete_profile;"
# Expected: 89
```

### 2. Install dependencies

```bash
cd demo
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the `demo/` folder:

```
AZURE_OPENAI_API_KEY=your-azure-key-here
TAVILY_API_KEY=your-tavily-key-here
# Optional — override if your PostgreSQL user/port differs from the defaults:
# DATABASE_URL=postgresql://youruser:@localhost:5432/procurement_agent
```

| Variable | Required | Where to get it |
|----------|----------|----------------|
| `AZURE_OPENAI_API_KEY` | Yes | Azure Portal → OpenAI resource → Keys |
| `TAVILY_API_KEY` | Yes | [tavily.com](https://tavily.com) → Overview → API Keys |
| `DATABASE_URL` | No | Defaults to `postgresql://localhost:5432/procurement_agent` |

### 4. Verify setup

Run each command — all must pass before proceeding.

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
# Expected: "Loaded 3 Tavily tools:" followed by tavily_web_search, tavily_answer_search, tavily_news_search

# Graph compilation
python -c "from graph.builder import build_graph; app = build_graph(); print('Graph compiled OK')"
```

### 5. Run the application

**Option A — Streamlit UI (recommended for demos):**

```bash
streamlit run streamlit_app.py
```

Open http://localhost:8501. Type a query, review the plan, click **Approve Plan**, and watch results stream in progressively.

**Option B — FastAPI server:**

```bash
python main.py
# Server runs at http://localhost:8000
```

## Usage

### API flow (two-step, human-in-the-loop)

Every query pauses after plan generation for approval:

```bash
# Step 1: Submit query → returns plan for review
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Rank the top 3 transistor suppliers for 10000 units, I care about risk"}' \
  | python -m json.tool

# Step 2: Approve plan → returns final analysis
curl -s -X POST http://localhost:8000/resume \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "<thread_id_from_step_1>", "feedback": "ok"}' \
  | python -m json.tool
```

### Example queries

| Query | Agents Used |
|-------|-------------|
| `Rank the top 3 transistor suppliers with balanced risk, show score breakdown` | chart_agent (plot_score_breakdown) |
| `Compare price volatility for microprocessors across China, Taiwan, and USA` | chart_agent (plot_cross_country_volatility) |
| `Show me the logistics and governance profile for Vietnam, China, and Korea` | chart_agent (plot_country_comparison) |
| `How many suppliers are in the database?` | data_agent (SQL via MCP) |
| `Rank top 5 power_devices suppliers, very risk averse. Also check recent geopolitical risks.` | risk_agent + chart_agent |

### Available products

Use these product names in queries (case-insensitive):

`transistors` · `microprocessors` · `integrated_circuit_components` · `power_devices`

## Project Structure

```
demo/
├── main.py                 # FastAPI server (/chat, /resume endpoints)
├── streamlit_app.py        # Streamlit UI with streaming output + chart rendering
├── config.py               # Environment variables, DB URL, API keys
├── llm.py                  # Azure OpenAI client setup (GPT-5-mini)
├── mcp_client.py           # PostgreSQL MCP session management
├── tavily_client.py        # Tavily MCP session management
├── timing.py               # Performance profiling utilities
├── .env                    # API keys (create this file — see step 3)
├── graph/
│   ├── builder.py          # Two-phase LangGraph topology with conditional routing
│   ├── state.py            # AgentState schema (tasks, agent_results, chart_results)
│   ├── orchestrator.py     # LLM task planning + human-in-the-loop approval (interrupt)
│   ├── data_agent.py       # SQL exploration via MCP PostgreSQL (ReAct)
│   ├── risk_agent.py       # Geopolitical risk analysis via Tavily MCP (ReAct)
│   ├── chart_agent.py      # Scoring + visualization, direct mode, multi-task support
│   └── synthesizer.py      # LLM cross-analysis, references charts, <150 words
└── tools/
    ├── scoring.py           # score_suppliers @tool wrapper (DB → SupplierScorer → markdown)
    └── chart_tools.py       # 7 chart function wrappers (conn → matplotlib → base64 PNG)
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `[Errno 48] address already in use` | Port 8000 occupied | `lsof -i :8000` then `kill <PID>` |
| Database connection fails | PostgreSQL not running | `brew services start postgresql` |
| LLM returns 401 | API key expired or wrong | Check `AZURE_OPENAI_API_KEY` in `.env` |
| MCP tools fail to load | `postgres-mcp` not installed | `pip install postgres-mcp` |
| Tavily tools fail to load | `mcp-tavily` not installed | `pip install mcp-tavily` |
| Tavily search returns no results | API key missing or invalid | Check `TAVILY_API_KEY` in `.env` |
| Query returns empty results | Product not in database | Use one of the four products listed above |
| `ModuleNotFoundError` | venv not activated | `source venv/bin/activate && pip install -r requirements.txt` |
