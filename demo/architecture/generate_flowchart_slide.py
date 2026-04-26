"""
System Architecture — slide edition (16:9, one-minute talk).

Horizontal flow, large type, minimal chrome. Keeps the logical skeleton
of the poster (Orchestrator → HITL → Phase 1 fan-out → Phase 2 → Response)
but drops: dependency chips, legend, phase router pill, synth gate,
bypass paths. What remains is what you actually say out loud in 60–90s.

Outputs: architecture_flowchart_slide.png
"""

import graphviz

OUTPUT_PATH = "architecture_flowchart_slide"

LIME = "#76b900"
LIME_HALO = "#F4FAE8"
AMBER = "#D4A017"
AMBER_TINT = "#FBF1D6"
TEXT = "#1B2A21"
MUTED = "#6B7A72"

PHASE1_BORDER = "#3E8FCC"
PHASE1_HALO = "#E5EFF9"
PHASE2_BORDER = "#2EAD6B"
PHASE2_HALO = "#E4F5EC"


def agent(title, subtitle, border):
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="18" COLOR="{TEXT}">{title}</FONT></TD></TR>'
        f'<TR><TD HEIGHT="4"></TD></TR>'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica" POINT-SIZE="12" COLOR="{MUTED}">{subtitle}</FONT></TD></TR>'
        '</TABLE>>'
    )


def hero(title, subtitle):
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="20" COLOR="white">{title}</FONT></TD></TR>'
        f'<TR><TD HEIGHT="4"></TD></TR>'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica" POINT-SIZE="12" COLOR="#F4FAE8"><I>{subtitle}</I></FONT></TD></TR>'
        '</TABLE>>'
    )


def terminal(title, subtitle):
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="18" COLOR="{TEXT}">{title}</FONT></TD></TR>'
        f'<TR><TD HEIGHT="3"></TD></TR>'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica" POINT-SIZE="11" COLOR="{MUTED}">{subtitle}</FONT></TD></TR>'
        '</TABLE>>'
    )


