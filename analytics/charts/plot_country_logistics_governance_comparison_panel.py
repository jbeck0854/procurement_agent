from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox, VPacker, HPacker, TextArea


LOGISTICS_COLS = [
    "lpi_customs",
    "lpi_infrastructure",
    "lpi_international_shipments",
    "lpi_logistics_competence",
    "lpi_tracking",
    "lpi_timeliness",
]

GOVERNANCE_COLS = [
    "control_of_corruption",
    "government_effectiveness",
    "political_stability",
    "regulatory_quality",
    "rule_of_law",
    "voice_and_accountability",
]


DISPLAY_LABELS = {
    "lpi_customs":                  "Customs",
    "lpi_infrastructure":           "Infrastructure",
    "lpi_international_shipments":  "Intl Shipments",
    "lpi_logistics_competence":     "Logistics Competence",
    "lpi_tracking":                 "Tracking",
    "lpi_timeliness":               "Timeliness",
    "control_of_corruption":        "Control of Corruption",
    "government_effectiveness":     "Gov Effectiveness",
    "political_stability":          "Political Stability",
    "regulatory_quality":           "Regulatory Quality",
    "rule_of_law":                  "Rule of Law",
    "voice_and_accountability":     "Voice & Accountability",
}


# ── Country color palette ─────────────────────────────────────────────────────
# Mirrors supplier_comparison_panel.py with four deliberate changes for this
# chart, which may display more countries simultaneously:
#   KOR: amber → teal-cyan   (breaks 5-country orange/amber cluster)
#   TWN: light amber → yellow (gives a unique, unambiguous hue)
#   CHN: deep crimson → slate blue-grey (removes from red family entirely)
#   THA: deep violet → vivid orchid (clear separation from GBR deep purple)
COUNTRY_COLORS = {
    "USA": "#1F78B4",    # strong blue
    "CAN": "#D62728",    # red (maple leaf)
    "MEX": "#D84315",    # deep burnt orange
    "BRA": "#FF7F0E",    # vivid amber-orange

    "GBR": "#6A3D9A",    # deep royal purple
    "FRA": "#E7298A",    # magenta-pink
    "DEU": "#33A02C",    # dark forest green
    "NLD": "#BCBD22",    # olive / chartreuse
    "BEL": "#17BECF",    # cyan-teal
    "FIN": "#004D40",    # very dark forest teal

    "JPN": "#F46D43",    # coral-orange
    "KOR": "#0097A7",    # teal-cyan  ← changed from amber #E6AB02
    "CHN": "#546E7A",    # slate blue-grey  ← changed from crimson #A50026
    "TWN": "#FDD835",    # bright yellow  ← changed from light amber #FDAE61
    "HKG": "#74ADD1",    # sky blue

    "SGP": "#66C2A5",    # sage green
    "MYS": "#A65628",    # sienna
    "THA": "#E040FB",    # vivid orchid  ← changed from deep violet #5E35B1
    "IND": "#4DAC26",    # vivid lime-green
    "IDN": "#C51B7D",    # deep rose

    "AUS": "#F06292",    # medium pink
    "ARE": "#FDB863",    # desert peach/gold
}
_FALLBACK_PALETTE = [
    "#8DD3C7", "#FB8072", "#80B1D3", "#FDB462",
    "#B3DE69", "#FCCDE5", "#BC80BD", "#FFED6F",
]


# ── Annotation box content (sourced from 00_risk_model_formalization.md) ──────

_LOGISTICS_TITLE    = "Logistics Performance Index (LPI)"
_LOGISTICS_SUBTITLE = "Score range: 1 \u2013 5  \u00b7  Higher is better"
_LOGISTICS_ENTRIES  = [
    ("Customs:",             "Efficiency of border clearance and administration."),
    ("Infrastructure:",      "Quality of ports, roads, railways, and systems."),
    ("Intl Shipments:",      "Ease of arranging competitive-price shipments."),
    ("Logistics Competence:", "Quality of freight operators and brokers."),
    ("Tracking:",            "Ability to track shipments in transit."),
    ("Timeliness:",          "Reliability of on-time delivery."),
]

