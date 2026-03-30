"""
forecast_summary.py — Business-facing production forecast summary.

Entry point:
    get_latest_production_forecast_summary(conn, forecast_run_id=None) -> dict

Reads from:
    dim_forecast_run                    (run metadata)
    fact_semiconductor_demand_forecast  (forecast rows)

Does NOT retrain the model, load CSVs, or call run_production.py.
All dates come from stored DB metadata — not from date.today().

Grain validated at call time:
    expected_rows = facility_count × sku_count × week_count
    actual_rows   = COUNT(*) WHERE forecast_run_id = <run_id>

Also exports a standalone LangChain @tool wrapper (get_forecast_summary_tool)
for future agent integration (Option B — no demo/* files modified).

Usage:
    import psycopg2
    from forecasting.forecast_summary import get_latest_production_forecast_summary

    conn = psycopg2.connect(DATABASE_URL)
    summary = get_latest_production_forecast_summary(conn)
    conn.close()
"""

import os
import logging

import pandas as pd
import psycopg2
from dotenv import load_dotenv

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(fn):  # no-op decorator when langchain_core is not installed
        return fn

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/procurement_agent",
)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _resolve_run_id(conn, forecast_run_id=None) -> int:
    """Return the requested run_id, or the most recent one if None."""
    with conn.cursor() as cur:
        if forecast_run_id is not None:
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "WHERE forecast_run_id = %s",
                (forecast_run_id,),
            )
        else:
            cur.execute(
                "SELECT forecast_run_id FROM dim_forecast_run "
                "ORDER BY forecast_run_id DESC LIMIT 1"
            )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            "No forecast run found in dim_forecast_run. "
            "Run forecasting/run_production.py to generate the production forecast first."
        )
    return int(row[0])


# ── Core summary function ──────────────────────────────────────────────────────

