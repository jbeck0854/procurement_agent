from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.offsetbox import AnnotationBbox, VPacker, HPacker, TextArea

from analytics.scoring import SupplierScorer, load_contract


ANALYTICS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = ANALYTICS_DIR / "metric_contract.yaml"


DISPLAY_LABELS = {
    "supplier_id":          "Supplier",
    "country_code":         "Country",
    "product":              "Product",
    "decision_tier_global": "Global Tier",
    "decision_tier_local":  "Local Comparison Tier",
    "effective_unit_price": "Effective Unit Price",
    "landed_unit_cost":     "Landed Unit Cost",
    "risk_penalty":         "Risk Penalty",
    "risk_adjusted_cost":   "Risk-Adjusted Cost",
    "risk_disruption":      "Disruption Risk",
    "risk_leadtime":        "Lead Time Risk",
    "risk_logistics":       "Logistics Risk",
    "risk_cost_instability": "Cost Instability",
    "risk_quality":         "Quality Risk",
}

FINAL_SCORE_COLS    = ["risk_adjusted_cost"]
COST_DRIVER_COLS    = ["effective_unit_price", "landed_unit_cost"]
AGGREGATE_RISK_COLS = ["risk_penalty"]
RISK_DRIVER_COLS    = [
    "risk_disruption",
    "risk_leadtime",
    "risk_logistics",
    "risk_cost_instability",
    "risk_quality",
]


