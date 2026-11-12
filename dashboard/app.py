"""Institutional finance dashboard (Computer Science fund).
Run from the project folder:   streamlit run dashboard/app.py
Reads data/finance_tracker.db, which the notebook builds.
"""
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("FUND_TRACKER_DB") or ROOT / "data" / "finance_tracker.db")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ROLLUPS = ["Salaries", "Fringe", "Travel", "Supplies/Vendor", "Other"]

st.set_page_config(page_title="CS Fund Tracker", layout="wide")


@st.cache_data
def load(table):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        return pd.read_sql(f"SELECT * FROM {table}", conn)


def money(v):
    return f"${v:,.0f}"


def dollars_axis(ax, millions=False):
    if millions:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v/1e6:.1f}M"))
    else:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v/1e3:,.0f}K"))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def update_data_ui():
    """Upload a new Banner export, check it, and rebuild the database."""
    st.subheader("Update data")
    st.write("Upload a new Banner export (.xls). The file is checked first, the current database is backed up, "
             "and then the history, the 12-month projections, the model comparison and the alerts are rebuilt. This takes about a minute.")

    done = st.session_state.get("last_build")
    if done:
        st.success(f"Dashboard updated: {done['rows']:,} transactions, {done['first']:%b %Y} to {done['last']:%b %Y}. "
                   f"Projected expended for the next 12 months: ${done['total']:,.0f}. "
                   + (f"The previous database was saved in data/backups." if done["backup"] else ""))
        if done.get("skipped"):
            st.warning("Some forecasting models could not run on this computer and were left out: " + ", ".join(done["skipped"]) + ".")

    up = st.file_uploader("Banner transactions export", type=["xls", "html", "htm"], key=f"export_upload_{st.session_state.get('upload_n', 0)}",
                          help="The same kind of file as Transactions-2020-2027.xls")
    if up is None:
        st.caption("Nothing is changed until you press the rebuild button below.")
        return
    try:
        import build_database as bd
    except Exception as e:                                           # e.g. a missing package
        st.error(f"The rebuild code could not be loaded: {e}")
        return

    sig = (up.name, up.size)
    if st.session_state.get("upload_sig") != sig:
        upload_dir = ROOT / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        saved = upload_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{Path(up.name).name}"
        saved.write_bytes(up.getbuffer())
        with st.spinner("Checking the file ..."):
            try:
                _, info = bd.inspect_export(saved)
                err = None
            except ValueError as e:
                info, err = None, str(e)
        st.session_state.update(upload_sig=sig, upload_path=str(saved), upload_info=info, upload_err=err)
        st.session_state.pop("last_build", None)

    info, err = st.session_state["upload_info"], st.session_state["upload_err"]
    if err:
        st.error(err)
        return

    cur = bd.current_db_info()
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows in this file", f"{info['rows']:,}", f"{info['rows'] - cur['rows']:+,} vs current" if cur else None, delta_color="off")
    c2.metric("First transaction", f"{info['first']:%b %d, %Y}")
    c3.metric("Last transaction", f"{info['last']:%b %d, %Y}")
    if cur:
        st.caption(f"Dashboard now: {cur['rows']:,} rows, {cur['first']:%b %d, %Y} to {cur['last']:%b %d, %Y}.")

    shorter = bool(cur) and (info["first"] > cur["first"] or info["rows"] < cur["rows"])
    if shorter:
        st.warning("This file has less history than the data now in the dashboard (it starts later or has fewer rows). "
                   "Rebuilding replaces the old data, so earlier months would be lost from the dashboard. "
                   "A backup of the current database is kept.")
    if info["unmapped"]:
        st.warning(f"{len(info['unmapped'])} account(s) are not in config.py and will show as 'Uncategorized': "
                   + ", ".join(info["unmapped"][:12]) + (" ..." if len(info["unmapped"]) > 12 else ""))

    ok = st.checkbox("I understand the old data will be replaced", key="confirm_replace") if shorter else True
    if st.button("Rebuild the dashboard with this file", type="primary", disabled=not ok):
        with st.status("Rebuilding ...", expanded=True) as status:
            try:
                result = bd.build(st.session_state["upload_path"], log=st.write)
            except Exception as e:
                status.update(label="The rebuild failed. The dashboard still shows the previous data.", state="error")
                st.error(f"{type(e).__name__}: {e}")
                return
            status.update(label="Done", state="complete")
        st.cache_data.clear()
        st.session_state["last_build"] = {"rows": result["info"]["rows"], "first": result["info"]["first"], "last": result["info"]["last"],
                                           "total": result["projected_total"], "backup": result["backup"],
                                           "skipped": list(result.get("skipped_models", {}))}
        st.session_state.pop("upload_sig", None)
        st.session_state["upload_n"] = st.session_state.get("upload_n", 0) + 1      # empties the uploader after a successful rebuild
        st.rerun()