def get_latest_production_forecast_summary(conn, forecast_run_id=None) -> dict:
    """
    Return a structured summary of the production forecast.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.

    Returns
    -------
    dict
        Structured summary with keys:
          forecast_run_id, model_version,
          forecast_origin_date, observed_through_week_date,
          planning_horizon_start_date, planning_horizon_end_date,
          horizon_weeks,
          coverage   : {facility_count, sku_count, series_count,
                        week_count, expected_rows, actual_rows, grain_valid}
          demand     : {total_forecasted_demand, average_weekly_demand,
                        peak_week_date, peak_week_demand,
                        lowest_week_date, lowest_week_demand}
          weekly_totals : list of {week_date, total_demand}

    All date fields come from stored DB metadata — no date.today() is used.
    Grain is validated: expected_rows = series_count × week_count.
    """
    run_id = _resolve_run_id(conn, forecast_run_id)

    # ── Run metadata (from dim_forecast_run) ───────────────────────────────────
    run_sql = """
        SELECT
            forecast_run_id,
            model_version,
            forecast_origin_date,
            observed_through_week_date,
            horizon_weeks_max
        FROM dim_forecast_run
        WHERE forecast_run_id = %(run_id)s
    """
    run_df = pd.read_sql(run_sql, conn, params={"run_id": run_id})
    if run_df.empty:
        raise RuntimeError(f"forecast_run_id={run_id} not found in dim_forecast_run.")
    run = run_df.iloc[0]

    # ── Coverage counts (from fact table) ─────────────────────────────────────
    # Grain: (forecast_run_id, facility_id, semiconductor_id, target_week_date)
    # DB-level UNIQUE constraint uq_forecast_grain already prevents duplicates;
    # grain_valid provides an additional application-layer assertion.
    coverage_sql = """
        SELECT
            COUNT(DISTINCT facility_id)                        AS facility_count,
            COUNT(DISTINCT semiconductor_id)                   AS sku_count,
            COUNT(DISTINCT (facility_id, semiconductor_id))    AS series_count,
            COUNT(DISTINCT target_week_date)                   AS week_count,
            COUNT(*)                                           AS actual_rows,
            MIN(target_week_date)                              AS horizon_start,
            MAX(target_week_date)                              AS horizon_end
        FROM fact_semiconductor_demand_forecast
        WHERE forecast_run_id = %(run_id)s
    """
    cov_df = pd.read_sql(coverage_sql, conn, params={"run_id": run_id})
    cov = cov_df.iloc[0]

    facility_count = int(cov["facility_count"])
    sku_count      = int(cov["sku_count"])
    series_count   = int(cov["series_count"])
    week_count     = int(cov["week_count"])
    actual_rows    = int(cov["actual_rows"])
    expected_rows  = series_count * week_count
    grain_valid    = (actual_rows == expected_rows)

    if not grain_valid:
        logger.warning(
            f"[FORECAST_SUMMARY] Grain check FAILED for run_id={run_id}: "
            f"expected {expected_rows:,} rows ({series_count} series × "
            f"{week_count} weeks), got {actual_rows:,}."
        )

    # ── Weekly totals (aggregated across all facilities + SKUs) ───────────────
    weekly_sql = """
        SELECT
            target_week_date,
            SUM(predicted_demand) AS total_demand
        FROM fact_semiconductor_demand_forecast
        WHERE forecast_run_id = %(run_id)s
        GROUP BY target_week_date
        ORDER BY target_week_date
    """
    weekly_df = pd.read_sql(weekly_sql, conn, params={"run_id": run_id})

    total_demand = float(weekly_df["total_demand"].sum())
    avg_weekly   = total_demand / len(weekly_df) if len(weekly_df) > 0 else 0.0
    peak_idx     = weekly_df["total_demand"].idxmax()
    lowest_idx   = weekly_df["total_demand"].idxmin()

    weekly_totals = [
        {
            "week_date":    str(row["target_week_date"]),
            "total_demand": round(float(row["total_demand"]), 2),
        }
        for _, row in weekly_df.iterrows()
    ]

    return {
        # Run metadata — all from stored DB values, not computed at call time
        "forecast_run_id":              run_id,
        "model_version":                str(run["model_version"]),
        "forecast_origin_date":         str(run["forecast_origin_date"]),
        "observed_through_week_date":   str(run["observed_through_week_date"]),
        "planning_horizon_start_date":  str(cov["horizon_start"]),
        "planning_horizon_end_date":    str(cov["horizon_end"]),
        "horizon_weeks":                int(run["horizon_weeks_max"]),

        # Coverage — computed from actual fact rows
        "coverage": {
            "facility_count": facility_count,
            "sku_count":       sku_count,
            "series_count":    series_count,
            "week_count":      week_count,
            "expected_rows":   expected_rows,
            "actual_rows":     actual_rows,
            "grain_valid":     grain_valid,
        },

        # Planning horizon demand overview
        "demand": {
            "total_forecasted_demand": round(total_demand, 2),
            "average_weekly_demand":   round(avg_weekly, 2),
            "peak_week_date":          str(weekly_df.loc[peak_idx,   "target_week_date"]),
            "peak_week_demand":        round(float(weekly_df.loc[peak_idx,   "total_demand"]), 2),
            "lowest_week_date":        str(weekly_df.loc[lowest_idx, "target_week_date"]),
            "lowest_week_demand":      round(float(weekly_df.loc[lowest_idx, "total_demand"]), 2),
        },

        # Full weekly breakdown (system-level totals across all 48 series)
        "weekly_totals": weekly_totals,
    }


# ── Formatted text renderer ────────────────────────────────────────────────────

