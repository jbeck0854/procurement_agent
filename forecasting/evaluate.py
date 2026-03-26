"""
evaluate.py — Metrics computation and visualization for the forecasting pipeline.

Evaluation outputs:
  1. CV fold summary (MAE/RMSE by variant and horizon)
  2. Holdout aggregate (system-level: all 48 series summed per week)
  3. Holdout per-series summary (mean/median MAE + worst 5 series)
  4. Plots:
       - CV MAE by horizon (raw vs log)
       - System-level actual vs predicted (holdout)
       - Per-series sample plots (holdout)
       - Residual distribution + residuals vs predicted
       - Feature importance (h=1, h=4, h=12)
       - 12-week forward forecast (most volatile series)
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

ARTIFACTS = Path("artifacts/forecasting")

# Consistent colour palette for business-facing plots
_BLUE   = "#1f4e79"   # actuals / historical
_ORANGE = "#ed7d31"   # model predictions
_GRAY   = "#a5a5a5"   # baselines / reference lines
_LBLUE  = "#9dc3e6"   # secondary / low-importance bars


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Scalar metrics ────────────────────────────────────────────────────────────

def _mae(a: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(a - p)))


def _rmse(a: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - p) ** 2)))


def _mape(a: np.ndarray, p: np.ndarray) -> float:
    mask = a != 0
    return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask]))) if mask.any() else np.nan


# ── CV summary ────────────────────────────────────────────────────────────────

def summarize_cv(cv_df: pd.DataFrame) -> pd.DataFrame:
    """Average CV metrics across folds, grouped by variant × horizon."""
    return (
        cv_df
        .groupby(["variant", "horizon"])[["mae", "rmse", "mape"]]
        .mean()
        .reset_index()
        .sort_values(["variant", "horizon"])
    )


def print_cv_summary(cv_df: pd.DataFrame) -> None:
    summary = summarize_cv(cv_df)
    for variant, grp in summary.groupby("variant"):
        print(f"\n  CV ({variant}) — mean across folds:")
        print(
            grp[["horizon", "mae", "rmse", "mape"]]
            .round(1)
            .to_string(index=False)
        )


# ── Holdout metrics ───────────────────────────────────────────────────────────

def holdout_aggregate(holdout_df: pd.DataFrame) -> pd.DataFrame:
    """
    System-level evaluation: sum all 48 series per target week, then
    compute MAE and RMSE on the weekly totals.

    Returns one row per variant.
    """
    rows = []
    for variant, grp in holdout_df.groupby("variant"):
        sys = (
            grp.dropna(subset=["actual"])
            .groupby("target_week")[["actual", "predicted"]]
            .sum()
            .reset_index()
        )
        if sys.empty:
            continue
        rows.append({
            "variant":     variant,
            "mae_system":  _mae(sys["actual"].values, sys["predicted"].values),
            "rmse_system": _rmse(sys["actual"].values, sys["predicted"].values),
            "n_weeks":     len(sys),
        })
    return pd.DataFrame(rows).sort_values("mae_system").reset_index(drop=True)


def holdout_per_series(holdout_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-(facility × semiconductor) MAE and RMSE over the holdout window.
    Returns one row per (variant × facility × semiconductor).
    """
    records = []
    for (variant, fac, semi), grp in holdout_df.groupby(
        ["variant", "facility_id", "semiconductor_id"]
    ):
        grp = grp.dropna(subset=["actual"])
        if grp.empty:
            continue
        a = grp["actual"].values
        p = grp["predicted"].values
        records.append({
            "variant":          variant,
            "facility_id":      str(fac),
            "semiconductor_id": str(semi),
            "mae":              _mae(a, p),
            "rmse":             _rmse(a, p),
            "n":                len(a),
        })
    return pd.DataFrame(records)


