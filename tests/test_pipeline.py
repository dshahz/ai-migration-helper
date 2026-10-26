"""Unit tests. None of these call the real API, so they run free in CI."""

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.mapper import LLMMapper, RuleBasedMapper, enforce_one_to_one
from src.transform import apply_mapping
from src.validate import validate

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "legacy_invoices.csv"

CORRECT = {
    "Inv #": "invoice_number", "Client": "customer_name", "E-mail Addr": "customer_email",
    "Date Issued": "invoice_date", "Pay By": "due_date", "Amt": "amount",
    "Curr": "currency", "Stat": "status", "Sales Rep": None, "Notes": None,
}


@pytest.fixture
def raw():
    return pd.read_csv(DATA, dtype=str, keep_default_na=False, na_values=[""])


def correct_mapping():
    return [{"source_column": c, "target_field": t, "confidence": 1.0, "reason": "test"}
            for c, t in CORRECT.items()]


def test_validator_catches_every_injected_problem(raw):
    clean, quarantine, recon = validate(apply_mapping(raw, correct_mapping()))
    problems = " | ".join(quarantine["problems"])
    for expected in ["customer_name: missing", "amount: must be greater than zero",
                     "customer_email: invalid format", "invoice_date: could not read date",
                     "due_date: earlier than invoice_date", "currency: 'BTC'",
                     "amount: missing", "invoice_number: duplicate"]:
        assert expected in problems, expected
    assert len(quarantine) == 8          # exactly the 8 rows we broke on purpose
    assert recon["rows_accounted_for"] and recon["amount_reconciles"]


def test_formats_are_standardized(raw):
    clean, _, _ = validate(apply_mapping(raw, correct_mapping()))
    assert set(clean["currency"]) <= {"CAD", "USD"}          # 'cad' became 'CAD'
    assert clean["amount"].map(type).eq(float).all()          # '$7,147.34' became 7147.34
    assert set(clean["status"]) <= {"Open", "Paid", "Overdue"}


def test_rules_baseline_misses_client_column(raw):
    got = {m["source_column"]: m["target_field"] for m in RuleBasedMapper().map_columns(raw)}
    assert got["Client"] is None          # the gap the LLM is meant to close


def test_one_to_one_keeps_most_confident():
    maps = [{"source_column": "A", "target_field": "amount", "confidence": 0.6, "reason": ""},
            {"source_column": "B", "target_field": "amount", "confidence": 0.9, "reason": ""}]
    out = {m["source_column"]: m["target_field"] for m in enforce_one_to_one(maps)}
    assert out == {"A": None, "B": "amount"}


class FakeClient:
    """Stands in for the Anthropic client and returns a canned tool call."""

    def __init__(self, mappings):
        block = SimpleNamespace(type="tool_use", input={"mappings": mappings})
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[block]))


def test_llm_output_is_checked_not_trusted(raw):
    proposed = [
        {"source_column": "Client", "target_field": "customer_name", "confidence": 0.95, "reason": "names"},
        {"source_column": "Amt", "target_field": "total_amount", "confidence": 0.9, "reason": "made-up field"},
        {"source_column": "Inv #", "target_field": "invoice_number", "confidence": 0.99, "reason": "ids"},
        {"source_column": "Notes", "target_field": "invoice_number", "confidence": 0.3, "reason": "dup"},
        # 'Curr' is left out entirely
    ]
    got = {m["source_column"]: m["target_field"]
           for m in LLMMapper(client=FakeClient(proposed)).map_columns(raw)}
    assert got["Client"] == "customer_name"
    assert got["Amt"] is None              # unknown field rejected
    assert got["Notes"] is None            # lost the duplicate claim to 'Inv #'
    assert got["Curr"] is None             # missing column still gets a row
    assert set(got) == set(raw.columns)


def test_llm_retries_when_model_skips_the_tool(raw):
    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="Here you go...")])
    tool_call = SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"mappings": [
        {"source_column": "Client", "target_field": "customer_name", "confidence": 0.9, "reason": "names"}]})])
    replies = iter([text_only, tool_call])
    calls = []
    client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: calls.append(kw) or next(replies)))
    got = {m["source_column"]: m["target_field"] for m in LLMMapper(client=client).map_columns(raw)}
    assert got["Client"] == "customer_name"
    assert len(calls) == 2
    assert all(c["tool_choice"] == {"type": "auto"} for c in calls)


def test_llm_gives_up_cleanly_if_never_uses_tool(raw):
    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="no")])
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: text_only))
    with pytest.raises(RuntimeError, match="submit_mapping"):
        LLMMapper(client=client).map_columns(raw)


def test_approved_mapping_round_trip(raw, tmp_path):
    from pipeline import run
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(correct_mapping()))
    result = run(str(DATA), approved_mapping=str(path), out_dir=str(tmp_path / "out"))
    assert result["mapper"] == "approved"
    assert result["rows_clean"] == 33 and result["rows_quarantined"] == 8