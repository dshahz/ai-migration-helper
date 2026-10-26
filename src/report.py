"""Step 5: a short, client-readable summary of what happened."""

from __future__ import annotations

import pandas as pd


def build_report(mappings: list[dict], recon: dict, quarantine: pd.DataFrame,
                 mapper_name: str, low_confidence: float = 0.7) -> str:
    lines = ["# Migration report", ""]

    lines += ["## Column mapping", f"Proposed by: **{mapper_name}** mapper, then reviewed.", "",
              "| Source column | Target field | Confidence | Reason |",
              "| --- | --- | --- | --- |"]
    for m in mappings:
        target = m["target_field"] or "(not migrated)"
        flag = " (check)" if m["target_field"] and m["confidence"] < low_confidence else ""
        lines.append(f"| {m['source_column']} | {target}{flag} | {m['confidence']:.2f} | {m['reason']} |")

    lines += ["", "## Reconciliation",
              f"- Rows in: {recon['rows_in']}",
              f"- Clean, ready to import: {recon['rows_clean']}",
              f"- Quarantined for review: {recon['rows_quarantined']}",
              f"- Every row accounted for: {'yes' if recon['rows_accounted_for'] else 'NO'}",
              f"- Amount in: {recon['amount_in']:,.2f} = clean {recon['amount_clean']:,.2f}"
              f" + quarantined {recon['amount_quarantined']:,.2f}"
              f" ({'reconciles' if recon['amount_reconciles'] else 'DOES NOT RECONCILE'})"]

    if len(quarantine):
        lines += ["", "## Rows needing a human decision", "",
                  "| Source row | Invoice | Problems |", "| --- | --- | --- |"]
        for _, r in quarantine.iterrows():
            lines.append(f"| {r['source_row']} | {r['invoice_number'] or '-'} | {r['problems']} |")

    lines += ["", "_Ambiguous dates such as 03/04/2026 were read as month/day (North American)._"]
    return "\n".join(lines)
