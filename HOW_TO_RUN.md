# Computer Science Fund Tracker: how to run it

This is a small dashboard for the Computer Science fund (Fund 190000). It reads a Banner transaction export, shows
spending and encumbered balances by category, projects the next 12 months, compares 12 forecasting models, and lists alerts.
Everything runs on your own computer. Nothing is sent anywhere.

## Quick start
- **Windows:** double-click `setup.bat` (once, about 10 minutes), then double-click `run.bat`.
- **Mac or Linux:** in a terminal, `./setup.sh` (once), then `./run.sh`.

At the end of setup, a short report says whether every package loads on your computer. If a security policy blocks one, the dashboard
still works and the Models tab just leaves out the models that need it. The sections below are the same steps done by hand.

## What you need
- Python 3.10 or newer (built and tested with 3.13). Check with `python --version`.
- An internet connection for the first install (about 10 minutes, Prophet is the largest package).
- A Banner export (.xls) of the fund's transactions, the same kind of file as `Transactions-2020-2027.xls`.

## 1. Set up (once)
Unzip the folder, open a terminal in it, then:

**Windows (Command Prompt)**
```
cd finance_tracker
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

**Mac or Linux**
```
cd finance_tracker
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

You will see `(venv)` at the start of the line when the environment is active. Do the activate line again each time you open a new terminal.

## 2. Start the dashboard
```
python -m streamlit run dashboard/app.py
```
Your browser opens at http://localhost:8501. The first time there is no data, so the page asks for an export:
choose your .xls file, check the summary it shows, and press **Rebuild the dashboard with this file**.
It takes about a minute, then all tabs fill in.

(Command line alternative: copy the export into a folder named `data` and run `python build_database.py data/your_file.xls`.)

## 3. Updating with newer data
Open the **Update data** tab, upload the newer export and press the rebuild button. The tool:
- checks that the file is a valid export and shows its row count and date range next to what is loaded now;
- warns if the new file has less history than the current data (it replaces the old data, it does not add to it, so upload a full export);
- keeps a copy of the previous database in `data/backups` (the last 5);
- leaves the old data in place if anything fails.

## 4. The tabs
| Tab | What it shows |
|---|---|
| Overview | Expended per month and encumbered balance, history plus the next 12 months |
| Projections | Next 12 months by category, with the low and high seen in the last 3 fiscal years |
| Models | All 12 forecasting models on every category, how far off each was on the last 12 months, and what each predicts |
| Yearly | Expended per fiscal year (July to June) with next year projected |
| Alerts | Unusual months, negative balances, data gaps (for example no GTA accounts) |
| Transactions | Search and download the transactions |
| Update data | Upload a new export, download the projection as CSV |

## 5. How the numbers are defined
- **Expended** = payroll payments (HENA, HFEA) plus paid invoices (INEI, INEC, PCRD). Commitments, releases and year-end roll entries are not counted as spent.
- **Encumbered balance** = running total of all transaction amounts per category since the first month in the file.
- **Projection** = average of the same fiscal month in the last 3 complete fiscal years (a seasonal average). The low and high are the smallest and largest of those years. It is a range of past years, not a statistical confidence interval.
- **Categories** come from the account number in `config.py` (Salaries, Fringe, Travel, Supplies/Vendor, Other). Travel accounts are 742000, 746600 and 746900.
- All forecasts are floored at zero.

## 6. Accounts that are not mapped yet
If a new export has accounts that `config.py` does not know (for example GTA accounts starting with 773), the Update data tab lists them
and they show as "Uncategorized". Add them in `config.py` under `ACCOUNT_CATEGORY_MAP`, for example `"773100": "GTA/GA"`,
add `"GTA/GA": "GTA/GA"` to `CATEGORY_ROLLUP` and `ROLLUP_ORDER`, then rebuild.

## 7. Optional: run the checks
```
python -m pytest tests -v
```
Checks that compare against the original export's exact numbers are skipped automatically on other data.

## If something goes wrong
- **A program is "blocked by Application Control / Device Guard":** run tools through Python, for example `python -m streamlit run dashboard/app.py` and `python -m pip install ...` instead of `streamlit` or `pip`.
- **`pip install prophet` fails:** update pip (`python -m pip install --upgrade pip`) and try again. Python 3.13 or 3.12 works best.
- **"No such table" error:** the data has not been built yet. Upload an export in the Update data tab, or run `python build_database.py data/your_file.xls`.
- **The rebuild says the database is open in another program:** close any program holding `data/finance_tracker.db` and try again.
- **A file is rejected:** the message says why (not a Banner export, too little history, or missing columns).

## Privacy
The export lists payments to named people (for example under Travel). Keep the data folder private and mask names in any screenshots you share.
