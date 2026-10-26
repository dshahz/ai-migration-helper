"""Run the whole migration from the command line.

    python pipeline.py data/legacy_invoices.csv            # uses Claude if ANTHROPIC_API_KEY is set
    python pipeline.py data/legacy_invoices.csv --rules    # keyword rules only, no API key needed
    python pipeline.py data/legacy_invoices.csv --mapping output/mapping.json   # after you edit it

Outputs go to output/: clean.csv, quarantine.csv, mapping.json, report.md
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from src.mapper import get_mapper
from src.report import build_report
from src.transform import apply_mapping
from src.validate import validate


def run(input_path: str, use_llm: bool = True, out_dir: str = "output",
        approved_mapping: str | None = None) -> dict:
    raw = pd.read_csv(input_path, dtype=str, keep_default_na=False, na_values=[""])

    if approved_mapping:                          # 1. a human-approved mapping wins
        mappings = json.loads(Path(approved_mapping).read_text())
        mapper_name = "approved"
    else:                                         # 1. AI (or rules) proposes
        mapper = get_mapper(prefer_llm=use_llm)
        mappings = mapper.map_columns(raw)
        mapper_name = mapper.name

    cleaned = apply_mapping(raw, mappings)        # 2. code transforms
    clean, quarantine, recon = validate(cleaned)  # 3. rules check and route

    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    clean.to_csv(out / "clean.csv", index=False)
    quarantine.to_csv(out / "quarantine.csv", index=False)
    (out / "mapping.json").write_text(json.dumps(mappings, indent=2))
    (out / "report.md").write_text(build_report(mappings, recon, quarantine, mapper_name))
    return {"mapper": mapper_name, **recon}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--rules", action="store_true", help="skip the LLM and use keyword rules")
    ap.add_argument("--mapping", help="use a reviewed mapping.json instead of proposing one")
    args = ap.parse_args()
    print(json.dumps(run(args.input, use_llm=not args.rules, approved_mapping=args.mapping), indent=2))
