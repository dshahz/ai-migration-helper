"""Create a harder version of the sample export, full of look-alike "decoy" columns.

Same 41 invoices (and the same 8 planted problems) as legacy_invoices.csv, but
with extra columns that look like they belong in the new system and don't:

    Subtotal, HST    money columns next to the real Total
    Last Modified    a date column next to the real invoice and due dates
    Rep Email        an email column next to the customer's email
    Approval         a status-like column next to the real payment status
    Contact Person   a name column next to the company being billed

Decoys are where a mapper can be plausibly wrong, and plausibly-wrong is the
dangerous kind: if Subtotal is mapped to amount, every row still passes
validation and the totals still reconcile, just to the wrong number.

Run:  python data/generate_hard_data.py      (reads legacy_invoices.csv)
"""

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from dateutil import parser as dateparser

random.seed(7)  # reproducible

HERE = Path(__file__).parent
SRC = HERE / "legacy_invoices.csv"
OUT = HERE / "legacy_invoices_hard.csv"

HEADERS = ["Document No.", "Sold To", "Contact Person", "Contact Email", "Rep Email",
           "Posting Date", "Due", "Last Modified", "Subtotal", "HST", "Total",
           "Ccy", "Stat", "Approval", "Notes"]

CONTACTS = ["Ava Singh", "Liam Tremblay", "Noah Gagnon", "Olivia Roy", "Ethan Wong",
            "Mia Kowalski", "Lucas Martin", "Zoe Bouchard"]
APPROVALS = ["Approved", "Approved", "Approved", "Pending", "Rejected"]
HST_RATE = 0.13  # Ontario


def parse_money(text: str) -> float | None:
    try:
        return float(text.replace("$", "").replace(",", "").strip())
    except (AttributeError, ValueError):
        return None


def parse_date(text: str) -> date | None:
    try:
        return dateparser.parse(text).date()
    except (TypeError, ValueError, OverflowError):
        return None


def rep_email(rep: str) -> str:
    # "J. Patel" -> "j.patel@ourco-internal.example": an email, but ours, not the customer's.
    return rep.replace(" ", "").lower() + "@ourco-internal.example" if rep else ""


def main():
    with SRC.open(newline="") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    for r in rows:
        total = parse_money(r["Amt"])
        subtotal = round(total / (1 + HST_RATE), 2) if total is not None else None
        issued = parse_date(r["Date Issued"]) or date(2026, 6, 1)
        modified = datetime.combine(issued, datetime.min.time()) + timedelta(
            days=random.randint(1, 60), hours=random.randint(8, 18), minutes=random.randint(0, 59))
        out_rows.append({
            "Document No.": r["Inv #"],
            "Sold To": r["Client"],
            "Contact Person": random.choice(CONTACTS),
            "Contact Email": r["E-mail Addr"],
            "Rep Email": rep_email(r["Sales Rep"]),
            "Posting Date": r["Date Issued"],
            "Due": r["Pay By"],
            "Last Modified": modified.strftime("%Y-%m-%d %H:%M"),
            "Subtotal": "" if subtotal is None else f"{subtotal:.2f}",
            "HST": "" if subtotal is None else f"{total - subtotal:.2f}",
            "Total": r["Amt"],
            "Ccy": r["Curr"],
            "Stat": r["Stat"],
            "Approval": random.choice(APPROVALS),
            "Notes": r["Notes"],
        })

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote {len(out_rows)} rows x {len(HEADERS)} columns to {OUT}")


if __name__ == "__main__":
    main()