def print_holdout_summary(holdout_df: pd.DataFrame) -> None:
    """Print aggregate and per-series summaries for all variants."""
    agg = holdout_aggregate(holdout_df)
    print("\n  Holdout — System-Level Aggregate (all 48 series summed per week):")
    print(agg.round(1).to_string(index=False))

    per_series = holdout_per_series(holdout_df)
    for variant, grp in per_series.groupby("variant"):
        maes = grp["mae"]
        print(f"\n  Holdout — Per-Series MAE ({variant}):")
        print(f"    Mean   : {maes.mean():.1f}")
        print(f"    Median : {maes.median():.1f}")
        worst = grp.nlargest(5, "mae")[["facility_id", "semiconductor_id", "mae", "rmse"]]
        print("    Worst 5 series:")
        print(worst.round(1).to_string(index=False))


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_cv_mae_by_horizon(cv_df: pd.DataFrame) -> None:
    """CV MAE vs forecast horizon, one line per variant."""
    summary = cv_df.groupby(["variant", "horizon"])["mae"].mean().reset_index()
    palette = {"raw": _BLUE, "log": _ORANGE}

    fig, ax = plt.subplots(figsize=(10, 4))
    for variant, grp in summary.groupby("variant"):
        ax.plot(
            grp["horizon"], grp["mae"],
            marker="o", lw=2, label=variant,
            color=palette.get(variant, _GRAY),
        )
    ax.set_xlabel("Forecast Horizon (weeks ahead)")
    ax.set_ylabel("CV MAE  (original units)")
    ax.set_title("Cross-Validation MAE by Horizon — raw vs log target")
    ax.set_xticks(range(1, 13))
    ax.legend(title="Target variant")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    plt.tight_layout()
    _ensure_dir(ARTIFACTS)
    out = ARTIFACTS / "cv_mae_by_horizon.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out.name}")


def plot_system_actual_vs_predicted(
    holdout_df: pd.DataFrame, variant: str
) -> None:
    """
    System-level weekly actual vs predicted over the holdout window.
    All 48 series are summed per target week before plotting.
    """
    grp = holdout_df[holdout_df["variant"] == variant].dropna(subset=["actual"])
    if grp.empty:
        return
    sys = grp.groupby("target_week")[["actual", "predicted"]].sum().reset_index()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(sys["target_week"], sys["actual"],    color=_BLUE,   lw=2.5, label="Actual")
    ax.plot(sys["target_week"], sys["predicted"], color=_ORANGE, lw=2,   ls="--", label="Predicted")
    ax.set_xlabel("Week")
    ax.set_ylabel("Total Customer Orders (all series)")
    ax.set_title(f"System-Level Demand — Actual vs Predicted  [{variant}]")
    ax.legend()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xticks(sys["target_week"])
    plt.tight_layout()
    _ensure_dir(ARTIFACTS)
    out = ARTIFACTS / f"system_actual_vs_predicted_{variant}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out.name}")


def plot_series_sample(
    holdout_df: pd.DataFrame,
    df_full: pd.DataFrame,
    variant: str,
    n_series: int = 6,
) -> None:
    """
    Per-series actual vs predicted over the holdout window, with 24 weeks
    of historical context.  Selects n_series spanning low → high MAE.
    """
    ps = holdout_per_series(holdout_df[holdout_df["variant"] == variant])
    ps = ps[ps["variant"] == variant].sort_values("mae").reset_index(drop=True)
    n  = min(n_series, len(ps))
    idx = np.linspace(0, len(ps) - 1, n, dtype=int)
    sample = ps.iloc[idx]

    fig, axes = plt.subplots(n, 1, figsize=(12, 3.2 * n), sharex=False)
    if n == 1:
        axes = [axes]

    for ax, (_, row) in zip(axes, sample.iterrows()):
        fac  = str(row["facility_id"])
        semi = str(row["semiconductor_id"])

        # Historical context (last 24 training weeks)
        hist = (
            df_full[(df_full["facility_id"] == fac) & (df_full["semiconductor_id"] == semi)]
            .sort_values("week")
        )
        hist_tail = hist[hist["week"] >= hist["week"].max() - 23]

        # Holdout predictions
        ho = (
            holdout_df[
                (holdout_df["variant"] == variant)
                & (holdout_df["facility_id"].astype(str) == fac)
                & (holdout_df["semiconductor_id"].astype(str) == semi)
            ]
            .sort_values("target_week")
            .dropna(subset=["actual"])
        )

        ax.plot(hist_tail["week"], hist_tail["customer_orders"],
                color=_BLUE, lw=1.5, alpha=0.8, label="Historical")
        ax.plot(ho["target_week"], ho["actual"],
                color=_BLUE, lw=1.5, alpha=0.5)
        ax.plot(ho["target_week"], ho["predicted"],
                color=_ORANGE, lw=2, ls="--", marker="o", ms=4, label="Predicted")
        ax.axvline(132.5, color=_GRAY, ls=":", lw=1.2, label="Holdout start")
        ax.set_title(f"{fac} × {semi}   MAE = {row['mae']:.0f}")
        ax.legend(fontsize=7, loc="upper left")
        ax.set_ylabel("Orders")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    plt.suptitle(f"Per-Series Holdout Forecast — {variant}", fontsize=12, y=1.01)
    plt.tight_layout()
    _ensure_dir(ARTIFACTS)
    out = ARTIFACTS / f"series_holdout_{variant}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out.name}")


