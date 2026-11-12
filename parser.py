"""
parser.py
Day 2 deliverable. Included now (tested against Transactions-2020-2027.xls)
so the folder structure is runnable end-to-end from the start.

The source file is NOT a real .xls — it's an HTML "Transaction List" export
from Banner, and most data rows are missing their opening <tr> tag, so
pandas.read_html() returns nothing. This parser splits on </tr> and pulls
the 16 <td> cells per row directly.
"""

import re
import pandas as pd

from config import get_type, get_category, PASSTHROUGH_COLUMNS
from transforms import clean_date, clean_description, clean_amount

RAW_COLUMNS = [
    "Year", "Period", "DocCode", "Description", "TranDate", "ActvDate",
    "Rule", "Fund", "Org", "Account", "Prog", "Actv", "Loc",
    "EncNum", "PredAcct", "Encumb",
]


def _extract_raw_rows(html_content: str) -> list[list[str]]:
    """Split on </tr> and pull td text for rows that have exactly 16 cells."""
    chunks = html_content.split("</tr>")
    rows = []
    for chunk in chunks:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", chunk, flags=re.S)
        if len(tds) == len(RAW_COLUMNS):
            clean_cells = []
            for cell in tds:
                text = re.sub(r"<[^>]+>", " ", cell)
                text = text.replace("&amp;", "&")
                text = re.sub(r"\s+", " ", text).strip()
                clean_cells.append(text)
            rows.append(clean_cells)
    return rows


def parse_xls(file_path: str) -> pd.DataFrame:
    """
    Parse the Banner HTML export into the normalized schema:
    [date, description, category, amount, type] + passthrough audit columns.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    raw_rows = _extract_raw_rows(content)
    raw_df = pd.DataFrame(raw_rows, columns=RAW_COLUMNS)
    raw_df = raw_df[raw_df["Year"] != "Year"]  # drop stray duplicated header row

    normalized = pd.DataFrame({
        "date": raw_df["TranDate"].apply(clean_date),
        "description": raw_df["Description"].apply(clean_description),
        "amount": raw_df["Encumb"].apply(clean_amount),
        "type": raw_df["Rule"].apply(get_type),
        "category": raw_df["Account"].apply(get_category),
    })

    # carry over passthrough/audit columns
    for col in PASSTHROUGH_COLUMNS:
        normalized[col] = raw_df[col]

    return normalized


if __name__ == "__main__":
    df = parse_xls("data/Transactions-2020-2027.xls")
    print(f"Parsed {len(df)} rows")
    print(df.head())
