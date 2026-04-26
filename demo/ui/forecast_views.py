import os
import base64
import streamlit as st

from ui.common import _fig_to_b64, _format_facility_label

# Deterministic transition sentence shown immediately after kickoff confirmation.
# Appears before the forecast result so the user sees instant acknowledgement.
_KICKOFF_TRANSITION_SENTENCE = (
    "I will now generate forecasts over the upcoming planning horizon "
    "(20-week period), based on your historical demand data."
)

# Transition sentences and section headings for each assessment direction.
_FORECAST_ASSESS_META = {
    "validation": (
        "Yes — I can explain how the forecast model was trained and validated. "
        "Here is the model assessment summary.",
        "📐 Forecast Model — Validation & Training Performance",
    ),
    "features": (
        "Here is a breakdown of which features drove the forecast model most, "
        "based on permutation importance measured on the held-out validation set.",
        "📐 Forecast Model — Feature Importance",
    ),
    "baseline": (
        "Here is how the production forecast compares with the baseline approaches "
        "used for validation.",
        "📐 Forecast Model — Baseline Comparison",
    ),
}

# Project root — two levels up from demo/ui/. Used to resolve artifact PNG paths.
_ARTIFACTS_BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Path to the historical demand CSV (relative to this file).
_CSV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "cleaned_data", "finished_goods_demand_table.csv")
)

# Fixed opening response — no variability.
_KICKOFF_OPENING_RESPONSE = """\
Understood. We will:

1. Verify your historical demand across all four facilities and semiconductor SKUs
2. Translate that demand into the exact component requirements needed to support production
3. Assess inventory coverage and identify where procurement is required
4. Optimize supplier allocation to minimize cost while controlling supplier risk and disruption

Your objective balances cost efficiency with supply reliability:

<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px; padding:0.5rem 0.9rem; margin:0.3rem 0;'><p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'><strong>Lower emphasis</strong> prioritizes cost minimization</p></div>
<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px; padding:0.5rem 0.9rem; margin:0.3rem 0;'><p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'><strong>Higher emphasis</strong> prioritizes more stable, lower-risk suppliers even if slightly more expensive</p></div>

Let's begin by validating the historical demand that drives this entire workflow.

Please review the historical demand file below and confirm it looks correct. Once reviewed, \
reply with **'Yes, proceed'** to continue.\
"""


def _render_csv_button() -> None:
    """Compact summary line + download button for historical demand CSV.

    Shows dataset shape and key dimensions without rendering the full table inline.
    """
    try:
        import pandas as pd
        df = pd.read_csv(_CSV_PATH)
        n_rows, n_cols = df.shape
        facilities = df["facility_id"].nunique() if "facility_id" in df.columns else "?"
        skus       = df["semiconductor_id"].nunique() if "semiconductor_id" in df.columns else "?"
        weeks      = df["week"].nunique() if "week" in df.columns else "?"
        st.caption(
            f"Historical demand file: **{n_rows:,} rows** · **{n_cols} columns** · "
            f"**{facilities} facilities** · **{skus} SKUs** · **{weeks} weeks**"
        )
        st.download_button(
            label="📥 Download Historical Demand CSV",
            data=df.to_csv(index=False).encode(),
            file_name="finished_goods_demand_table.csv",
            mime="text/csv",
            key="kickoff_csv_download",
        )
    except Exception:
        st.caption("Historical demand file: `cleaned_data/finished_goods_demand_table.csv`")


def _render_kickoff_response() -> None:
    """Render the deterministic opening assistant message and CSV button (first turn only)."""
    from ui.theme import CPU_AVATAR
    with st.chat_message("assistant", avatar=CPU_AVATAR):
        st.markdown(_KICKOFF_OPENING_RESPONSE, unsafe_allow_html=True)
        _render_csv_button()
    st.session_state.messages.append({
        "role": "assistant",
        "content": _KICKOFF_OPENING_RESPONSE,
        "has_trace": False,
        "summary": "",
    })


def _render_demand_verification_banner() -> None:
    """Persistent info banner + CSV button shown on every rerender while verification is pending."""
    st.info(
        "Waiting for your confirmation on the historical demand data. "
        "Reply **'Yes, proceed'** when ready to begin the analysis pipeline.",
        icon="📋",
    )
    _render_csv_button()
    st.divider()


