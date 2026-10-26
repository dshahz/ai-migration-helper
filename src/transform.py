"""Step 3: apply the approved mapping and clean up the values.

This is plain, predictable code. No AI here. It renames columns, drops the ones
with no home, and standardizes formats (dates, money, currency codes, etc.).
Anything it can't parse is recorded as a problem instead of being guessed.
"""

from __future__ import annotations

import re

import pandas as pd
from dateutil import parser as dateparser

from src.target_schema import TARGET_FIELDS, TARGET_SCHEMA


def _clean_text(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value):
    text = _clean_text(value)
    if text is None:
        return None, None
    try:
        # Assumes month-first for ambiguous dates like 03/04/2026 (North American style).
        return dateparser.parse(text, dayfirst=False).date(), None
    except (ValueError, OverflowError):
        return None, f"could not read date '{text}'"


def _parse_money(value):
    text = _clean_text(value)
    if text is None:
        return None, None
    cleaned = re.sub(r"[$,\s]", "", text)
    try:
        return round(float(cleaned), 2), None
    except ValueError:
        return None, f"could not read amount '{text}'"


def apply_mapping(raw: pd.DataFrame, mappings: list[dict]) -> pd.DataFrame:
    """Rename and clean columns. Adds `source_row` and `parse_errors` for traceability."""
    rename = {m["source_column"]: m["target_field"] for m in mappings if m["target_field"]}
    df = raw[list(rename)].rename(columns=rename).copy()
    for field in TARGET_FIELDS:            # fields the source didn't have stay empty
        if field not in df.columns:
            df[field] = None
    df = df[TARGET_FIELDS]

    out_rows = []
    for i, row in df.iterrows():
        errors = []
        clean = {"source_row": i + 2}       # +2: header is line 1, data starts on line 2
        for field in TARGET_FIELDS:
            kind = TARGET_SCHEMA[field]["type"]
            value = row[field]
            if kind == "date":
                parsed, err = _parse_date(value)
            elif kind == "money":
                parsed, err = _parse_money(value)
            else:
                parsed, err = _clean_text(value), None
                if parsed and kind == "currency":
                    parsed = parsed.upper()
                elif parsed and kind == "email":
                    parsed = parsed.lower()
                elif parsed and field == "status":
                    parsed = parsed.title()
            if err:
                errors.append(f"{field}: {err}")
            clean[field] = parsed
        clean["parse_errors"] = errors
        out_rows.append(clean)
    return pd.DataFrame(out_rows)
