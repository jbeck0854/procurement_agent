from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


# ── Country color palette (deterministic, professional) ───────────────────────
# Hues are spread across the full color wheel.
# No region dominates a single hue family — blues and greens are deliberately
# limited to at most two clearly differentiated shades each.
COUNTRY_COLORS = {
    # Americas — spread across blue / red / orange / green
    "USA": "#1F78B4",    # strong blue (flag/iconic)
    "CAN": "#D62728",    # red (maple leaf)
    "MEX": "#D84315",    # deep burnt orange (warm, distinct from both USA blue and CAN red)
    "BRA": "#FF7F0E",    # vivid amber-orange

    # Europe — purple / magenta / green / olive / teal
    "GBR": "#6A3D9A",    # deep purple
    "FRA": "#E7298A",    # magenta-pink
    "DEU": "#33A02C",    # dark forest green (industry/nature)
    "NLD": "#BCBD22",    # olive / chartreuse
    "BEL": "#17BECF",    # cyan-teal
    "FIN": "#004D40",    # very dark forest teal (Scandinavian lakes; no longer purple)

    # East Asia — coral / teal-cyan / slate / yellow / sky-blue
    # KOR, TWN, CHN, THA updated to match plot_country_logistics_governance_comparison_panel.py:
    #   KOR amber → teal-cyan  (breaks orange/amber cluster)
    #   TWN light amber → bright yellow  (unique hue, unambiguous)
    #   CHN deep crimson → slate blue-grey  (removed from red family)
    #   THA deep violet → vivid orchid  (clear separation from GBR deep purple)
    "JPN": "#F46D43",    # coral-orange (warm, iconic)
    "KOR": "#0097A7",    # teal-cyan
    "CHN": "#546E7A",    # slate blue-grey
    "TWN": "#FDD835",    # bright yellow
    "HKG": "#74ADD1",    # sky blue (lighter/cooler than USA)

    # Southeast Asia & South Asia — sage / sienna / orchid / lime / rose
    "SGP": "#66C2A5",    # sage green
    "MYS": "#A65628",    # sienna
    "THA": "#E040FB",    # vivid orchid (distinct from GBR deep purple)
    "IND": "#4DAC26",    # vivid lime-green
    "IDN": "#C51B7D",    # deep rose

    # Other — pink / peach
    "AUS": "#F06292",    # medium pink (vivid, nothing else in the palette is pink)
    "ARE": "#FDB863",    # desert peach/gold
}
_FALLBACK_PALETTE = [
    "#8DD3C7", "#FB8072", "#80B1D3", "#FDB462",
    "#B3DE69", "#FCCDE5", "#BC80BD", "#FFED6F",
]


DISPLAY_LABELS = {
    "total_baseline_price":       "Total Baseline Price",
    "total_effective_unit_price": "Total Effective Price",
    "total_landed_unit_cost":     "Total Landed Cost",
    "baseline_price":             "Baseline Price",
    "effective_unit_price":       "Effective Unit Price",
    "landed_unit_cost":           "Landed Unit Cost",
    "price_volatility":           "Price Volatility",
    "bulk_discount":              "Bulk Discount",
    "lead_time_mean":             "Lead Time Mean",
    "lead_time_stddev":           "Lead Time Std Dev",
    "disruption_probability":     "Disruption Probability",
    "logistics_reliability":      "Logistics Reliability",
    "probability_of_defect":      "Probability Of Defect",
    "compliance_eligibility":     "Compliance Eligibility",
    "mfn_text_rate_pct":          "Tariff Rate (%)",
}


# Default metrics correspond exactly to the four active panels.
DEFAULT_METRICS = [
    "total_baseline_price",
    "total_effective_unit_price",
    "total_landed_unit_cost",
    "price_volatility",
    "bulk_discount",
    "lead_time_mean",
    "lead_time_stddev",
]


HIGHER_IS_BETTER = {"bulk_discount", "logistics_reliability", "compliance_eligibility"}