# ── Country color palette — identical across all three chart modules ───────────
COUNTRY_COLORS = {
    "USA": "#1F78B4",
    "CAN": "#D62728",
    "MEX": "#D84315",
    "BRA": "#FF7F0E",
    "GBR": "#6A3D9A",
    "FRA": "#E7298A",
    "DEU": "#33A02C",
    "NLD": "#BCBD22",
    "BEL": "#17BECF",
    "FIN": "#004D40",
    "JPN": "#F46D43",
    "KOR": "#0097A7",
    "CHN": "#546E7A",
    "TWN": "#FDD835",
    "HKG": "#74ADD1",
    "SGP": "#66C2A5",
    "MYS": "#A65628",
    "THA": "#E040FB",
    "IND": "#4DAC26",
    "IDN": "#C51B7D",
    "AUS": "#F06292",
    "ARE": "#FDB863",
}
_FALLBACK_PALETTE = [
    "#8DD3C7", "#FB8072", "#80B1D3", "#FDB462",
    "#B3DE69", "#FCCDE5", "#BC80BD", "#FFED6F",
]
_HATCH_STYLES = ["//", "\\\\", "xx", "++"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pretty_label(col: str) -> str:
    return DISPLAY_LABELS.get(col, col)


def _pretty_product_name(product: str) -> str:
    return product.replace("_", " ").title()


def _get_country_color(country_code: str, fallback_index: int = 0) -> str:
    if country_code in COUNTRY_COLORS:
        return COUNTRY_COLORS[country_code]
    return _FALLBACK_PALETTE[fallback_index % len(_FALLBACK_PALETTE)]


def _fmt_bar(val: float, col: str) -> str:
    """Format a bar annotation by metric type."""
    if col in ("effective_unit_price", "landed_unit_cost"):
        if val >= 10:
            return f"${val:.2f}"
        elif val >= 1:
            return f"${val:.3f}"
        else:
            return f"${val:.4f}"
    elif col == "risk_penalty":
        return f"{val:.2f}"
    elif col == "risk_adjusted_cost":
        return f"{val:.4f}"
    else:
        return f"{val:.3f}"   # risk components: 0–1


# ── Annotation box primitives (mirrors plot_country_logistics_governance_comparison_panel.py) ──

def _ta(text: str, size: float = 7.5, weight: str = "normal", color: str = "#111111") -> TextArea:
    return TextArea(text, textprops={"fontsize": size, "fontweight": weight, "color": color})


def _rule() -> TextArea:
    return _ta("\u2500" * 42, size=6, color="#BBBBBB")


def _spacer() -> TextArea:
    return _ta(" ", size=3)


def _inline(label: str, value: str, lsize: float = 7.5, vsize: float = 7.5):
    """Bold label + normal value side-by-side on one line."""
    return HPacker(
        children=[
            _ta(label + "  ", size=lsize, weight="bold"),
            _ta(value, size=vsize),
        ],
        pad=0, sep=0, align="baseline",
    )


def _place_annotation_box(ax, rows: list, xy: tuple = (1.04, 0.5)) -> None:
    """Wrap a list of TextArea / Packer rows in a styled AnnotationBbox."""
    packed = VPacker(children=rows, pad=6, sep=3, align="left")
    ab = AnnotationBbox(
        packed,
        xy=xy,
        xycoords="axes fraction",
        box_alignment=(0, 0.5),
        annotation_clip=False,
        bboxprops=dict(
            boxstyle="round,pad=0.5",
            facecolor="#F5F5F0",
            edgecolor="#BBBBBB",
            linewidth=0.9,
            alpha=0.97,
        ),
        frameon=True,
    )
    ax.add_artist(ab)


# ── Main plot function ────────────────────────────────────────────────────────

def plot_supplier_score_breakdown_panel(
    conn,
    supplier_ids: list[str],
    product: str,
    Q: int = 5000,
    lambda_risk: float | None = None,
    compliance_threshold: float | None = None,
    save_path: str | None = None,
):
    contract = load_contract(str(DEFAULT_CONTRACT_PATH))

    if not supplier_ids:
        raise ValueError("supplier_ids must contain at least 1 supplier")

    if len(supplier_ids) > 3:
        raise ValueError("Recommended maximum is 3 suppliers for readability")

    if Q <= 0:
        raise ValueError("Q must be a positive integer")

    # IMPORTANT: query the full product universe so global tiers are meaningful.
    query = """
        SELECT *
        FROM vw_supplier_complete_profile
        WHERE product = %(product)s
        ORDER BY supplier_id
    """

    universe_df = pd.read_sql(
        query,
        conn,
        params={"product": product},
    )

    if universe_df.empty:
        raise ValueError(f"No supplier data found for product={product}")

    scorer = SupplierScorer(contract)
    result = scorer.score(
        universe_df,
        Q=Q,
        lambda_risk=lambda_risk,
        top_k=len(universe_df),
        compare_supplier_ids=supplier_ids,
        compliance_threshold=compliance_threshold,
        compare_strict=False,
    )

    scored = result.ranked.copy()
    excluded_requested_suppliers = result.excluded_requested_suppliers

    if scored.empty:
        raise ValueError(
            f"No scored suppliers returned for selected supplier_ids={supplier_ids}, "
            f"product={product}"
        )

    required_cols = [
        "supplier_id", "country_code",
        "decision_tier_global", "decision_tier_local",
        "risk_adjusted_cost", "effective_unit_price", "landed_unit_cost",
        "risk_penalty", "risk_disruption", "risk_leadtime", "risk_logistics",
        "risk_cost_instability", "risk_quality",
    ]
    missing = [c for c in required_cols if c not in scored.columns]
    if missing:
        raise ValueError(
            "The scorer output is missing expected explainability columns: "
            f"{missing}"
        )

    lam_display = (
        lambda_risk
        if lambda_risk is not None
        else contract.metrics["risk_adjusted_cost"]["params"]["lambda_risk"]
    )

    threshold_display = (
        float(compliance_threshold)
        if compliance_threshold is not None
        else float(contract.constraints.get("compliance_gate", {}).get("threshold", 0.50))
    )

    n_suppliers = len(scored)

    # ── Country colors + hatching ─────────────────────────────────────────────
    # Hatching is applied ONLY when multiple suppliers share the same country.
    # Different countries always use distinct colors with no hatching.
    country_counts: dict[str, int] = scored["country_code"].value_counts().to_dict()
    hatch_cycle:    dict[str, int] = {}
    supplier_colors: list[str]        = []
    supplier_hatches: list[str | None] = []

    for i, (_, row) in enumerate(scored.iterrows()):
        cc = row["country_code"]
        supplier_colors.append(_get_country_color(cc, i))
        if country_counts.get(cc, 1) > 1:
            idx = hatch_cycle.get(cc, 0)
            hatch_cycle[cc] = idx + 1
            supplier_hatches.append(_HATCH_STYLES[idx % len(_HATCH_STYLES)] if idx > 0 else None)
        else:
            supplier_hatches.append(None)

    supplier_labels = [
        f"{row['supplier_id']} ({row['country_code']})"
        for _, row in scored.iterrows()
    ]

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(
        nrows=4,
        ncols=1,
        figsize=(16, 14),
        gridspec_kw={"height_ratios": [1.0, 1.1, 1.0, 1.6]},
    )

    _left        = 0.08
    right_margin = 0.72    # all 4 panels carry right-side annotation boxes
    title_x      = (_left + right_margin) / 2.0

    # ── Inner helper: draw bars + annotations for one panel ───────────────────
    def _draw_panel(ax, panel_cols: list, rotation: int = 20) -> None:
        n_groups  = len(panel_cols)
        x         = np.arange(n_groups)

        # Narrower bars for single-metric panels (Final Score, Risk Penalty).
        if n_groups == 1:
            bar_width = 0.14 if n_suppliers == 3 else 0.18
        else:
            bar_width = 0.20 if n_suppliers == 3 else 0.26

        offsets = (np.arange(n_suppliers) - (n_suppliers - 1) / 2.0) * (bar_width + 0.04)

        for i, (_, row) in enumerate(scored.iterrows()):
            values        = [float(row[col]) if pd.notna(row[col]) else 0.0 for col in panel_cols]
            bar_positions = x + offsets[i]

            bars = ax.bar(
                bar_positions,
                values,
                width=bar_width,
                label=supplier_labels[i],
                color=supplier_colors[i],
                hatch=supplier_hatches[i],
                edgecolor="white",
                linewidth=0.6,
                zorder=3,
            )

            for bar, col, val in zip(bars, panel_cols, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    val,
                    _fmt_bar(val, col),
                    ha="center", va="bottom",
                    fontsize=8, clip_on=False, zorder=4,
                )

        ax.set_xticks(x)
        if n_groups == 1:
            ax.set_xticklabels([])
            ax.tick_params(axis="x", bottom=False)
        else:
            ax.set_xticklabels(
                [_pretty_label(c) for c in panel_cols],
                rotation=rotation,
                ha="right",
                fontsize=9,
            )

        ax.grid(True, axis="y", alpha=0.18, linewidth=0.7, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="y", labelsize=8.5)
        ax.margins(y=0.22)

    # ═══════════════════════════════════════════════════════════════════════════
    # Panel 1 — Final Score = Risk Adjusted Cost
    # ═══════════════════════════════════════════════════════════════════════════
    axes[0].set_title("Final Score = Risk Adjusted Cost", fontsize=11, fontweight="bold", pad=10)
    axes[0].set_ylabel("Score", fontsize=9)
    _draw_panel(axes[0], FINAL_SCORE_COLS)

    rows_final = [
        _ta("Risk Adjusted Cost", size=8, weight="bold"),
        _rule(),
        _ta("Lower score = stronger procurement choice based on your risk aversion.", size=7.5),
        _spacer(),
        _ta("Formula:", size=7.5, weight="bold"),
        _ta("  Value = Norm(LandedCost) + λ · Norm(RiskPenalty)", size=7.5),
        _spacer(),
        _inline(f"\u03bb = {lam_display}", "(risk aversion parameter)"),
        _ta("  Higher \u03bb \u2192 risk weighted more heavily;", size=7.5, color="#444444"),
        _ta("  safer suppliers rank better, even if costlier.", size=7.5, color="#444444"),
        _rule(),
        _ta("Global Tier \u2014 vs. all suppliers for this product:", size=7.5, weight="bold"),
        _inline("Preferred:", "top third by risk-adjusted score"),
        _inline("Acceptable:", "middle third"),
        _inline("Avoid:", "bottom third"),
        _spacer(),
        _ta("This Comparison:", size=7.5, weight="bold"),
        *[
            _inline(
                f"{row['supplier_id']}:",
                str(row.get("decision_tier_global", "\u2014"))
                if pd.notna(row.get("decision_tier_global"))
                else "\u2014",
            )
            for _, row in scored.iterrows()
        ],
    ]
    _place_annotation_box(axes[0], rows_final)

    # ═══════════════════════════════════════════════════════════════════════════
    # Panel 2 — Cost Drivers
    # ═══════════════════════════════════════════════════════════════════════════
    axes[1].set_title("Cost Drivers", fontsize=11, fontweight="bold", pad=10)
    axes[1].set_ylabel("Unit Cost ($)", fontsize=9)
    axes[1].yaxis.set_major_formatter(
        mticker.FuncFormatter(
            lambda v, _: f"${v:.2f}" if v >= 1 else f"${v:.4f}"
        )
    )
    _draw_panel(axes[1], COST_DRIVER_COLS, rotation=15)

    # Build cost drivers annotation dynamically per supplier
    rows_cost: list = [
        _ta("Effective Unit Price", size=8, weight="bold"),
        _rule(),
        _ta("Baseline price with bulk discount applied when", size=7.5),
        _ta("Q \u2265 MOQ; otherwise effective unit price = baseline unit price.", size=7.5),
        _spacer(),
    ]
    for _, row in scored.iterrows():
        sid  = row["supplier_id"]
        cc   = row.get("country_code", "")
        disc = row.get("bulk_discount", None) if "bulk_discount" in scored.columns else None
        moq  = row.get("bulk_units",   None) if "bulk_units"    in scored.columns else None
        disc_str = f"{float(disc)*100:.1f}% discount" if pd.notna(disc) else "discount n/a"
        moq_str  = f"MOQ = {float(moq):,.0f} units"  if pd.notna(moq)  else "MOQ n/a"
        rows_cost.append(_inline(f"{sid} ({cc}):", f"{disc_str}  \u00b7  {moq_str}"))

    rows_cost += [
        _spacer(),
        _rule(),
        _ta("Landed Unit Cost", size=8, weight="bold"),
        _rule(),
        _ta("Effective price \u00d7 (1 + MFN tariff rate).", size=7.5),
        _spacer(),
    ]
    for _, row in scored.iterrows():
        sid   = row["supplier_id"]
        cc    = row.get("country_code", "")
        rate  = row.get("mfn_text_rate_pct", None) if "mfn_text_rate_pct"  in scored.columns else None
        hts8  = row.get("hts8",              None) if "hts8"               in scored.columns else None
        tdesc = row.get("tariff_description", None) if "tariff_description" in scored.columns else None

        if pd.notna(rate) and float(rate) > 0:
            rate_str = f"{float(rate):.1f}% tariff"
            code_str = f"  [{hts8}]" if pd.notna(hts8) and hts8 else ""
            rows_cost.append(_inline(f"{sid} ({cc}):", f"{rate_str}{code_str}"))
            if pd.notna(tdesc) and tdesc:
                rows_cost.append(_ta('  "Printed circuit assemblies"', size=7, color="#555555"))
        else:
            rows_cost.append(_inline(f"{sid} ({cc}):", "no tariff applied"))

    _place_annotation_box(axes[1], rows_cost)

    # ═══════════════════════════════════════════════════════════════════════════
    # Panel 3 — Risk Penalty
    # ═══════════════════════════════════════════════════════════════════════════
    axes[2].set_title("Risk Penalty", fontsize=11, fontweight="bold", pad=10)
    axes[2].set_ylabel("Penalty (0 \u2013 100)", fontsize=9)
    _draw_panel(axes[2], AGGREGATE_RISK_COLS)

    rows_risk_pen = [
        _ta("Risk Penalty", size=8, weight="bold"),
        _rule(),
        _ta("Composite risk score (scale: 0 \u2013 100).", size=7.5),
        _ta("Higher = greater overall supplier risk.", size=7.5),
        _spacer(),
        _ta("Weighted components:", size=7.5, weight="bold"),
        _inline("32%", "Disruption Risk"),
        _inline("28%", "Lead Time Risk"),
        _inline("20%", "Logistics Risk"),
        _inline("12%", "Cost Instability Risk"),
        _inline(" 8%", "Quality Risk  (normalized)"),
    ]
    _place_annotation_box(axes[2], rows_risk_pen)

    # ═══════════════════════════════════════════════════════════════════════════
    # Panel 4 — Risk Components Breakdown
    # ═══════════════════════════════════════════════════════════════════════════
    axes[3].set_title("Risk Components Breakdown", fontsize=11, fontweight="bold", pad=10)
    axes[3].set_ylabel("Risk Score (0 \u2013 1)", fontsize=9)
    _draw_panel(axes[3], RISK_DRIVER_COLS, rotation=20)

    rows_risk_comp = [
        _ta("Risk Components", size=8, weight="bold"),
        _rule(),
        _ta("All scores on a [0 \u2013 1] scale. Lower is better.", size=7.5, color="#555555"),
        _spacer(),
        _ta("Disruption Risk", size=7.5, weight="bold"),
        _ta("  Derived from political stability,", size=7.5),
        _ta("  governance, and infrastructure signals.", size=7.5),
        _spacer(),
        _ta("Lead Time Risk", size=7.5, weight="bold"),
        _ta("  Delivery speed + consistency.", size=7.5),
        _ta("  70% normalized mean lead time", size=7.5, color="#777777"),
        _ta("  + 30% lead time variability (CV).", size=7.5, color="#777777"),
        _spacer(),
        _ta("Logistics Risk", size=7.5, weight="bold"),
        _ta("  1 \u2212 supplier country logistics reliability.", size=7.5),
        _ta("  Higher = weaker freight / border performance.", size=7.5),
        _spacer(),
        _ta("Cost Instability Risk", size=7.5, weight="bold"),
        _ta("  Rolling 5-yr price volatility blended", size=7.5),
        _ta("  with disruption risk.", size=7.5),
        _spacer(),
        _ta("Quality Risk", size=7.5, weight="bold"),
        _ta("  Estimated quality of product based on", size=7.5),
        _ta("  manufacturing origin and process fit.", size=7.5),
    ]
    _place_annotation_box(axes[3], rows_risk_comp)

    # ═══════════════════════════════════════════════════════════════════════════
    # Compliance exclusion notice
    # Positioned in figure-fraction coordinates so it always sits near the
    # main title row and never overlaps the panel annotation boxes.
    # ═══════════════════════════════════════════════════════════════════════════
    if excluded_requested_suppliers:
        rows_excl: list = [
            _ta("Compliance Exclusion Notice", size=8, weight="bold", color="#C62828"),
            _rule(),
            _ta("The following supplier(s) were removed from", size=7.5),
            _ta("scoring because compliance eligibility fell", size=7.5),
            _ta(f"below the minimum threshold of {threshold_display}.", size=7.5),
            _spacer(),
        ]
        for d in excluded_requested_suppliers:
            sid = d.get("supplier_id", "UNKNOWN")
            sup_rows = universe_df[universe_df["supplier_id"] == sid]
            if not sup_rows.empty and "compliance_eligibility" in sup_rows.columns:
                comp_val = sup_rows["compliance_eligibility"].iloc[0]
                score_str = f"{float(comp_val):.2f}" if pd.notna(comp_val) else "n/a"
            else:
                score_str = "n/a"
            rows_excl.append(_inline(f"{sid}:", f"compliance score = {score_str}"))

        packed_excl = VPacker(children=rows_excl, pad=6, sep=3, align="left")
        ab_excl = AnnotationBbox(
            packed_excl,
            # x=1.04 in axes fraction is the SAME anchor used by every other
            # annotation box, guaranteeing pixel-perfect left-edge alignment.
            # y=1.80 places the box top in the title/legend band (above axes top)
            # with a small gap from the figure edge; box extends downward via
            # box_alignment=(0, 1).
            xy=(1.04, 2.20),
            xycoords="axes fraction",
            box_alignment=(0, 1),       # top-left of box at xy; box extends downward
            annotation_clip=False,
            bboxprops=dict(
                boxstyle="round,pad=0.5",
                facecolor="#FFF5F5",
                edgecolor="#C62828",
                linewidth=0.9,
                alpha=0.97,
            ),
            frameon=True,
        )
        axes[0].add_artist(ab_excl)

    # ═══════════════════════════════════════════════════════════════════════════
    # Figure-level title and legend
    # ═══════════════════════════════════════════════════════════════════════════
    handles, labels_leg = axes[0].get_legend_handles_labels()

    # title_x centres the title and legend over the axes region [_left, right_margin],
    # not the full canvas — same approach as the other updated chart modules.
    fig.suptitle(
        f"Why This Supplier? \u2014 {_pretty_product_name(product)}"
        f" | Q = {Q:,} | \u03bb = {lam_display} | Comp. Thresh = {threshold_display}",
        fontsize=13,
        fontweight="bold",
        x=title_x,
        y=0.998,
    )

    fig.legend(
        handles,
        labels_leg,
        loc="upper center",
        bbox_to_anchor=(title_x, 0.972),
        ncol=len(labels_leg),
        frameon=False,
        fontsize=9.5,
    )

    fig.subplots_adjust(
        top=0.88,
        hspace=0.72,
        left=_left,
        right=right_margin,
        bottom=0.07,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig, axes, scored
