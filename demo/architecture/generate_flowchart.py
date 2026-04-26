"""
System Architecture flowchart — poster edition (V3.1).

Keeps V1 visual language (Graphviz DOT, Phase 1 / Phase 2 dashed cluster
boxes) but (a) inlines each agent's external dependency as a small chip
inside the card — no more spaghetti arrows to a separate deps row, and
(b) uses white terminals with lime borders, not black. All fonts sized
up for poster legibility.

Fixes vs earlier team draft:
  - model name is gpt-5.3-chat, not GPT-5 Mini
  - Orchestrator → Approve? (HITL amber) → Phase 1 → Phase Router
    → Phase 2 → needs-synthesis? → (Synthesizer | bypass) → Response
  - Synthesizer is a conditional stop (fires only if Data or Risk ran)
  - LP Agent amber dashed "modify · re-plan" back to Orchestrator

Outputs: architecture_flowchart.png
"""

import graphviz

OUTPUT_PATH = "architecture_flowchart"

# ── Palette (slide-deck design language) ────────────────────────────
# Brand green: bright saturated mint, matches "Procurement Pilot" title
LIME = "#5CDC7A"
LIME_SOFT = "#8AE7A0"
LIME_TINT = "#E8FAED"
LIME_HALO = "#F2FCF6"

AMBER = "#D4A017"
AMBER_TINT = "#FBF1D6"

INK = "#0A0A0A"
TEXT = "#111111"
MUTED = "#5A6A62"
LINE = "#D4DBD7"

PHASE1_BORDER = "#3E8FCC"
PHASE1_HALO = "#EBF3FA"
PHASE1_CARD = "#FFFFFF"

PHASE2_BORDER = "#1F9A5A"
PHASE2_HALO = "#ECF7F0"
PHASE2_CARD = "#FFFFFF"

DEP_PG = "#CC7A1E"
DEP_TAVILY = "#12886B"
DEP_SOLVER = "#4D5B6B"


def pill(bg, fg, text, size=12):
    return (
        f'<TD BGCOLOR="{bg}" ALIGN="CENTER" CELLPADDING="6" HEIGHT="26">'
        f'<FONT FACE="Helvetica Bold" POINT-SIZE="{size}" COLOR="{fg}">'
        f'&nbsp;{text}&nbsp;</FONT></TD>'
    )


def agent_label(title, subtitle, pills_row, summary, uses_pill=None,
                title_color=TEXT, border_color=PHASE1_BORDER):
    pill_cells = "".join(pills_row)
    n_cols = max(len(pills_row), 1)
    uses_row = ""
    if uses_pill:
        uses_row = (
            f'<TR><TD COLSPAN="{n_cols}" HEIGHT="6"></TD></TR>'
            f'<TR><TD COLSPAN="{n_cols}" ALIGN="CENTER">'
            f'<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
            f'<TR>{uses_pill}</TR></TABLE></TD></TR>'
        )
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD COLSPAN="{n_cols}" ALIGN="CENTER">'
        f'<FONT FACE="Helvetica Bold" POINT-SIZE="19" COLOR="{title_color}">'
        f'{title}</FONT></TD></TR>'
        f'<TR><TD COLSPAN="{n_cols}" ALIGN="CENTER">'
        f'<FONT FACE="Helvetica" POINT-SIZE="13" COLOR="{MUTED}">'
        f'{subtitle}</FONT></TD></TR>'
        f'<TR><TD COLSPAN="{n_cols}" HEIGHT="10"></TD></TR>'
        f'<TR>{pill_cells}</TR>'
        f'<TR><TD COLSPAN="{n_cols}" HEIGHT="9"></TD></TR>'
        f'<TR><TD COLSPAN="{n_cols}" ALIGN="CENTER">'
        f'<FONT FACE="Helvetica" POINT-SIZE="13" COLOR="{TEXT}">'
        f'{summary}</FONT></TD></TR>'
        f'{uses_row}'
        '</TABLE>>'
    )


