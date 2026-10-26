# AI Migration Helper

**AI suggests the mapping, rules check the data, a human makes the final call.**

Moving a client's data out of a legacy system usually starts with the same tedious job: working out which of their columns (`Amt`, `Client`, `Pay By`...) belong in which fields of the new system, then cleaning up mixed date formats, currency symbols, blanks, and duplicates. This project uses an LLM for the first pass on the mapping, then runs the data through ordinary, testable pipeline steps so nothing the AI suggests reaches the output unchecked.

## How it works

```
legacy CSV ──► 1. Propose mapping ──► 2. Human review ──► 3. Transform ──► 4. Validate ──┬─► clean.csv
               (Claude, or keyword       (edit any         (rename, parse    (business     └─► quarantine.csv
                rules as a baseline)      mapping)          dates & money)    rules)            + report.md
```

1. **Propose:** Claude reads the target schema plus a few sample values per column and returns a structured mapping (target field, confidence, reason) through a tool call with a fixed schema, so the answer is structured JSON rather than chatty text (if Claude replies in plain text, it's asked once more, then the run fails loudly instead of guessing). The output is checked, not trusted: unknown fields are rejected, missing columns are filled in, and if two columns claim the same field, the more confident one wins.
2. **Review:** a person approves or edits the mapping (in the Streamlit app, or by editing `mapping.json`).
3. **Transform:** plain Python renames columns and standardizes values: `$7,147.34` → `7147.34`, `cad` → `CAD`, `Mar 05 2026` → `2026-03-05`. Anything unreadable is recorded as a problem, never guessed.
4. **Validate:** every row lands in exactly one place, clean or quarantine, with reasons. Row counts and dollar totals are reconciled so nothing goes missing silently.

## Results

The sample file has 8 problems injected on purpose (missing customer, negative amount, bad email, unreadable date, due date before invoice date, unsupported currency, missing amount, duplicate invoice). With a correct mapping, the validator quarantines exactly those 8 rows and passes the other 33, and amounts reconcile to the cent.

**Mapping accuracy** on two test sets of 30 column decisions each:

- **Basic:** the same 10 columns renamed three ways (abbreviations, accounting jargon, and meaningless `fld_01`-style names).
- **Hard:** a 15-column version of the file where 7 columns are look-alike decoys that should *not* be migrated (`Subtotal` and `HST` next to `Total`, `Last Modified` next to the real dates, `Rep Email` next to the customer email, `Approval` next to `Stat`, `Contact Person` next to the company). Tested once with readable names and once with cryptic, shuffled names (`c01`...`c15`), so neither the name nor the position gives the answer away.

| Mapper | Basic | Hard: real fields found | Hard: decoys left out |
| --- | --- | --- | --- |
| Keyword rules (baseline) | 12 / 30 (40%) | 4 / 16 | 13 / 14 |
| Claude | 30 / 30 (100%, 3 of 3 runs) | 16 / 16 (2 of 3 runs; 15 / 16 once) | 14 / 14 (2 of 3 runs; 13 / 14 once) |

The hard set's score is split because leaving a column out counts as "correct" for a decoy: a mapper that mapped nothing would still look half-decent on a single number.

Decoys matter because they fail quietly. The keyword baseline maps `Rep Email` to `customer_email`: every row still passes validation and the totals still reconcile, and the company's own sales reps' addresses get imported as customer emails. Claude is far better but not immune: on one of three cryptic-name runs it mapped a decoy column to `amount` (at 0.72 confidence) because its values looked cleaner than the real amount column's inconsistent `$`/comma formatting, and left the real column unmapped. That mapping also passes every rule and still reconciles. Rules can't catch a wrong-but-plausible mapping. That's what the human review step is for.

## Run it

```bash
pip install -r requirements.txt
python data/generate_messy_data.py                       # synthetic sample data (already included)
python data/generate_hard_data.py                        # the 15-column decoy version (already included)
python -m pytest -q                                      # unit tests (no API key needed)

python pipeline.py data/legacy_invoices.csv --rules      # keyword baseline
export ANTHROPIC_API_KEY=...                              # then, with Claude (PowerShell: $env:ANTHROPIC_API_KEY="...")
python pipeline.py data/legacy_invoices.csv
python pipeline.py data/legacy_invoices.csv --mapping output/mapping.json   # after editing it

python eval/run_eval.py --mapper llm                     # measure accuracy (both test sets)
python eval/run_eval.py --mapper llm --set hard          # just the decoy test
streamlit run app.py                                     # the review UI
```

CI runs the unit tests and the baseline on every push. If you add `ANTHROPIC_API_KEY` as a repository secret, it also runs the LLM accuracy check: the basic set fails the build below 90%, and the hard set is reported without failing it.

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
| `data/` | Synthetic sample files and the scripts that generate them |
| `eval/` | Answer keys for both test sets and the accuracy script |
| `tests/` | Unit tests, including a fake LLM client |

## Notes

- All data is synthetic. No real client data is used.
- Ambiguous dates like `03/04/2026` are read month-first (North American); the report says so.
- The target schema is a generic invoice import template, not tied to any specific ERP.
