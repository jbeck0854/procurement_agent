"""
Orchestrator smoke test — verify routing accuracy and speed.

Usage:
    cd demo
    python smoke_test_v2.py
"""

import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import AZURE_DEPLOYMENT
from llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from graph.orchestrator import (
    ORCHESTRATOR_PROMPT,
    OrchestratorOutput,
)

# ── Test queries ─────────────────────────────────────────────────────────────

# Simulated prior LP context — injected before what-if/urgency queries
# to mimic real conversation history where an LP run already happened.
_LP_CONTEXT_MESSAGES = [
    HumanMessage(content=(
        "From our available suppliers, provide a procurement plan to ensure we "
        "have enough transistors across all facilities. Moderate risk aversion. "
        "No supplier should exceed 40%."
    )),
    SystemMessage(content=(
        "LP optimization completed for transistors. Parameters used: "
        "product=transistors, lambda_risk=0.5, max_supplier_share=0.4, "
        "diversification_mode=supplier_share_only. "
        "3 suppliers selected. Total cost: $245,000."
    )),
]

_NEEDS_LP_CONTEXT = {"What-if scenario", "Urgency rerun"}

TEST_QUERIES = [
    ("Kickoff / planning",
     "I need to make sure we can meet the next 12-16 weeks of demand "
     "for our semiconductor components. Minimize cost, but keep supplier "
     "risk at a moderate level."),
    ("Proceed / forecast",
     "Yes, proceed"),
    ("All-facilities forecast",
     "Compare forecast demand across all facilities"),
    ("Component requirements",
     "Show total component requirements for the upcoming demand window"),
    ("BOM translation",
     "How exactly is forecasted SKU demand translated into component demand?"),
    ("Procurement summary",
     "After our inventory is factored in, what is the total amount that needs "
     "to be ordered for each component to meet our upcoming demand?"),
    ("LP optimization",
     "From our available suppliers, provide a procurement plan to ensure we "
     "have enough transistors across all facilities to meet our upcoming "
     "demand window. Implement a moderate risk aversion supply strategy. "
     "No supplier should exceed 40% of total supply volume for this order."),
    ("What-if scenario",
     "What if SUP_HKG_38 becomes unavailable next quarter?"),
    ("Urgency rerun",
     "We need to expedite this component"),
    ("Out of scope",
     "What's the weather like today?"),
]


def run_test():
    """Run all queries against the orchestrator, return results."""
    llm = get_llm().with_structured_output(OrchestratorOutput)
    results = []

    print(f"\n{'='*70}")
    print(f"  Orchestrator Smoke Test  |  Model: {AZURE_DEPLOYMENT}")
    print(f"  Prompt length: ~{len(ORCHESTRATOR_PROMPT.split())} words")
    print(f"  Queries: {len(TEST_QUERIES)}")
    print(f"{'='*70}\n")

    total = 0.0
    for label, query in TEST_QUERIES:
        messages = [SystemMessage(content=ORCHESTRATOR_PROMPT)]
        if label in _NEEDS_LP_CONTEXT:
            messages.extend(_LP_CONTEXT_MESSAGES)
        messages.append(HumanMessage(content=query))
        t0 = time.perf_counter()
        try:
            result = llm.invoke(messages)
            elapsed = time.perf_counter() - t0
            total += elapsed

            tasks = []
            for t in result.tasks:
                d = t.model_dump()
                agent = d.get("agent", "?")
                tool = d.get("tool", "auto")
                params_raw = d.get("params_json")
                params_str = ""
                if params_raw:
                    try:
                        p = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
                        params_str = json.dumps(p, separators=(",", ":"))
                        if len(params_str) > 80:
                            params_str = params_str[:77] + "..."
                    except Exception:
                        params_str = str(params_raw)[:80]
                task_str = f"{agent}({tool or 'auto'})"
                if params_str:
                    task_str += f" {params_str}"
                tasks.append(task_str)

            tasks_display = " | ".join(tasks)
            print(f"  [{elapsed:5.1f}s] {label}")
            print(f"          intent: {result.intent}")
            print(f"          tasks:  {tasks_display}")
            results.append({"label": label, "elapsed": elapsed, "ok": True})

        except Exception as e:
            elapsed = time.perf_counter() - t0
            total += elapsed
            print(f"  [{elapsed:5.1f}s] {label} — ERROR: {e}")
            results.append({"label": label, "elapsed": elapsed, "ok": False, "error": str(e)})

    avg = total / len(TEST_QUERIES) if TEST_QUERIES else 0
    passed = sum(1 for r in results if r["ok"])
    print(f"\n  Total: {total:.1f}s  |  Average: {avg:.1f}s  |  Passed: {passed}/{len(TEST_QUERIES)}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run_test()
