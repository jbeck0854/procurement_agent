import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


PRODUCT_COMMODITY_MAP = {
    "integrated_circuit_components": ["Copper", "Aluminum"],
    "transistors": ["Copper", "Aluminum"],
    "microprocessors": ["Copper", "Natural gas index"],
    "power_devices": ["Copper", "Aluminum"]
}


def plot_product_price_vs_commodity_trends(
    conn,
    country_code: str,
    product: str,
    commodity_families: list[str] | None = None,
    save_path: str | None = None
):
    if commodity_families is None:
        commodity_families = PRODUCT_COMMODITY_MAP.get(product, [])

    if not commodity_families:
        raise ValueError(f"No commodity mapping found for product={product}")

    product_query = """
        SELECT date, real_price
        FROM vw_product_price_history
        WHERE country_code = %(country_code)s
          AND product = %(product)s
        ORDER BY date
    """

    product_df = pd.read_sql(
        product_query,
        conn,
        params={
            "country_code": country_code,
            "product": product
        }
    )

    if product_df.empty:
        raise ValueError(f"No product price data found for product={product}, country_code={country_code}")

    commodity_query = """
        SELECT date, commodity_family, nominal_price
        FROM vw_commodity_price_history
        WHERE commodity_family = ANY(%(commodity_families)s)
        ORDER BY date
    """

    commodity_df = pd.read_sql(
        commodity_query,
        conn,
        params={"commodity_families": commodity_families}
    )

    if commodity_df.empty:
        raise ValueError(f"No commodity data found for {commodity_families}")

    product_df["date"] = pd.to_datetime(product_df["date"])
    commodity_df["date"] = pd.to_datetime(commodity_df["date"])

    product_df = product_df.sort_values("date").copy()
    product_df["product_price_index"] = (
        product_df["real_price"] / product_df["real_price"].iloc[0] * 100
    )
    product_df["product_price_index"] = (
        product_df["product_price_index"].rolling(window=3, min_periods=1).mean()
    )

    commodity_agg = (
        commodity_df
        .groupby(["date", "commodity_family"], as_index=False)["nominal_price"]
        .mean()
    )

    commodity_wide = (
        commodity_agg
        .pivot(index="date", columns="commodity_family", values="nominal_price")
        .sort_index()
    )

    for col in commodity_wide.columns:
        commodity_wide[col] = commodity_wide[col] / commodity_wide[col].iloc[0] * 100

    commodity_wide = commodity_wide.rolling(window=3, min_periods=1).mean()

    fig, ax = plt.subplots(figsize=(11, 5.5))

    ax.plot(
        product_df["date"],
        product_df["product_price_index"],
        linewidth=2.5,
        label=f"{product.replace('_', ' ').title()} Price"
    )

    for col in commodity_wide.columns:
        ax.plot(
            commodity_wide.index,
            commodity_wide[col],
            linestyle="--",
            linewidth=1.8,
            label=col
        )

    ax.set_title(
        f"{product.replace('_', ' ').title()} - Indexed Price vs Selected Upstream Commodity Trends ({country_code})"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Index (Start = 100)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches="tight")

    return fig