if not DB_PATH.exists():
    st.title("Computer Science Fund Tracker")
    st.info("There is no data yet. Upload a Banner export below to build the dashboard.")
    update_data_ui()
    st.stop()

snap = load("monthly_snapshot")
proj = load("monthly_projection")
alerts = load("alerts")
tx = load("transactions")
snap["month"] = pd.PeriodIndex(snap["month"], freq="M").to_timestamp()
proj["month"] = pd.PeriodIndex(proj["month"], freq="M").to_timestamp()

st.markdown("<style>h1 {font-size: 2.3rem !important;}</style>", unsafe_allow_html=True)   # title one step smaller
st.title("Computer Science Fund Tracker")
_m = proj["method"].iloc[0]                                  # e.g. "seasonal average FY2024-FY2026"
_basis = _m.replace("seasonal average ", "")
st.caption("Wright State Banner export. Fiscal year runs July to June. "
           f"Blue lines show all actual history ({snap['month'].min():%b %Y} to {snap['month'].max():%b %Y}). "
           f"Orange lines show only the next 12 months, calculated from the same months in {_basis} (the last 3 complete fiscal years).")

tab_over, tab_proj, tab_models, tab_year, tab_alerts, tab_tx, tab_update = st.tabs(
    ["Overview", "Projections", "Models", "Yearly", "Alerts", "Transactions", "Update data"])

