# AI Migration Helper

**AI suggests the mapping, rules check the data, a human makes the final call.**

Moving a client's data out of a legacy system usually starts with the same tedious job: working out which of their columns (`Amt`, `Client`, `Pay By`...) belong in which fields of the new system, then cleaning up mixed date formats, currency symbols, blanks, and duplicates. This project uses an LLM for the first pass on the mapping, then runs the data through ordinary, testable pipeline steps so nothing the AI suggests reaches the output unchecked.

## How it works

```
legacy CSV ──► 1. Propose mapping ──► 2. Human review ──► 3. Transform ──► 4. Validate ──┬─► clean.csv
               (Claude, or keyword       (edit any         (rename, parse    (business     └─► quarantine.csv
                rules as a baseline)      mapping)          dates & money)    rules)            + report.md
```

1. **Propose:** Claude reads the target schema plus a few sample values per column and returns a structured mapping (target field, confidence, reason) through a forced tool call, so the answer is always valid JSON. The output is checked, not trusted: unknown fields are rejected, missing columns are filled in, and if two columns claim the same field, the more confident one wins.
2. **Review:** a person approves or edits the mapping (in the Streamlit app, or by editing `mapping.json`).
3. **Transform:** plain Python renames columns and standardizes values: `$7,147.34` → `7147.34`, `cad` → `CAD`, `Mar 05 2026` → `2026-03-05`. Anything unreadable is recorded as a problem, never guessed.
4. **Validate:** every row lands in exactly one place, clean or quarantine, with reasons. Row counts and dollar totals are reconciled so nothing goes missing silently.

## Results

The sample file has 8 problems injected on purpose (missing customer, negative amount, bad email, unreadable date, due date before invoice date, unsupported currency, missing amount, duplicate invoice). With a correct mapping, the validator quarantines exactly those 8 rows and passes the other 33, and amounts reconcile to the cent.

**Mapping accuracy** across 30 columns (the same data with three sets of column names: abbreviations, accounting jargon, and meaningless `fld_01`-style names):

| Mapper | Correct | Accuracy |
| --- | --- | --- |
| Keyword rules (baseline) | 12 / 30 | 40% |
| Claude | _run `python eval/run_eval.py --mapper llm`_ | _TBD_ |

The keyword baseline misses obvious-to-a-human columns like `Client`, so every row fails validation. That's the gap the LLM is meant to close.

## Run it

```bash
pip install -r requirements.txt
python data/generate_messy_data.py                       # synthetic sample data
python -m pytest -q                                      # unit tests (no API key needed)

python pipeline.py data/legacy_invoices.csv --rules      # keyword baseline
export ANTHROPIC_API_KEY=...                              # then, with Claude:
python pipeline.py data/legacy_invoices.csv
python pipeline.py data/legacy_invoices.csv --mapping output/mapping.json   # after editing it

python eval/run_eval.py --mapper llm                     # measure accuracy
streamlit run app.py                                     # the review UI
```

CI runs the unit tests and the baseline on every push. If you add `ANTHROPIC_API_KEY` as a repository secret, it also runs the LLM accuracy check and fails the build below 90%.

## Project layout

| Path | What it does |
| --- | --- |
| `src/target_schema.py` | The clean format the new system expects |
| `src/mapper.py` | Claude mapper and keyword-rules baseline |
| `src/transform.py` | Applies the mapping and standardizes values |
| `src/validate.py` | Business rules, clean/quarantine routing, reconciliation |
| `src/report.py` | Client-readable migration report |
| `pipeline.py` | Command-line runner |
| `app.py` | Streamlit review UI |
| `eval/` | Ground-truth header variants and the accuracy script |
| `tests/` | Unit tests, including a fake LLM client |

## Notes

- All data is synthetic. No real client data is used.
- Ambiguous dates like `03/04/2026` are read month-first (North American); the report says so.
- The target schema is a generic invoice import template, not tied to any specific ERP.
