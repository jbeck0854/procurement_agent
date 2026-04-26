"""
Generate a system architecture flowchart for the Procurement Intelligence Agent.
Reflects the refactored hybrid orchestrator architecture (April 2026).
Outputs: architecture_flowchart.png
"""

import graphviz

OUTPUT_PATH = "architecture_flowchart"


def build_flowchart() -> graphviz.Digraph:
    g = graphviz.Digraph(
        "Procurement Agent Architecture",
        format="png",
        engine="dot",
    )
    g.attr(
        rankdir="TB",
        bgcolor="white",
        fontname="Helvetica Neue",
        pad="0.8",
        nodesep="0.9",
        ranksep="1.0",
        dpi="200",
        compound="true",
    )
    g.attr("node", fontname="Helvetica Neue", fontsize="11", style="filled")
    g.attr("edge", fontname="Helvetica Neue", fontsize="9", color="#666666")

    # ── Colors ──────────────────────────────────────────────────────
    C_USER = "#2C3E50"
    C_ORCH = "#C0392B"
    C_P1 = "#2980B9"
    C_P2 = "#27AE60"
    C_SYNTH = "#8E44AD"
    C_DB = "#E67E22"
    C_OOS = "#95A5A6"
    C_SKIP = "#7F8C8D"

    # ════════════════════════════════════════════════════════════════
    # TOP: User → Streamlit → Orchestrator
    # ════════════════════════════════════════════════════════════════

    g.node("user", "  User  \n(Natural Language)",
           shape="ellipse", fillcolor=C_USER, fontcolor="white",
           fontsize="14", penwidth="0")

    g.node("streamlit",
           "  Streamlit UI  \n  Dark Theme · Streaming · Rich Rendering  ",
           shape="box", fillcolor="#34495E", fontcolor="white",
           style="filled,rounded", width="3.5")

    g.node("orchestrator",
           "Hybrid Orchestrator (GPT-5 Mini)\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "1. LLM classifies intent → selects agent + tool\n"
           "2. param_extractor.py fills LP params (code-side, 0ms)\n"
           "3. interrupt() → User approves work plan",
           shape="box", fillcolor=C_ORCH, fontcolor="white",
           style="filled,rounded,bold", penwidth="2", width="5")

    g.node("oos", "Out of Scope\n(fixed refusal)",
           shape="box", fillcolor=C_OOS, fontcolor="white",
           style="filled,rounded", fontsize="9")

    # ════════════════════════════════════════════════════════════════
    # PHASE 1: Data Retrieval
    # ════════════════════════════════════════════════════════════════

    with g.subgraph(name="cluster_phase1") as p1:
        p1.attr(
            label="PHASE 1 — Data Retrieval (parallel fan-out)",
            style="dashed,rounded", color=C_P1, fontcolor=C_P1,
            fontsize="13", fontname="Helvetica Neue Bold",
            bgcolor="#F7FBFF", penwidth="1.5",
        )
        p1.node("pipeline_agent",
                "Pipeline Agent\n(Direct Execution)\n───────────\n"
                "10 pre-built tools\nForecast · BOM\nInventory · Procurement",
                shape="box", fillcolor="#D6EAF8", fontcolor="#1A5276",
                style="filled,rounded", width="2.6")
        p1.node("data_agent",
                "Data Agent\n(ReAct Loop)\n───────────\n"
                "Free-form SQL\nPostgres MCP",
                shape="box", fillcolor="#D6EAF8", fontcolor="#1A5276",
                style="filled,rounded", width="2.2")
        p1.node("risk_agent",
                "Risk Agent\n(ReAct Loop)\n───────────\n"
                "Web Search\nTavily MCP",
                shape="box", fillcolor="#D6EAF8", fontcolor="#1A5276",
                style="filled,rounded", width="2.2")

    # ════════════════════════════════════════════════════════════════
    # PHASE 2: Analysis & Optimization
    # ════════════════════════════════════════════════════════════════

    with g.subgraph(name="cluster_phase2") as p2:
        p2.attr(
            label="PHASE 2 — Analysis & Optimization (parallel fan-out)",
            style="dashed,rounded", color=C_P2, fontcolor=C_P2,
            fontsize="13", fontname="Helvetica Neue Bold",
            bgcolor="#F5FFF5", penwidth="1.5",
        )
        p2.node("chart_agent",
                "Chart Agent\n(Direct Execution)\n───────────\n"
                "7 chart tools\nSupplier Scoring",
                shape="box", fillcolor="#D5F5E3", fontcolor="#1E8449",
                style="filled,rounded", width="2.6")
        p2.node("lp_agent",
                "LP Agent\n(Direct Execution)\n───────────\n"
                "Procurement Optimizer\nPuLP/CBC Solver\ninterrupt() → User Approval",
                shape="box", fillcolor="#D5F5E3", fontcolor="#1E8449",
                style="filled,rounded", width="2.8")

    # ════════════════════════════════════════════════════════════════
    # POST-EXECUTION ROUTING
    # ════════════════════════════════════════════════════════════════

    g.node("synthesizer",
           "  Synthesizer (GPT-5 Mini)  \n"
           "  Executive Summary · Next Steps  ",
           shape="box", fillcolor=C_SYNTH, fontcolor="white",
           style="filled,rounded", width="3")

    g.node("end_direct",
           "END (Direct Return)\n"
           "━━━━━━━━━━━━━━━━━━━━\n"
           "⚡ Skip Synthesizer\n"
           "Structured results go\n"
           "straight to UI",
           shape="box", fillcolor="#E8E8E8", fontcolor="#555555",
           style="filled,rounded,dashed", fontsize="9", width="2.2")

    g.node("response",
           "  Response  \n(Text + Charts + Structured Data)",
           shape="ellipse", fillcolor=C_USER, fontcolor="white",
           fontsize="13", penwidth="0")

    # ── Demo note ──────────────────────────────────────────────────
    g.node("demo_note",
           "⚡ Demo Speed Optimization\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "In demo, pipeline / chart / LP agents\n"
           "skip Synthesizer and return structured\n"
           "results directly for speed (~4s vs ~12s).\n"
           "Synthesizer is part of the full architecture\n"
           "and fires for data_agent / risk_agent flows\n"
           "(free-form text needing LLM summary).",
           shape="note", fillcolor="#F5EEF8", fontcolor="#6C3483",
           fontsize="9")

    # ════════════════════════════════════════════════════════════════
    # INFRASTRUCTURE (right side)
    # ════════════════════════════════════════════════════════════════

    g.node("backend",
           "Backend Modules\n═══════════════\n"
           "forecasting/forecast_summary.py\n"
           "inventory/procurement_summary.py\n"
           "optimization/run_lp_optimization.py\n"
           "analytics/scoring.py + charts/",
           shape="box3d", fillcolor="#FDEBD0", fontcolor="#784212",
           fontsize="9", style="filled")

    g.node("postgres", "  PostgreSQL  \n  Procurement DB  ",
           shape="cylinder", fillcolor=C_DB, fontcolor="white",
           fontsize="10")
    g.node("tavily", "  Tavily API  \n  (Web Search)  ",
           shape="cylinder", fillcolor="#1ABC9C", fontcolor="white",
           fontsize="10")

    # ════════════════════════════════════════════════════════════════
    # RANK CONSTRAINTS
    # ════════════════════════════════════════════════════════════════

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("synthesizer")
        s.node("end_direct")
        s.node("demo_note")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("backend")
        s.node("postgres")
        s.node("tavily")

    # ════════════════════════════════════════════════════════════════
    # EDGES: Main Flow
    # ════════════════════════════════════════════════════════════════

    g.edge("user", "streamlit", penwidth="1.5")
    g.edge("streamlit", "orchestrator", penwidth="1.5")

    # Orchestrator → out_of_scope
    g.edge("orchestrator", "oos", label="  unrelated",
           color=C_OOS, style="dashed", constraint="false")
    g.edge("oos", "response", color=C_OOS, style="dashed",
           constraint="false")

    # ── Orchestrator → Phase 1 ─────────────────────────────────────
    g.edge("orchestrator", "pipeline_agent", color=C_P1, penwidth="1.5",
           label="  structured\n  queries")
    g.edge("orchestrator", "data_agent", color=C_P1, penwidth="1.5",
           label="  SQL explore")
    g.edge("orchestrator", "risk_agent", color=C_P1, penwidth="1.5",
           label="  geopolitical")

    # ── Phase 1 → Phase 2 ─────────────────────────────────────────
    g.edge("pipeline_agent", "chart_agent", color=C_P2, penwidth="1.5",
           label="  data →\n  visualization")
    g.edge("pipeline_agent", "lp_agent", color=C_P2, penwidth="1.5",
           label="  data →\n  optimization")

    # ════════════════════════════════════════════════════════════════
    # EDGES: Post-Execution Routing (key architectural change)
    # ════════════════════════════════════════════════════════════════

    # data_agent / risk_agent → Synthesizer (needs LLM summary)
    g.edge("data_agent", "synthesizer", color=C_SYNTH, penwidth="1.5",
           label="  free-form →\n  LLM summary")
    g.edge("risk_agent", "synthesizer", color=C_SYNTH, penwidth="1.5",
           label="  risk intel →\n  LLM summary")

    # pipeline / chart / LP → END directly (skip Synthesizer)
    g.edge("pipeline_agent", "end_direct", color=C_SKIP,
           style="dashed", penwidth="1.2")
    g.edge("chart_agent", "end_direct", color=C_SKIP,
           style="dashed", penwidth="1.2")
    g.edge("lp_agent", "end_direct", color=C_SKIP,
           style="dashed", penwidth="1.2")

    # Both paths → Response
    g.edge("synthesizer", "response", penwidth="1.5", color=C_SYNTH)
    g.edge("end_direct", "response", penwidth="1.2", color=C_SKIP,
           style="dashed")

    # Demo note → END
    g.edge("demo_note", "end_direct", style="dotted", color="#6C3483",
           arrowsize="0.5", constraint="false")

    # ════════════════════════════════════════════════════════════════
    # EDGES: Infrastructure (side connections)
    # ════════════════════════════════════════════════════════════════

    g.edge("pipeline_agent", "backend", style="dotted", color="#B0B0B0",
           arrowsize="0.7", constraint="false", label="helpers")
    g.edge("chart_agent", "backend", style="dotted", color="#B0B0B0",
           arrowsize="0.7", constraint="false")
    g.edge("lp_agent", "backend", style="dotted", color="#B0B0B0",
           arrowsize="0.7", constraint="false")

    g.edge("backend", "postgres", style="dotted", color="#CCCCCC",
           arrowsize="0.6")
    g.edge("data_agent", "postgres", style="dashed", color=C_DB,
           constraint="false", label="MCP", fontcolor=C_DB, fontsize="8")
    g.edge("risk_agent", "tavily", style="dashed", color="#1ABC9C",
           constraint="false", label="MCP", fontcolor="#1ABC9C", fontsize="8")

    return g


if __name__ == "__main__":
    g = build_flowchart()
    path = g.render(OUTPUT_PATH, cleanup=True)
    print(f"Flowchart saved to: {path}")
