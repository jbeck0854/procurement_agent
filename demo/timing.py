"""
Lightweight performance profiling for the agentic pipeline.
Usage:
    timer = PipelineTimer()
    with timer.step("orchestrator"):
        ...
    with timer.step("data_agent"):
        with timer.step("mcp_session_init"):
            ...
        with timer.step("react_loop"):
            ...
    print(timer.summary())
"""

import time
from contextlib import contextmanager


class PipelineTimer:
    def __init__(self):
        self.steps: list[dict] = []

    @contextmanager
    def step(self, name: str):
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.steps.append({"name": name, "duration": round(elapsed, 3)})

    def get(self, name: str) -> float | None:
        for s in self.steps:
            if s["name"] == name:
                return s["duration"]
        return None

    def to_dict(self) -> dict[str, float]:
        return {s["name"]: s["duration"] for s in self.steps}

    def summary(self) -> str:
        if not self.steps:
            return "No timing data recorded."
        lines = ["--- Pipeline Timing ---"]
        total = 0.0
        for s in self.steps:
            lines.append(f"  {s['name']:.<40s} {s['duration']:.3f}s")
            # Only sum top-level steps for total
            if "." not in s["name"]:
                total += s["duration"]
        lines.append(f"  {'TOTAL':.<40s} {total:.3f}s")
        lines.append("-" * 28)
        return "\n".join(lines)
