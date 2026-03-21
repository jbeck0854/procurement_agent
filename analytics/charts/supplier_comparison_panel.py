from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


DISPLAY_LABELS = {
    "baseline_price": "Baseline Price",
    "effective_unit_price": "Effective Unit Price",
    "landed_unit_cost": "Landed Unit Cost",
    "price_volatility": "Price Volatility",
    "bulk_discount": "Bulk Discount",
    "lead_time_mean": "Lead Time Mean (Days)",
    "lead_time_stddev": "Lead Time Std Dev (Days)",
    "disruption_probability": "Disruption Probability",
    "logistics_reliability": "Logistics Reliability",
    "probability_of_defect": "Probability Of Defect",
    "compliance_eligibility": "Compliance Eligibility",
    "mfn_text_rate_pct": "Tariff Rate (%)",
}


DEFAULT_METRICS = [
    "baseline_price",
    "effective_unit_price",
    "landed_unit_cost",
    "price_volatility",
    "bulk_discount",
    "lead_time_mean",
    "lead_time_stddev",
    "disruption_probability",
    "logistics_reliability",
    "probability_of_defect",
    "compliance_eligibility",
    "mfn_text_rate_pct",
]


HIGHER_IS_BETTER = {
    "bulk_discount",
    "logistics_reliability",
    "compliance_eligibility",
}


LOWER_IS_BETTER = {
    "baseline_price",
    "effective_unit_price",
    "landed_unit_cost",
    "price_volatility",
    "lead_time_mean",
    "lead_time_stddev",
    "disruption_probability",
    "probability_of_defect",
    "mfn_text_rate_pct",
}


PANEL_MAP = {
    "Cost & Pricing": [
        "baseline_price",
        "effective_unit_price",
        "landed_unit_cost",
        "price_volatility",
        "bulk_discount",
    ],
    "Lead Time": [
        "lead_time_mean",
        "lead_time_stddev",
    ],
    "Risk & Reliability": [
        "disruption_probability",
        "logistics_reliability",
    ],
    "Quality": [
        "probability_of_defect"
    ],
    "Compliance": [
        "compliance_eligibility"
    ]
}


def _pretty_label(metric: str) -> str:
    return DISPLAY_LABELS.get(metric, metric.replace("_", " ").title())


def _pretty_product_name(product: str) -> str:
    return product.replace("_", " ").title()


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
    missing = sorted(set(supplier_ids) - found)
    if missing:
        raise ValueError(f"Missing supplier(s) for product={product}: {missing}")

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

    required_cols = ["supplier_id", "country_code"] + metrics
    missing_metric_cols = [c for c in metrics if c not in df.columns]
    if missing_metric_cols:
        raise ValueError(f"Requested metrics not available: {missing_metric_cols}")

    plot_df = df[required_cols].copy()


    panel_metrics = {
        panel: [m for m in panel_list if m in metrics]
        for panel, panel_list in PANEL_MAP.items()
    }
    active_panels = {k: v for k, v in panel_metrics.items() if v}

    if not active_panels:
        raise ValueError("No valid metrics selected for plotting")

    fig, axes = plt.subplots(
        nrows=len(active_panels),
        ncols=1,
        figsize=(14, 3.8 * len(active_panels)),
    )

    if len(active_panels) == 1:
        axes = [axes]

    supplier_labels = [
        f"{sid} ({cc})"
        for sid, cc in zip(plot_df["supplier_id"], plot_df["country_code"])
    ]

    for ax, (panel_name, panel_cols) in zip(axes, active_panels.items()):
        x = np.arange(len(panel_cols))
        width = 0.8 / len(plot_df)

        for i, (_, row) in enumerate(plot_df.iterrows()):
            values = [row[col] for col in panel_cols]
            bar_positions = x + i * width - ((len(plot_df) - 1) * width / 2)

            ax.bar(
                bar_positions,
                values,
                width=width,
                label=supplier_labels[i],
            )

        ax.set_xticks(x)
        ax.set_xticklabels(
            [_pretty_label(col) for col in panel_cols],
            rotation=20,
            ha="right",
        )
        ax.set_title(panel_name, fontsize=12)
        ax.grid(True, axis="y", alpha=0.3)

        ax.set_ylabel("Raw Value")

    handles, labels = axes[0].get_legend_handles_labels()

    fig.suptitle(
        f"Supplier Comparison Panel — {_pretty_product_name(product)} | Q={Q:,}",
        fontsize=16,
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

    fig.subplots_adjust(
        top=0.86,
        hspace=0.70,
        left=0.08,
        right=0.98,
        bottom=0.09,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return fig, axes, df