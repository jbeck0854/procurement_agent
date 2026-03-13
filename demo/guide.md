# Demo Test Guide

## Prerequisites

- Python 3.12+
- PostgreSQL installed (`psql --version` to verify)
- An Azure OpenAI API key

---

## Step 0: Set up the database

The demo depends on the `procurement_agent` PostgreSQL database. Follow the instructions in `sql/README.md` (in the project root) to create and load it.

Quick summary (run from the **project root**, not the demo folder):

```bash
cd /path/to/procurement_agent

# Create the database
psql -U postgres -c "CREATE DATABASE procurement_agent;"

# Run scripts in order
psql -U postgres -d procurement_agent -f sql/load/stage.sql
psql -U postgres -d procurement_agent -f sql/load/copy_staging.sql
psql -U postgres -d procurement_agent -f sql/dimensions.sql
psql -U postgres -d procurement_agent -f sql/load/load_dimensions.sql
psql -U postgres -d procurement_agent -f sql/facts.sql
psql -U postgres -d procurement_agent -f sql/load/load_facts.sql

# Create the view used by the demo
psql -U postgres -d procurement_agent -f sql/views.sql
```

Verify:

```bash
psql -U postgres -d procurement_agent -c "SELECT COUNT(*) FROM vw_supplier_complete_profile;"
```

Expected: a row count (e.g. 89).

---

## Step 1: Set up the demo environment

```bash
cd /path/to/procurement_agent/demo

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Step 2: Configure the API key

Create a `.env` file in the demo folder:

```bash
echo 'AZURE_OPENAI_API_KEY=your-key-here' > .env
```

Replace `your-key-here` with your actual Azure OpenAI API key.

---

## Step 3: Verify environment

Run each command one by one. All four must pass before proceeding.

### 3.1 Database connection

```bash
python -c "import psycopg2; conn = psycopg2.connect('postgresql://frank:@localhost:5432/procurement_agent'); print('DB OK'); conn.close()"
```

Expected: `DB OK`

### 3.2 LLM connection

```bash
python -c "from llm import get_llm; llm = get_llm(); print(llm.invoke('Say hello in one word').content)"
```

Expected: A greeting word (e.g. `Hello!`)

### 3.3 MCP tools

```bash
python mcp_client.py
```

Expected: `Loaded X MCP tools:` followed by tool names

### 3.4 Graph compilation

```bash
python -c "from graph.builder import build_graph; app = build_graph(); print('Graph compiled OK')"
```

Expected: `Graph compiled OK`

---

## Step 4: Start the FastAPI server

```bash
python main.py
```

Expected output:

```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

The server will keep running. **Open a new terminal window** for the test commands below. In the new window, activate the venv first:

```bash
cd /path/to/procurement_agent/demo
source venv/bin/activate
```

---

## Step 5: Test queries

### Test 1: Simple count (SQL query via MCP)

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many suppliers are in the database?"}' | python -m json.tool
```

Expected: Returns supplier count (89). Verifies the full pipeline: Orchestrator → Router → Data Agent (MCP SQL) → Synthesizer.

### Test 2: Supplier scoring and ranking

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Rank the top 3 transistor suppliers for an order of 10000 units, I care a lot about risk"}' | python -m json.tool
```

Expected: Returns top 3 ranked suppliers with risk-adjusted cost, lead time, disruption probability, and recommendations. Verifies Data Agent calls the `score_suppliers` tool.

### Test 3: SQL analytics

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Give me a breakdown of how many suppliers we have per country"}' | python -m json.tool
```

Expected: Returns supplier count grouped by country.

### Test 4: Chinese language query

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我分析一下 microprocessors 的供应商，采购量5000，风险敏感度中等"}' | python -m json.tool
```

Expected: Response in Chinese with microprocessor supplier analysis. Verifies the Synthesizer responds in the user's language.

---

## Step 6: Stop the server

Go back to the terminal running the server and press `Ctrl + C`.

---

## Available products in the database

Use these product names in your queries (case-insensitive):

- `transistors`
- `microprocessors`
- `integrated_circuit_components`
- `power_devices`

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `[Errno 48] address already in use` | Port 8000 occupied | `lsof -i :8000` then `kill <PID>` |
| Database connection fails | PostgreSQL not running | `brew services start postgresql` |
| LLM returns 401 | API key expired or wrong | Check `AZURE_OPENAI_API_KEY` in `.env` |
| MCP tools fail to load | `postgres-mcp` not installed | `pip install postgres-mcp` |
| Query returns empty results | Product not in database | Use one of the four products listed above |
| `ModuleNotFoundError` | venv not activated or deps missing | `source venv/bin/activate && pip install -r requirements.txt` |
