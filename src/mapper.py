"""Step 2: decide which messy column maps to which clean field.

Two mappers with the same output shape:

* LLMMapper     - asks Claude to propose the mapping (the "AI first pass").
* RuleBasedMapper - simple keyword matching. Used as a baseline to compare
                  the LLM against, and as a fallback when there's no API key.

Each mapping is a dict:
    {"source_column": "Amt", "target_field": "amount",
     "confidence": 0.95, "reason": "Short for amount; values are money."}
target_field is None when a column doesn't belong in the new system.
"""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher

import pandas as pd

from src.target_schema import TARGET_FIELDS, TARGET_SCHEMA

DEFAULT_MODEL = os.environ.get("MAPPER_MODEL", "claude-sonnet-5-5")


# ---------------------------------------------------------------------------
# Shared clean-up: every target field may be used at most once
# ---------------------------------------------------------------------------

def enforce_one_to_one(mappings: list[dict]) -> list[dict]:
    """If two columns claim the same target, keep the more confident one."""
    best: dict[str, dict] = {}
    for m in mappings:
        t = m["target_field"]
        if t is None:
            continue
        if t not in best or m["confidence"] > best[t]["confidence"]:
            best[t] = m
    for m in mappings:
        t = m["target_field"]
        if t is not None and best[t] is not m:
            m["reason"] = f"Also matched {t}, but another column was a better fit. " + m["reason"]
            m["target_field"] = None
            m["confidence"] = 0.0
    return mappings


# ---------------------------------------------------------------------------
# Baseline: keyword rules
# ---------------------------------------------------------------------------

KEYWORDS = {
    "invoice_number": ["invoice number", "invoice no", "invoice id", "inv no", "inv"],
    "customer_name": ["customer", "customer name", "cust name"],
    "customer_email": ["email", "e mail", "customer email"],
    "invoice_date": ["invoice date", "date"],
    "due_date": ["due date", "due"],
    "amount": ["amount", "amt", "total"],
    "currency": ["currency", "curr", "ccy"],
    "status": ["status", "stat"],
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


class RuleBasedMapper:
    """Match column names to keywords. Fast and free, but brittle."""

    name = "rules"

    def map_columns(self, df: pd.DataFrame) -> list[dict]:
        mappings = []
        for col in df.columns:
            norm = _normalize(col)
            best_field, best_score = None, 0.0
            for field, words in KEYWORDS.items():
                for w in words:
                    score = SequenceMatcher(None, norm, w).ratio()
                    if norm == w or norm.split() and norm.split()[0] == w:
                        score = max(score, 0.9)
                    if score > best_score:
                        best_field, best_score = field, score
            if best_score >= 0.75:
                mappings.append({"source_column": col, "target_field": best_field,
                                 "confidence": round(best_score, 2),
                                 "reason": f"Name is similar to '{best_field}'."})
            else:
                mappings.append({"source_column": col, "target_field": None,
                                 "confidence": 0.0,
                                 "reason": "No keyword match."})
        return enforce_one_to_one(mappings)


# ---------------------------------------------------------------------------
# The AI first pass: Claude proposes the mapping
# ---------------------------------------------------------------------------

MAPPING_TOOL = {
    "name": "submit_mapping",
    "description": "Submit the proposed mapping from source columns to target fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_column": {"type": "string"},
                        "target_field": {
                            "type": ["string", "null"],
                            "enum": TARGET_FIELDS + [None],
                            "description": "Target field, or null if the column has no home.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string", "description": "One short sentence."},
                    },
                    "required": ["source_column", "target_field", "confidence", "reason"],
                },
            }
        },
        "required": ["mappings"],
    },
}

SYSTEM_PROMPT = (
    "You are helping migrate data from a legacy system into a new one. "
    "Map each source column to exactly one target field, or to null if it does not "
    "belong in the target. Each target field may be used at most once. Use the sample "
    "values, not just the column names. Be honest about uncertainty in the confidence score."
)


def build_prompt(df: pd.DataFrame, n_samples: int = 3) -> str:
    """Describe the target schema and show a few sample values per column."""
    samples = {col: df[col].dropna().astype(str).head(n_samples).tolist() for col in df.columns}
    return (
        "Target fields:\n"
        + json.dumps({f: s["description"] for f, s in TARGET_SCHEMA.items()}, indent=2)
        + "\n\nSource columns with sample values:\n"
        + json.dumps(samples, indent=2)
    )


class LLMMapper:
    """Ask Claude for a mapping, returned as structured JSON through a tool call.

    Some models reject a *forced* tool choice, so the tool is offered with
    tool_choice "auto" and the prompt tells Claude to use it. If Claude answers
    in plain text anyway, we ask once more, then fail loudly rather than guess.
    """

    name = "llm"
    max_attempts = 2

    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        if client is None:
            import anthropic  # imported here so the rules mapper works without it
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        self.client = client
        self.model = model

    def _request_mapping(self, df: pd.DataFrame) -> list[dict]:
        messages = [{"role": "user", "content": build_prompt(df)}]
        for _ in range(self.max_attempts):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=SYSTEM_PROMPT + " Always answer by calling the submit_mapping tool.",
                tools=[MAPPING_TOOL],
                tool_choice={"type": "auto"},
                messages=messages,
            )
            tool_use = next((b for b in response.content if b.type == "tool_use"), None)
            if tool_use is not None:
                return tool_use.input.get("mappings", [])
            # No tool call: show Claude its reply and ask again, once.
            messages += [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": "Please submit the mapping by calling the submit_mapping tool."},
            ]
        raise RuntimeError(f"{self.model} did not return a mapping via the submit_mapping tool.")

    def map_columns(self, df: pd.DataFrame) -> list[dict]:
        proposed = {m["source_column"]: m for m in self._request_mapping(df)}

        # Never trust the model blindly: every real column must appear exactly once,
        # and any target the schema doesn't know about is dropped.
        mappings = []
        for col in df.columns:
            m = proposed.get(col)
            if m is None:
                mappings.append({"source_column": col, "target_field": None,
                                 "confidence": 0.0, "reason": "Model did not map this column."})
                continue
            target = m.get("target_field")
            if target not in TARGET_FIELDS:
                target = None
            mappings.append({"source_column": col, "target_field": target,
                             "confidence": float(m.get("confidence", 0)),
                             "reason": m.get("reason", "")})
        return enforce_one_to_one(mappings)


def get_mapper(prefer_llm: bool = True):
    """Use the LLM if an API key is set, otherwise fall back to rules."""
    if prefer_llm and os.environ.get("ANTHROPIC_API_KEY"):
        return LLMMapper()
    return RuleBasedMapper()