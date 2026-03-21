from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from analytics.scoring import SupplierScorer, load_contract


ANALYTICS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = ANALYTICS_DIR / "metric_contract.yaml"


DISPLAY_LABELS = {
    "supplier_id": "Supplier",
    "country_code": "Country",
    "product": "Product",
    "decision_tier_global": "Global Tier",
    "decision_tier_local": "Local Comparison Tier",
    "effective_unit_price": "Effective Unit Price",
    "landed_unit_cost": "Landed Unit Cost",
    "risk_penalty": "Aggregate Risk Penalty",
    "risk_adjusted_cost": "Risk-Adjusted Cost",
    "risk_disruption": "Disruption Risk",
    "risk_leadtime": "Lead Time Risk",
    "risk_logistics": "Logistics Risk",
    "risk_cost_instability": "Cost Instability Risk",
    "risk_quality": "Quality Risk",
}


FINAL_SCORE_COLS = ["risk_adjusted_cost"]
COST_DRIVER_COLS = ["effective_unit_price", "landed_unit_cost"]
AGGREGATE_RISK_COLS = ["risk_penalty"]
RISK_DRIVER_COLS = [
    "risk_disruption",
    "risk_leadtime",
    "risk_logistics",
    "risk_cost_instability",
    "risk_quality",
]


def _pretty_label(col: str) -> str:
    return DISPLAY_LABELS.get(col, col)


def _pretty_product_name(product: str) -> str:
    return product.replace("_", " ").title()


def _plot_grouped_bar_panel(
    ax,
    df: pd.DataFrame,
    supplier_labels: list[str],
    panel_cols: list[str],
    title: str,
    ylabel: str,
    rotation: int = 15,
):
    x = np.arange(len(panel_cols))
    width = 0.8 / len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        values = [row[col] for col in panel_cols]
        positions = x + i * width - ((len(df) - 1) * width / 2)

        ax.bar(
            positions,
            values,
            width=width,
            label=supplier_labels[i],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [_pretty_label(col) for col in panel_cols],
        rotation=rotation,
        ha="right",
    )
    ax.set_title(title, fontsize=12)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.3)


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

    # IMPORTANT:
    # query full product universe so global tiers are meaningful
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
            f"No scored suppliers returned for selected supplier_ids={supplier_ids}, product={product}"
        )

    required_cols = [
    "supplier_id",
    "country_code",
    "decision_tier_global",
    "decision_tier_local",
    "risk_adjusted_cost",
    "effective_unit_price",
    "landed_unit_cost",
    "risk_penalty",
    "risk_disruption",
    "risk_leadtime",
    "risk_logistics",
    "risk_cost_instability",
    "risk_quality",
]
    missing = [c for c in required_cols if c not in scored.columns]
    if missing:
        raise ValueError(
            "The scorer output is missing expected explainability columns: "
            f"{missing}"
        )

    supplier_labels = [
        f"{sid} ({cc})"
        for sid, cc in zip(scored["supplier_id"], scored["country_code"])
    ]

    fig, axes = plt.subplots(
        nrows=4,
        ncols=1,
        figsize=(15.5, 13),
        gridspec_kw={"height_ratios": [1.0, 1.1, 1.0, 1.6]},
    )

    # Panel 1: Final Score
    _plot_grouped_bar_panel(
        ax=axes[0],
        df=scored,
        supplier_labels=supplier_labels,
        panel_cols=FINAL_SCORE_COLS,
        title="Final Score",
        ylabel="Score",
    )

    x = np.arange(len(FINAL_SCORE_COLS))
    width = 0.8 / len(scored)
    final_values = scored["risk_adjusted_cost"].astype(float).tolist()
    y_max = max(final_values) if final_values else 0.0
    y_offset = max(y_max * 0.05, 0.05)

    # Annotate global/local tiers
    for i, (_, row) in enumerate(scored.iterrows()):
        positions = x + i * width - ((len(scored) - 1) * width / 2)
        y = float(row["risk_adjusted_cost"])

        global_tier = row.get("decision_tier_global", "")
        local_tier = row.get("decision_tier_local", None)

        label = f"Global: {global_tier}"
        if pd.notna(local_tier) and local_tier:
            label += f"\nLocal: {local_tier}"

        axes[0].text(
            positions[0],
            y + y_offset,
            label,
            ha="center",
            va="bottom",
            fontsize=8.5,
        )

    axes[0].set_ylim(0, y_max + y_offset * 4)

    # Panel 2: Cost Drivers
    _plot_grouped_bar_panel(
        ax=axes[1],
        df=scored,
        supplier_labels=supplier_labels,
        panel_cols=COST_DRIVER_COLS,
        title="Cost Drivers",
        ylabel="Unit Cost",
    )

    # Panel 3: Aggregate Risk Penalty
    _plot_grouped_bar_panel(
        ax=axes[2],
        df=scored,
        supplier_labels=supplier_labels,
        panel_cols=AGGREGATE_RISK_COLS,
        title="Aggregate Risk Penalty",
        ylabel="Penalty Value",
    )

    # Panel 4: Risk Breakdown
    _plot_grouped_bar_panel(
        ax=axes[3],
        df=scored,
        supplier_labels=supplier_labels,
        panel_cols=RISK_DRIVER_COLS,
        title="Risk Breakdown Components",
        ylabel="Risk Component Value",
    )

    handles, labels = axes[0].get_legend_handles_labels()

    lam_display = (
        lambda_risk
        if lambda_risk is not None
        else contract.metrics["risk_adjusted_cost"]["params"]["lambda_risk"]
    )

    formula_text = (
        "RiskAdjustedCost =\n"
        "  Norm(LandedUnitCost)\n"
        f"+ {lam_display}·Norm(RiskPenalty)\n\n"
        "RiskPenalty = 100 × [\n"
        "  0.32·DisruptionRisk\n"
        "+ 0.28·LeadTimeRisk\n"
        "+ 0.20·LogisticsRisk\n"
        "+ 0.12·CostInstabilityRisk\n"
        "+ 0.08·Norm(QualityRisk)\n"
        "]\n\n"
        "LeadTimeRisk =\n"
        "  0.70·Norm(LeadTimeMean)\n"
        "+ 0.30·Norm(LeadTimeCV)\n\n"
    )

    fig.suptitle(
        f"Why This Supplier? — {_pretty_product_name(product)} | Q={Q:,} | λ={lam_display}",
        fontsize=17,
        y=0.985,
    )

    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
        ncol=len(labels),
        frameon=False,
        fontsize=10,
    )

    fig.text(
        0.985,
        0.75,
        formula_text,
        ha="right",
        va="center",
        fontsize=9,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9),
    )

    if excluded_requested_suppliers:
        excluded_text = "Excluded requested suppliers:\n" + "\n".join(
            [
                f"- {d.get('supplier_id', 'UNKNOWN')}: {d.get('drop_reason', 'unknown_reason')}"
                + (
                    f" (threshold={d.get('applied_compliance_threshold')})"
                    if d.get("applied_compliance_threshold") is not None
                    else ""
                )
                for d in excluded_requested_suppliers
            ]
        )

        fig.text(
            0.985,
            0.92,
            excluded_text,
            ha="right",
            va="top",
            fontsize=9,
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.5",
                      facecolor="#fff5f5",
                      edgecolor="#d62728",
                      alpha=0.95,),
        )

    fig.subplots_adjust(
        top=0.88,
        hspace=0.62,
        left=0.08,
        right=0.80,
        bottom=0.07,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig, axes, scored