def hero_label(title, subtitle, pills_row):
    pill_cells = "".join(pills_row)
    n_cols = max(len(pills_row), 1)
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD COLSPAN="{n_cols}" ALIGN="CENTER">'
        f'<FONT FACE="Helvetica Bold" POINT-SIZE="22" COLOR="{INK}">'
        f'{title}</FONT></TD></TR>'
        f'<TR><TD COLSPAN="{n_cols}" ALIGN="CENTER">'
        f'<FONT FACE="Helvetica" POINT-SIZE="13" COLOR="#0F2416">'
        f'<I>{subtitle}</I></FONT></TD></TR>'
        f'<TR><TD COLSPAN="{n_cols}" HEIGHT="10"></TD></TR>'
        f'<TR>{pill_cells}</TR>'
        '</TABLE>>'
    )


def terminal_label(title, subtitle):
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER">'
        f'<FONT FACE="Helvetica Bold" POINT-SIZE="19" COLOR="{TEXT}">'
        f'{title}</FONT></TD></TR>'
        f'<TR><TD ALIGN="CENTER">'
        f'<FONT FACE="Helvetica" POINT-SIZE="13" COLOR="{MUTED}">'
        f'{subtitle}</FONT></TD></TR>'
        '</TABLE>>'
    )


def build_flowchart() -> graphviz.Digraph:
    g = graphviz.Digraph(
        "Procurement Pilot — System Architecture",
        format="png",
        engine="dot",
    )
    g.attr(
        rankdir="TB",
        bgcolor="white",
        fontname="Helvetica",
        pad="0.8",
        nodesep="1.1",
        ranksep="1.15",
        dpi="220",
        compound="true",
        splines="spline",
        labelloc="t",
        label=(
            f'<<FONT FACE="Helvetica Bold" POINT-SIZE="32" COLOR="{LIME}">'
            'Procurement Pilot</FONT>'
            f'<FONT FACE="Helvetica Bold" POINT-SIZE="32" COLOR="{TEXT}">'
            ' — System Architecture</FONT><BR/>'
            f'<FONT FACE="Helvetica" POINT-SIZE="15" COLOR="{MUTED}">'
            '<I>Hybrid LangGraph orchestrator  ·  parallel two-phase agent '
            'fleet  ·  human-in-the-loop gates</I></FONT>>'
        ),
    )
    g.attr("node", fontname="Helvetica", style="filled")
    g.attr("edge", fontname="Helvetica", fontsize="13", color=LIME,
           fontcolor=MUTED, arrowsize="1.0", penwidth="1.8")

    # ── Terminals (white fill, lime border) ──────────────────────────
    g.node(
        "user",
        terminal_label("User", "natural-language request"),
        shape="box", style="filled,rounded", fillcolor="white",
        color=LIME, penwidth="2", margin="0.32,0.18",
    )
    g.node(
        "streamlit",
        terminal_label("Streamlit UI",
                       "dark theme · streaming · plan approval"),
        shape="box", style="filled,rounded", fillcolor="white",
        color=LIME, penwidth="2", margin="0.32,0.18",
    )

    # ── Orchestrator (hero) ───────────────────────────────────────────
    g.node(
        "orchestrator",
        hero_label(
            "Orchestrator",
            "gpt-5.3-chat  ·  hybrid routing engine",
            [
                pill("white", TEXT, "INTENT", 13),
                '<TD WIDTH="6"></TD>',
                pill("white", TEXT, "23 FEW-SHOT", 13),
                '<TD WIDTH="6"></TD>',
                pill("white", TEXT, "REGEX PARAMS", 13),
            ],
        ),
        shape="box", style="filled,rounded", fillcolor=LIME,
        color=LIME, penwidth="0", margin="0.40,0.22",
    )

    # ── Approve? diamond (amber HITL) ─────────────────────────────────
    g.node(
        "approve",
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="19" COLOR="{AMBER}">Approve?</FONT></TD></TR>'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="12" COLOR="{AMBER}"><I>HITL gate</I></FONT></TD></TR>'
        '</TABLE>>',
        shape="diamond", style="filled", fillcolor=AMBER_TINT,
        color=AMBER, penwidth="2.8", margin="0.30,0.12",
    )

    # ════ PHASE 1 cluster ═════════════════════════════════════════════
    with g.subgraph(name="cluster_phase1") as p1:
        p1.attr(
            label=(
                '<<FONT FACE="Helvetica Bold" POINT-SIZE="17" '
                f'COLOR="{PHASE1_BORDER}">PHASE 1 </FONT>'
                '<FONT FACE="Helvetica" POINT-SIZE="14" '
                f'COLOR="{PHASE1_BORDER}">— Data Retrieval · parallel fan-out</FONT>>'
            ),
            style="dashed,rounded",
            color=PHASE1_BORDER,
            bgcolor=PHASE1_HALO,
            penwidth="2.8",
            margin="22",
        )
        p1.node(
            "pipeline_agent",
            agent_label(
                "Pipeline Agent",
                "Direct Execution  ·  zero LLM in loop",
                [
                    pill(LIME, INK, "⚡ FAST"),
                    '<TD WIDTH="5"></TD>',
                    pill("#F4FAE8", TEXT, "10 TOOLS"),
                ],
                "Forecast · BOM · Inventory · Procurement",
                uses_pill=pill("white", DEP_PG, "uses: PostgreSQL", 11),
                border_color=PHASE1_BORDER,
            ),
            shape="box", style="filled,rounded",
            fillcolor=PHASE1_CARD, color=PHASE1_BORDER, penwidth="2",
            margin="0.28,0.20",
        )
        p1.node(
            "data_agent",
            agent_label(
                "Data Agent",
                "ReAct Loop",
                [
                    pill(PHASE1_BORDER, "white", "↻ REACT"),
                    '<TD WIDTH="5"></TD>',
                    pill("#EAF3FB", TEXT, "SQL"),
                ],
                "Free-form queries over procurement DB",
                uses_pill=pill("white", DEP_PG, "uses: Postgres MCP", 11),
                border_color=PHASE1_BORDER,
            ),
            shape="box", style="filled,rounded",
            fillcolor=PHASE1_CARD, color=PHASE1_BORDER, penwidth="2",
            margin="0.28,0.20",
        )
        p1.node(
            "risk_agent",
            agent_label(
                "Risk Agent",
                "ReAct Loop",
                [
                    pill(PHASE1_BORDER, "white", "↻ REACT"),
                    '<TD WIDTH="5"></TD>',
                    pill("#EAF3FB", TEXT, "WEB"),
                ],
                "Geopolitical &amp; tariff news search",
                uses_pill=pill("white", DEP_TAVILY, "uses: Tavily MCP", 11),
                border_color=PHASE1_BORDER,
            ),
            shape="box", style="filled,rounded",
            fillcolor=PHASE1_CARD, color=PHASE1_BORDER, penwidth="2",
            margin="0.28,0.20",
        )

    # ── Phase Router pill ────────────────────────────────────────────
    g.node(
        "phase_router",
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="16" COLOR="{TEXT}">Phase Router</FONT></TD></TR>'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica" POINT-SIZE="12" COLOR="{MUTED}"><I>dispatch by intent</I></FONT></TD></TR>'
        '</TABLE>>',
        shape="box", style="filled,rounded", fillcolor=LIME_HALO,
        color=LIME, penwidth="2.2", margin="0.34,0.16",
    )

    # ════ PHASE 2 cluster ════════════════════════════════════════════
    with g.subgraph(name="cluster_phase2") as p2:
        p2.attr(
            label=(
                '<<FONT FACE="Helvetica Bold" POINT-SIZE="17" '
                f'COLOR="{PHASE2_BORDER}">PHASE 2 </FONT>'
                '<FONT FACE="Helvetica" POINT-SIZE="14" '
                f'COLOR="{PHASE2_BORDER}">— Analysis &amp; Optimization · parallel</FONT>>'
            ),
            style="dashed,rounded",
            color=PHASE2_BORDER,
            bgcolor=PHASE2_HALO,
            penwidth="2.8",
            margin="22",
        )
        p2.node(
            "chart_agent",
            agent_label(
                "ChartBuilder",
                "Direct Execution",
                [
                    pill(LIME, INK, "⚡ FAST"),
                    '<TD WIDTH="5"></TD>',
                    pill("#E4F5EC", TEXT, "7 TOOLS"),
                ],
                "Supplier scoring · charts · comparisons",
                uses_pill=pill("white", DEP_PG,
                               "uses: PostgreSQL (read-only)", 11),
                border_color=PHASE2_BORDER,
            ),
            shape="box", style="filled,rounded",
            fillcolor=PHASE2_CARD, color=PHASE2_BORDER, penwidth="2",
            margin="0.28,0.20",
        )
        p2.node(
            "lp_agent",
            agent_label(
                "LP Optimizer",
                "Direct Execution  ·  procurement optimizer",
                [
                    pill(LIME, INK, "⚡ FAST"),
                    '<TD WIDTH="5"></TD>',
                    pill(AMBER, "white", "⏸ HITL"),
                ],
                "Risk-adjusted allocation · approve / modify",
                uses_pill=pill("white", DEP_SOLVER,
                               "uses: PuLP + CBC solver", 11),
                border_color=PHASE2_BORDER,
            ),
            shape="box", style="filled,rounded",
            fillcolor=PHASE2_CARD, color=PHASE2_BORDER, penwidth="2",
            margin="0.28,0.20",
        )

    # ── needs synthesis? diamond ──────────────────────────────────────
    g.node(
        "synth_gate",
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica Bold" POINT-SIZE="17" COLOR="{TEXT}">needs synthesis?</FONT></TD></TR>'
        f'<TR><TD ALIGN="CENTER"><FONT FACE="Helvetica" POINT-SIZE="12" COLOR="{MUTED}"><I>fires if Data or Risk ran</I></FONT></TD></TR>'
        '</TABLE>>',
        shape="diamond", style="filled", fillcolor=LIME_HALO,
        color=LIME, penwidth="2.8", margin="0.34,0.14",
    )

    # ── Synthesizer (hero) ────────────────────────────────────────────
    g.node(
        "synthesizer",
        hero_label(
            "Synthesizer",
            "gpt-5.3-chat  ·  executive summary",
            [
                pill("white", TEXT, "SUMMARY", 13),
                '<TD WIDTH="6"></TD>',
                pill("white", TEXT, "NEXT STEPS", 13),
            ],
        ),
        shape="box", style="filled,rounded", fillcolor=LIME,
        color=LIME, penwidth="0", margin="0.36,0.20",
    )

    # ── Response terminal (white, lime border) ────────────────────────
    g.node(
        "response",
        terminal_label("Response",
                       "text · tables · charts · LP allocations"),
        shape="box", style="filled,rounded", fillcolor="white",
        color=LIME, penwidth="2", margin="0.36,0.18",
    )

    # ════ EDGES ═══════════════════════════════════════════════════════
    g.edge("user", "streamlit", color=LIME, penwidth="1.8")
    g.edge("streamlit", "orchestrator", color=LIME, penwidth="1.8")

    g.edge("orchestrator", "approve",
           label="  work orders  ", color=LIME, penwidth="1.8",
           fontcolor=MUTED)

    for target, lbl in (
        ("pipeline_agent", "  structured queries"),
        ("data_agent", "  SQL explore"),
        ("risk_agent", "  geopolitical"),
    ):
        g.edge("approve", target, label=lbl, color=LIME, penwidth="1.6",
               fontcolor=MUTED)

    # Phase 1 → Phase Router
    for src in ("pipeline_agent", "data_agent", "risk_agent"):
        g.edge(src, "phase_router", color=LIME, penwidth="1.4")

    g.edge("phase_router", "chart_agent",
           label="  chart task", color=LIME, penwidth="1.5",
           fontcolor=MUTED)
    g.edge("phase_router", "lp_agent",
           label="  optimization task", color=LIME, penwidth="1.5",
           fontcolor=MUTED)
    # Bypass Phase 2 when only Data/Risk produced text
    g.edge("phase_router", "synth_gate",
           label="  text-only flow", color=LIME_SOFT, penwidth="1.2",
           style="dashed", fontcolor=MUTED, constraint="false")

    # Phase 2 → synth gate
    g.edge("chart_agent", "synth_gate", color=LIME, penwidth="1.5")
    g.edge("lp_agent", "synth_gate", color=LIME, penwidth="1.5")

    # synth gate → synthesizer (yes) / bypass to response (no)
    g.edge("synth_gate", "synthesizer",
           label="  yes", color=LIME, penwidth="1.8",
           fontcolor=LIME)
    g.edge("synth_gate", "response",
           label="  no · bypass", color=MUTED, penwidth="1.3",
           style="dashed", fontcolor=MUTED, constraint="false")

    g.edge("synthesizer", "response", color=LIME, penwidth="1.8")

    # LP modify loop (amber dashed)
    g.edge("lp_agent", "orchestrator",
           label="  modify · re-plan  ", color=AMBER, penwidth="1.6",
           style="dashed", fontcolor=AMBER, constraint="false",
           arrowsize="1.0")

    # ── Legend (compact, right-aligned footnote) ─────────────────────
    # Combine into a single plaintext node so it reads as one tidy block,
    # then anchor it to the right of Response with an invisible spacer.
    g.node(
        "legend",
        (
            '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6">'
            f'<TR><TD ALIGN="LEFT" COLSPAN="2"><FONT FACE="Helvetica Bold" POINT-SIZE="12" COLOR="{MUTED}">LEGEND</FONT></TD></TR>'
            f'<TR><TD ALIGN="LEFT"><FONT FACE="Helvetica Bold" POINT-SIZE="13" COLOR="{LIME}">━━</FONT></TD>'
            f'<TD ALIGN="LEFT"><FONT FACE="Helvetica" POINT-SIZE="13" COLOR="{TEXT}">Primary flow</FONT></TD></TR>'
            f'<TR><TD ALIGN="LEFT"><FONT FACE="Helvetica Bold" POINT-SIZE="13" COLOR="{AMBER}">⧫</FONT></TD>'
            f'<TD ALIGN="LEFT"><FONT FACE="Helvetica" POINT-SIZE="13" COLOR="{TEXT}">HITL gate / loop</FONT></TD></TR>'
            f'<TR><TD ALIGN="LEFT"><FONT FACE="Helvetica Bold" POINT-SIZE="13" COLOR="{MUTED}">┈┈</FONT></TD>'
            f'<TD ALIGN="LEFT"><FONT FACE="Helvetica" POINT-SIZE="13" COLOR="{TEXT}">Optional path / bypass</FONT></TD></TR>'
            '</TABLE>>'
        ),
        shape="box", style="filled,rounded",
        fillcolor="white", color=LINE, penwidth="1",
        margin="0.18,0.10",
    )
    # Invisible spacer so legend ends up on the right of Response
    g.node("leg_spacer", "", shape="plaintext", width="1.4", height="0.01")
    with g.subgraph() as r:
        r.attr(rank="same")
        r.node("leg_spacer"); r.node("response"); r.node("legend")
    g.edge("leg_spacer", "response", style="invis")
    g.edge("response", "legend", style="invis")

    return g


if __name__ == "__main__":
    g = build_flowchart()
    path = g.render(OUTPUT_PATH, cleanup=True)
    print(f"Flowchart saved to: {path}")
