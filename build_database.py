"""Rebuild the whole finance tracker database from a Banner export.

Usage (from the project folder, with the venv active):
    python build_database.py                          # uses data/Transactions-2020-2027.xls
    python build_database.py data/new_export.xls      # use a different export

It reloads the transactions, rebuilds the monthly table, the 12-month projections, the model
comparison and the alerts, and writes everything to data/finance_tracker.db.
The dashboard's "Update data" tab calls build() below, so both routes give the same result.
"""
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import ACCOUNT_CATEGORY_MAP, EXPENDED_RULES, ROLLUP_ORDER, get_rollup  # noqa: E402
from parser import parse_xls  # noqa: E402
import model_runs  # noqa: E402

DB_PATH = ROOT / "data" / "finance_tracker.db"
MIN_DOLLARS = {"Salaries": 25000, "Fringe": 8000, "Travel": 500, "Supplies/Vendor": 500, "GTA/GA": 1000, "Other": 500}
SPIKE_PCT = 0.50


def load(path):
    df = parse_xls(str(path))
    df["date"] = pd.to_datetime(df["date"])
    df["rollup"] = df["category"].map(get_rollup)
    df["expended"] = np.where(df["Rule"].isin(EXPENDED_RULES), -df["amount"], 0.0)   # payments are negative, so flip the sign
    df["month"] = df["date"].dt.to_period("M")
    return df


def check_mapping(df, log=print):
    """Say clearly if the export has accounts that config.py does not know about. Returns the unknown accounts."""
    unknown = sorted(set(df.loc[df["category"] == "Uncategorized", "Account"]))
    if unknown:
        log(f"WARNING: {len(unknown)} account(s) are not in ACCOUNT_CATEGORY_MAP in config.py: {', '.join(unknown)}")
        gta = [a for a in unknown if a.startswith("773")]
        if gta:
            log(f"  {len(gta)} of them start with 773 (GTA/GA). Map them in config.py, for example:  \"{gta[0]}\": \"GTA/GA\"")
            log("  and add \"GTA/GA\": \"GTA/GA\" to CATEGORY_ROLLUP and ROLLUP_ORDER.")
    return unknown


NEEDED_COLUMNS = {"date", "description", "category", "type", "amount", "Account", "Rule", "Prog", "PredAcct", "EncNum"}
MIN_MONTHS = 30        # the projection needs at least one complete fiscal year, the models need a few more


def inspect_export(path):
    """Read an export and check it, without touching the database.
    Returns (dataframe, info dict). Raises ValueError with a plain-language message if the file is not usable."""
    try:
        df = load(path)
    except Exception as e:
        raise ValueError(f"This file could not be read as a Banner transactions export ({type(e).__name__}: {e}).") from e
    if df.empty:
        raise ValueError("The file was read but it contains no transactions.")
    missing = NEEDED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"The file is missing expected columns: {', '.join(sorted(missing))}.")
    if df["date"].isna().all():
        raise ValueError("No valid dates were found in the file.")
    months = (df["date"].max().year - df["date"].min().year) * 12 + df["date"].max().month - df["date"].min().month + 1
    if months < MIN_MONTHS:
        raise ValueError(f"The file covers only {months} months. At least {MIN_MONTHS} months of history are needed for the projections.")
    unknown = sorted(set(df.loc[df["category"] == "Uncategorized", "Account"]))
    info = {"rows": len(df), "first": df["date"].min(), "last": df["date"].max(), "months": months,
            "unmapped": unknown, "has_gta": bool(df["Account"].str.startswith("773").any()),
            "unclassified": int((df["type"] == "Unclassified").sum())}
    return df, info


def current_db_info(db_path=None):
    """Row count and date range of the database that is in place now, or None if there is none."""
    db_path = Path(db_path or DB_PATH)
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            n, lo, hi = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM transactions").fetchone()
        finally:
            conn.close()
        return {"rows": n, "first": pd.Timestamp(lo), "last": pd.Timestamp(hi), "modified": datetime.fromtimestamp(db_path.stat().st_mtime)}
    except Exception:
        return None


def build_monthly(df):
    idx = pd.period_range(df["month"].min(), df["month"].max(), freq="M")
    parts = []
    for r in ROLLUP_ORDER:
        d = df[df["rollup"] == r]
        m = pd.DataFrame(index=idx)
        m["expended"] = d.groupby("month")["expended"].sum().reindex(idx, fill_value=0.0)
        m["net_change"] = d.groupby("month")["amount"].sum().reindex(idx, fill_value=0.0)
        m["enc_balance"] = m["net_change"].cumsum()
        m["rollup"] = r
        parts.append(m.rename_axis("month").reset_index())
    monthly = pd.concat(parts, ignore_index=True)
    monthly["fy"] = monthly["month"].apply(lambda p: p.year + (1 if p.month >= 7 else 0))   # fiscal year = Jul to Jun
    monthly["fm"] = monthly["month"].apply(lambda p: (p.month - 7) % 12 + 1)                # Jul = 1 ... Jun = 12
    return idx, monthly


