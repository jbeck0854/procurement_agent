"""
Generate a system architecture flowchart for the Procurement Intelligence Agent.
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
        pad="0.5",
        nodesep="0.7",
        ranksep="0.9",
        dpi="200",
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

    # ── Row 0: User ─────────────────────────────────────────────────
    g.node("user", "  User  \n(Natural Language)",
           shape="ellipse", fillcolor=C_USER, fontcolor="white",
           fontsize="13", penwidth="0")

    # ── Row 1: Streamlit ────────────────────────────────────────────
    g.node("streamlit", "  Streamlit UI  ",
           shape="box", fillcolor="#34495E", fontcolor="white",
           style="filled,rounded", width="2")

    # ── Row 2: Orchestrator ─────────────────────────────────────────
    g.node("orchestrator",
           "  Orchestrator (GPT-5 Mini)  \n"
           "Intent | Task Planning | Params",
           shape="box", fillcolor=C_ORCH, fontcolor="white",
           style="filled,rounded,bold", penwidth="2")

    # ── Row 3: Approval ─────────────────────────────────────────────
    g.node("gate", "Approve?",
           shape="diamond", fillcolor="#FADBD8", fontcolor=C_ORCH,
           fontsize="10", width="1.0", height="0.7")

    # ── Row 4: Phase 1 label ────────────────────────────────────────
    g.node("p1_label",
           "PHASE 1 — Data Retrieval (parallel)",
           shape="plaintext", fontcolor=C_P1, fontsize="12",
           fontname="Helvetica Neue Bold")

    # Phase 1 agents
    g.node("pipeline_agent",
           "Pipeline Agent\n(Direct Mode)\n───────────\n"
           "10 pre-built tools\nForecast | BOM\nInventory | Procurement",
           shape="box", fillcolor="#D6EAF8", fontcolor="#1A5276",
           style="filled,rounded", width="2.4")
    g.node("data_agent",
           "Data Agent\n(ReAct Loop)\n───────────\n"
           "Free-form SQL\nPostgres MCP",
           shape="box", fillcolor="#D6EAF8", fontcolor="#1A5276",
           style="filled,rounded", width="2.0")
    g.node("risk_agent",
           "Risk Agent\n(ReAct Loop)\n───────────\n"
           "Web Search\nTavily MCP",
           shape="box", fillcolor="#D6EAF8", fontcolor="#1A5276",
           style="filled,rounded", width="2.0")

    # ── Row 5: Phase 2 label ────────────────────────────────────────
    g.node("p2_label",
           "PHASE 2 — Analysis & Optimization (parallel)",
           shape="plaintext", fontcolor=C_P2, fontsize="12",
           fontname="Helvetica Neue Bold")

    # Phase 2 agents
    g.node("chart_agent",
           "Chart Agent\n(Direct Mode)\n───────────\n"
           "7 chart tools\nSupplier Scoring",
           shape="box", fillcolor="#D5F5E3", fontcolor="#1E8449",
           style="filled,rounded", width="2.4")
    g.node("lp_agent",
           "LP Agent\n(Direct Mode)\n───────────\n"
           "Procurement Optimizer\nPuLP/CBC Solver\nBaseline Comparison",
           shape="box", fillcolor="#D5F5E3", fontcolor="#1E8449",
           style="filled,rounded", width="2.4")

    # ── Row 6: Synthesizer ──────────────────────────────────────────
    g.node("synthesizer",
           "  Synthesizer (GPT-5 Mini)  \n"
           "Executive Summary | Next Steps",
           shape="box", fillcolor=C_SYNTH, fontcolor="white",
           style="filled,rounded")

    # ── Row 7: Response ─────────────────────────────────────────────
    g.node("response", "  Response  \n(Text + Charts)",
           shape="ellipse", fillcolor=C_USER, fontcolor="white",
           fontsize="12", penwidth="0")

    # ── Side: Backend + DB ──────────────────────────────────────────
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

    # ── Enforce ranks ───────────────────────────────────────────────
    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("user")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("streamlit")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("orchestrator")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("gate")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("pipeline_agent")
        s.node("data_agent")
        s.node("risk_agent")
        s.node("p1_label")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("chart_agent")
        s.node("lp_agent")
        s.node("p2_label")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("synthesizer")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("response")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("backend")
        s.node("postgres")
        s.node("tavily")

    # ── Edges: Main vertical flow ───────────────────────────────────
    g.edge("user", "streamlit")
    g.edge("streamlit", "orchestrator")
    g.edge("orchestrator", "gate", label=" work\n orders")

    # Gate → Phase 1
    g.edge("gate", "pipeline_agent", color=C_P1, penwidth="1.5",
           label="demo queries")
    g.edge("gate", "data_agent", color=C_P1, penwidth="1.5",
           label="SQL explore")
    g.edge("gate", "risk_agent", color=C_P1, penwidth="1.5",
           label="geopolitical")

    # Invisible edge to position p1_label
    g.edge("gate", "p1_label", style="invis")
    g.edge("p1_label", "p2_label", style="invis")

    # Phase 1 → Phase 2
    g.edge("pipeline_agent", "chart_agent", color=C_P2,
           penwidth="1.5", label=" ")
    g.edge("pipeline_agent", "lp_agent", color=C_P2,
           penwidth="1.5", label=" ")
    g.edge("data_agent", "chart_agent", color="#CCCCCC", style="dashed")

    # Phase 2 → Synthesizer
    g.edge("chart_agent", "synthesizer", color=C_SYNTH, penwidth="1.5",
           label="charts + scores")
    g.edge("lp_agent", "synthesizer", color=C_SYNTH, penwidth="1.5",
           label="allocation + cost")
    g.edge("risk_agent", "synthesizer", color="#CCCCCC", style="dashed",
           label="risk intel\n(if called)")

    # Synthesizer → Response
    g.edge("synthesizer", "response")

    # ── Edges: Agents → Backend / DB (side connections) ─────────────
    g.edge("pipeline_agent", "backend", style="dotted", color="#B0B0B0",
           arrowsize="0.7", constraint="false", label="helpers")
    g.edge("chart_agent", "backend", style="dotted", color="#B0B0B0",
           arrowsize="0.7", constraint="false")
    g.edge("lp_agent", "backend", style="dotted", color="#B0B0B0",
           arrowsize="0.7", constraint="false")

    g.edge("backend", "postgres", style="dotted", color="#CCCCCC",
           arrowsize="0.6", constraint="false")
    g.edge("data_agent", "postgres", style="dashed", color=C_DB,
           constraint="false", label="MCP", fontcolor=C_DB, fontsize="8")
    g.edge("risk_agent", "tavily", style="dashed", color="#1ABC9C",
           constraint="false", label="MCP", fontcolor="#1ABC9C", fontsize="8")

    return g


if __name__ == "__main__":
    g = build_flowchart()
    path = g.render(OUTPUT_PATH, cleanup=True)
    print(f"Flowchart saved to: {path}")
