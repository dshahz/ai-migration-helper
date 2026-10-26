"""Step 4: check every row against business rules and route it.

Each row lands in exactly one place:
  * clean       - passed every rule, ready to import
  * quarantine  - failed at least one rule, with the reasons listed

Nothing is silently dropped, and the totals are reconciled at the end so we can
prove no rows or money went missing between input and output.
"""

from __future__ import annotations

import re

import pandas as pd

from src.target_schema import ALLOWED_CURRENCIES, REQUIRED_FIELDS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


def check_row(row: pd.Series, seen_invoices: set) -> list[str]:
    problems = list(row["parse_errors"])

    for field in REQUIRED_FIELDS:
        if row[field] is None or pd.isna(row[field]):
            if not any(p.startswith(field) for p in problems):
                problems.append(f"{field}: missing (required)")

    if row["amount"] is not None and not pd.isna(row["amount"]) and row["amount"] <= 0:
        problems.append(f"amount: must be greater than zero (got {row['amount']})")

    email = row["customer_email"]
    if email and not EMAIL_RE.match(email):
        problems.append(f"customer_email: invalid format '{email}'")

    if row["invoice_date"] and row["due_date"] and row["due_date"] < row["invoice_date"]:
        problems.append("due_date: earlier than invoice_date")

    currency = row["currency"]
    if currency and currency not in ALLOWED_CURRENCIES:
        problems.append(f"currency: '{currency}' not in allowed list")

    inv = row["invoice_number"]
    if inv:
        if inv in seen_invoices:
            problems.append(f"invoice_number: duplicate of an earlier row ({inv})")
        seen_invoices.add(inv)

    return problems


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Split rows into clean and quarantine, and return reconciliation numbers."""
    seen: set = set()
    df = df.copy()
    df["problems"] = [check_row(row, seen) for _, row in df.iterrows()]
    is_clean = df["problems"].str.len() == 0

    clean = df[is_clean].drop(columns=["parse_errors", "problems"])
    quarantine = df[~is_clean].drop(columns=["parse_errors"])
    quarantine["problems"] = quarantine["problems"].str.join("; ")

    recon = {
        "rows_in": len(df),
        "rows_clean": len(clean),
        "rows_quarantined": len(quarantine),
        "rows_accounted_for": len(clean) + len(quarantine) == len(df),
        "amount_in": round(float(pd.to_numeric(df["amount"]).fillna(0).sum()), 2),
        "amount_clean": round(float(pd.to_numeric(clean["amount"]).fillna(0).sum()), 2),
        "amount_quarantined": round(float(pd.to_numeric(quarantine["amount"]).fillna(0).sum()), 2),
    }
    recon["amount_reconciles"] = abs(
        recon["amount_in"] - recon["amount_clean"] - recon["amount_quarantined"]) < 0.01
    return clean, quarantine, recon
