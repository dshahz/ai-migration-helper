"""Measure how often a mapper picks the right target for each column.

    python eval/run_eval.py --mapper rules                 # both test sets
    python eval/run_eval.py --mapper llm                   # needs ANTHROPIC_API_KEY
    python eval/run_eval.py --mapper llm --set hard        # just the decoy test
    python eval/run_eval.py --mapper llm --set basic --min-accuracy 0.9   # what CI runs

Two test sets, each a JSON file naming its data file and some "variants" (the
same data with the columns renamed and/or reordered), plus the correct answer
for every column:

    basic  eval/header_variants.json  10 columns, renamed 3 ways (30 decisions)
    hard   eval/hard_variants.json    15 columns, 7 of them look-alike decoys,
                                      named and cryptic+shuffled (30 decisions)

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

TEST_SETS = {
    "basic": ROOT / "eval" / "header_variants.json",
    "hard": ROOT / "eval" / "hard_variants.json",
}
LOW_CONFIDENCE = 0.7


def evaluate(mapper, variants_path: Path) -> dict:
    spec_file = json.loads(variants_path.read_text())
    base = pd.read_csv(ROOT / spec_file["data"], dtype=str, keep_default_na=False, na_values=[""])
    results = {"mapper": mapper.name, "variants": {}, "misses": [], "unsure": []}
    total = correct = 0
    fields_right = fields_total = skips_right = skips_total = 0

    for name, spec in spec_file["variants"].items():
        renamed = base.rename(columns={orig: new for orig, (new, _) in spec.items()})
        renamed = renamed[[new for new, _ in spec.values()]]   # column order as listed
        expected = {new: target for new, target in spec.values()}
        got = {m["source_column"]: m for m in mapper.map_columns(renamed)}

        v_correct = 0
        for col, want in expected.items():
            total += 1
            m = got.get(col, {})
            answer, conf = m.get("target_field"), float(m.get("confidence", 0))
            if want is None:
                skips_total += 1
                skips_right += answer is None
            else:
                fields_total += 1
                fields_right += answer == want
            if answer == want:
                correct += 1
                v_correct += 1
                if answer is not None and conf < LOW_CONFIDENCE:
                    results["unsure"].append({"variant": name, "column": col,
                                              "target": answer, "confidence": conf})
            else:
                results["misses"].append({"variant": name, "column": col, "expected": want,
                                          "got": answer, "confidence": conf,
                                          "reason": m.get("reason", "")})
        results["variants"][name] = f"{v_correct}/{len(expected)}"

    results["correct"], results["total"] = correct, total
    # Split the score: leaving a column out is "correct" for a decoy, so a mapper that
    # maps nothing would still look half-decent on the total alone.
    results["real_fields"] = f"{fields_right}/{fields_total}"
    results["decoys_skipped"] = f"{skips_right}/{skips_total}"
    results["accuracy"] = round(correct / total, 3)
    return results


def print_results(set_name: str, r: dict):
    print(f"[{set_name}] {r['mapper']} mapper: {r['correct']}/{r['total']} correct ({r['accuracy']:.0%})")
    print(f"  real fields mapped correctly: {r['real_fields']}"
          f" | columns correctly left out: {r['decoys_skipped']}")
    for name, score in r["variants"].items():
        print(f"  {name}: {score}")
    for m in r["misses"]:
        print(f"  MISS [{m['variant']}] {m['column']}: expected {m['expected']}, got {m['got']}"
              f" (confidence {m['confidence']:.2f}) - {m['reason']}")
    for u in r["unsure"]:
        print(f"  right but unsure [{u['variant']}] {u['column']} -> {u['target']}"
              f" (confidence {u['confidence']:.2f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapper", choices=["rules", "llm"], default="rules")
    ap.add_argument("--set", choices=["basic", "hard", "all"], default="all")
    ap.add_argument("--min-accuracy", type=float, default=None)
    args = ap.parse_args()

    mapper = LLMMapper() if args.mapper == "llm" else RuleBasedMapper()
    sets = list(TEST_SETS) if args.set == "all" else [args.set]

    correct = total = 0
    for set_name in sets:
        r = evaluate(mapper, TEST_SETS[set_name])
        (ROOT / "eval" / f"results_{mapper.name}_{set_name}.json").write_text(json.dumps(r, indent=2))
        print_results(set_name, r)
        correct, total = correct + r["correct"], total + r["total"]

    accuracy = correct / total
    if len(sets) > 1:
        print(f"OVERALL: {correct}/{total} ({accuracy:.0%})")
    if args.min_accuracy is not None and accuracy < args.min_accuracy:
        print(f"FAIL: accuracy below {args.min_accuracy:.0%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
