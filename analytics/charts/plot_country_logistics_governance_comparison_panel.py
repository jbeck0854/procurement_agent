from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


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
    "lpi_customs": "Customs",
    "lpi_infrastructure": "Infrastructure",
    "lpi_international_shipments": "Intl Shipments",
    "lpi_logistics_competence": "Logistics Competence",
    "lpi_tracking": "Tracking",
    "lpi_timeliness": "Timeliness",
    "control_of_corruption": "Control of Corruption",
    "government_effectiveness": "Gov Effectiveness",
    "political_stability": "Political Stability",
    "regulatory_quality": "Regulatory Quality",
    "rule_of_law": "Rule of Law",
    "voice_and_accountability": "Voice & Accountability",
}


def _pretty_label(metric: str) -> str:
    return DISPLAY_LABELS.get(metric, metric.replace("_", " ").title())


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

    df = df.sort_values("country_code")

    fig, axes = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(14, 8),
    )

    countries = [
        f"{cc}"
        for cc in df["country_code"]
    ]

    # -----------------------------
    # Panel 1 — Logistics
    # -----------------------------
    ax = axes[0]
    cols = LOGISTICS_COLS

    x = np.arange(len(cols))
    width = 0.8 / len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        values = [row[col] for col in cols]
        positions = x + i * width - ((len(df) - 1) * width / 2)

        ax.bar(
            positions,
            values,
            width=width,
            label=countries[i],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [_pretty_label(c) for c in cols],
        rotation=20,
        ha="right",
    )
    ax.set_title("Logistics Performance Indicators")
    ax.set_ylabel("Score")
    ax.grid(True, axis="y", alpha=0.3)

    # -----------------------------
    # Panel 2 — Governance
    # -----------------------------
    ax = axes[1]
    cols = GOVERNANCE_COLS

    x = np.arange(len(cols))
    width = 0.8 / len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        values = [row[col] for col in cols]
        positions = x + i * width - ((len(df) - 1) * width / 2)

        ax.bar(
            positions,
            values,
            width=width,
            label=countries[i],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [_pretty_label(c) for c in cols],
        rotation=20,
        ha="right",
    )
    ax.set_title("Governance Indicators")
    ax.set_ylabel("Score")
    ax.grid(True, axis="y", alpha=0.3)

    # Legend (shared)
    handles, labels = axes[0].get_legend_handles_labels()

    fig.suptitle(
        "Country Logistics & Governance Inputs",
        fontsize=16,
        y=0.98,
    )

    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.94),
        ncol=len(labels),
        frameon=False,
    )

    fig.subplots_adjust(
        top=0.88,
        hspace=0.45,
        left=0.08,
        right=0.98,
        bottom=0.08,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig, axes, df