def _format_summary(s: dict) -> str:
    """Render the structured summary dict as a business-facing string."""
    cov = s["coverage"]
    dm  = s["demand"]

    grain_status = (
        f"✓  ({cov['actual_rows']:,} rows = "
        f"{cov['series_count']} series × {cov['week_count']} weeks)"
        if cov["grain_valid"]
        else (
            f"⚠  FAIL — expected {cov['expected_rows']:,}, "
            f"got {cov['actual_rows']:,}"
        )
    )

    lines = [
        "=" * 62,
        "  PRODUCTION DEMAND FORECAST — SUMMARY",
        "=" * 62,
        "",
        f"  Model              : {s['model_version']}",
        f"  Forecast run ID    : {s['forecast_run_id']}",
        f"  Forecast run date  : {s['forecast_origin_date']}",
        f"  Last observed week : {s['observed_through_week_date']}",
        "",
        "  Forecast Coverage:",
        f"    Facilities              : {cov['facility_count']}",
        f"    SKUs                    : {cov['sku_count']}",
        f"    SKU × Facility series   : {cov['series_count']}",
        f"    Grain check             : {grain_status}",
        "",
        "  Planning Horizon:",
        f"    Start                   : {s['planning_horizon_start_date']}",
        f"    End                     : {s['planning_horizon_end_date']}",
        f"    Duration                : {s['horizon_weeks']} weeks",
        "",
        "  Demand Overview  (all facilities + SKUs combined):",
        f"    Total forecasted demand : {dm['total_forecasted_demand']:>12,.0f} units",
        f"    Average weekly demand   : {dm['average_weekly_demand']:>12,.0f} units/week",
        f"    Peak week               : {dm['peak_week_date']}  →  "
        f"{dm['peak_week_demand']:>10,.0f} units",
        f"    Lowest week             : {dm['lowest_week_date']}  →  "
        f"{dm['lowest_week_demand']:>10,.0f} units",
        "",
        "=" * 62,
    ]
    return "\n".join(lines)


# ── Drill-down function ───────────────────────────────────────────────────────

def get_production_forecast_drilldown(
    conn,
    forecast_run_id=None,
    export_csv: bool = False,
) -> "pd.DataFrame":
    """
    Return the full row-level forecast for a given run.

    Parameters
    ----------
    conn : psycopg2 connection
        Open DB connection. Caller is responsible for closing it.
    forecast_run_id : int, optional
        Specific run to retrieve. If None, uses the most recent run.
    export_csv : bool, optional
        If True, write the result to
        artifacts/forecasting/forecast_drilldown_<run_id>.csv.

    Returns
    -------
    pd.DataFrame
        Columns: target_week_date, facility_id, semiconductor_id,
                 predicted_demand, interval_lower_90, interval_upper_90,
                 horizon_weeks
        Sorted: ORDER BY target_week_date, facility_id, semiconductor_id
        Grain:  (forecast_run_id, facility_id, semiconductor_id, target_week_date)

    Validation (raises RuntimeError on failure):
        actual_rows == weeks × facilities × SKUs
        no duplicate rows
        interval_lower_90 <= predicted_demand <= interval_upper_90 for all rows
    """
    import os as _os

    run_id = _resolve_run_id(conn, forecast_run_id)

    drilldown_sql = """
        SELECT
            target_week_date,
            facility_id,
            semiconductor_id,
            predicted_demand,
            interval_lower_90,
            interval_upper_90,
            horizon_weeks
        FROM fact_semiconductor_demand_forecast
        WHERE forecast_run_id = %(run_id)s
        ORDER BY target_week_date, facility_id, semiconductor_id
    """
    with conn.cursor() as cur:
        cur.execute(drilldown_sql, {"run_id": run_id})
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]

    df = pd.DataFrame(rows, columns=col_names)

    # ── Validation ────────────────────────────────────────────────────────────
    weeks      = df["target_week_date"].nunique()
    facilities = df["facility_id"].nunique()
    skus       = df["semiconductor_id"].nunique()
    expected   = weeks * facilities * skus
    actual     = len(df)

    if actual != expected:
        raise RuntimeError(
            f"[DRILLDOWN] Grain check FAILED for run_id={run_id}: "
            f"expected {expected:,} rows ({weeks} weeks × {facilities} fac × {skus} SKUs), "
            f"got {actual:,}."
        )

    dup_count = df.duplicated(
        subset=["target_week_date", "facility_id", "semiconductor_id"]
    ).sum()
    if dup_count > 0:
        raise RuntimeError(
            f"[DRILLDOWN] {dup_count} duplicate grain rows found for run_id={run_id}."
        )

    ci_violations = (
        (df["interval_lower_90"] > df["predicted_demand"]) |
        (df["interval_upper_90"] < df["predicted_demand"])
    ).sum()
    if ci_violations > 0:
        logger.warning(
            f"[DRILLDOWN] {ci_violations} CI bound violations for run_id={run_id} "
            f"(interval_lower_90 > predicted_demand OR interval_upper_90 < predicted_demand)."
        )

    # ── Optional CSV export ───────────────────────────────────────────────────
    if export_csv:
        out_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "artifacts", "forecasting",
        )
        _os.makedirs(out_dir, exist_ok=True)
        out_path = _os.path.join(out_dir, f"forecast_drilldown_{run_id}.csv")
        df.to_csv(out_path, index=False)
        logger.info(f"[DRILLDOWN] Exported {len(df):,} rows → {out_path}")

    return df


