# Procurement Supply Chain Agent — Demo

An AI-powered procurement analysis system that ranks suppliers by risk-adjusted cost and cross-references real-time geopolitical news to surface supply chain risks.

## Architecture

```
User Query
    ↓
Orchestrator (LLM) ─── generates structured tasks + human-in-the-loop approval
    ↓
┌─────────────────────────┐
│  Parallel Execution     │
│                         │
│  Data Agent             │  Direct tool call → PostgreSQL + Scoring Engine
│  Search Agent           │  ReAct loop → Tavily News Search (geopolitical risk)
└─────────────────────────┘
    ↓
Synthesizer (LLM) ─── cross-analysis & actionable recommendations
    ↓
Streamed Response (progressive output as each agent completes)
```

**Key technologies:** LangGraph, Azure OpenAI, PostgreSQL (via MCP), Tavily Web Search (via MCP), Streamlit, FastAPI

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

| Query | What it tests |
|-------|---------------|
| `How many suppliers are in the database?` | SQL query via MCP (Data Agent, ReAct mode) |
| `Rank the top 3 transistor suppliers for 10000 units, I care about risk` | Supplier scoring (Data Agent, direct tool call) |
| `Give me a breakdown of suppliers per country` | SQL analytics (Data Agent, ReAct mode) |
| `Rank the top 5 microprocessor suppliers for 50000 units, balanced risk. I'm concerned about recent tariff changes.` | Parallel scoring + geopolitical news (Data Agent + Search Agent) |

### Available products

Use these product names in queries (case-insensitive):

`transistors` · `microprocessors` · `integrated_circuit_components` · `power_devices`

## Project Structure

```
demo/
├── main.py                 # FastAPI server (/chat, /resume endpoints)
├── streamlit_app.py        # Streamlit UI with streaming output
├── config.py               # Environment variables and paths
├── llm.py                  # Azure OpenAI client setup
├── mcp_client.py           # PostgreSQL MCP session management
├── tavily_client.py        # Tavily MCP session management
├── timing.py               # Performance profiling utilities
├── .env                    # API keys (create this file — see step 3)
├── graph/
│   ├── builder.py          # LangGraph state graph (parallel fan-out/fan-in)
│   ├── state.py            # AgentState with merge reducers
│   ├── orchestrator.py     # Plan generation + human approval interrupt
│   ├── data_agent.py       # Direct tool call or ReAct fallback
│   ├── search_agent.py     # Tavily news search with ReAct
│   └── synthesizer.py      # Lightweight cross-analysis
└── tools/
    └── scoring.py          # score_suppliers tool (DB query + scoring engine)
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
