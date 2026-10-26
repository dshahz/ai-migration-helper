"""Streamlit page: upload a legacy export, review the AI's mapping, run the migration.

    streamlit run app.py
"""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.mapper import LLMMapper, RuleBasedMapper
from src.report import build_report
from src.target_schema import TARGET_FIELDS
from src.transform import apply_mapping
from src.validate import validate

SAMPLE = Path(__file__).parent / "data" / "legacy_invoices.csv"
NOT_MIGRATED = "(not migrated)"

st.set_page_config(page_title="AI Migration Helper", layout="wide")
st.title("AI Migration Helper")
st.caption("AI suggests the mapping, rules check the data, a human makes the final call.")

# 1. Load the legacy file ------------------------------------------------------
uploaded = st.file_uploader("Upload a legacy export (CSV)", type="csv")
source = uploaded if uploaded is not None else SAMPLE
raw = pd.read_csv(source, dtype=str, keep_default_na=False, na_values=[""])
st.write(f"**{len(raw)} rows**, {len(raw.columns)} columns"
         + ("" if uploaded else " (using the synthetic sample file)"))
st.dataframe(raw.head(8), width="stretch")

# 2. Propose a mapping ---------------------------------------------------------
has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
choice = st.radio("Who proposes the mapping?",
                  ["Claude (LLM)", "Keyword rules"], index=0 if has_key else 1, horizontal=True)
if choice == "Claude (LLM)" and not has_key:
    st.warning("Set ANTHROPIC_API_KEY to use Claude. Using keyword rules instead.")
    choice = "Keyword rules"

if st.button("Propose mapping") or "mappings" not in st.session_state:
    mapper = LLMMapper() if choice == "Claude (LLM)" else RuleBasedMapper()
    with st.spinner(f"Asking the {mapper.name} mapper..."):
        st.session_state.mappings = mapper.map_columns(raw)
        st.session_state.mapper_name = mapper.name

# 3. Human review: edit any target field before running -------------------------
st.subheader("Review the mapping")
st.caption("Low-confidence rows deserve a second look. Change any target field before running.")
table = pd.DataFrame(st.session_state.mappings)
table["target_field"] = table["target_field"].fillna(NOT_MIGRATED)
edited = st.data_editor(
    table,
    column_config={
        "target_field": st.column_config.SelectboxColumn(
            "Target field", options=TARGET_FIELDS + [NOT_MIGRATED], required=True),
        "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1),
    },
    disabled=["source_column", "confidence", "reason"],
    hide_index=True, width="stretch",
)

# 4. Run: transform, validate, report ------------------------------------------
if st.button("Run migration", type="primary"):
    reviewed = edited.replace({"target_field": {NOT_MIGRATED: None}}).to_dict("records")
    clean, quarantine, recon = validate(apply_mapping(raw, reviewed))

    c1, c2, c3 = st.columns(3)
    c1.metric("Rows in", recon["rows_in"])
    c2.metric("Clean", recon["rows_clean"])
    c3.metric("Quarantined", recon["rows_quarantined"])
    st.write("Rows reconcile:", "yes" if recon["rows_accounted_for"] else "NO",
             " | Amounts reconcile:", "yes" if recon["amount_reconciles"] else "NO")

    st.subheader("Needs a human decision")
    st.dataframe(quarantine, width="stretch")
    st.subheader("Ready to import")
    st.dataframe(clean, width="stretch")

    report = build_report(reviewed, recon, quarantine, st.session_state.mapper_name + " + human review")
    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("clean.csv", clean.to_csv(index=False), "clean.csv")
    d2.download_button("quarantine.csv", quarantine.to_csv(index=False), "quarantine.csv")
    d3.download_button("mapping.json", json.dumps(reviewed, indent=2), "mapping.json")
    d4.download_button("report.md", report, "report.md")
    with st.expander("Migration report"):
        st.markdown(report)