def plot_residuals(holdout_df: pd.DataFrame, variant: str) -> None:
    """Residual histogram and residuals-vs-predicted scatter."""
    grp      = holdout_df[holdout_df["variant"] == variant].dropna(subset=["actual"])
    residuals = grp["actual"].values - grp["predicted"].values

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Histogram
    axes[0].hist(residuals, bins=40, color=_BLUE, edgecolor="white", alpha=0.85)
    axes[0].axvline(0, color="red", lw=1.5, ls="--")
    axes[0].set_title("Residual Distribution")
    axes[0].set_xlabel("Actual − Predicted")
    axes[0].set_ylabel("Count")
    axes[0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    # Scatter: residuals vs predicted
    axes[1].scatter(grp["predicted"], residuals, alpha=0.25, s=10, color=_BLUE)
    axes[1].axhline(0, color="red", lw=1.5, ls="--")
    axes[1].set_title("Residuals vs Predicted")
    axes[1].set_xlabel("Predicted")
    axes[1].set_ylabel("Residual")
    axes[1].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    plt.suptitle(f"Residual Analysis — {variant}", fontsize=12)
    plt.tight_layout()
    _ensure_dir(ARTIFACTS)
    out = ARTIFACTS / f"residuals_{variant}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out.name}")


def plot_feature_importance(
    models: dict, feature_cols: list, horizon: int
) -> None:
    """Horizontal bar chart of HistGBT feature importances for a given horizon."""
    m = models.get(horizon)
    if m is None:
        print(f"  No model for horizon {horizon}")
        return

    imp = pd.Series(m.feature_importances_, index=feature_cols).sort_values()
    median_imp = imp.median()
    colors = [_BLUE if v >= median_imp else _LBLUE for v in imp]

    fig, ax = plt.subplots(figsize=(8, 6))
    imp.plot(kind="barh", ax=ax, color=colors, edgecolor="white")
    ax.set_title(f"Feature Importance — Horizon h = {horizon}")
    ax.set_xlabel("Importance Score")
    plt.tight_layout()
    _ensure_dir(ARTIFACTS)
    out = ARTIFACTS / f"feature_importance_h{horizon}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved: {out.name}")


def plot_forward_forecasts(
    forecast_df: pd.DataFrame,
    df_full: pd.DataFrame,
    n_series: int = 6,
) -> None:
    """
    12-week forward forecast plot (weeks 146–157) for the n most volatile
    series, with 24 weeks of historical context shown for continuity.
    """
    # Select most volatile series so the procurement signal is visible
    vol = (
        df_full.groupby(["facility_id", "semiconductor_id"])["customer_orders"]
        .std()
        .nlargest(n_series)
        .reset_index()
    )

    fig, axes = plt.subplots(n_series, 1, figsize=(12, 3.2 * n_series), sharex=False)
    if n_series == 1:
        axes = [axes]

    for ax, (_, row) in zip(axes, vol.iterrows()):
        fac  = str(row["facility_id"])
        semi = str(row["semiconductor_id"])

        hist = (
            df_full[(df_full["facility_id"] == fac) & (df_full["semiconductor_id"] == semi)]
            .sort_values("week")
            .tail(24)
        )
        fc = (
            forecast_df[(forecast_df["facility_id"] == fac) & (forecast_df["semiconductor_id"] == semi)]
            .sort_values("target_week")
        )

        ax.plot(hist["week"], hist["customer_orders"],
                color=_BLUE, lw=1.5, label="Historical (last 24 wks)")
        ax.plot(fc["target_week"], fc["predicted"],
                color=_ORANGE, lw=2, ls="--", marker="o", ms=4, label="Forecast")
        ax.axvline(145.5, color=_GRAY, ls=":", lw=1.2, label="Forecast origin")
        ax.set_title(f"{fac} × {semi}")
        ax.legend(fontsize=7, loc="upper left")
        ax.set_ylabel("Predicted Orders")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    plt.suptitle("12-Week Forward Demand Forecast  (Weeks 146–157)", fontsize=12, y=1.01)
    plt.tight_layout()
    _ensure_dir(ARTIFACTS)
    out = ARTIFACTS / "forward_forecasts.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out.name}")