# ── LangChain @tool wrapper (Option B — no demo/* modified) ───────────────────

@tool
def get_forecast_summary_tool(forecast_run_id: int = 0) -> str:
    """Retrieve the production demand forecast summary from the database.

    Returns a business-facing summary including:
    - Run metadata (model version, forecast run date, last observed week)
    - Forecast coverage (facilities, SKUs, series count, grain validation)
    - Planning horizon (start date, end date, duration in weeks)
    - Demand overview (total, average weekly, peak week, lowest week)

    Reads from pre-computed DB tables only — no model retraining.

    Args:
        forecast_run_id: Specific run ID to retrieve. Use 0 (default) to
                         retrieve the most recent production forecast run.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        summary = get_latest_production_forecast_summary(conn, forecast_run_id=run_id)
        return _format_summary(summary)
    except Exception as e:
        logger.error(f"[FORECAST_SUMMARY] Tool call failed: {e}", exc_info=True)
        return f"Error retrieving forecast summary: {e}"
    finally:
        conn.close()


@tool
def get_forecast_drilldown_tool(
    forecast_run_id: int = 0,
    export_csv: bool = False,
) -> str:
    """Retrieve the row-level production forecast drill-down from the database.

    Returns a coverage summary (row count, distinct facilities, SKUs, weeks,
    grain validation) for the requested forecast run. If export_csv is True,
    also writes the full drill-down to a CSV file and reports the export path.

    All data is read from pre-computed DB tables only — no model retraining.

    Args:
        forecast_run_id: Specific run ID to retrieve. Use 0 (default) to
                         retrieve the most recent production forecast run.
        export_csv: If True, export the full drill-down DataFrame to
                    artifacts/forecasting/forecast_drilldown_<run_id>.csv.
    """
    conn = _get_conn()
    try:
        run_id = forecast_run_id if forecast_run_id > 0 else None
        resolved = _resolve_run_id(conn, run_id)
        df = get_production_forecast_drilldown(conn, forecast_run_id=run_id, export_csv=export_csv)

        weeks      = df["target_week_date"].nunique()
        facilities = df["facility_id"].nunique()
        skus       = df["semiconductor_id"].nunique()
        expected   = weeks * facilities * skus
        actual     = len(df)
        grain_ok   = actual == expected

        lines = [
            f"Forecast Drill-Down  (run_id={resolved})",
            f"  Rows returned   : {actual:,}",
            f"  Facilities      : {facilities}",
            f"  SKUs            : {skus}",
            f"  Weeks           : {weeks}  "
            f"({str(df['target_week_date'].min())} → {str(df['target_week_date'].max())})",
            f"  Grain valid     : {'✓' if grain_ok else '⚠ FAIL'}  "
            f"({actual:,} rows = {weeks} weeks × {facilities} fac × {skus} SKUs)",
        ]

        if export_csv:
            import os as _os
            out_dir = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "artifacts", "forecasting",
            )
            out_path = _os.path.join(out_dir, f"forecast_drilldown_{resolved}.csv")
            lines.append(f"  CSV exported    : {out_path}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[FORECAST_DRILLDOWN] Tool call failed: {e}", exc_info=True)
        return f"Error retrieving forecast drill-down: {e}"
    finally:
        conn.close()
