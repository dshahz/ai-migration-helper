"""Create a fake "legacy system export" full of realistic problems.

The data is synthetic (made up), so it's safe to share publicly. It mimics what
a real client export often looks like: odd column names, mixed date formats,
currency symbols in amounts, blanks, duplicates, and a couple of columns the
new system doesn't need.

Run:  python data/generate_messy_data.py
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)  # same "random" data every time, so results are reproducible

OUT = Path(__file__).parent / "legacy_invoices.csv"

# Deliberately messy column names, like a real legacy export.
HEADERS = ["Inv #", "Client", "E-mail Addr", "Date Issued", "Pay By",
           "Amt", "Curr", "Stat", "Sales Rep", "Notes"]

CUSTOMERS = ["Northwind Traders", "Maple Leaf Supply", "Blue Harbour Foods",
             "Cedar & Pine Co", "Lakeview Electronics", "Summit Outfitters",
             "Riverbend Bakery", "Granite Field Services"]
REPS = ["J. Patel", "M. Chen", "S. Okafor", "L. Moreau"]
STATUSES = ["Open", "Paid", "Overdue", "open", "PAID"]


def fmt_date(d: date, style: int) -> str:
    """Write the same date in different formats, like a messy export would."""
    return [d.isoformat(), d.strftime("%m/%d/%Y"), d.strftime("%b %d %Y")][style]


def make_rows(n: int = 40):
    rows = []
    start = date(2026, 1, 5)
    for i in range(n):
        issued = start + timedelta(days=random.randint(0, 250))
        due = issued + timedelta(days=random.choice([15, 30, 45]))
        customer = random.choice(CUSTOMERS)
        email = customer.lower().replace(" & ", "").replace(" ", "") + "@example.com"
        amount = round(random.uniform(150, 12000), 2)
        rows.append({
            "Inv #": f"INV-{1001 + i}",
            "Client": customer,
            "E-mail Addr": email,
            "Date Issued": fmt_date(issued, i % 3),
            "Pay By": fmt_date(due, (i + 1) % 3),
            "Amt": f"${amount:,.2f}" if i % 2 else f"{amount}",
            "Curr": random.choice(["CAD", "USD", "cad"]),
            "Stat": random.choice(STATUSES),
            "Sales Rep": random.choice(REPS),
            "Notes": random.choice(["", "net 30", "rush order", ""]),
        })

    # Inject known problems so we can check the validator catches them.
    rows[3]["Client"] = ""                      # missing required field
    rows[7]["Amt"] = "-250.00"                  # negative amount
    rows[11]["E-mail Addr"] = "billing@@bad"    # malformed email
    rows[15]["Date Issued"] = "sometime in May" # unparseable date
    rows[19]["Pay By"] = "01/02/2026"           # due date before invoice date
    rows[22]["Curr"] = "BTC"                    # currency not allowed
    rows[26]["Amt"] = ""                        # missing amount
    rows.append(dict(rows[5]))                  # exact duplicate invoice
    return rows


def main():
    rows = make_rows()
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