def _plot_facility_faceted(df, facility_id: str):
    """6×2 faceted figure — one subplot per semiconductor SKU for a single facility.

    Each panel shows the 20-week predicted demand line with a lightly shaded 90% CI.
    SKUs are sorted alphabetically so the layout is deterministic across facilities.
    """
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import pandas as pd

    fac_df = df[df["facility_id"] == facility_id].copy()
    # Coerce numeric columns — psycopg2 returns Decimal, pandas stores as object.
    for col in ("predicted_demand", "interval_lower_90", "interval_upper_90"):
        fac_df[col] = pd.to_numeric(fac_df[col], errors="coerce").fillna(0.0)
    fac_df["target_week_date"] = fac_df["target_week_date"].astype(str)
    skus = sorted(fac_df["semiconductor_id"].unique())
    n_skus = len(skus)
    ncols = 2
    nrows = (n_skus + 1) // 2  # ceil division — handles odd counts cleanly
    palette = [cm.tab10(i / 10) for i in range(min(n_skus, 10))]

    fig, axes = plt.subplots(nrows, ncols, figsize=(12, nrows * 3), sharey=False)
    axes = axes.flatten()

    for i, sku in enumerate(skus):
        ax = axes[i]
        s = fac_df[fac_df["semiconductor_id"] == sku].sort_values("target_week_date")
        color = palette[i % len(palette)]
        ax.plot(s["target_week_date"], s["predicted_demand"],
                color=color, linewidth=1.8)
        ax.fill_between(
            s["target_week_date"],
            s["interval_lower_90"], s["interval_upper_90"],
            alpha=0.12, color=color,
        )
        ax.set_title(sku, fontsize=9, pad=4)
        ax.tick_params(axis="x", rotation=45, labelsize=6)
        ax.tick_params(axis="y", labelsize=7)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

    # Hide any unused subplot panels (if SKU count is odd)
    for j in range(n_skus, len(axes)):
        axes[j].set_visible(False)

    label = _format_facility_label(facility_id)
    fig.suptitle(
        f"Production Demand Forecast — {label} by SKU",
        fontsize=12, y=1.005,
    )
    fig.tight_layout()
    return fig


def _narrative_facility_bullets(df, facility_id: str) -> str:
    """Styled HTML bullet summary for a single-facility faceted forecast view.

    Covers: total/avg demand, peak + lowest week, SKU concentration, and a
    cross-SKU comparative insight (highest-volume SKUs + most/least volatile).
    Returned string is passed directly to st.markdown(unsafe_allow_html=True).
    """
    import pandas as pd
    fac_df = df[df["facility_id"] == facility_id].copy()
    # Coerce to numeric — psycopg2 returns Decimal, which groupby().sum() keeps as
    # object dtype, causing nlargest() / arithmetic to fail.
    fac_df["predicted_demand"] = pd.to_numeric(fac_df["predicted_demand"], errors="coerce").fillna(0.0)
    weekly = fac_df.groupby("target_week_date")["predicted_demand"].sum()
    total     = weekly.sum()
    avg       = weekly.mean()
    n_weeks   = weekly.nunique()
    peak_week = str(weekly.idxmax())
    peak_val  = weekly.max()
    low_week  = str(weekly.idxmin())
    low_val   = weekly.min()

    by_sku = fac_df.groupby("semiconductor_id")["predicted_demand"].sum()
    top_sku   = by_sku.idxmax()
    top_share = by_sku.max() / by_sku.sum() * 100
    n_skus    = len(by_sku)

    if top_share > 40:
        concentration = (
            f"Demand is concentrated — **{top_sku}** accounts for "
            f"**{top_share:.0f}%** of facility volume"
        )
    else:
        concentration = (
            f"Demand is broadly distributed across {n_skus} SKUs "
            f"(top SKU: **{top_sku}** at **{top_share:.0f}%**)"
        )

    # Top 3 by total volume and SKU-level coefficient of variation (volatility proxy)
    top3 = by_sku.nlargest(3).index.tolist()
    top3_str = ", ".join(f"**{s}**" for s in top3)
    sku_cv = (
        fac_df.groupby("semiconductor_id")["predicted_demand"]
        .apply(lambda x: x.std() / x.mean() if x.mean() > 0 else 0.0)
    )
    most_volatile  = sku_cv.idxmax()
    least_volatile = sku_cv.idxmin()
    cross_sku = (
        f"{top3_str} lead in total volume; "
        f"**{most_volatile}** shows the highest week-to-week variability "
        f"while **{least_volatile}** is the most stable"
    )

    _div_style = (
        "background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
        "padding:0.5rem 0.9rem; margin:0.3rem 0;"
    )
    _p_style = (
        "font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;"
    )

    def _bullet(label: str, value: str) -> str:
        return (
            f"<div style='{_div_style}'>"
            f"<p style='{_p_style}'>"
            f"<strong>{label}:</strong> {value}</p></div>"
        )

    return "".join([
        _bullet("Total horizon demand", f"{total:,.0f} units across {n_weeks} weeks"),
        _bullet("Average weekly demand", f"{avg:,.0f} units/week"),
        _bullet("Peak week", f"{peak_week} → {peak_val:,.0f} units"),
        _bullet("Lowest week", f"{low_week} → {low_val:,.0f} units"),
        _bullet("SKU concentration", concentration),
        _bullet("Cross-SKU insight", cross_sku),
    ])


