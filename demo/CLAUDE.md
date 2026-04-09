# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Primary UI (Streamlit)
streamlit run streamlit_app.py
# Opens http://localhost:8501

# Alternative REST API (FastAPI)
python main.py
# Runs on http://localhost:8000
```

## Verification Commands

```bash
# Test database connection
python -c "import psycopg2; conn = psycopg2.connect('postgresql://localhost:5432/procurement_agent'); print('DB OK'); conn.close()"

# Test LLM
python -c "from llm import get_llm; llm = get_llm(); print(llm.invoke('Say hello in one word').content)"

# Test MCP clients
python mcp_client.py
python tavily_client.py

# Test graph compiles
python -c "from graph.builder import build_graph; app = build_graph(); print('Graph compiled OK')"

# Test tools load
python -c "from tools.pipeline_queries import DIRECT_PIPELINE_TOOLS; print(f'{len(DIRECT_PIPELINE_TOOLS)} pipeline tools loaded')"
```

## Environment Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in `demo/`:
```
AZURE_OPENAI_API_KEY=...
TAVILY_API_KEY=...
# DATABASE_URL defaults to postgresql://localhost:5432/procurement_agent
```

Database initialization SQL lives in `../sql/` (parent directory).

## Architecture

This is a **LangGraph multi-agent orchestration system** for procurement supply chain intelligence. The LLM is Azure OpenAI (GPT-4o-mini, configured in `config.py`).

### Two-Phase Fan-Out Pipeline

```
User Query → Orchestrator (intent + task plan) → [Human-in-the-loop approval interrupt]
    ↓
Phase 1 (parallel):
  ├── pipeline_agent   — 10 direct-mode tools: forecast, BOM, inventory queries (sub-second)
  ├── data_agent       — ReAct loop via PostgreSQL MCP for exploratory SQL
  └── risk_agent       — ReAct loop via Tavily MCP for geopolitical risk/tariff news
    ↓
Phase 2 (parallel, after Phase 1 completes):
  ├── chart_agent      — 7 chart visualizations + supplier scoring (direct mode)
  └── lp_agent         — Linear programming optimization via PuLP/CBC
    ↓
Synthesizer → Executive summary streamed to UI
```

### Key Files

| File | Role |
|------|------|
| `graph/builder.py` | LangGraph state machine definition; nodes, edges, conditional routing |
| `graph/state.py` | `AgentState` TypedDict — the shared state schema for all agents |
| `graph/orchestrator.py` | Intent recognition, task planning, human-in-the-loop interrupt |
| `graph/synthesizer.py` | Final response generation |
| `graph/pipeline_agent.py` | Direct-mode agent wrapping the 10 pipeline tools |
| `graph/data_agent.py` | ReAct agent with PostgreSQL MCP |
| `graph/risk_agent.py` | ReAct agent with Tavily MCP |
| `graph/lp_agent.py` | Direct-mode LP optimization agent |
| `graph/chart_agent.py` | Direct-mode visualization + scoring agent |
| `tools/pipeline_queries.py` | 10 wrapped forecast/BOM/procurement query tools |
| `tools/optimization.py` | `run_optimization()` wrapper (calls `../optimization/run_lp_optimization.py`) |
| `tools/chart_tools.py` | 7 matplotlib chart tool wrappers |
| `tools/scoring.py` | Supplier scoring wrapper |
| `streamlit_app.py` | Main UI: streaming, session state, plan approval, chart rendering |
| `config.py` | All credentials and constants; reads from `.env` |
| `llm.py` | Azure OpenAI client factory |
| `mcp_client.py` | PostgreSQL MCP async session manager |
| `tavily_client.py` | Tavily MCP async session manager |
| `timing.py` | `PipelineTimer` context manager for per-agent profiling |

### Backend Modules (parent directory, read-only by demo)

The `tools/` wrappers call into sibling Python packages outside `demo/`:
- `../forecasting/forecast_summary.py` — demand forecast helpers
- `../inventory/procurement_summary.py` — BOM translation, procurement status
- `../optimization/run_lp_optimization.py` — PuLP/CBC LP solver
- `../analytics/scoring.py` — risk-adjusted supplier scoring
- `../analytics/charts/` — matplotlib chart renderers

### Agent State Schema (`graph/state.py`)

```python
AgentState {
    messages: List           # conversation history
    intent: str              # parsed user intent
    tasks: List[Task]        # orchestrator's work orders for Phase 1/2 agents
    current_agent: str       # active agent
    agent_results: Dict      # {agent_name: output text}
    chart_results: Dict      # {chart_name: base64 PNG}
    raw_data: Dict           # structured data from data_agent
    final_response: str      # synthesizer output
    timings: Dict            # per-agent execution times
}
```

### LP Optimization Parameters

The `run_optimization()` function (called by `lp_agent`) accepts:
- `product`: `"transistors" | "microprocessors" | "integrated_circuit_components" | "power_devices"`
- `lambda_risk`: `0.0` (cost-only) → `1.0` (risk-only)
- `diversification_mode`: `"none" | "supplier_share_only" | "country_diversified"`
- `max_supplier_share`, `budget_cap`, `urgency`, `exclude_supplier_ids`, `facility_id`, `forecast_run_id`

### Human-in-the-Loop Pattern

The orchestrator uses a LangGraph `interrupt` before dispatching agents. In `streamlit_app.py`, session state tracks `waiting_for_approval`. On approval, `graph.invoke(Command(resume=True), config)` resumes the graph. The FastAPI equivalent uses `POST /resume`.
