from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def plot_product_price_trend(conn, country_code:str, product: str,
                              save_path: str | None = None):
    query = """
        SELECT date, real_price
        FROM vw_product_price_history
        WHERE country_code = %(country_code)s
        AND product = %(product)s
        ORDER BY date
        """
    
    df = pd.read_sql(query, conn, params={"country_code": country_code, "product": product})

    if df.empty:
        raise ValueError(f"No data found for country_code={country_code}, product={product}")
    
    df['date'] = pd.to_datetime(df['date'])

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(df['date'], df['real_price'])
    ax.set_title(f"{product.title().replace('_', ' ')}; Wholesale per unit trend - {country_code}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Real price")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches='tight')

    return fig