def _render_forecast_summary_structured(s: dict) -> None:
    """Render a production forecast summary dict as structured Streamlit UI.

    Consumes the dict returned by get_latest_production_forecast_summary().
    No ASCII blocks — identical data values, clean component-based layout.
    """
    import pandas as _pd_fs
    cov = s["coverage"]
    dm  = s["demand"]

    # ── Metadata row (subtle caption) ────────────────────────────────────────
    st.caption(
        f"Model: **{s['model_version']}**  ·  "
        f"Forecast run: **{s['forecast_origin_date']}**  ·  "
        f"Last observed week: **{s['observed_through_week_date']}**  ·  "
        f"Run ID: {s['forecast_run_id']}"
    )

    # ── Coverage cards ────────────────────────────────────────────────────────
    _fc1, _fc2, _fc3, _fc4 = st.columns(4)
    _fc1.metric("Facilities",             cov["facility_count"])
    _fc2.metric("SKUs",                   cov["sku_count"])
    _fc3.metric("Forecast Series",        cov["series_count"])
    _fc4.metric("Total Forecasted Demand", f"{dm['total_forecasted_demand']:,.0f} units")

    # ── Planning horizon + Demand summary ────────────────────────────────────
    _col_l, _col_r = st.columns(2)
    with _col_l:
        st.markdown("**Planning Horizon**")
        st.markdown(
            f"<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
            f"padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
            f"<strong>Start:</strong> {s['planning_horizon_start_date']}</p></div>"
            f"<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
            f"padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
            f"<strong>End:</strong> {s['planning_horizon_end_date']}</p></div>"
            f"<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
            f"padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
            f"<strong>Duration:</strong> {s['horizon_weeks']} weeks</p></div>",
            unsafe_allow_html=True,
        )
    with _col_r:
        st.markdown("**Demand Summary**")
        st.dataframe(
            _pd_fs.DataFrame([
                {"Metric": "Total Demand",       "Value": f"{dm['total_forecasted_demand']:,.0f} units"},
                {"Metric": "Avg Weekly Demand",  "Value": f"{dm['average_weekly_demand']:,.0f} units/week"},
                {"Metric": "Peak Week",          "Value": f"{dm['peak_week_date']}  →  {dm['peak_week_demand']:,.0f} units"},
                {"Metric": "Lowest Week",        "Value": f"{dm['lowest_week_date']}  →  {dm['lowest_week_demand']:,.0f} units"},
            ]),
            use_container_width=True,
            hide_index=True,
        )

    # ── Coverage details expander ─────────────────────────────────────────────
    with st.expander("View Forecast Coverage Details", expanded=False):
        if cov["grain_valid"]:
            st.success(
                f"**Grain check passed** — {cov['actual_rows']:,} rows = "
                f"{cov['series_count']} series × {cov['week_count']} weeks"
            )
        else:
            st.error(
                f"**Grain check FAILED** — expected {cov['expected_rows']:,} rows, "
                f"got {cov['actual_rows']:,}"
            )
        st.markdown(
            f"<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
            f"padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
            f"<strong>Coverage:</strong> {cov['facility_count']} facilities × "
            f"{cov['sku_count']} SKUs = <strong>{cov['series_count']} series</strong></p></div>"
            f"<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
            f"padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
            f"<strong>Weeks per series:</strong> {cov['week_count']}</p></div>"
            f"<div style='background:#0A1F17; border-left:3px solid #76b900; border-radius:2px;"
            f"padding:0.5rem 0.9rem; margin:0.3rem 0;'>"
            f"<p style='font-family:Inter,sans-serif; font-size:0.84rem; color:#ffffff; margin:0; line-height:1.55;'>"
            f"<strong>Total rows validated:</strong> {cov['actual_rows']:,}</p></div>",
            unsafe_allow_html=True,
        )