def build() -> graphviz.Digraph:
    g = graphviz.Digraph("slide", format="png", engine="dot")
    g.attr(
        rankdir="LR",
        bgcolor="white",
        fontname="Helvetica",
        pad="0.5",
        nodesep="0.55",
        ranksep="0.95",
        dpi="200",
        compound="true",
        splines="spline",
        labelloc="t",
        label=(
            '<<FONT FACE="Helvetica Bold" POINT-SIZE="24" COLOR="#1B2A21">'
            'System Architecture</FONT><BR/>'
            '<FONT FACE="Helvetica" POINT-SIZE="13" COLOR="#6B7A72">'
            '<I>Two-phase multi-agent pipeline with human-in-the-loop gates</I></FONT>>'
        ),
    )
    g.attr("node", fontname="Helvetica", style="filled")
    g.attr("edge", fontname="Helvetica", fontsize="11",
           color=LIME, fontcolor=MUTED, arrowsize="0.9", penwidth="1.8")

    # Entry
    g.node("user", terminal("User", "natural-language request"),
           shape="box", style="filled,rounded", fillcolor="white",
           color=LIME, penwidth="2", margin="0.25,0.18")

    # Orchestrator
    g.node("orchestrator",
           hero("Orchestrator", "gpt-5.3-chat · intent routing"),
           shape="box", style="filled,rounded", fillcolor=LIME,
           color=LIME, penwidth="0", margin="0.30,0.22")

    # HITL gate
    g.node("approve",
           f'<<FONT FACE="Helvetica Bold" POINT-SIZE="14" COLOR="{AMBER}">Approve?</FONT><BR/>'
           f'<FONT FACE="Helvetica" POINT-SIZE="10" COLOR="{AMBER}"><I>HITL</I></FONT>>',
           shape="diamond", style="filled", fillcolor=AMBER_TINT,
           color=AMBER, penwidth="2.5", margin="0.20,0.08")

    # Phase 1 cluster
    with g.subgraph(name="cluster_phase1") as p1:
        p1.attr(
            label=(
                f'<<FONT FACE="Helvetica Bold" POINT-SIZE="13" COLOR="{PHASE1_BORDER}">'
                'PHASE 1</FONT>'
                f'<FONT FACE="Helvetica" POINT-SIZE="11" COLOR="{PHASE1_BORDER}">'
                ' — Data Retrieval</FONT>>'
            ),
            style="dashed,rounded",
            color=PHASE1_BORDER, bgcolor=PHASE1_HALO,
            penwidth="2.2", margin="14",
        )
        for key, title, sub in [
            ("pipeline_agent", "Pipeline Agent", "⚡ Fast · 10 tools"),
            ("data_agent",    "Data Agent",     "↻ ReAct · SQL"),
            ("risk_agent",    "Risk Agent",     "↻ ReAct · Web"),
        ]:
            p1.node(key, agent(title, sub, PHASE1_BORDER),
                    shape="box", style="filled,rounded",
                    fillcolor="white", color=PHASE1_BORDER,
                    penwidth="2", margin="0.22,0.16")

    # Phase 2 cluster
    with g.subgraph(name="cluster_phase2") as p2:
        p2.attr(
            label=(
                f'<<FONT FACE="Helvetica Bold" POINT-SIZE="13" COLOR="{PHASE2_BORDER}">'
                'PHASE 2</FONT>'
                f'<FONT FACE="Helvetica" POINT-SIZE="11" COLOR="{PHASE2_BORDER}">'
                ' — Analysis &amp; Optimization</FONT>>'
            ),
            style="dashed,rounded",
            color=PHASE2_BORDER, bgcolor=PHASE2_HALO,
            penwidth="2.2", margin="14",
        )
        p2.node("chart_agent",
                agent("Chart Builder", "⚡ Fast · charts &amp; scoring", PHASE2_BORDER),
                shape="box", style="filled,rounded",
                fillcolor="white", color=PHASE2_BORDER,
                penwidth="2", margin="0.22,0.16")
        p2.node("lp_agent",
                agent("LP Agent", "⚡ Fast · PuLP + CBC · HITL", PHASE2_BORDER),
                shape="box", style="filled,rounded",
                fillcolor="white", color=PHASE2_BORDER,
                penwidth="2", margin="0.22,0.16")

    # Synthesizer
    g.node("synthesizer",
           hero("Synthesizer", "gpt-5.3-chat · summary"),
           shape="box", style="filled,rounded", fillcolor=LIME,
           color=LIME, penwidth="0", margin="0.28,0.20")

    # Response
    g.node("response",
           terminal("Response", "text · tables · charts · allocations"),
           shape="box", style="filled,rounded", fillcolor="white",
           color=LIME, penwidth="2", margin="0.25,0.18")

    # Edges
    g.edge("user", "orchestrator")
    g.edge("orchestrator", "approve", label="  work orders  ")

    for tgt in ("pipeline_agent", "data_agent", "risk_agent"):
        g.edge("approve", tgt)

    for src in ("pipeline_agent", "data_agent", "risk_agent"):
        for tgt in ("chart_agent", "lp_agent"):
            g.edge(src, tgt, color="#B7D98A", penwidth="1.1")

    for src in ("chart_agent", "lp_agent"):
        g.edge(src, "synthesizer")

    g.edge("synthesizer", "response")

    # LP modify loop (amber dashed)
    g.edge("lp_agent", "orchestrator",
           label="  modify · re-plan  ",
           color=AMBER, fontcolor=AMBER, style="dashed",
           penwidth="1.6", constraint="false")

    return g


if __name__ == "__main__":
    g = build()
    path = g.render(OUTPUT_PATH, cleanup=True)
    print(f"Slide flowchart saved to: {path}")
