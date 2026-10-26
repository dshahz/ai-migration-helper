"""Measure how often a mapper picks the right target for each column.

    python eval/run_eval.py --mapper rules
    python eval/run_eval.py --mapper llm --min-accuracy 0.9    # needs ANTHROPIC_API_KEY

It renames the sample file's columns three different ways (see header_variants.json),
runs the mapper on each, and compares every answer to the known-correct one.
--min-accuracy makes the script fail (exit code 1), which is how CI blocks a regression.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mapper import LLMMapper, RuleBasedMapper  # noqa: E402


def evaluate(mapper, data_path: Path, variants_path: Path) -> dict:
    base = pd.read_csv(data_path, dtype=str, keep_default_na=False, na_values=[""])
    variants = json.loads(variants_path.read_text())["variants"]
    results = {"mapper": mapper.name, "variants": {}, "misses": []}
    total = correct = 0

    for name, spec in variants.items():
        renamed = base.rename(columns={orig: new for orig, (new, _) in spec.items()})
        expected = {new: target for new, target in spec.values()}
        got = {m["source_column"]: m["target_field"] for m in mapper.map_columns(renamed)}

        v_correct = 0
        for col, want in expected.items():
            total += 1
            if got.get(col) == want:
                correct += 1
                v_correct += 1
            else:
                results["misses"].append(
                    {"variant": name, "column": col, "expected": want, "got": got.get(col)})
        results["variants"][name] = f"{v_correct}/{len(expected)}"

    results["correct"], results["total"] = correct, total
    results["accuracy"] = round(correct / total, 3)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapper", choices=["rules", "llm"], default="rules")
    ap.add_argument("--min-accuracy", type=float, default=None)
    args = ap.parse_args()

    mapper = LLMMapper() if args.mapper == "llm" else RuleBasedMapper()
    results = evaluate(mapper, ROOT / "data" / "legacy_invoices.csv",
                       ROOT / "eval" / "header_variants.json")
    out = ROOT / "eval" / f"results_{mapper.name}.json"
    out.write_text(json.dumps(results, indent=2))

    print(f"{mapper.name} mapper: {results['correct']}/{results['total']} "
          f"correct ({results['accuracy']:.0%})")
    for name, score in results["variants"].items():
        print(f"  {name}: {score}")
    for miss in results["misses"]:
        print(f"  miss [{miss['variant']}] {miss['column']}: expected {miss['expected']}, got {miss['got']}")

    if args.min_accuracy is not None and results["accuracy"] < args.min_accuracy:
        print(f"FAIL: accuracy below {args.min_accuracy:.0%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