def _render_forecast_expanders(key_suffix: str = "live") -> None:
    """
    Render three collapsed expanders below the forecast summary.
    Reads pre-loaded data from st.session_state.forecast_expander_cache.
    Safe to call in replay loop (no DB queries).
    """
    cache = st.session_state.get("forecast_expander_cache", {})
    if not cache:
        return

    # ── Expander 1: Week × facility × SKU detail ──────────────────────────
    drilldown_df = cache.get("drilldown_df")
    if drilldown_df is not None:
        with st.expander("Show forecast detail  (week × facility × SKU)", expanded=False):
            import pandas as _pd_fe
            _dd = drilldown_df.copy()
            _rename_map = {
                "target_week_date":   "Week",
                "facility_id":        "Facility",
                "semiconductor_id":   "SKU",
                "predicted_demand":   "Forecast",
                "horizon_weeks":      "Horizon Wks",
            }
            _dd = _dd.rename(columns={k: v for k, v in _rename_map.items() if k in _dd.columns})
            _fac_opts = sorted(_dd["Facility"].unique().tolist()) if "Facility" in _dd.columns else []
            _sku_opts = sorted(_dd["SKU"].unique().tolist())      if "SKU"      in _dd.columns else []
            _e1c1, _e1c2 = st.columns(2)
            with _e1c1:
                _sel_fac = st.multiselect(
                    "Filter by Facility", _fac_opts, default=_fac_opts,
                    key=f"fe_fac_{key_suffix}",
                )
            with _e1c2:
                _sel_sku = st.multiselect(
                    "Filter by SKU", _sku_opts, default=_sku_opts,
                    key=f"fe_sku_{key_suffix}",
                )
            if _sel_fac and "Facility" in _dd.columns:
                _dd = _dd[_dd["Facility"].isin(_sel_fac)]
            if _sel_sku and "SKU" in _dd.columns:
                _dd = _dd[_dd["SKU"].isin(_sel_sku)]
            _drop_cols = [c for c in ("interval_lower_90", "interval_upper_90", "Lower 90%", "Upper 90%") if c in _dd.columns]
            if _drop_cols:
                _dd = _dd.drop(columns=_drop_cols)
            _fmt_fe = {c: "{:,.0f}" for c in ["Forecast"] if c in _dd.columns}
            st.caption(f"{len(_dd):,} rows")
            st.dataframe(
                _dd.style.format(_fmt_fe),
                use_container_width=True,
                hide_index=True,
                height=500,
            )

    # ── Expander 2: Model validation & training performance ────────────────
    val_data = cache.get("validation", {})
    if val_data:
        with st.expander("Model detail  (validation & training performance)", expanded=False):
            if val_data.get("chart_b64"):
                st.image(base64.b64decode(val_data["chart_b64"]))
            if val_data.get("content"):
                st.markdown(val_data["content"], unsafe_allow_html=True)

    # ── Expander 3: Performance versus baselines ───────────────────────────
    base_data = cache.get("baseline", {})
    if base_data:
        with st.expander("Performance versus baselines", expanded=False):
            if base_data.get("chart_b64"):
                st.image(base64.b64decode(base_data["chart_b64"]))
            if base_data.get("content"):
                st.markdown(base_data["content"], unsafe_allow_html=True)