def build_projection(idx, monthly):
    first, last = idx[0], idx[-1]
    complete = lambda fy: pd.Period(f"{fy-1}-07", "M") >= first and pd.Period(f"{fy}-06", "M") <= last
    fys = sorted(fy for fy in monthly["fy"].unique() if complete(fy))
    train_fys = fys[-3:]
    proj_idx = pd.period_range(last + 1, periods=12, freq="M")
    rows = []
    for r in ROLLUP_ORDER:
        for measure in ["expended", "enc_balance"]:
            for p in proj_idx:
                fm = (p.month - 7) % 12 + 1
                v = monthly[(monthly["rollup"] == r) & (monthly["fy"].isin(train_fys)) & (monthly["fm"] == fm)][measure]
                rows.append((str(p), r, measure, v.mean(), v.min(), v.max()))
    projection = pd.DataFrame(rows, columns=["month", "rollup", "measure", "projected", "low", "high"])
    projection["method"] = f"seasonal average FY{train_fys[0]}-FY{train_fys[-1]}"
    return fys, train_fys, proj_idx, projection


def build_alerts(df, idx, monthly, fys, train_fys, proj_idx, projection):
    alerts = []
    alert_rollups = [r for r in ROLLUP_ORDER if r != "Other"]
    for r in alert_rollups:                                   # unusual month vs the same fiscal month in earlier years
        d = monthly[monthly["rollup"] == r]
        for p in list(idx[-12:]):
            row = d[d["month"] == p].iloc[0]
            hist = d[(d["fm"] == row["fm"]) & (d["fy"] < row["fy"]) & (d["fy"].isin(fys))]["expended"]
            if len(hist) < 3 or hist.mean() == 0:
                continue
            diff = row["expended"] - hist.mean()
            if abs(diff) >= MIN_DOLLARS.get(r, 500) and abs(diff) / hist.mean() >= SPIKE_PCT:
                sev = "high" if (abs(diff) / hist.mean() >= 1.0 and abs(diff) >= 3 * MIN_DOLLARS.get(r, 500)) else "medium"
                word = "above" if diff > 0 else "below"
                alerts.append(("Unusual month", sev,
                               f"{r}: expended ${row['expended']:,.0f} in {p}, ${abs(diff):,.0f} {word} the usual ${hist.mean():,.0f} for this month", r, str(p)))
    for r in alert_rollups:                                   # negative encumbered balance
        d = monthly[(monthly["rollup"] == r) & (monthly["enc_balance"] < -1)]
        if len(d):
            w = d.loc[d["enc_balance"].idxmin()]
            alerts.append(("Negative balance", "high",
                           f"{r}: encumbered balance below zero in {len(d)} month(s); lowest ${w['enc_balance']:,.0f} in {w['month']}", r, str(w["month"])))
    last_fy = train_fys[-1]
    for r in alert_rollups:                                   # projection vs last full fiscal year
        actual = monthly[(monthly["rollup"] == r) & (monthly["fy"] == last_fy)]["expended"].sum()
        proj = projection[(projection["rollup"] == r) & (projection["measure"] == "expended")]["projected"].sum()
        if actual > 0 and abs(proj - actual) >= MIN_DOLLARS.get(r, 500) and abs(proj / actual - 1) >= 0.15:
            alerts.append(("Projection change", "medium",
                           f"{r}: projected ${proj:,.0f} for next 12 months vs ${actual:,.0f} in FY{last_fy} ({proj/actual-1:+.0%})", r, str(proj_idx[0])))
    n_unc, n_unk = int((df["category"] == "Uncategorized").sum()), int((df["type"] == "Unclassified").sum())
    if n_unc or n_unk:
        alerts.append(("Data quality", "medium", f"{n_unc} uncategorized and {n_unk} unclassified rows", "All", ""))
    if not df["Account"].str.startswith("773").any():
        alerts.append(("Missing data", "info", "No GTA accounts (773xxx) in this export, so GTA spending cannot be shown", "GTA", ""))
    return alerts


