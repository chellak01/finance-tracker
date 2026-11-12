"""
config.py
Day 1 output: static mapping tables used across the pipeline.
Edit ACCOUNT_CATEGORY_MAP here as you confirm/relabel categories —
every other module imports from this single source of truth.
"""

# Raw columns kept as-is on the transactions table (audit / drill-down fields,
# not part of the core normalized [date, description, category, amount, type] schema).
# Account and Rule are included even though they're also used to derive
# category/type, so the raw codes stay available for review/drill-down.
PASSTHROUGH_COLUMNS = [
    "DocCode", "EncNum", "Fund", "Org", "Account", "Rule", "Prog",
    "Year", "Period", "Actv", "Loc", "PredAcct", "ActvDate",
]

# Rule code -> lifecycle-stage type (replaces the personal-finance debit/credit concept)
# NOTE: these meanings are INFERRED from the data (sign, description, timing),
# not from official Banner documentation. Confirm with the professor.
# Changed Oct 2026:
#   - HFEN is the original fringe commitment and HFEA the monthly fringe
#     adjustment (same pattern as HENC / HENA), so they are no longer both "Final".
#   - E032 / E090 are the "ENCUMBRANCE ROLL" entries on June 30 / July 1
#     (year-end carry-forward), which is bookkeeping, not spending.
#   - E10 / E035 only appear on the travel accounts (name + date descriptions):
#     amounts set aside and later released. Not spending, so no longer "Expense".
RULE_TYPE_MAP = {
    "HENC": "Encumbrance-Original", "HFEN": "Encumbrance-Original",
    "HENA": "Encumbrance-Adjustment", "HFEA": "Encumbrance-Adjustment",
    "PORD": "Purchase-Order", "POBC": "Purchase-Order", "POCL": "Purchase-Order",
    "INEI": "Invoice", "INEC": "Invoice", "ICEI": "Invoice",
    "E032": "Year-End Roll", "E090": "Year-End Roll",
    "E10": "Encumbrance-Other", "E035": "Encumbrance-Release",
    "PCRD": "Other", "CORD": "Other",
}

# Rule codes that count as money actually EXPENDED (everything else is either a
# new commitment, a release of unspent money, or bookkeeping).
#   Payroll:    HENA / HFEA are the monthly salary / fringe payments (mostly negative)
#   Purchasing: INEI invoices, INEC invoice corrections, PCRD credits
# Not expended: HENC, HFEN, PORD (new commitments), POCL, POBC (PO closed, money
# released), E032, E090 (year-end roll), E10, E035, CORD, ICEI.
EXPENDED_PAYROLL_RULES = ["HENA", "HFEA"]
EXPENDED_PURCHASING_RULES = ["INEI", "INEC", "PCRD"]
EXPENDED_RULES = EXPENDED_PAYROLL_RULES + EXPENDED_PURCHASING_RULES

# Account code -> category. Draft built from the real Account/Description pairs
# in Transactions-2020-2027.xls — confirm or relabel as needed.
ACCOUNT_CATEGORY_MAP = {
    "611100": "Salaries", "611108": "Salaries", "611500": "Salaries",
    "611800": "Salaries", "612100": "Salaries", "612200": "Salaries",
    "612255": "Salaries", "614100": "Salaries", "614200": "Salaries",
    "614205": "Salaries", "615100": "Salaries", "615150": "Salaries",
    "615200": "Salaries", "615400": "Salaries",
    "621100": "Fringe Benefits", "621110": "Fringe Benefits",
    "622100": "Fringe Benefits", "623100": "Fringe Benefits",
    "623200": "Fringe Benefits", "624200": "Fringe Benefits",
    "717150": "Legal/Professional Services",
    "730100": "Supplies/Vendor", "730300": "Supplies/Vendor",
    "730500": "Supplies/Vendor", "731100": "Supplies/Vendor",
    "738100": "Supplies/Vendor",
    # Travel: confirmed by the professor (Oct 2026). These were previously
    # "Personnel Services" (742000, 746900) and "Supplies/Vendor" (746600).
    "742000": "Travel", "746600": "Travel", "746900": "Travel",
    "751300": "PO Closeout", "751800": "Subscriptions/Publications",
    "753100": "Supplies/Vendor",
}

# Detailed category -> the groups used for the projections.
# Anything not listed falls into "Other" (Legal, Subscriptions, PO Closeout).
CATEGORY_ROLLUP = {
    "Salaries": "Salaries",
    "Fringe Benefits": "Fringe",
    "Travel": "Travel",
    "Supplies/Vendor": "Supplies/Vendor",
}
ROLLUP_ORDER = ["Salaries", "Fringe", "Travel", "Supplies/Vendor", "Other"]

# GTA/GA funding: the professor says GTA accounts start with 773. There are NO
# 773 accounts in Transactions-2020-2027.xls, so nothing is mapped here yet.
# Add them when an export that includes them is available:
#     "773xxx": "GTA/GA",


def get_type(rule: str) -> str:
    return RULE_TYPE_MAP.get(rule, "Unclassified")


def get_category(account: str) -> str:
    return ACCOUNT_CATEGORY_MAP.get(account, "Uncategorized")


def get_rollup(category: str) -> str:
    return CATEGORY_ROLLUP.get(category, "Other")
