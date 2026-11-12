# Fund Tracker

A dashboard for the Computer Science fund (Fund 190000). It reads a Banner transaction export and shows what has been spent, what is still committed, and a projection for the next 12 months. Built as an MSITM capstone project, guided by Professor Wischgoll.

## What it does

- Sorts transactions into five categories: Salaries, Fringe, Travel, Supplies/Vendor and Other.
- Shows money paid out each month and money committed but not yet paid (the encumbered balance).
- Projects the next 12 months from the same month in the last three complete fiscal years (July to June).
- Compares 12 forecasting methods on every category.
- Raises alerts for unusual months, negative balances and data problems.
- Rebuilds itself from a newer export with one button (Update data tab).

## Quick start

You need Python 3 installed.

**Windows:** double-click `setup.bat` once, then `run.bat`.

**Mac / Linux:** run `./setup.sh` once, then `./run.sh`.

The dashboard opens in your browser. Full instructions and troubleshooting are in [HOW_TO_RUN.md](HOW_TO_RUN.md).

## Loading data

The repository does not include any data, because the Banner export lists payments to named people. Open the **Update data** tab, upload your own Banner export (.xls) and press the rebuild button. The file is checked first, the current data is backed up, and the dashboard is rebuilt in about a minute.

You can also rebuild from a terminal: `python build_database.py data/<your export>.xls`

## Tests

`python -m pytest tests -v` runs 25 automatic checks. A few compare against the exact numbers of the original export and are skipped automatically on newer data.

## Files

| File | What it does |
| --- | --- |
| `config.py` | Rule code types and the account-to-category map |
| `parser.py`, `transforms.py` | Read and clean the Banner export |
| `build_database.py` | Checks an export and rebuilds the database |
| `model_runs.py` | Runs the 12 forecasting methods |
| `dashboard/app.py` | The Streamlit dashboard |
| `tests/test_pipeline.py` | The automatic checks |
| `setup.bat`, `run.bat`, `setup.sh`, `run.sh` | One-step install and run |
