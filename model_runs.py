"""Run every forecasting model on the monthly EXPENDED series of each category.

Used by build_database.py. For each category it produces
  * scores:   how far off each model was on the last 12 months (MAE, RMSE)
  * backtest: each model's forecast for those last 12 months (trained on the earlier months only)
  * future:   each model's forecast for the next 12 months

All forecasts are multi-step (the model never sees the months it is predicting) and are floored at 0.

If a package cannot be loaded on this computer (for example a security policy blocks one of its compiled files),
only the models that need it are left out. The rest still run, and LAST_SKIPPED says which ones were dropped and why.
Salaries and Fringe are fitted on a log scale; Travel and Supplies/Vendor on raw values
(the log step helped the big categories and hurt the tiny ones in earlier tests).
"""
import logging
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

LAST_SKIPPED = {}          # model name -> why it did not run, filled in by run_all()

CATEGORIES = ["Salaries", "Fringe", "Travel", "Supplies/Vendor", "Other"]
USE_LOG = {"Salaries": True, "Fringe": True, "Travel": False, "Supplies/Vendor": False, "Other": False}
STAT_MODELS = ["Seasonal average (dashboard)", "Seasonal naive", "SARIMA", "Holt-Winters", "Theta", "Prophet"]
ML_MODELS = ["Linear regression", "Ridge", "Random forest", "Gradient boosting", "KNN", "Neural network (MLP)"]


def _seasonal_average(series, dates, n_years=3):
    """Average of the same calendar month in the last 3 years (same method as the dashboard projection)."""
    out = []
    for d in dates:
        vals = [series.get(d - pd.DateOffset(years=k)) for k in range(1, n_years + 1)]
        vals = [v for v in vals if v is not None and not pd.isna(v)]
        out.append(float(np.mean(vals)) if vals else 0.0)
    return pd.Series(out, index=dates)


def _skip(name, err):
    LAST_SKIPPED.setdefault(name, f"{type(err).__name__}: {str(err).strip().splitlines()[0][:140] if str(err).strip() else ''}")


def _stat_forecasts(train, n, log):
    train = train.clip(lower=0)                           # net corrections can make a month slightly negative
    f, inv = (np.log1p, np.expm1) if log else (lambda x: x, lambda x: x)
    y = f(train)
    dates = pd.date_range(train.index[-1] + pd.DateOffset(months=1), periods=n, freq="MS")
    res = {
        "Seasonal average (dashboard)": _seasonal_average(train, dates),
        "Seasonal naive": pd.Series(train.iloc[-12:].values.astype(float)[:n], index=dates),
    }

    def sarima():
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        return SARIMAX(y, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12), enforce_stationarity=False,
                       enforce_invertibility=False).fit(disp=False).forecast(n).values

    def holt_winters():
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        return ExponentialSmoothing(y, trend="add", seasonal="add", seasonal_periods=12).fit().forecast(n).values

    def theta():
        from statsmodels.tsa.forecasting.theta import ThetaModel
        return ThetaModel(y, period=12).fit().forecast(n).values

    def prophet():
        from prophet import Prophet
        m = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
        m.fit(pd.DataFrame({"ds": y.index, "y": y.values}))
        return m.predict(m.make_future_dataframe(periods=n, freq="MS"))["yhat"].iloc[-n:].values

    for name, fn in {"SARIMA": sarima, "Holt-Winters": holt_winters, "Theta": theta, "Prophet": prophet}.items():
        try:
            res[name] = pd.Series(inv(np.asarray(fn(), float)), index=dates)
        except Exception as e:                            # a model that cannot load or fit is left out and reported, never hidden
            _skip(name, e)
    return {k: v.clip(lower=0) for k, v in res.items()}


def _features(hist, d, t):
    return [d.month, t, hist.iloc[-1], hist.iloc[-12], hist.iloc[-3:].mean()]


def _ml_forecasts(train, n):
    """Machine-learning models on lag features, forecast one month at a time (each step uses the previous predictions)."""
    try:
        from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
        from sklearn.linear_model import LinearRegression, Ridge
        from sklearn.neighbors import KNeighborsRegressor
        from sklearn.neural_network import MLPRegressor
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as e:                                # scikit-learn missing or blocked: leave out all six ML models
        for name in ML_MODELS:
            _skip(name, e)
        return {}

    train = train.clip(lower=0)
    rows = [(_features(train.iloc[:i], train.index[i], i), train.iloc[i]) for i in range(12, len(train))]
    X, y = np.array([r[0] for r in rows], float), np.array([r[1] for r in rows], float)
    models = {
        "Linear regression": LinearRegression(), "Ridge": Ridge(alpha=1.0),
        "Random forest": RandomForestRegressor(n_estimators=200, random_state=0),
        "Gradient boosting": GradientBoostingRegressor(random_state=0),
        "KNN": make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=5)),
        "Neural network (MLP)": make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=2000, random_state=0)),
    }
    dates = pd.date_range(train.index[-1] + pd.DateOffset(months=1), periods=n, freq="MS")
    out = {}
    for name, model in models.items():
        try:
            model.fit(X, y)
            hist = train.copy()
            for d in dates:
                p = max(float(model.predict(np.array([_features(hist, d, len(hist))], float))[0]), 0.0)
                hist.loc[d] = p
            out[name] = hist.loc[dates]
        except Exception as e:
            _skip(name, e)
    return out


def run_all(monthly, projection=None, n_test=12, n_future=12):
    """monthly = the monthly table from build_database (columns month, rollup, expended).
    projection = the dashboard's monthly_projection table; when given, the 'Seasonal average (dashboard)' line for the
    next 12 months is taken from it so the Models tab and the Projections tab always show the same numbers."""
    LAST_SKIPPED.clear()
    scores, backtest, future = [], [], []
    for cat in CATEGORIES:
        s = monthly[monthly["rollup"] == cat].copy()
        s["month"] = s["month"].dt.to_timestamp() if hasattr(s["month"].dt, "to_timestamp") else s["month"]
        series = s.set_index("month")["expended"].astype(float).asfreq("MS").fillna(0.0)
        log = USE_LOG[cat]
        print(f"  {cat} ...")
        train, test = series.iloc[:-n_test], series.iloc[-n_test:]
        bt = {**_stat_forecasts(train, n_test, log), **_ml_forecasts(train, n_test)}
        for name, pred in bt.items():
            err = test.values - pred.values
            scores.append((cat, name, float(np.mean(np.abs(err))), float(np.sqrt(np.mean(err ** 2)))))
            backtest += [(cat, name, str(d.to_period("M")), float(v)) for d, v in pred.items()]
        fut = {**_stat_forecasts(series, n_future, log), **_ml_forecasts(series, n_future)}   # next 12 months, every model
        if projection is not None:
            pr = projection[(projection["rollup"] == cat) & (projection["measure"] == "expended")]
            fut["Seasonal average (dashboard)"] = pd.Series(pr["projected"].values, index=pd.PeriodIndex(pr["month"], freq="M").to_timestamp())
        for name, pred in fut.items():
            future += [(cat, name, str(d.to_period("M")), float(v)) for d, v in pred.items()]
    if LAST_SKIPPED:
        print("  Models left out on this computer: " + "; ".join(f"{k} ({v})" for k, v in LAST_SKIPPED.items()))
    return (pd.DataFrame(scores, columns=["category", "model", "mae", "rmse"]),
            pd.DataFrame(backtest, columns=["category", "model", "month", "predicted"]),
            pd.DataFrame(future, columns=["category", "model", "month", "predicted"]))