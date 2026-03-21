import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


def plot_cross_country_rolling_volatility(
    conn,
    product: str,
    country_codes: list[str],
    window: int = 6,
    start_date: str | None = None,
    save_path: str | None = None
):
    if not country_codes:
        raise ValueError("country_codes must contain at least one country code")

    query = """
        SELECT date, country_code, real_price
        FROM vw_product_price_history
        WHERE product = %(product)s
          AND country_code = ANY(%(country_codes)s)
        ORDER BY country_code, date
    """

    df = pd.read_sql(
        query,
        conn,
        params={
            "product": product,
            "country_codes": country_codes
        }
    )

    if df.empty:
        raise ValueError(
            f"No data found for product={product}, country_codes={country_codes}"
        )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["country_code", "date"]).copy()

    if start_date is not None:
        start_date = pd.to_datetime(start_date)
        df = df[df["date"] >= start_date].copy()

    # monthly percent change within each country
    df["pct_change"] = df.groupby("country_code")["real_price"].pct_change()

    # rolling volatility within each country, scaled to %
    df["rolling_volatility"] = (
        df.groupby("country_code")["pct_change"]
        .transform(lambda s: s.rolling(window=window).std() * 100)
    )

    fig, ax = plt.subplots(figsize=(11, 5.5))
    
    line_styles = ["-", "--", "-.", ":"]
    for i, country in enumerate(country_codes):
        sub = df[df["country_code"] == country].copy()
    
        if sub["rolling_volatility"].notna().sum() == 0:
            continue
    
        ax.plot(
                sub["date"],
                sub["rolling_volatility"],
                linewidth=2,
                label=country,
                linestyle=line_styles[i % len(line_styles)]
         )

    ax.set_title(
        f"{product.replace('_', ' ').title()} - Cross-Country Rolling Price Volatility ({window}-Month Window)"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Rolling Std. Dev. of Monthly % Change (%)")
    ax.grid(True, alpha=0.3)
    ax.legend(title="Country", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches="tight")

    return fig