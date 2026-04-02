"""
Direct-mode query tools for the upstream pipeline (forecast, BOM, inventory).
These bypass the ReAct loop — each tool runs pre-built queries and returns
a formatted business-friendly summary. Designed for speed in the demo flow.

Delegates to Jonathan's helper modules in forecasting/ and inventory/.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import psycopg2

from config import DATABASE_URL

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


# ── Forecast helpers (from forecasting/forecast_summary.py) ─────────────────

from forecasting.forecast_summary import (
    get_forecast_summary_tool,
    get_forecast_drilldown_tool,
    get_forecast_model_assessment,
)

# ── Inventory/Procurement helpers (from inventory/procurement_summary.py) ───

from inventory.procurement_summary import (
    get_component_requirements_summary_tool,
    get_procurement_status_summary_tool,
    get_procurement_planning_summary_tool,
    get_aggregated_procurement_need_tool,
    get_bom_translation_tool,
    get_procurement_requirement_drilldown,
    get_triggered_procurement_rows,
)


# ── Wrappers ────────────────────────────────────────────────────────────────
#
# Jonathan's @tool-decorated helpers manage their own DB connections.
# We wrap them so pipeline_agent gets a uniform {content, name} interface.
#
# For functions that require a `conn` argument (drill-down, triggered rows),
# we manage the connection here.
# ────────────────────────────────────────────────────────────────────────────


def query_forecast_summary(**kwargs) -> dict:
    """Business-friendly production demand forecast summary."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_forecast_summary_tool.invoke({"forecast_run_id": forecast_run_id})
    return {"content": result, "name": "forecast_summary"}


def query_forecast_drilldown(**kwargs) -> dict:
    """Week × facility × SKU forecast detail with confidence bounds."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    export_csv = kwargs.get("export_csv", False)
    result = get_forecast_drilldown_tool.invoke({
        "forecast_run_id": forecast_run_id,
        "export_csv": export_csv,
    })
    return {"content": result, "name": "forecast_drilldown"}


def query_forecast_model_assessment(**kwargs) -> dict:
    """Model explainability: validation, feature importance, or baseline comparison."""
    direction = kwargs.get("direction", "validation")
    try:
        assessment = get_forecast_model_assessment(direction)
        lines = [
            assessment["title"],
            "=" * len(assessment["title"]),
            "",
            assessment["executive_summary"],
            "",
            f"Artifact: {assessment['artifact'].get('label', '')}",
            f"  Path: {assessment['artifact'].get('path', '')}",
            f"  Why it matters: {assessment['artifact'].get('why_it_matters', '')}",
            "",
            f"Suggested next step: {assessment['next_step_prompt']}",
        ]
        if "improvement_recommendations" in assessment:
            lines.append("")
            lines.append("Improvement recommendations:")
            for rec in assessment["improvement_recommendations"]:
                lines.append(f"  - {rec}")
        return {"content": "\n".join(lines), "name": "forecast_model_assessment"}
    except (ValueError, FileNotFoundError) as e:
        return {"content": f"Error: {e}", "name": "forecast_model_assessment"}


def query_component_requirements(**kwargs) -> dict:
    """Full-horizon gross BOM demand (before inventory offset)."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_component_requirements_summary_tool.invoke({
        "forecast_run_id": forecast_run_id,
    })
    return {"content": result, "name": "component_requirements"}


def query_procurement_status(**kwargs) -> dict:
    """Week-by-week inventory-adjusted procurement trigger signal."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_procurement_status_summary_tool.invoke({
        "forecast_run_id": forecast_run_id,
    })
    return {"content": result, "name": "procurement_status"}


def query_procurement_planning_summary(**kwargs) -> dict:
    """Combined: gross BOM demand + weekly procurement trigger signal."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    result = get_procurement_planning_summary_tool.invoke({
        "forecast_run_id": forecast_run_id,
    })
    return {"content": result, "name": "procurement_planning_summary"}


def query_aggregated_procurement_need(**kwargs) -> dict:
    """Horizon-level LP demand floor — what the optimizer allocates against."""
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    product = kwargs.get("product", "")
    facility_id = kwargs.get("facility_id", "")
    result = get_aggregated_procurement_need_tool.invoke({
        "forecast_run_id": forecast_run_id,
        "product": product,
        "facility_id": facility_id,
    })
    return {"content": result, "name": "aggregated_procurement_need"}


def query_procurement_drilldown(**kwargs) -> dict:
    """Week-by-week drill-down at component × facility × week grain."""
    product = kwargs.get("product", None)
    facility_id = kwargs.get("facility_id", None)
    forecast_run_id = kwargs.get("forecast_run_id", None)
    conn = _get_conn()
    try:
        result = get_procurement_requirement_drilldown(
            conn,
            forecast_run_id=forecast_run_id,
            product=product,
            facility_id=facility_id,
        )
        return {"content": result, "name": "procurement_drilldown"}
    finally:
        conn.close()


def query_triggered_procurement_rows(**kwargs) -> dict:
    """Only weeks/facilities where net requirement > 0."""
    product = kwargs.get("product", None)
    facility_id = kwargs.get("facility_id", None)
    forecast_run_id = kwargs.get("forecast_run_id", None)
    conn = _get_conn()
    try:
        result = get_triggered_procurement_rows(
            conn,
            forecast_run_id=forecast_run_id,
            product=product,
            facility_id=facility_id,
        )
        return {"content": result, "name": "triggered_procurement_rows"}
    finally:
        conn.close()


def query_bom_translation(**kwargs) -> dict:
    """BOM recipe or forecast-row explosion for a semiconductor SKU."""
    semiconductor_id = kwargs.get("semiconductor_id", "")
    forecast_run_id = kwargs.get("forecast_run_id", 0)
    facility_id = kwargs.get("facility_id", "")
    target_week_date = kwargs.get("target_week_date", "")
    result = get_bom_translation_tool.invoke({
        "semiconductor_id": semiconductor_id,
        "forecast_run_id": forecast_run_id,
        "facility_id": facility_id,
        "target_week_date": target_week_date,
    })
    return {"content": result, "name": "bom_translation"}


# ── Tool registry ───────────────────────────────────────────────────────────

DIRECT_PIPELINE_TOOLS = {
    # Forecast
    "query_forecast_summary": query_forecast_summary,
    "query_forecast_drilldown": query_forecast_drilldown,
    "query_forecast_model_assessment": query_forecast_model_assessment,
    # BOM / Component requirements
    "query_component_requirements": query_component_requirements,
    "query_bom_translation": query_bom_translation,
    # Inventory / Procurement
    "query_procurement_status": query_procurement_status,
    "query_procurement_planning_summary": query_procurement_planning_summary,
    "query_aggregated_procurement_need": query_aggregated_procurement_need,
    "query_procurement_drilldown": query_procurement_drilldown,
    "query_triggered_procurement_rows": query_triggered_procurement_rows,
}
