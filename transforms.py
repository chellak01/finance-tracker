"""
transforms.py
Day 1 output: field-level cleaning functions.
Pure functions, no I/O — parser.py calls these row by row.
"""

import re
from datetime import datetime, date
from typing import Optional


def clean_date(raw_date: str) -> Optional[date]:
    """TranDate/ActvDate: 'MM/DD/YYYY' -> datetime.date. Returns None on bad/missing input."""
    if not raw_date or not str(raw_date).strip():
        return None
    try:
        return datetime.strptime(raw_date.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def clean_description(raw_desc: str) -> str:
    """Trim + collapse internal whitespace, e.g. 'Salaries         (Orig)' -> 'Salaries (Orig)'."""
    if not raw_desc:
        return ""
    return re.sub(r"\s+", " ", raw_desc).strip()


def clean_amount(raw_amount: str) -> float:
    """'$118,490.80' -> 118490.80 ; '($11,849.08)' -> -11849.08"""
    if not raw_amount or not str(raw_amount).strip():
        return 0.0
    s = raw_amount.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "")
    value = float(s) if s else 0.0
    return -value if negative else value
