"""
Thin wrappers around the teammate's analytics/charts functions.
Each wrapper opens a psycopg2 connection, calls the original function,
encodes the resulting matplotlib Figure as base64 PNG, and cleans up.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import base64
import io
import logging

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for server use
import matplotlib.pyplot as plt
import psycopg2

from config import DATABASE_URL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn():
    """Create a fresh psycopg2 connection."""
    return psycopg2.connect(DATABASE_URL)


def _fig_to_base64(fig) -> str:
    """Encode a matplotlib Figure as a base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Chart wrappers — each returns {"image": base64_str, "name": str}
# ---------------------------------------------------------------------------

def plot_score_breakdown(
    supplier_ids: list[str],
    product: str,
    Q: int = 5000,
    lambda_risk: float | None = None,
    compliance_threshold: float | None = None,
    **_kwargs,
) -> dict:
    """Supplier score breakdown: final score, cost drivers, risk penalty, risk components."""
    from analytics.charts.plot_supplier_score_breakdown_panel import (
        plot_supplier_score_breakdown_panel,
    )

    conn = _get_conn()
    try:
        kwargs = {"conn": conn, "supplier_ids": supplier_ids, "product": product, "Q": Q}
        if lambda_risk is not None:
            kwargs["lambda_risk"] = lambda_risk
        if compliance_threshold is not None:
            kwargs["compliance_threshold"] = compliance_threshold
        fig, _axes, _df = plot_supplier_score_breakdown_panel(**kwargs)
        return {"image": _fig_to_base64(fig), "name": "plot_score_breakdown"}
    finally:
        conn.close()


def plot_supplier_comparison(
    supplier_ids: list[str],
    product: str,
    Q: int = 5000,
    metrics: list[str] | None = None,
    tariff_enabled: bool = True,
    **_kwargs,
) -> dict:
    """Side-by-side supplier comparison on cost, volatility, discount, lead time."""
    from analytics.charts.supplier_comparison_panel import (
        plot_supplier_comparison_panel,
    )

    conn = _get_conn()
    try:
        kwargs = {
            "conn": conn,
            "supplier_ids": supplier_ids,
            "product": product,
            "Q": Q,
            "tariff_enabled": tariff_enabled,
        }
        if metrics is not None:
            kwargs["metrics"] = metrics
        fig, _axes, _df = plot_supplier_comparison_panel(**kwargs)
        return {"image": _fig_to_base64(fig), "name": "plot_supplier_comparison"}
    finally:
        conn.close()


def plot_country_comparison(
    country_codes: list[str],
    **_kwargs,
) -> dict:
    """Country-level logistics (LPI) and governance (WGI) indicator comparison."""
    from analytics.charts.plot_country_logistics_governance_comparison_panel import (
        plot_country_indicator_comparison_panel,
    )

    conn = _get_conn()
    try:
        fig, _axes, _df = plot_country_indicator_comparison_panel(
            conn=conn, country_codes=country_codes,
        )
        return {"image": _fig_to_base64(fig), "name": "plot_country_comparison"}
    finally:
        conn.close()


def plot_price_trend(
    country_code: str,
    product: str,
    **_kwargs,
) -> dict:
    """Product real-price trend over time for a single country."""
    from analytics.charts.product_price_trend import plot_product_price_trend

    conn = _get_conn()
    try:
        fig = plot_product_price_trend(conn=conn, country_code=country_code, product=product)
        return {"image": _fig_to_base64(fig), "name": "plot_price_trend"}
    finally:
        conn.close()


def plot_volatility_trend(
    country_code: str,
    product: str,
    window: int = 6,
    start_date: str | None = None,
    **_kwargs,
) -> dict:
    """Rolling price volatility trend for a single country + product."""
    from analytics.charts.rolling_price_volatility_trend import (
        plot_rolling_price_volatility_trend,
    )

    conn = _get_conn()
    try:
        kwargs = {
            "conn": conn,
            "country_code": country_code,
            "product": product,
            "window": window,
        }
        if start_date is not None:
            kwargs["start_date"] = start_date
        fig = plot_rolling_price_volatility_trend(**kwargs)
        return {"image": _fig_to_base64(fig), "name": "plot_volatility_trend"}
    finally:
        conn.close()


def plot_cross_country_volatility(
    product: str,
    country_codes: list[str],
    window: int = 6,
    start_date: str | None = None,
    **_kwargs,
) -> dict:
    """Compare rolling price volatility across multiple countries for one product."""
    from analytics.charts.cross_country_rolling_volatility import (
        plot_cross_country_rolling_volatility,
    )

    conn = _get_conn()
    try:
        kwargs = {
            "conn": conn,
            "product": product,
            "country_codes": country_codes,
            "window": window,
        }
        if start_date is not None:
            kwargs["start_date"] = start_date
        fig = plot_cross_country_rolling_volatility(**kwargs)
        return {"image": _fig_to_base64(fig), "name": "plot_cross_country_volatility"}
    finally:
        conn.close()


def plot_price_vs_commodity(
    country_code: str,
    product: str,
    commodity_families: list[str] | None = None,
    **_kwargs,
) -> dict:
    """Indexed product price vs commodity baseline trends."""
    from analytics.charts.product_price_vs_commodity_trends import (
        plot_product_price_vs_commodity_trends,
    )

    conn = _get_conn()
    try:
        kwargs = {"conn": conn, "country_code": country_code, "product": product}
        if commodity_families is not None:
            kwargs["commodity_families"] = commodity_families
        fig = plot_product_price_vs_commodity_trends(**kwargs)
        return {"image": _fig_to_base64(fig), "name": "plot_price_vs_commodity"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Registry — maps tool name strings to callables (mirrors DIRECT_TOOLS pattern)
# ---------------------------------------------------------------------------

DIRECT_CHART_TOOLS: dict[str, callable] = {
    "plot_score_breakdown": plot_score_breakdown,
    "plot_supplier_comparison": plot_supplier_comparison,
    "plot_country_comparison": plot_country_comparison,
    "plot_price_trend": plot_price_trend,
    "plot_volatility_trend": plot_volatility_trend,
    "plot_cross_country_volatility": plot_cross_country_volatility,
    "plot_price_vs_commodity": plot_price_vs_commodity,
}