# ---------------------------------------------------------------- Overview
with tab_over:
    last_fy = int(snap.groupby("fy")["month"].nunique().loc[lambda s: s >= 12].index.max())      # last fiscal year with all 12 months in the data
    fy_actual = snap[snap["fy"] == last_fy]["expended"].sum()
    exp_proj = proj[proj["measure"] == "expended"]
    next_total = exp_proj["projected"].sum()
    bal_proj = proj[proj["measure"] == "enc_balance"].groupby("month")["projected"].sum()
    latest_bal = snap[snap["month"] == snap["month"].max()]["enc_balance"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Expended FY{last_fy} (actual)", money(fy_actual))
    c2.metric("Expended next 12 months (projected)", money(next_total),
              f"{next_total / fy_actual - 1:+.1%} vs FY{last_fy}")
    c3.metric("Encumbered balance (latest month)", money(latest_bal))
    c4.metric("Projected balance peak", money(bal_proj.max()), bal_proj.idxmax().strftime("%b %Y"), delta_color="off")

    choice = st.selectbox("Category", ["All"] + ROLLUPS, key="ov_cat")
    s = snap if choice == "All" else snap[snap["rollup"] == choice]
    p = proj if choice == "All" else proj[proj["rollup"] == choice]

    left, right = st.columns(2)
    with left:
        st.subheader("Expended per month: history and next 12 months")
        a = s.groupby("month")["expended"].sum()
        f = p[p["measure"] == "expended"].groupby("month")["projected"].sum()
        fig, ax = plt.subplots(figsize=(6.5, 3.6))
        ax.plot(a.index, a.values, color="#2a78d6", label="Actual")
        ax.plot(f.index, f.values, color="#eb6834", linestyle="--", marker="o", ms=3, label="Projected")
        dollars_axis(ax); ax.legend(frameon=False)
        st.pyplot(fig, clear_figure=True)
    with right:
        st.subheader("Encumbered balance: history and next 12 months")
        a = s.groupby("month")["enc_balance"].sum()
        f = p[p["measure"] == "enc_balance"].groupby("month")["projected"].sum()
        fig, ax = plt.subplots(figsize=(6.5, 3.6))
        ax.plot(a.index, a.values, color="#2a78d6", label="Actual")
        ax.plot(f.index, f.values, color="#eb6834", linestyle="--", marker="o", ms=3, label="Projected")
        dollars_axis(ax, millions=True); ax.legend(frameon=False)
        st.pyplot(fig, clear_figure=True)

# ------------------------------------------------------------- Projections
with tab_proj:
    st.subheader("Next 12 months by category")
    e = exp_proj.groupby("rollup")[["projected", "low", "high"]].sum().reindex(ROLLUPS).dropna()
    last_actual = snap[snap["fy"] == last_fy].groupby("rollup")["expended"].sum().reindex(e.index)
    table = pd.DataFrame({
        f"FY{last_fy} actual": last_actual,
        "Projected": e["projected"],
        "Low (lowest past year)": e["low"],
        "High (highest past year)": e["high"],
    })
    table.loc["TOTAL"] = table.sum()
    # the total band uses one scenario per past fiscal year (same as the notebook), not a sum of per-category extremes
    m = proj["method"].iloc[0]                       # e.g. "seasonal average FY2024-FY2026"
    y0, y1 = int(m.split("FY")[1].split("-")[0]), int(m.split("FY")[2])
    fms = [(d.month - 7) % 12 + 1 for d in exp_proj["month"].drop_duplicates()]
    scen = [snap[(snap["fy"] == y) & (snap["fm"].isin(fms))]["expended"].sum() for y in range(y0, y1 + 1)]
    table.loc["TOTAL", "Low (lowest past year)"] = min(scen)
    table.loc["TOTAL", "High (highest past year)"] = max(scen)
    st.dataframe(table.style.format("${:,.0f}"), width="stretch")
    st.caption("Low and high are the smallest and largest totals seen in the last 3 fiscal years. For the total row they come from whole past years. "
               "They show how much past years varied. They are not a confidence interval. "
               "Travel and Supplies/Vendor are small, so their projections are rough.")

    st.subheader("Monthly projection")
    cat = st.selectbox("Category", ROLLUPS[:4], key="pj_cat")
    meas = st.radio("Measure", ["expended", "enc_balance"], horizontal=True,
                    format_func=lambda m: "Expended per month" if m == "expended" else "Encumbered balance")
    pj = proj[(proj["rollup"] == cat) & (proj["measure"] == meas)].sort_values("month")
    hist = snap[snap["rollup"] == cat].set_index("month")[meas].iloc[-24:]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.plot(hist.index, hist.values, color="#2a78d6", label="Actual (last 24 months)")
    ax.fill_between(pj["month"], pj["low"], pj["high"], color="#eb6834", alpha=0.15, label="Low to high of past years")
    ax.plot(pj["month"], pj["projected"], color="#eb6834", linestyle="--", marker="o", ms=3, label="Projected")
    dollars_axis(ax, millions=(meas == "enc_balance" and cat in ("Salaries", "Fringe")))
    ax.legend(frameon=False)
    st.pyplot(fig, clear_figure=True)
    st.dataframe(pj[["month", "projected", "low", "high"]].assign(month=pj["month"].dt.strftime("%Y-%m"))
                 .style.format({"projected": "${:,.0f}", "low": "${:,.0f}", "high": "${:,.0f}"}),
                 width="stretch", hide_index=True)

# ------------------------------------------------------------------ Models
MODEL_CATS = ["Salaries", "Fringe", "Travel", "Supplies/Vendor", "Other"]
DASH_MODEL = "Seasonal average (dashboard)"
MODEL_COLORS = {
    DASH_MODEL: "#e8710a", "Seasonal naive": "#8d6e63", "SARIMA": "#1b9e77", "Holt-Winters": "#7570b3",
    "Theta": "#e7298a", "Prophet": "#66a61e", "Linear regression": "#17becf", "Ridge": "#0b5394",
    "Random forest": "#a6761d", "Gradient boosting": "#d95f02", "KNN": "#666666", "Neural network (MLP)": "#b30000",
}
with tab_models:
    st.subheader("Model comparison, every category")
    st.caption("Every model forecasts monthly expended dollars (payments actually made). Salaries and Fringe are fitted on a log scale, "
               "Travel and Supplies/Vendor on raw values. Forecasts are never below zero. 'Other' has only two months with payments in six years, so its forecasts are not meaningful and are shown only for completeness.")
    m_scores = load("model_scores")
    m_back = load("model_backtest")
    m_fut = load("model_future")
    all_models = [m for m in MODEL_COLORS if m in set(m_scores["model"])]
    view = st.radio("What to plot", ["Next 12 months", "Last 12 months test (forecast vs what really happened)"], horizontal=True)
    missing_models = [m for m in MODEL_COLORS if m not in all_models]
    if missing_models:
        st.warning("These models did not run on this computer and are not shown: " + ", ".join(missing_models) + ". "
                   "Usually a security policy blocked a Python package they need, or the package is not installed. The other models are shown.")
    chosen = st.multiselect("Models", all_models,
                            default=[m for m in [DASH_MODEL, "Seasonal naive", "SARIMA", "Holt-Winters", "Theta", "Prophet"] if m in all_models])
    is_future = view.startswith("Next")
    src = m_fut if is_future else m_back

    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color="#1f77b4", lw=2, label="Actual")] + [
        Line2D([], [], color=MODEL_COLORS[m], lw=2.4 if m == DASH_MODEL else 1.3, ls="-" if m == DASH_MODEL else "--", label=m) for m in chosen]
    lfig, lax = plt.subplots(figsize=(13, 0.5 + 0.25 * (len(handles) // 6)))
    lax.axis("off")
    lax.legend(handles=handles, loc="center", ncol=6, frameon=False, fontsize=9)
    st.pyplot(lfig)
    plt.close(lfig)

    cols = st.columns(2)
    for i, cat in enumerate(MODEL_CATS):
        hist = snap[snap["rollup"] == cat].set_index("month")["expended"]
        fig, ax = plt.subplots(figsize=(6.4, 3.6))
        if is_future:
            ax.plot(hist.index[-36:], hist.values[-36:], color="#1f77b4", lw=2, label="Actual")
        else:
            ax.plot(hist.index[-24:], hist.values[-24:], color="#1f77b4", lw=2, label="Actual")
        for mname in chosen:
            d = src[(src["category"] == cat) & (src["model"] == mname)].copy()
            if d.empty:
                continue
            d["month"] = pd.PeriodIndex(d["month"], freq="M").to_timestamp()
            ax.plot(d["month"], d["predicted"], color=MODEL_COLORS[mname], lw=2.4 if mname == DASH_MODEL else 1.3,
                    ls="-" if mname == DASH_MODEL else "--", label=mname)
        if is_future:
            ax.axvline(hist.index[-1], color="grey", lw=0.8, ls=":")
        ax.set_title(cat, fontsize=11, loc="left")
        ax.set_ylim(bottom=0)
        dollars_axis(ax)
        if ax.get_ylim()[1] < 10000:                       # small categories: show whole dollars, not rounded thousands
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.tick_params(axis="x", labelsize=8)
        cols[i % 2].pyplot(fig)
        plt.close(fig)

    st.markdown("#### How far off was each model on the last 12 months?")
    _bm = pd.PeriodIndex(m_back["month"], freq="M")
    st.caption(f"Each model was trained on data up to {(_bm.min() - 1).to_timestamp():%b %Y}, then asked to forecast {_bm.min().to_timestamp():%b %Y} to {_bm.max().to_timestamp():%b %Y}. "
               "Numbers are the average miss per month "
               "(MAE, in dollars); lower is better and the best model in each column is highlighted. "
               "In Travel nearly every month is zero, so a model that predicts zero everywhere looks best without being useful.")
    tbl = m_scores.pivot(index="model", columns="category", values="mae").reindex(columns=MODEL_CATS).reindex(all_models)
    st.dataframe(tbl.style.format("${:,.0f}").highlight_min(axis=0, color="#cfe8cf"), width="stretch")

    st.markdown("#### What each model says the next 12 months will total")
    ftbl = m_fut.groupby(["model", "category"])["predicted"].sum().unstack("category").reindex(columns=MODEL_CATS).reindex(all_models)
    ftbl["TOTAL"] = ftbl.sum(axis=1)
    st.dataframe(ftbl.style.format("${:,.0f}"), width="stretch")
    st.caption("The dashboard model is the one used on the Projections and Yearly tabs. "
               "Models that cannot see the yearly payroll pattern (for example the neural network) can be far from the others.")

# ------------------------------------------------------------------ Yearly
with tab_year:
    st.subheader("Expended per fiscal year (July to June)")
    cats4 = ["Salaries", "Fringe", "Travel", "Supplies/Vendor"]
    colors = {"Salaries": "#2a78d6", "Fringe": "#7fb2ea", "Travel": "#eb6834", "Supplies/Vendor": "#898781"}

    # actual years from the monthly table
    actual = snap.groupby(["fy", "rollup"])["expended"].sum().unstack(fill_value=0).reindex(columns=cats4, fill_value=0)
    next_fy = last_fy + 1
    # next fiscal year = months already in the data + projected months that fall inside it (Sep 2026 to Jun 2027)
    p_ex = exp_proj.assign(fy=exp_proj["month"].apply(lambda d: d.year + (1 if d.month >= 7 else 0)))
    p_next = p_ex[p_ex["fy"] == next_fy].groupby("rollup")["projected"].sum().reindex(cats4, fill_value=0)
    done = actual.loc[next_fy] if next_fy in actual.index else pd.Series(0.0, index=cats4)
    proj_row = p_next + done
    years = actual.loc[actual.index <= last_fy].copy()
    years.loc[next_fy] = proj_row
    years["Total"] = years.sum(axis=1)

    # low / high for the projected year: whole past years, same months (same method as the Projections tab)
    m = proj["method"].iloc[0]
    y0, y1 = int(m.split("FY")[1].split("-")[0]), int(m.split("FY")[2])
    fms_next = sorted({(d.month - 7) % 12 + 1 for d in p_ex[p_ex["fy"] == next_fy]["month"]})
    month_done = snap[snap["fy"] == next_fy]["fm"].unique()
    scen = [snap[(snap["fy"] == y) & (snap["fm"].isin(fms_next))]["expended"].sum() + done.sum() for y in range(y0, y1 + 1)]
    lo, hi = min(scen), max(scen)

    fig, ax = plt.subplots(figsize=(10, 4.2))
    labels = [f"FY{y}" if y <= last_fy else f"FY{y}\n(projected)" for y in years.index]
    bottom = pd.Series(0.0, index=years.index)
    for c in cats4:
        vals = years[c]
        bars = ax.bar(labels, vals, bottom=bottom, color=colors[c], label=c, width=0.62)
        bars[-1].set_alpha(0.55); bars[-1].set_hatch("//"); bars[-1].set_edgecolor("white")
        bottom += vals
    for i, tot in enumerate(years["Total"]):
        top = max(tot, hi) if i == len(years) - 1 else tot        # keep the label above the whisker
        ax.text(i, top + 80_000, f"${tot/1e6:.2f}M", ha="center", fontsize=9)
    ax.errorbar([len(years) - 1], [years["Total"].iloc[-1]], yerr=[[years["Total"].iloc[-1] - lo], [hi - years["Total"].iloc[-1]]],
                color="#0b0b0b", capsize=5, lw=1.2, label="Low to high of past years")
    dollars_axis(ax, millions=True)
    ax.set_ylim(0, max(years["Total"].max(), hi) * 1.15)
    ax.legend(frameon=False, ncol=3, fontsize=8, loc="upper left")
    st.pyplot(fig, clear_figure=True)

    tbl = years.copy()
    tbl["Change vs prior year"] = tbl["Total"].pct_change().map(lambda v: "" if pd.isna(v) else f"{v:+.1%}")
    tbl.index = [f"FY{y}" if y <= last_fy else f"FY{y} (projected)" for y in tbl.index]
    st.dataframe(tbl.style.format({c: "${:,.0f}" for c in cats4 + ["Total"]}),
                 width="stretch")
    st.caption(f"FY{next_fy} (Jul {next_fy - 1} to Jun {next_fy}) projected total is ${years['Total'].iloc[-1]:,.0f}, with a range of ${lo:,.0f} to ${hi:,.0f} "
               f"from the last 3 fiscal years. The Projections tab covers the next 12 months ({proj['month'].min():%b %Y} to {proj['month'].max():%b %Y}), "
               "so its total can differ by a few hundred dollars. "
               f"FY{years.index.min()} starts at the beginning of the export ({snap['month'].min():%b %Y}). "
               "Expended = payroll payments plus paid invoices. The projection is a seasonal average, not a statistical interval.")

# ------------------------------------------------------------------ Alerts
with tab_alerts:
    st.subheader("Alerts")
    sev = st.multiselect("Severity", ["high", "medium", "info"], default=["high", "medium", "info"])
    a = alerts[alerts["severity"].isin(sev)].copy()
    order = {"high": 0, "medium": 1, "info": 2}
    a = a.sort_values("severity", key=lambda s: s.map(order))
    st.write(f"{len(a)} alerts")
    # st.dataframe shows text as-is, so the dollar signs are safe here
    st.dataframe(a[["severity", "alert_type", "related_category", "description"]],
                 width="stretch", hide_index=True)
    st.caption("Most 'unusual month' alerts are payroll timing: a payment posted a month earlier or later than in past years.")

# ------------------------------------------------------------ Transactions
with tab_tx:
    st.subheader("Search transactions")
    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("Search description")
    cats = c2.multiselect("Category", sorted(tx["category"].unique()))
    rules = c3.multiselect("Rule code", sorted(tx["rule"].unique()))
    t = tx
    if q:
        t = t[t["description"].str.contains(q, case=False, na=False)]
    if cats:
        t = t[t["category"].isin(cats)]
    if rules:
        t = t[t["rule"].isin(rules)]
    st.write(f"{len(t):,} of {len(tx):,} rows")
    st.dataframe(t[["date", "description", "category", "type", "rule", "account", "amount", "expended"]],
                 width="stretch", hide_index=True)
    st.download_button("Download these rows (CSV)", t.to_csv(index=False), "transactions_filtered.csv", "text/csv")

# ------------------------------------------------------------- Update data
with tab_update:
    update_data_ui()
    st.divider()
    st.subheader("Download the current forecast")
    dl = proj[proj["measure"] == "expended"][["month", "rollup", "projected", "low", "high"]].copy()
    dl["month"] = dl["month"].dt.strftime("%Y-%m")
    dl.columns = ["month", "category", "projected_expended", "low_past_year", "high_past_year"]
    st.download_button("Download next-12-month projection (CSV)", dl.to_csv(index=False), "projection_next_12_months.csv", "text/csv")