"""
Smoke test: verify Azure OpenAI connectivity + Orchestrator quality/speed.

Usage:
    cd demo
    python smoke_test.py
"""

import json
import time
import sys
import os

# Ensure project root is on path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from config import AZURE_DEPLOYMENT
from llm import get_llm

# ── Test 1: Basic connectivity ──────────────────────────────────────────────

print(f"=== Test 1: Smoke test — {AZURE_DEPLOYMENT} ===\n")
llm = get_llm()

t0 = time.perf_counter()
try:
    resp = llm.invoke("Say hello in one sentence.")
    t1 = time.perf_counter()
    print(f"  Response: {resp.content}")
    print(f"  Latency:  {t1 - t0:.2f}s")
    print(f"  Status:   OK\n")
except Exception as e:
    print(f"  ERROR: {e}\n")
    sys.exit(1)

# ── Test 2: Orchestrator structured output — kickoff query ──────────────────

from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage
from graph.orchestrator import ORCHESTRATOR_PROMPT, OrchestratorOutput

print(f"=== Test 2: Orchestrator structured output — kickoff query ===\n")

kickoff_query = (
    "I need to make sure we can meet the next 12-16 weeks of demand "
    "for our semiconductor components. Minimize cost, but keep supplier "
    "risk at a moderate level."
)
print(f"  User query: {kickoff_query}\n")

structured_llm = llm.with_structured_output(OrchestratorOutput)
messages = [
    SystemMessage(content=ORCHESTRATOR_PROMPT),
    HumanMessage(content=kickoff_query),
]

t0 = time.perf_counter()
try:
    result = structured_llm.invoke(messages)
    t1 = time.perf_counter()
    print(f"  Intent:   {result.intent}")
    print(f"  Tasks:    {len(result.tasks)}")
    for i, task in enumerate(result.tasks):
        print(f"    Task {i+1}: agent={task.agent}, tool={task.tool}, phase={task.phase}")
        if task.params_json:
            print(f"            params={task.params_json}")
        print(f"            objective: {task.objective}")
    print(f"\n  Latency:  {t1 - t0:.2f}s")
    print(f"  Status:   OK\n")
except Exception as e:
    print(f"  ERROR: {e}\n")
    sys.exit(1)

# ── Test 3: Orchestrator — demo script queries ──────────────────────────────

print(f"=== Test 3: Orchestrator — multiple demo queries ===\n")

test_queries = [
    ("Proceed / forecast", "Yes, proceed"),
    ("All-facilities forecast", "Compare forecast demand across all facilities"),
    ("Component requirements", "Show total component requirements for the upcoming demand window"),
    ("BOM translation", "How exactly is forecasted SKU demand translated into component demand?"),
    ("Procurement summary", "After our inventory is factored in, what is the total amount that needs to be ordered for each component to meet our upcoming demand?"),
    ("LP optimization", "From our available suppliers, provide a procurement plan to ensure we have enough transistors across all facilities to meet our upcoming demand window. Implement a moderate risk aversion supply strategy. No supplier should exceed 40% of total supply volume for this order."),
    ("What-if scenario", "What if SUP_HKG_38 becomes unavailable next quarter?"),
]

total_time = 0.0
for label, query in test_queries:
    messages = [
        SystemMessage(content=ORCHESTRATOR_PROMPT),
        HumanMessage(content=query),
    ]
    t0 = time.perf_counter()
    try:
        result = structured_llm.invoke(messages)
        t1 = time.perf_counter()
        elapsed = t1 - t0
        total_time += elapsed
        tasks_summary = ", ".join(
            f"{t.agent}({t.tool or 'auto'})" for t in result.tasks
        )
        print(f"  [{elapsed:.2f}s] {label}")
        print(f"          intent: {result.intent}")
        print(f"          tasks:  {tasks_summary}")
    except Exception as e:
        print(f"  [ERROR] {label}: {e}")

print(f"\n  Total:   {total_time:.2f}s for {len(test_queries)} queries")
print(f"  Average: {total_time / len(test_queries):.2f}s per query")
print(f"\n=== All tests complete ===")
