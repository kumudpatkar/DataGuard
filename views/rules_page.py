"""Quality Rules page: run saved rules, get suggestions, or build your own."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from core import config
from core.quality_rules import (load_rule_sets, overall_pass_rate, rules_to_yaml, rule_scorecard,
                                run_quality_rules_engine, suggest_rules)
from core.utils import read_any
from views.common import Context, download_buttons, get_retail, page_header, show_table

BUILDER_TYPES = ["required", "positive", "non_negative", "unique", "allowed_values",
                 "range", "regex", "date_format", "cross_column"]
TYPE_HELP = {
    "required": "The value must not be empty.",
    "positive": "The value must be a number above 0.",
    "non_negative": "The value must be a number of 0 or more.",
    "unique": "The value must not appear twice.",
    "allowed_values": "The value must be one of a list you give.",
    "range": "The number must be between a minimum and a maximum.",
    "regex": "The text must match a pattern.",
    "date_format": "The value must be a date written in a given format.",
    "cross_column": "This column must equal two other columns combined (for example Quantity x UnitPrice).",
}
MAX_ISSUES_SHOWN = 2000


def _rules_table(rules: list[dict]) -> pd.DataFrame:
    """Rules as a table. Lists (such as allowed values) become plain text so the table displays cleanly."""
    table = pd.DataFrame(rules).fillna("")
    for column in table.columns:
        table[column] = table[column].map(
            lambda v: ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else v
        ).astype(str)
    return table


def _choose_dataset():
    choice = st.radio("Data to check",
                      ["Orders (demo file)", "Retail transactions", "Upload a file"], horizontal=True)
    if choice == "Orders (demo file)":
        return read_any(config.DATA_DIR / "source_orders.csv"), "orders", "source_orders.csv"
    if choice == "Retail transactions":
        df, info = get_retail()
        st.caption(f"Using {info['file']} ({len(df):,} rows after removing {info['duplicates_removed']:,} exact duplicates). "
                   "Row numbers refer to the cleaned data.")
        return df, "retail_transactions", info["file"]
    uploaded = st.file_uploader("CSV or Excel file", type=["csv", "xlsx", "xls"], key="rules_upload")
    if uploaded is None:
        return None, None, None
    return read_any(uploaded), None, uploaded.name


def _store(rules, df, label):
    issues = run_quality_rules_engine(df, rules)
    st.session_state["rules_result"] = {
        "label": label, "rows": len(df), "rules": rules, "issues": issues,
        "card": rule_scorecard(df, rules, issues),
    }


def _show_result():
    result = st.session_state.get("rules_result")
    if not result:
        return
    st.divider()
    st.subheader(f"Results for: {result['label']}")
    card, issues = result["card"], result["issues"]

    failed_rules = int((card["Failed Rows"] > 0).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall pass rate", f"{overall_pass_rate(card):.1f}%", border=True)
    c2.metric("Rules run", len(card), border=True)
    c3.metric("Rules with failures", failed_rules, border=True)
    c4.metric("Failed values", f"{int(card['Failed Rows'].sum()):,}", border=True)

    left, right = st.columns([3, 2])
    with left:
        show_table(card, height=320)
    with right:
        fig = px.bar(card.sort_values("Pass Rate %"), x="Pass Rate %", y="Rule Name", orientation="h",
                     range_x=[0, 100], color="Severity",
                     color_discrete_map={"High": "#d9534f", "Medium": "#e0a800", "Low": "#2e9e6b"})
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")

    if issues.empty:
        st.success("All values pass every rule.")
        return
    st.markdown("**Failed values**")
    st.caption(f"{len(issues):,} failed values" + (f" (showing the first {MAX_ISSUES_SHOWN:,}; download for all)"
                                                    if len(issues) > MAX_ISSUES_SHOWN else ""))
    show_table(issues.head(MAX_ISSUES_SHOWN), height=360)
    download_buttons(issues, "dataguard_rule_issues", "rule_issues")


def _saved_tab(df, default_set, label):
    sets = load_rule_sets(config.RULES_CONFIG)
    if not sets:
        st.warning("No rule sets found in config/rules.yaml.")
        return
    names = list(sets)
    name = st.selectbox("Rule set", names, index=names.index(default_set) if default_set in names else 0)
    st.caption(sets[name]["description"])
    rules = sets[name]["rules"]
    show_table(_rules_table(rules), height=240)
    if st.button("Run this rule set", type="primary"):
        _store(rules, df, f"{label} with rule set '{name}'")


def _suggest_tab(df, label):
    st.write("DataGuard looks at your data and proposes rules. Untick any you do not want, then run them.")
    if st.button("Analyse this data and suggest rules"):
        suggestions = suggest_rules(df)
        st.session_state["suggestions"] = suggestions
    suggestions = st.session_state.get("suggestions")
    if not suggestions:
        return
    table = pd.DataFrame([{
        "Use": True, "Column": s["column"], "Type": s["type"], "Reason": s["reason"],
    } for s in suggestions])
    edited = st.data_editor(table, hide_index=True, width="stretch", key="suggestion_editor",
                            disabled=["Column", "Type", "Reason"],
                            column_config={"Use": st.column_config.CheckboxColumn("Use")})
    chosen = [
        {k: v for k, v in suggestions[i].items() if k != "reason"}
        for i in edited.index[edited["Use"]]
    ]
    c1, c2 = st.columns([1, 3])
    if c1.button("Run selected rules", type="primary", disabled=not chosen):
        _store(chosen, df, f"{label} with suggested rules")
    if chosen:
        c2.download_button("Download as YAML (paste into config/rules.yaml)",
                           rules_to_yaml("my_rules", chosen, "Suggested by DataGuard"),
                           "my_rules.yaml", "text/yaml")


def _builder_tab(df, label):
    custom = st.session_state.setdefault("custom_rules", [])
    columns = list(df.columns)

    b1, b2, b3 = st.columns(3)
    column = b1.selectbox("Column", columns, key="b_col")
    rule_type = b2.selectbox("Rule type", BUILDER_TYPES, key="b_type")
    severity = b3.selectbox("Severity", ["High", "Medium", "Low"], index=1, key="b_sev")
    st.caption(TYPE_HELP[rule_type])

    rule = {"column": column, "type": rule_type, "severity": severity}
    if rule_type == "allowed_values":
        text = st.text_input("Allowed values, separated by commas", key="b_allowed")
        rule["allowed_values"] = [v.strip() for v in text.split(",") if v.strip()]
    elif rule_type == "range":
        r1, r2 = st.columns(2)
        rule["min"] = r1.number_input("Minimum", value=0.0, key="b_min")
        rule["max"] = r2.number_input("Maximum", value=1000.0, key="b_max")
    elif rule_type == "regex":
        rule["pattern"] = st.text_input("Pattern (a regular expression)", value=r"[A-Z]{2}\d{4}", key="b_pat")
    elif rule_type == "date_format":
        rule["format"] = st.text_input("Date format", value="%Y-%m-%d", key="b_fmt")
    elif rule_type == "cross_column":
        x1, x2, x3 = st.columns(3)
        first = x1.selectbox("First column", columns, key="b_left1")
        operator = x2.selectbox("Operator", ["multiply", "add", "subtract", "divide"], key="b_op")
        second = x3.selectbox("Second column", columns, index=min(1, len(columns) - 1), key="b_left2")
        rule.update({"left": [first, second], "operator": operator, "tolerance": 0.01})

    if st.button("Add this rule"):
        custom.append(rule)
        st.rerun()

    if custom:
        st.markdown("**My rules**")
        show_table(_rules_table(custom), height=200)
        r1, r2, _ = st.columns([1, 1, 3])
        if r1.button("Run my rules", type="primary"):
            _store(custom, df, f"{label} with my rules")
        if r2.button("Clear my rules"):
            st.session_state["custom_rules"] = []
            st.rerun()


def render(ctx: Context):
    page_header("Quality Rules", "Check your data against rules. Run saved rule sets, let DataGuard suggest "
                                 "rules for you, or build your own.")
    df, default_set, label = _choose_dataset()
    if df is None:
        st.info("Upload a file to continue.")
        return

    st.caption(f"{len(df):,} rows and {len(df.columns)} columns.")
    tabs = st.tabs(["Saved rule sets", "Suggest rules for me", "Build my own rule"])
    with tabs[0]:
        _saved_tab(df, default_set, label)
    with tabs[1]:
        _suggest_tab(df, label)
    with tabs[2]:
        _builder_tab(df, label)
    _show_result()