_GOVERNANCE_TITLE    = "World Governance Indicators (WGI)"
_GOVERNANCE_SUBTITLE = "Score range: \u22122.5 \u2013 +2.5  \u00b7  Higher is better"
_GOVERNANCE_ENTRIES  = [
    ("Control of Corruption:", "Extent public power is used for private gain."),
    ("Gov Effectiveness:",     "Quality of services and policy implementation."),
    ("Political Stability:",   "Stability of government; absence of conflict."),
    ("Regulatory Quality:",    "Government support for private sector growth."),
    ("Rule of Law:",           "Confidence in contracts and legal institutions."),
    ("Voice & Accountability:", "Citizen participation; freedom of expression."),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pretty_label(metric: str) -> str:
    return DISPLAY_LABELS.get(metric, metric.replace("_", " ").title())


def _get_country_color(country_code: str, fallback_index: int = 0) -> str:
    if country_code in COUNTRY_COLORS:
        return COUNTRY_COLORS[country_code]
    return _FALLBACK_PALETTE[fallback_index % len(_FALLBACK_PALETTE)]


def _build_annotation_box(title: str, subtitle: str, entries: list) -> VPacker:
    """
    Build a structured offsetbox with:
      - Bold title + horizontal rule (simulated underline)
      - Small grey subtitle
      - Bold metric label + normal definition side-by-side on each row

    Uses matplotlib.offsetbox primitives so each text element can carry
    its own font weight independently — something ax.text() cannot do.
    """
    rows = []

    # Title: bold
    rows.append(
        TextArea(
            title,
            textprops={"fontsize": 8, "fontweight": "bold"},
        )
    )
    # Horizontal rule (simulated underline under title)
    rows.append(
        TextArea(
            "\u2500" * 40,
            textprops={"fontsize": 6, "color": "#BBBBBB"},
        )
    )
    # Subtitle: small, muted
    rows.append(
        TextArea(
            subtitle,
            textprops={"fontsize": 7, "color": "#666666"},
        )
    )
    # Spacer
    rows.append(TextArea(" ", textprops={"fontsize": 3}))

    # Metric entries: bold label + normal definition on the same visual line
    for label, definition in entries:
        label_area = TextArea(
            label + "  ",
            textprops={"fontsize": 7.5, "fontweight": "bold"},
        )
        def_area = TextArea(
            definition,
            textprops={"fontsize": 7.5},
        )
        row = HPacker(children=[label_area, def_area], pad=0, sep=0, align="baseline")
        rows.append(row)

    return VPacker(children=rows, pad=6, sep=3, align="left")


# ── Main plot function ────────────────────────────────────────────────────────

def plot_country_indicator_comparison_panel(
    conn,
    country_codes: list[str],
    save_path: str | None = None,
):
    if not country_codes:
        raise ValueError("country_codes must contain at least one country")

    query = """
        SELECT *
        FROM vw_country_risk_snapshot
        WHERE country_code = ANY(%(country_codes)s)
    """

    df = pd.read_sql(
        query,
        conn,
        params={"country_codes": country_codes},
    )

    if df.empty:
        raise ValueError(f"No data found for country_codes={country_codes}")

    # Ensure numeric
    for col in LOGISTICS_COLS + GOVERNANCE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("country_code").reset_index(drop=True)

    n_countries    = len(df)
    country_labels = list(df["country_code"])
    country_colors = [_get_country_color(cc, i) for i, cc in enumerate(country_labels)]

    bar_width = max(0.10, 0.72 / n_countries - 0.02)
    group_gap = 1.15
    offsets   = (np.arange(n_countries) - (n_countries - 1) / 2.0) * (bar_width + 0.03)

    fig, axes = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(14, 9),
    )

    panels = [
        (
            LOGISTICS_COLS,
            "Logistics Performance Indicators",
            _LOGISTICS_TITLE,
            _LOGISTICS_SUBTITLE,
            _LOGISTICS_ENTRIES,
        ),
        (
            GOVERNANCE_COLS,
            "Governance Indicators",
            _GOVERNANCE_TITLE,
            _GOVERNANCE_SUBTITLE,
            _GOVERNANCE_ENTRIES,
        ),
    ]

    for ax, (cols, panel_title, box_title, box_subtitle, entries) in zip(axes, panels):
        x = np.arange(len(cols)) * group_gap

        for i, (_, row) in enumerate(df.iterrows()):
            values        = [float(row[col]) if pd.notna(row[col]) else 0.0 for col in cols]
            bar_positions = x + offsets[i]

            bars = ax.bar(
                bar_positions,
                values,
                width=bar_width,
                label=country_labels[i],
                color=country_colors[i],
                edgecolor="white",
                linewidth=0.6,
                zorder=3,
            )

            # Value annotations: above positive bars, below negative bars.
            for bar, val in zip(bars, values):
                x_pos = bar.get_x() + bar.get_width() / 2.0
                if val >= 0:
                    ax.text(
                        x_pos, val, f"{val:.2f}",
                        ha="center", va="bottom",
                        fontsize=8, clip_on=False, zorder=4,
                    )
                else:
                    ax.text(
                        x_pos, val, f"{val:.2f}",
                        ha="center", va="top",
                        fontsize=8, clip_on=False, zorder=4,
                    )

        ax.set_xticks(x)
        ax.set_xticklabels(
            [_pretty_label(c) for c in cols],
            rotation=20,
            ha="right",
            fontsize=9,
        )
        ax.set_title(panel_title, fontsize=11, fontweight="bold", pad=10)
        ax.set_ylabel("Score", fontsize=9)
        ax.grid(True, axis="y", alpha=0.18, linewidth=0.7, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="y", labelsize=8.5)

        # Dynamic y-axis range fitted to actual data.
        all_vals = [
            float(row[col])
            for col in cols
            for _, row in df.iterrows()
            if pd.notna(row[col])
        ]
        if all_vals:
            y_min = min(all_vals)
            y_max = max(all_vals)
            span  = (y_max - y_min) if y_max != y_min else max(abs(y_max), 1.0)
            pad   = span * 0.25
            ax.set_ylim(y_min - pad, y_max + pad)

        # Governance: subtle zero reference line.
        if panel_title == "Governance Indicators":
            ax.axhline(
                0,
                color="#999999",
                linewidth=0.8,
                linestyle="--",
                alpha=0.55,
                zorder=1,
            )

        # Rich annotation box: bold title + rule + bold metric labels + normal definitions.
        packed = _build_annotation_box(box_title, box_subtitle, entries)
        ab = AnnotationBbox(
            packed,
            xy=(1.04, 0.5),
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

    # ── Figure-level title and legend ──────────────────────────────────────────
    # The axes span left=0.08 to right=0.72, so the visual centre is 0.40.
    # Setting x=0.40 aligns the title and legend over the bars, not the figure.
    handles, labels = axes[0].get_legend_handles_labels()

    fig.suptitle(
        "Country Logistics & Governance Inputs",
        fontsize=13,
        fontweight="bold",
        x=0.40,          # centred over axes region [0.08, 0.72], not full figure
        y=0.998,
    )

    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.40, 0.972),   # same x anchor as suptitle
        ncol=len(labels),
        frameon=False,
        fontsize=9.5,
    )

    fig.subplots_adjust(
        top=0.88,
        hspace=0.65,
        left=0.08,
        right=0.72,
        bottom=0.08,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig, axes, df
