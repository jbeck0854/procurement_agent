import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


def plot_rolling_price_volatility_trend(
    conn,
    country_code: str,
    product: str,
    window: int = 6,
    start_date: str | None = None,
    save_path: str | None = None
):
    query = """
        SELECT date, real_price
        FROM vw_product_price_history
        WHERE country_code = %(country_code)s
          AND product = %(product)s
        ORDER BY date
    """

    df = pd.read_sql(
        query,
        conn,
        params={
            "country_code": country_code,
            "product": product
        }
    )

    if df.empty:
        raise ValueError(f"No data found for product={product}, country_code={country_code}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").copy()

    if start_date is not None:
        start_date = pd.to_datetime(start_date)
        df = df[df["date"] >= start_date].copy()

    if len(df) < window + 1:
        raise ValueError(
            f"Not enough observations to compute rolling volatility with window={window}"
        )

    # monthly percent change
    df["pct_change"] = df["real_price"].pct_change()

    # rolling volatility of returns
    df["rolling_volatility"] = df["pct_change"].rolling(window=window).std() * 100

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        df["date"],
        df["rolling_volatility"],
        linewidth=2.2,
        label=f"{product.replace('_', ' ').title()} Rolling Volatility"
    )

    ax.set_title(
        f"{product.replace('_', ' ').title()} - Rolling Price Volatility ({country_code}, {window}-Month Window)"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Rolling Std. Dev. of Monthly % Change (%)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")

    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches="tight")

    return fig