LOWER_IS_BETTER = {
    "baseline_price", "effective_unit_price", "landed_unit_cost",
    "total_baseline_price", "total_effective_unit_price", "total_landed_unit_cost",
    "price_volatility", "lead_time_mean", "lead_time_stddev",
    "disruption_probability", "probability_of_defect", "mfn_text_rate_pct",
}


# "Pricing Characteristics" has been split into two separate panels so that
# metrics with different units and interpretations are never mixed on one axis.
PANEL_MAP = {
    "Total Cost": [
        "total_baseline_price",
        "total_effective_unit_price",
        "total_landed_unit_cost",
    ],
    "Price Volatility": [
        "price_volatility",
    ],
    "Bulk Discount": [
        "bulk_discount",
    ],
    "Lead Time": [
        "lead_time_mean",
        "lead_time_stddev",
    ],
}


# Annotation format routing.
# price_volatility is intentionally NOT in _PERCENT_METRICS:
# it is a normalized 0–1 composite score and should be read as a decimal.
_CURRENCY_METRICS = {
    "total_baseline_price",
    "total_effective_unit_price",
    "total_landed_unit_cost",
}
_PERCENT_METRICS = {
    "bulk_discount",
    "disruption_probability",
    "probability_of_defect",
    "mfn_text_rate_pct",
}


# Total Cost panel explanation box — faithful to metric_contract.md.
_TOTAL_COST_ANNOTATION = (
    "How Total Cost Is Calculated\n\n"
    "Effective Unit Price\n"
    "  Baseline price with bulk discount applied\n"
    "  when Q ≥ supplier MOQ.\n"
    "  Full baseline price charged when Q < MOQ.\n\n"
    "Landed Unit Cost\n"
    "  Effective unit price adjusted by MFN tariff rate.\n\n"
    "Total Cost = landed unit cost × Q\n"
    "All prices in USD."
)

