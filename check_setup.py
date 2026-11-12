"""Checks that the packages the tracker needs can be loaded on this computer.
Run by setup.bat / setup.sh at the end, or by hand:  python check_setup.py
A package that is installed but blocked by a security policy shows as BLOCKED here."""
import importlib
import sys

CORE = ["pandas", "numpy", "matplotlib", "streamlit", "lxml", "bs4", "html5lib"]
MODELS = {
    "SARIMA": "statsmodels.tsa.statespace.sarimax",
    "Holt-Winters": "statsmodels.tsa.holtwinters",
    "Theta": "statsmodels.tsa.forecasting.theta",
    "Prophet": "prophet",
    "Machine-learning models (scikit-learn)": "sklearn.ensemble",
}


def can_load(name):
    try:
        importlib.import_module(name)
        return None
    except Exception as e:                                   # includes DLL blocked by a security policy
        return f"{type(e).__name__}: {str(e).strip().splitlines()[0][:110] if str(e).strip() else ''}"


print(f"Python {sys.version.split()[0]}")
if sys.version_info < (3, 10):
    print("WARNING: Python 3.10 or newer is needed.")
bad_core = []
for name in CORE:
    err = can_load(name)
    print(f"  {'OK     ' if not err else 'BLOCKED'} {name}" + (f"  <- {err}" if err else ""))
    if err:
        bad_core.append(name)
print("Forecasting models:")
left_out = []
for label, mod in MODELS.items():
    err = can_load(mod)
    print(f"  {'OK     ' if not err else 'BLOCKED'} {label}" + (f"  <- {err}" if err else ""))
    if err:
        left_out.append(label)
print()
if bad_core:
    print("The dashboard cannot start until these load: " + ", ".join(bad_core))
elif left_out:
    print("The dashboard will work, but these models will be left out of the Models tab: " + ", ".join(left_out))
    print("(A security policy or a failed install is the usual cause. The other models still run.)")
else:
    print("Everything loads. All 12 models will run.")
