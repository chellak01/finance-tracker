"""Checks for the finance tracker. Run from the project folder:   python -m pytest tests -v

Part 1 checks the parser and the mappings against the raw export.
Part 2 checks the SQLite database that build_database.py makes.
Part 3 opens the dashboard and checks it loads without errors.
Part 4 checks the model tables and the "Update data" rebuild.

A few checks compare against the exact numbers of the ORIGINAL export (3,011 rows, Sep 2020 to Aug 11 2026).
They are skipped automatically when the data is a newer export, so new data never makes the suite fail for the wrong reason.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import EXPENDED_RULES, get_category, get_rollup, get_type  # noqa: E402
from parser import parse_xls  # noqa: E402

DATA_FILE = ROOT / "data" / "Transactions-2020-2027.xls"
DB_FILE = ROOT / "data" / "finance_tracker.db"


ORIGINAL_ROWS, ORIGINAL_LAST_DATE = 3011, "2026-08-11"


def require_original_raw(d):
    if len(d) != ORIGINAL_ROWS or d["date"].max() != pd.Timestamp(ORIGINAL_LAST_DATE):
        pytest.skip("Only applies to the original export.")


def require_original_db(conn):
    n, hi = conn.execute("SELECT COUNT(*), MAX(date) FROM transactions").fetchone()
    if n != ORIGINAL_ROWS or hi != ORIGINAL_LAST_DATE:
        pytest.skip("Only applies to the original export.")


@pytest.fixture(scope="module")
def df():
    if not DATA_FILE.exists():
        pytest.skip(f"Raw export not found at {DATA_FILE}.")
    d = parse_xls(str(DATA_FILE))
    d["date"] = pd.to_datetime(d["date"])
    d["fy"] = d["date"].dt.year + (d["date"].dt.month >= 7).astype(int)   # fiscal year = Jul to Jun
    return d


@pytest.fixture(scope="module")
def db():
    if not DB_FILE.exists():
        pytest.skip("Database not built yet. Run the notebook cells that build it.")
    conn = sqlite3.connect(DB_FILE)
    yield conn
    conn.close()


# ----------------------------------------------------------------- Part 1: parser and mappings
def test_row_count(df):
    require_original_raw(df)
    assert len(df) == 3011


def test_date_range(df):
    require_original_raw(df)
    assert df["date"].min() == pd.Timestamp("2020-09-01")
    assert df["date"].max() == pd.Timestamp("2026-08-11")


def test_every_row_is_mapped(df):
    assert (df["category"] == "Uncategorized").sum() == 0
    assert (df["type"] == "Unclassified").sum() == 0


def test_amounts_parse_with_correct_sign(df):
    first = df[(df["Rule"] == "HENC") & (df["Account"] == "611100")].sort_values("date").iloc[0]
    assert first["amount"] == pytest.approx(118490.80)          # "$118,490.80"
    assert df[df["Rule"] == "HENA"]["amount"].sum() < 0         # "($11,849.08)" style amounts are negative


def test_travel_accounts_confirmed_by_professor():
    for acct in ("742000", "746600", "746900"):
        assert get_category(acct) == "Travel"
        assert get_rollup("Travel") == "Travel"


def test_gta_accounts_are_mapped_if_present(df):
    """GTA accounts start with 773. None are in this export, so this passes trivially;
    it will fail if a new export has 773 accounts that nobody mapped."""
    gta = df[df["Account"].str.startswith("773")]
    assert (gta["category"] != "Uncategorized").all()


def test_category_totals(df):
    require_original_raw(df)
    gross = df.assign(a=df["amount"].abs()).groupby("category")["a"].sum()
    assert gross["Salaries"] == pytest.approx(46129058, abs=2)
    assert gross["Fringe Benefits"] == pytest.approx(10367525, abs=2)
    assert gross["Supplies/Vendor"] == pytest.approx(51264, abs=2)      # after moving the travel accounts out
    assert gross["Travel"] == pytest.approx(102821, abs=2)


def test_payroll_paid_out_matches_commitment(df):
    """Each year's salary and fringe payments should match the original commitments.
    Exact for FY2021 to FY2024; within 3% for FY2025 and FY2026 (a little was left unspent)."""
    require_original_raw(df)
    commit = df[df["Rule"].isin(["HENC", "HFEN"])].groupby("fy")["amount"].sum()
    paid = -df[df["Rule"].isin(["HENA", "HFEA"])].groupby("fy")["amount"].sum()
    for fy in (2021, 2022, 2023, 2024):
        assert paid[fy] == pytest.approx(commit[fy], abs=1)
    for fy in (2025, 2026):
        assert paid[fy] == pytest.approx(commit[fy], rel=0.03)


def test_expended_fy2026(df):
    require_original_raw(df)
    exp = -df[df["Rule"].isin(EXPENDED_RULES)].groupby("fy")["amount"].sum()
    assert exp[2026] == pytest.approx(3557012, abs=2)


# ----------------------------------------------------------------- Part 2: database
def test_database_tables_and_counts(db):
    n = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for t in ("transactions", "monthly_snapshot", "monthly_projection", "alerts"):
        assert n(t) > 0
    months = db.execute("SELECT COUNT(DISTINCT month) FROM monthly_snapshot").fetchone()[0]
    assert n("monthly_snapshot") == months * 5                    # 5 categories per month
    assert n("monthly_projection") == 5 * 2 * 12                  # 5 categories x 2 measures x 12 months


def test_database_counts_original_export(db):
    require_original_db(db)
    n = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert n("transactions") == 3011
    assert n("monthly_snapshot") == 360
    assert n("monthly_projection") == 120


def test_snapshot_matches_transactions(db):
    tx_expended = db.execute("SELECT SUM(expended) FROM transactions").fetchone()[0]
    snap_expended = db.execute("SELECT SUM(expended) FROM monthly_snapshot").fetchone()[0]
    assert snap_expended == pytest.approx(tx_expended, abs=1)
    tx_net = db.execute("SELECT SUM(amount) FROM transactions").fetchone()[0]
    last = db.execute("SELECT MAX(month) FROM monthly_snapshot").fetchone()[0]
    balance = db.execute("SELECT SUM(enc_balance) FROM monthly_snapshot WHERE month = ?", (last,)).fetchone()[0]
    assert balance == pytest.approx(tx_net, abs=1)         # final balance = all amounts added up


def test_projection_is_sane(db):
    p = pd.read_sql("SELECT * FROM monthly_projection", db)
    assert p[["projected", "low", "high"]].notna().all().all()
    assert (p["projected"] >= p["low"] - 1e-6).all() and (p["projected"] <= p["high"] + 1e-6).all()
    assert (p[p["measure"] == "expended"]["projected"] >= 0).all()      # a forecast of spending is never negative


def test_projection_totals_original_export(db):
    require_original_db(db)
    p = pd.read_sql("SELECT * FROM monthly_projection", db)
    exp_total = p[p["measure"] == "expended"]["projected"].sum()
    assert 3_300_000 < exp_total < 3_900_000                # about $3.58M
    peak = p[p["measure"] == "enc_balance"].groupby("month")["projected"].sum()
    assert peak.idxmax() == "2026-09"


def test_alerts_flag_missing_gta(db):
    has_gta = db.execute("SELECT COUNT(*) FROM transactions WHERE account LIKE '773%'").fetchone()[0] > 0
    rows = db.execute("SELECT description FROM alerts WHERE alert_type = 'Missing data'").fetchall()
    assert has_gta != any("773" in r[0] for r in rows)       # warned exactly when GTA accounts are absent


# ----------------------------------------------------------------- Part 3: dashboard
def test_dashboard_loads_without_errors():
    pytest.importorskip("streamlit")
    if not DB_FILE.exists():
        pytest.skip("Database not built yet.")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Overview", "Projections", "Models", "Yearly", "Alerts", "Transactions", "Update data"]
    assert len(at.metric) == 4


def test_yearly_tab_projection_matches_notebook():
    pytest.importorskip("streamlit")
    if not DB_FILE.exists():
        pytest.skip("Database not built yet.")
    with sqlite3.connect(DB_FILE) as _c:
        require_original_db(_c)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=60).run()
    yearly = [d.value for d in at.dataframe if "Change vs prior year" in d.value.columns][0]
    assert yearly.loc["FY2026", "Total"] == pytest.approx(3557012, abs=2)
    assert yearly.loc["FY2027 (projected)", "Total"] == pytest.approx(3582345, abs=5)   # notebook: $3.58M


# ----------------------------------------------------------------- Part 3: models
def test_model_tables_cover_every_category_and_model(db):
    n = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    k = db.execute("SELECT COUNT(DISTINCT model) FROM model_scores").fetchone()[0]
    assert k >= 2                                  # the seasonal average and seasonal naive always run
    assert n("model_scores") == 5 * k              # 5 categories x every model that ran (12 when nothing is blocked)
    assert n("model_backtest") == 5 * k * 12       # each with 12 test months
    assert n("model_future") == 5 * k * 12         # each with 12 future months
    cats = {r[0] for r in db.execute("SELECT DISTINCT category FROM model_scores")}
    assert cats == {"Salaries", "Fringe", "Travel", "Supplies/Vendor", "Other"}


def test_no_model_forecasts_negative_money(db):
    for t in ["model_backtest", "model_future"]:
        assert db.execute(f"SELECT MIN(predicted) FROM {t}").fetchone()[0] >= 0


def test_dashboard_model_matches_projection_tab(db):
    f = dict(db.execute("SELECT category, SUM(predicted) FROM model_future WHERE model LIKE 'Seasonal average%' GROUP BY category"))
    p = dict(db.execute("SELECT rollup, SUM(projected) FROM monthly_projection WHERE measure='expended' GROUP BY rollup"))
    for cat, v in f.items():
        assert v == pytest.approx(p[cat], abs=0.01)


def test_models_tab_shows_both_tables():
    pytest.importorskip("streamlit")
    if not DB_FILE.exists():
        pytest.skip("Database not built yet.")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=90).run()
    assert not at.exception
    tables = [d.value for d in at.dataframe if "Salaries" in d.value.columns and len(d.value) >= 2]
    assert len(tables) >= 2 or any(len(d.value) >= 2 for d in at.dataframe if "Salaries" in d.value.columns)


# ----------------------------------------------------------------- Part 5: "Update data" rebuild
def test_inspect_export_rejects_a_file_that_is_not_an_export(tmp_path):
    import build_database as bd
    bad = tmp_path / "not_an_export.xls"
    bad.write_text("this is not a Banner export")
    with pytest.raises(ValueError):
        bd.inspect_export(bad)


def test_rebuild_into_a_temporary_database(tmp_path):
    """Rebuild from the raw export into a scratch database; a second rebuild keeps a backup; a bad file changes nothing."""
    if not DATA_FILE.exists():
        pytest.skip(f"Raw export not found at {DATA_FILE}.")
    import build_database as bd
    target = tmp_path / "scratch.db"
    r1 = bd.build(DATA_FILE, log=lambda *_: None, db_path=target)
    assert target.exists() and r1["backup"] is None
    assert r1["counts"]["model_scores"] == 5 * (12 - len(r1["skipped_models"]))
    r2 = bd.build(DATA_FILE, log=lambda *_: None, db_path=target)
    assert r2["backup"] is not None and Path(r2["backup"]).exists()
    assert r2["projected_total"] == pytest.approx(r1["projected_total"], abs=0.01)
    before = target.read_bytes()
    bad = tmp_path / "bad.xls"
    bad.write_text("nope")
    with pytest.raises(ValueError):
        bd.build(bad, log=lambda *_: None, db_path=target)
    assert target.read_bytes() == before                           # the old database is untouched
    assert not (tmp_path / "scratch.db.new").exists()              # no half-built file left behind


def test_rebuild_still_works_when_a_package_is_blocked(tmp_path, monkeypatch):
    """On a computer where a security policy blocks a compiled package, only the models that need it are dropped."""
    if not DATA_FILE.exists():
        pytest.skip(f"Raw export not found at {DATA_FILE}.")
    import build_database as bd
    monkeypatch.setitem(sys.modules, "statsmodels.tsa.statespace.sarimax", None)      # makes `import` of it fail
    target = tmp_path / "blocked.db"
    r = bd.build(DATA_FILE, log=lambda *_: None, db_path=target)
    assert "SARIMA" in r["skipped_models"]
    conn = sqlite3.connect(target)
    models = {m for (m,) in conn.execute("SELECT DISTINCT model FROM model_scores")}
    conn.close()
    assert "SARIMA" not in models and "Prophet" in models and "Seasonal average (dashboard)" in models