# Volatility explanation box — exact construction from supplier-product linking doc.
_VOLATILITY_ANNOTATION = (
    "How This Score Is Calculated\n\n"
    "1.  Compute rolling 60-month standard deviation\n"
    "    of real price for each country × product pair.\n\n"
    "2.  Extract the most recent value per supplier\n"
    "    and apply min-max normalization.\n\n"
    "3.  Blend with supplier disruption probability:\n"
    "    60%  normalized price volatility\n"
    "    40%  disruption probability\n\n"
    "Score range: 0 – 1  ·  Lower = more stable, less volatile"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pretty_label(metric: str) -> str:
    return DISPLAY_LABELS.get(metric, metric.replace("_", " ").title())


def _pretty_product_name(product: str) -> str:
    return product.replace("_", " ").title()


def _get_supplier_color(country_code: str, fallback_index: int = 0) -> str:
    """Return a deterministic color for a given country code."""
    if country_code in COUNTRY_COLORS:
        return COUNTRY_COLORS[country_code]
    return _FALLBACK_PALETTE[fallback_index % len(_FALLBACK_PALETTE)]


def _format_annotation(val: float, metric: str) -> str:
    """Format a bar annotation label based on metric type."""
    if metric in _CURRENCY_METRICS:
        if abs(val) >= 1_000_000:
            return f"${val / 1_000_000:.2f}M"
        elif abs(val) >= 1_000:
            return f"${val:,.0f}"
        else:
            return f"${val:.2f}"
    elif metric in _PERCENT_METRICS:
        return f"{val * 100:.1f}%"
    else:
        # price_volatility and other 0–1 scores: show as decimal
        return f"{val:.3f}"


def _bulk_price(
    baseline_price: pd.Series,
    bulk_discount: pd.Series,
    bulk_units: pd.Series,
    Q: int,
) -> pd.Series:
    apply_discount = Q >= pd.to_numeric(bulk_units, errors="coerce").astype(float)
    base = pd.to_numeric(baseline_price, errors="coerce").astype(float)
    disc = pd.to_numeric(bulk_discount, errors="coerce").astype(float)

    return pd.Series(
        np.where(apply_discount, base * (1.0 - disc), base),
        index=baseline_price.index,
        dtype=float,
    )


def _derive_procurement_cost_metrics(
    df: pd.DataFrame,
    Q: int,
    tariff_enabled: bool = True,
    tariff_rate_col: str = "mfn_text_rate_pct",
    missing_rate_default_pct: float = 0.0,
) -> pd.DataFrame:
    out = df.copy()

    out["baseline_price"] = pd.to_numeric(
        out["baseline_price"], errors="coerce"
    ).astype(float)
    out["bulk_discount"] = pd.to_numeric(
        out["bulk_discount"], errors="coerce"
    ).astype(float)
    out["bulk_units"] = pd.to_numeric(
        out["bulk_units"], errors="coerce"
    ).astype(float)

    out["effective_unit_price"] = _bulk_price(
        out["baseline_price"],
        out["bulk_discount"],
        out["bulk_units"],
        Q,
    )

    if tariff_enabled:
        if tariff_rate_col in out.columns:
            out["tariff_rate"] = (
                pd.to_numeric(out[tariff_rate_col], errors="coerce")
                .fillna(missing_rate_default_pct)
                .astype(float)
                / 100.0
            )
        else:
            out["tariff_rate"] = missing_rate_default_pct / 100.0
    else:
        out["tariff_rate"] = 0.0

    out["landed_unit_cost"] = out["effective_unit_price"] * (1.0 + out["tariff_rate"])

    return out


# ── Main plot function ────────────────────────────────────────────────────────

def plot_supplier_comparison_panel(
    conn,
    supplier_ids: list[str],
    product: str,
    Q: int = 5000,
    metrics: list[str] | None = None,
    tariff_enabled: bool = True,
    tariff_rate_col: str = "mfn_text_rate_pct",
    missing_rate_default_pct: float = 0.0,
    save_path: str | None = None,
):
    if not supplier_ids or len(supplier_ids) < 2:
        raise ValueError("supplier_ids must contain at least 2 suppliers")

    if len(supplier_ids) > 3:
        raise ValueError("Recommended maximum is 3 suppliers for readability")

    if Q <= 0:
        raise ValueError("Q must be a positive integer")

    if metrics is None:
        metrics = DEFAULT_METRICS

    query = """
        SELECT
            supplier_id,
            country_code,
            product,
            lead_time_mean,
            lead_time_stddev,
            lead_time_variance,
            disruption_probability,
            compliance_eligibility,
            logistics_reliability,
            baseline_price,
            price_volatility,
            probability_of_defect,
            bulk_discount,
            bulk_units,
            hts8,
            mfn_text_rate_pct,
            tariff_description
        FROM vw_supplier_complete_profile
        WHERE product = %(product)s
          AND supplier_id = ANY(%(supplier_ids)s)
        ORDER BY supplier_id
    """

    df = pd.read_sql(
        query,
        conn,
        params={
            "product": product,
            "supplier_ids": supplier_ids,
        },
    )

    if df.empty:
        raise ValueError(
            f"No supplier data found for product={product}, supplier_ids={supplier_ids}"
        )

    found = set(df["supplier_id"].unique())
    missing_suppliers = sorted(set(supplier_ids) - found)
    if missing_suppliers:
        raise ValueError(f"Missing supplier(s) for product={product}: {missing_suppliers}")

    df["compliance_eligibility"] = (
        df["compliance_eligibility"]
        .astype(str)
        .str.lower()
        .map({"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0})
        .fillna(pd.to_numeric(df["compliance_eligibility"], errors="coerce"))
    )

    df = _derive_procurement_cost_metrics(
        df,
        Q=Q,
        tariff_enabled=tariff_enabled,
        tariff_rate_col=tariff_rate_col,
        missing_rate_default_pct=missing_rate_default_pct,
    )

    # Compute total cost columns (unit price × Q) for the Total Cost panel.
    # Presentation-only — no upstream scoring columns are modified.
    df["total_baseline_price"]       = df["baseline_price"]       * Q
    df["total_effective_unit_price"] = df["effective_unit_price"] * Q
    df["total_landed_unit_cost"]     = df["landed_unit_cost"]     * Q

    missing_metric_cols = [m for m in metrics if m not in df.columns]
    if missing_metric_cols:
        raise ValueError(f"Requested metrics not available: {missing_metric_cols}")

    # Capture MOQ values before narrowing to plot_df columns (used in Bulk Discount box)
    moq_lookup = (
        df[["supplier_id", "bulk_units"]]
        .drop_duplicates(subset=["supplier_id"])
        .set_index("supplier_id")["bulk_units"]
        .to_dict()
    )

    plot_df = (
        df[["supplier_id", "country_code"] + metrics]
        .drop_duplicates(subset=["supplier_id"])
        .reset_index(drop=True)
    )

    # Resolve which panels are active given the requested metrics
    panel_metrics = {
        panel: [m for m in panel_list if m in metrics]
        for panel, panel_list in PANEL_MAP.items()
    }
    active_panels = {k: v for k, v in panel_metrics.items() if v}

    if not active_panels:
        raise ValueError("No valid metrics selected for plotting")

    n_panels    = len(active_panels)
    n_suppliers = len(plot_df)

    # Three panels carry annotation boxes outside the right edge of the plot area.
    _ANNOTATION_PANELS = {"Total Cost", "Price Volatility", "Bulk Discount"}
    has_right_annotation = bool(active_panels.keys() & _ANNOTATION_PANELS)
    right_margin = 0.72 if has_right_annotation else 0.95

    fig, axes = plt.subplots(
        nrows=n_panels,
        ncols=1,
        figsize=(14, 4.2 * n_panels),
    )
    if n_panels == 1:
        axes = [axes]

    # Supplier display labels and colors — consistent across all panels.
    supplier_labels = [
        f"{row['supplier_id']} ({row['country_code']})"
        for _, row in plot_df.iterrows()
    ]
    supplier_colors = [
        _get_supplier_color(row["country_code"], i)
        for i, (_, row) in enumerate(plot_df.iterrows())
    ]

    group_gap = 1.35   # x-spacing between metric groups

    for ax, (panel_name, panel_cols) in zip(axes, active_panels.items()):
        n_groups = len(panel_cols)
        x        = np.arange(n_groups) * group_gap

        # Single-metric panels (Price Volatility, Bulk Discount) get narrower bars
        # so the chart doesn't look artificially stretched for one metric.
        if n_groups == 1:
            bar_width = 0.14 if n_suppliers == 3 else 0.18
        else:
            bar_width = 0.20 if n_suppliers == 3 else 0.26

        offsets = (np.arange(n_suppliers) - (n_suppliers - 1) / 2.0) * (bar_width + 0.04)

        for i, (_, row) in enumerate(plot_df.iterrows()):
            values        = [float(row[col]) if pd.notna(row[col]) else 0.0 for col in panel_cols]
            bar_positions = x + offsets[i]

            bars = ax.bar(
                bar_positions,
                values,
                width=bar_width,
                label=supplier_labels[i],
                color=supplier_colors[i],
                edgecolor="white",
                linewidth=0.6,
                zorder=3,
            )

            # Value labels above each bar
            for bar, col, val in zip(bars, panel_cols, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    val,
                    _format_annotation(val, col),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    clip_on=False,
                    zorder=4,
                )

        # X-axis: hide redundant tick label on single-metric panels
        ax.set_xticks(x)
        if n_groups == 1:
            ax.set_xticklabels([])
            ax.tick_params(axis="x", bottom=False)
        else:
            ax.set_xticklabels(
                [_pretty_label(col) for col in panel_cols],
                rotation=15,
                ha="right",
                fontsize=9,
            )

        ax.set_title(panel_name, fontsize=11, fontweight="bold", pad=10)
        ax.grid(True, axis="y", alpha=0.18, linewidth=0.7, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="y", labelsize=8.5)
        ax.margins(y=0.22)   # headroom for annotation labels

        # ── Panel-specific y-axis and annotation ────────────────────────────
        if panel_name == "Total Cost":
            ax.set_ylabel("Total Cost ($)", fontsize=9)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(
                    lambda v, _: (
                        f"${v / 1_000_000:.1f}M" if abs(v) >= 1_000_000
                        else f"${v:,.0f}"
                    )
                )
            )
            ax.text(
                1.04, 0.5,
                _TOTAL_COST_ANNOTATION,
                transform=ax.transAxes,
                fontsize=8,
                verticalalignment="center",
                linespacing=1.55,
                bbox=dict(
                    boxstyle="round,pad=0.7",
                    facecolor="#F5F5F0",
                    edgecolor="#BBBBBB",
                    linewidth=0.9,
                    alpha=0.97,
                ),
                clip_on=False,
            )

        elif panel_name == "Price Volatility":
            ax.set_ylabel("Volatility Score (0 – 1)", fontsize=9)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v:.2f}")
            )
            # Business-style explanation box to the right of this panel
            ax.text(
                1.04, 0.5,
                _VOLATILITY_ANNOTATION,
                transform=ax.transAxes,
                fontsize=8,
                verticalalignment="center",
                linespacing=1.55,
                bbox=dict(
                    boxstyle="round,pad=0.7",
                    facecolor="#F5F5F0",
                    edgecolor="#BBBBBB",
                    linewidth=0.9,
                    alpha=0.97,
                ),
                clip_on=False,
            )

        elif panel_name == "Bulk Discount":
            ax.set_ylabel("Discount (%)", fontsize=9)
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%")
            )
            # Build per-supplier MOQ lines from the captured moq_lookup
            moq_lines = "\n".join(
                f"  {lbl}:  MOQ = {moq_lookup.get(row['supplier_id'], float('nan')):,.0f} units"
                for lbl, (_, row) in zip(supplier_labels, plot_df.iterrows())
            )
            bulk_annotation = (
                f"Discount applies when Q \u2265 MOQ\n\n"
                f"{moq_lines}\n\n"
                f"Current order:  Q = {Q:,} units"
            )
            ax.text(
                1.04, 0.5,
                bulk_annotation,
                transform=ax.transAxes,
                fontsize=8,
                verticalalignment="center",
                linespacing=1.6,
                bbox=dict(
                    boxstyle="round,pad=0.7",
                    facecolor="#F5F5F0",
                    edgecolor="#BBBBBB",
                    linewidth=0.9,
                    alpha=0.97,
                ),
                clip_on=False,
            )

        elif panel_name == "Lead Time":
            ax.set_ylabel("Days", fontsize=9)

    # Shared legend at the top
    handles, labels = axes[0].get_legend_handles_labels()

    # Centre the title and legend over the axes region, not the full canvas.
    # With left=0.09 and right=right_margin (0.72 or 0.95), the axes midpoint
    # shifts depending on whether annotation boxes are present.
    _left = 0.09
    title_x = (_left + right_margin) / 2.0

    fig.suptitle(
        f"Supplier Comparison — {_pretty_product_name(product)} | Q = {Q:,}",
        fontsize=13,
        fontweight="bold",
        x=title_x,
        y=0.998,
    )
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(title_x, 0.972),
        ncol=len(labels),
        frameon=False,
        fontsize=9.5,
    )

    fig.subplots_adjust(
        top=0.88,
        hspace=0.82,
        left=_left,
        right=right_margin,
        bottom=0.05,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig, axes, df
