"""
Generate a diagram explaining helper functions pipeline.
Outputs: helpers_diagram.png
"""

import graphviz

OUTPUT_PATH = "helpers_diagram"


def build_diagram() -> graphviz.Digraph:
    g = graphviz.Digraph(
        "Helper Functions",
        format="png",
        engine="dot",
    )
    g.attr(
        rankdir="TB",
        bgcolor="white",
        fontname="Helvetica Neue",
        pad="0.5",
        nodesep="0.6",
        ranksep="0.7",
        dpi="200",
        label="Backend Helper Functions — What Each Script Does\n\n",
        labelloc="t",
        fontsize="16",
        fontcolor="#2C3E50",
    )
    g.attr("node", fontname="Helvetica Neue", fontsize="10", style="filled")
    g.attr("edge", fontname="Helvetica Neue", fontsize="9", color="#666666")

    # Colors
    C_DB = "#E67E22"
    C_STEP1 = "#3498DB"
    C_STEP2 = "#E74C3C"
    C_STEP3 = "#9B59B6"
    C_STEP4 = "#27AE60"
    C_HELPER = "#FDEBD0"
    C_OUTPUT = "#EBF5FB"
    C_Q = "#F9E79F"

    # ── Database (top) ──────────────────────────────────────────────
    g.node("db", "PostgreSQL  Procurement Database\n"
           "dim_forecast_run | fact_semiconductor_demand_forecast\n"
           "dim_bom | vw_component_requirement_lp\n"
           "fact_component_inventory_history | fact_inventory_policy\n"
           "vw_procurement_requirement | vw_supplier_complete_profile",
           shape="cylinder", fillcolor=C_DB, fontcolor="white",
           fontsize="9", width="5")

    # ════════════════════════════════════════════════════════════════
    # STEP 1: FORECASTING
    # ════════════════════════════════════════════════════════════════
    g.node("step1_label",
           "STEP 1 — Demand Forecasting\n"
           "forecasting/forecast_summary.py\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           '"Future 13-20 weeks, how much\n'
           'semiconductor demand do we expect?"',
           shape="box", fillcolor=C_STEP1, fontcolor="white",
           style="filled,rounded,bold", width="4")

    # Helpers
    g.node("h1a",
           "get_forecast_summary_tool()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Reads: dim_forecast_run +\n"
           "  fact_semiconductor_demand_forecast\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Returns: planning horizon,\n"
           "total demand, weekly totals,\n"
           "peak/lowest week, model metadata",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("h1b",
           "get_forecast_drilldown_tool()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Returns: week x facility x SKU\n"
           "detail with 90% confidence\n"
           "interval bounds\n"
           "Optional: export to CSV",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("h1c",
           "get_forecast_model_assessment()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Direction A: model validation\n"
           "Direction B: feature importance\n"
           "Direction C: baseline comparison\n"
           "Returns: summary + artifact path",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    # Example question
    g.node("q1", '"Show forecast for planning horizon"',
           shape="note", fillcolor=C_Q, fontcolor="#7D6608",
           fontsize="9")

    # ════════════════════════════════════════════════════════════════
    # STEP 2: BOM TRANSLATION
    # ════════════════════════════════════════════════════════════════
    g.node("step2_label",
           "STEP 2 — BOM Translation\n"
           "inventory/procurement_summary.py\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           '"Finished goods → What raw\n'
           'components do we need?"',
           shape="box", fillcolor=C_STEP2, fontcolor="white",
           style="filled,rounded,bold", width="4")

    g.node("h2a",
           "format_component_requirements()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Reads: vw_component_requirement_lp\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Returns: gross BOM demand\n"
           "per component type across\n"
           "ALL facilities x ALL weeks\n"
           "(before inventory offset)",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("h2b",
           "format_bom_translation()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Mode A: BOM recipe\n"
           "  1 SEMICONDUCTOR_6 =\n"
           "  3 transistors + 2 power_devices\n"
           "Mode B: forecast-row explosion\n"
           "  specific week x facility\n"
           "  demand → component qty",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("q2", '"Show total component requirements"\n'
           '"How does SKU translate to components?"',
           shape="note", fillcolor=C_Q, fontcolor="#7D6608",
           fontsize="9")

    # ════════════════════════════════════════════════════════════════
    # STEP 3: INVENTORY CHECK
    # ════════════════════════════════════════════════════════════════
    g.node("step3_label",
           "STEP 3 — Inventory & Procurement Need\n"
           "inventory/procurement_summary.py\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           '"We need 3000 transistors total,\n'
           'but we already have 500 in stock.\n'
           'How much do we actually need to BUY?"',
           shape="box", fillcolor=C_STEP3, fontcolor="white",
           style="filled,rounded,bold", width="4.5")

    g.node("h3a",
           "format_procurement_status()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Week-by-week rolling depletion:\n"
           "starting inventory shrinks each\n"
           "week until safety stock floor hit\n"
           "→ shows WHERE and WHEN\n"
           "procurement is triggered\n"
           "NOT the LP demand input",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("h3b",
           "format_aggregated_procurement_need()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Horizon-level LP demand floor:\n"
           "  net = gross_demand\n"
           "      + safety_stock + backorder\n"
           "      - on_hand - scheduled_recv\n"
           "THIS is what LP optimizes against\n"
           "Applied ONCE per facility",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("h3c",
           "get_procurement_requirement_drilldown()\n"
           "get_triggered_procurement_rows()\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Drilldown: week x facility x component\n"
           "Triggered: only rows where net > 0\n"
           "(weeks that actually need buying)",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("q3", '"Do we have enough inventory?"\n'
           '"What aggregated need for transistors?"',
           shape="note", fillcolor=C_Q, fontcolor="#7D6608",
           fontsize="9")

    # ════════════════════════════════════════════════════════════════
    # STEP 4: LP OPTIMIZATION
    # ════════════════════════════════════════════════════════════════
    g.node("step4_label",
           "STEP 4 — LP Optimization\n"
           "optimization/run_lp_optimization.py\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           '"We need to buy 2400 transistors.\n'
           'Which suppliers? How much each?"',
           shape="box", fillcolor=C_STEP4, fontcolor="white",
           style="filled,rounded,bold", width="4")

    g.node("h4a",
           "run(LPParams) → dict\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "min  Σ cost x (1 + λ x risk) x qty\n"
           "s.t. total ≥ demand\n"
           "     per_supplier ≤ max_share\n"
           "     compliance ≥ threshold\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "Returns: allocation table,\n"
           "cost summary, executive summary,\n"
           "formula description, baseline\n"
           "comparison",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("h4b",
           "Key User Parameters\n"
           "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
           "product: which component\n"
           "lambda_risk: 0=cost, 1=risk\n"
           "max_supplier_share: cap %\n"
           "urgency: penalize slow suppliers\n"
           "exclude_supplier_ids: what-if\n"
           "diversification_mode:\n"
           "  none | share_only | country",
           shape="box", fillcolor=C_HELPER, fontcolor="#784212",
           style="filled,rounded")

    g.node("q4", '"Optimize transistors, moderate risk, 40% cap"\n'
           '"What if SUP_HKG_38 unavailable?"\n'
           '"Diversify across countries"',
           shape="note", fillcolor=C_Q, fontcolor="#7D6608",
           fontsize="9")

    # ── Example output at bottom ────────────────────────────────────
    g.node("output",
           "Final Output Example\n"
           "═══════════════════════════════════\n"
           "SUP_CAN_10 (CAN) — 505,520 units (40%)\n"
           "SUP_HKG_38 (HKG) — 505,520 units (40%)\n"
           "SUP_HKG_35 (HKG) — 252,760 units (20%)\n"
           "Total: $133,046  |  Avg risk: 0.277\n"
           "═══════════════════════════════════",
           shape="box", fillcolor="#D5F5E3", fontcolor="#1E8449",
           style="filled,rounded", fontsize="9")

    # ── Ranks ───────────────────────────────────────────────────────
    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("step1_label")
        s.node("h1a")
        s.node("h1b")
        s.node("h1c")
        s.node("q1")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("step2_label")
        s.node("h2a")
        s.node("h2b")
        s.node("q2")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("step3_label")
        s.node("h3a")
        s.node("h3b")
        s.node("h3c")
        s.node("q3")

    with g.subgraph() as s:
        s.attr(rank="same")
        s.node("step4_label")
        s.node("h4a")
        s.node("h4b")
        s.node("q4")

    # ── Edges: main vertical flow ───────────────────────────────────
    g.edge("db", "step1_label", penwidth="2", color=C_STEP1,
           label="  historical demand")
    g.edge("step1_label", "step2_label", penwidth="2", color=C_STEP2,
           label="  finished-good forecast\n  (weekly x facility x SKU)")
    g.edge("step2_label", "step3_label", penwidth="2", color=C_STEP3,
           label="  gross component demand\n  (BOM-exploded)")
    g.edge("step3_label", "step4_label", penwidth="2", color=C_STEP4,
           label="  net procurement need\n  (inventory-adjusted)")
    g.edge("step4_label", "output", penwidth="2", color=C_STEP4)

    # ── Edges: step → helpers ───────────────────────────────────────
    g.edge("step1_label", "h1a", color=C_STEP1, style="dashed",
           arrowsize="0.7")
    g.edge("step1_label", "h1b", color=C_STEP1, style="dashed",
           arrowsize="0.7")
    g.edge("step1_label", "h1c", color=C_STEP1, style="dashed",
           arrowsize="0.7")

    g.edge("step2_label", "h2a", color=C_STEP2, style="dashed",
           arrowsize="0.7")
    g.edge("step2_label", "h2b", color=C_STEP2, style="dashed",
           arrowsize="0.7")

    g.edge("step3_label", "h3a", color=C_STEP3, style="dashed",
           arrowsize="0.7")
    g.edge("step3_label", "h3b", color=C_STEP3, style="dashed",
           arrowsize="0.7")
    g.edge("step3_label", "h3c", color=C_STEP3, style="dashed",
           arrowsize="0.7")

    g.edge("step4_label", "h4a", color=C_STEP4, style="dashed",
           arrowsize="0.7")
    g.edge("step4_label", "h4b", color=C_STEP4, style="dashed",
           arrowsize="0.7")

    # ── Edges: questions ────────────────────────────────────────────
    g.edge("q1", "h1a", style="dotted", color="#D4AC0D",
           arrowsize="0.5", constraint="false")
    g.edge("q2", "h2a", style="dotted", color="#D4AC0D",
           arrowsize="0.5", constraint="false")
    g.edge("q3", "h3b", style="dotted", color="#D4AC0D",
           arrowsize="0.5", constraint="false")
    g.edge("q4", "h4a", style="dotted", color="#D4AC0D",
           arrowsize="0.5", constraint="false")

    return g


if __name__ == "__main__":
    g = build_diagram()
    path = g.render(OUTPUT_PATH, cleanup=True)
    print(f"Helpers diagram saved to: {path}")