def write_db(df, monthly, projection, alerts, model_tables, db_path=None):
    db_path = Path(db_path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        DROP TABLE IF EXISTS transactions; DROP TABLE IF EXISTS monthly_snapshot;
        DROP TABLE IF EXISTS monthly_projection; DROP TABLE IF EXISTS alerts;
        DROP TABLE IF EXISTS model_scores; DROP TABLE IF EXISTS model_backtest; DROP TABLE IF EXISTS model_future;
        CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, date_detected TEXT, alert_type TEXT,
                             severity TEXT, description TEXT, related_category TEXT);""")
    tx = df[["date", "description", "category", "rollup", "type", "amount", "expended", "Account", "Rule", "Prog", "PredAcct", "EncNum"]].copy()
    tx["date"] = tx["date"].dt.strftime("%Y-%m-%d")
    tx.columns = ["date", "description", "category", "rollup", "type", "amount", "expended", "account", "rule", "prog", "pred_acct", "enc_num"]
    tx.to_sql("transactions", conn, index=False)
    snap = monthly.copy(); snap["month"] = snap["month"].astype(str)
    snap.to_sql("monthly_snapshot", conn, index=False)
    projection.to_sql("monthly_projection", conn, index=False)
    for name, table in zip(["model_scores", "model_backtest", "model_future"], model_tables):
        table.to_sql(name, conn, index=False)
    today = date.today().isoformat()
    conn.executemany("INSERT INTO alerts (date_detected, alert_type, severity, description, related_category) VALUES (?,?,?,?,?)",
                     [(today, a[0], a[1], a[2] + (f" [{a[4]}]" if a[4] else ""), a[3]) for a in alerts])
    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["transactions", "monthly_snapshot", "monthly_projection", "alerts", "model_scores", "model_backtest", "model_future"]}
    conn.close()
    return counts


def build(path, log=print, db_path=None, keep_backups=5):
    """Rebuild the database from one export. The new database is written to a temporary file first and only
    replaces the old one when everything has worked, so a failed run never leaves a half-built database.
    The old database is copied to data/backups/ before it is replaced. Returns a summary dict."""
    db_path = Path(db_path or DB_PATH)
    path = Path(path)
    log(f"Reading {path.name} ...")
    df, info = inspect_export(path)
    log(f"  {info['rows']:,} rows, {info['first'].date()} to {info['last'].date()}")
    check_mapping(df, log)
    idx, monthly = build_monthly(df)
    fys, train_fys, proj_idx, projection = build_projection(idx, monthly)
    alerts = build_alerts(df, idx, monthly, fys, train_fys, proj_idx, projection)
    log("Running the forecasting models (about a minute) ...")
    model_tables = model_runs.run_all(monthly, projection)
    skipped = dict(model_runs.LAST_SKIPPED)
    if skipped:
        log("Some models could not run on this computer and were left out (a security policy or a missing package):")
        for name, why in skipped.items():
            log(f"  {name}: {why}")

    tmp = db_path.with_name(db_path.name + ".new")
    if tmp.exists():
        tmp.unlink()
    counts = write_db(df, monthly, projection, alerts, model_tables, db_path=tmp)

    backup = None
    if db_path.exists():
        bdir = db_path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        backup = bdir / f"{db_path.stem}_{datetime.now():%Y%m%d_%H%M%S}{db_path.suffix}"
        shutil.copy2(db_path, backup)
        for old in sorted(bdir.glob(f"{db_path.stem}_*{db_path.suffix}"))[:-keep_backups]:
            old.unlink()
    try:
        os.replace(tmp, db_path)
    except PermissionError as e:
        raise RuntimeError("The database file is open in another program. Close it and try again.") from e

    e = projection[projection["measure"] == "expended"].groupby("rollup")["projected"].sum()
    return {"counts": counts, "info": info, "backup": backup, "alerts": len(alerts), "skipped_models": skipped,
            "proj_start": str(proj_idx[0]), "proj_end": str(proj_idx[-1]), "basis": f"FY{train_fys[0]}-FY{train_fys[-1]}",
            "projected": {r: float(v) for r, v in e.items()}, "projected_total": float(e.sum())}


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "Transactions-2020-2027.xls"
    if not path.exists():
        sys.exit(f"File not found: {path}")
    try:
        r = build(path)
    except ValueError as e:
        sys.exit(f"Stopped: {e}")
    print("\nDatabase written to", DB_PATH)
    if r["backup"]:
        print("Previous database saved as", r["backup"])
    for t, n in r["counts"].items():
        print(f"  {t}: {n:,} rows")
    print(f"\nProjected expended, {r['proj_start']} to {r['proj_end']} (seasonal average {r['basis']}):")
    for name, v in r["projected"].items():
        print(f"  {name:<16} ${v:>12,.0f}")
    print(f"  {'TOTAL':<16} ${r['projected_total']:>12,.0f}")
    print("\nNext: python -m pytest tests -v   (a few checks only apply to the original export)")


if __name__ == "__main__":
    main()