"""Reconciliation page: compare two files, see what matters first, and why."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from core.alerts import alert_if_needed, configured_channels
from core.pipeline import DEFAULT_HIGH, DEFAULT_MEDIUM, load_pipeline_files, run_pipeline
from core.reconciliation import ReconConfig, Status
from core.root_cause import FINDING_COLUMNS
from core.utils import find_column, read_any
from views.common import (STATUS_COLORS, Context, badge, download_buttons, get_pipeline_configs,
                          page_header, pipeline_config, score_color, show_table)

MAX_ROWS_SHOWN = 5000


@st.cache_data(show_spinner=False)
def _load_configured_files(name: str):
    return load_pipeline_files(pipeline_config(name))


def _parse_timing_rules(text: str) -> list[tuple[str, str]]:
    rules = []
    for line in text.splitlines():
        if "->" in line:
            left, right = line.split("->", 1)
            if left.strip() and right.strip():
                rules.append((left.strip(), right.strip()))
    return rules


def _upload_ui():
    """Let the user upload any two files and say how to compare them."""
    left, right = st.columns(2)
    source_file = left.file_uploader("Source file (for example your orders)",
                                     type=["csv", "xlsx", "xls"], key="up_source")
    target_file = right.file_uploader("Target file (for example payments)",
                                      type=["csv", "xlsx", "xls"], key="up_target")
    if not (source_file and target_file):
        st.info("Upload both files to continue. CSV and Excel files are supported.")
        return None, None, None

    source, target = read_any(source_file), read_any(target_file)
    st.success(f"Source: {len(source):,} rows, {len(source.columns)} columns.   "
               f"Target: {len(target):,} rows, {len(target.columns)} columns.")

    src_cols, tgt_cols = list(source.columns), list(target.columns)
    guess_src = find_column(source, ["order_id", "id", "key", "invoice", "reference"]) or src_cols[0]
    guess_tgt = find_column(target, [guess_src, "order_id", "id", "key", "reference"]) or tgt_cols[0]

    st.markdown("##### 1. Which column identifies a record?")
    k1, k2 = st.columns(2)
    key_source = k1.selectbox("Key column in source", src_cols, index=src_cols.index(guess_src))
    key_target = k2.selectbox("Key column in target", tgt_cols, index=tgt_cols.index(guess_tgt))

    st.markdown("##### 2. Which columns should be compared?")
    candidates = [c for c in src_cols if c != key_source]
    defaults = [c for c in candidates if c in tgt_cols]
    chosen = st.multiselect("Columns to compare", candidates, default=defaults)

    column_map = {}
    if chosen:
        with st.expander("Column mapping (change only if the names differ between files)"):
            for col in chosen:
                index = tgt_cols.index(col) if col in tgt_cols else 0
                column_map[col] = st.selectbox(f"'{col}' in source is called ... in target",
                                               tgt_cols, index=index, key=f"map_{col}")

    st.markdown("##### 3. Rules for what counts as a real difference")
    options = ["(none)"] + chosen
    amount_guess = find_column(source[chosen] if chosen else source,
                               ["amount", "order_amount", "total", "price", "value"])
    status_guess = find_column(source[chosen] if chosen else source, ["status", "state"])
    a1, a2 = st.columns(2)
    amount_column = a1.selectbox("Amount column (for Money-at-Risk and tolerance)", options,
                                 index=options.index(amount_guess) if amount_guess in options else 0)
    status_column = a2.selectbox("Status column (for timing rules)", options,
                                 index=options.index(status_guess) if status_guess in options else 0)

    t1, t2, t3 = st.columns(3)
    abs_tol = t1.number_input("Ignore amount differences up to", min_value=0.0, value=1.0, step=0.5)
    pct_tol = t2.number_input("... or up to this percent", min_value=0.0, value=0.0, step=0.1)
    prefix = t3.text_input("Remove this prefix from keys", value="", placeholder="^ORD-",
                           help="A regular expression. Example: ^ORD- turns ORD-1005 into 1005.")
    timing_text = st.text_area(
        "Timing rules: one per line, written as  SourceStatus -> TargetStatus",
        value="", height=80, placeholder="Completed -> Pending",
        help="A pair listed here is treated as a delay, not an error.")
    name = st.text_input("Name for this pipeline (used when saving tickets)", value="custom_reconciliation")

    if not chosen:
        st.warning("Choose at least one column to compare.")
        return None, None, None

    cfg = ReconConfig(
        key_source=key_source, key_target=key_target, column_map=column_map,
        amount_column=None if amount_column == "(none)" else amount_column,
        status_column=None if status_column == "(none)" else status_column,
        abs_tolerance=abs_tol, pct_tolerance=pct_tol, prefix_regex=prefix or None,
        timing_rules=_parse_timing_rules(timing_text), name=name or "custom_reconciliation",
    )
    return cfg, source, target


def _kpis(ctx: Context, out):
    stats, risk, health = out.recon.stats, out.risk, out.health
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Health score", f"{health['score']:.1f}", border=True)
    c2.metric(
    "Current run risk",
    ctx.fmt(risk["total_risk"]),
    border=True,
    help="Risk calculated from the current reconciliation run."
)
    c3.metric("Exceptions", f"{stats['exceptions']:,}", border=True)
    c4.metric("Match rate", f"{stats['match_rate']:.1f}%", border=True)
    c5.metric("Within tolerance", f"{stats['within_tolerance']:,}", border=True,
              help="Small differences that were ignored because of the tolerance setting.")
    st.markdown(
        f"{badge(health['label'], score_color(health['score']))} &nbsp; "
        f"{risk['high']} high, {risk['medium']} medium and {risk['low']} low priority exceptions. "
        f"The 20 worst exceptions hold **{risk['top20_share']:.0f}%** of the money at risk.",
        unsafe_allow_html=True,
    )


def _priority_tab(ctx: Context, out):
    exceptions = out.exceptions.sort_values("Risk Score", ascending=False)
    if exceptions.empty:
        st.success("No exceptions found. All records match.")
        return

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Work on these first**")
        cols = ["Record Key", "Status", "Priority", "Risk Score", "Exposure", "Fields Different", "Details"]
        show_table(exceptions[cols].head(25), height=420)
    with right:
        st.markdown("**Money at risk by exception type**")
        chart = out.risk_by_status
        fig = px.bar(chart, x="Risk Score", y="Status", orientation="h", color="Status",
                     color_discrete_map=STATUS_COLORS, text_auto=".3s")
        fig.update_layout(showlegend=False, height=420, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    st.caption("Risk score = exposure (the money affected) x severity (how serious this type of issue is). "
               "Priority levels use the thresholds in the settings above.")


def _root_cause_tab(ctx: Context, out):
    findings = out.findings
    if findings.empty:
        st.info("No clear pattern was found. The exceptions look unrelated to each other.")
        return
    st.markdown("**Patterns found in the exceptions.** Fixing one cause can remove many exceptions at once.")
    show_table(findings[FINDING_COLUMNS], height=380)

    labels = [f"{i + 1}. {row['Finding']} ({row['Records']} records)" for i, row in findings.iterrows()]
    pick = st.selectbox("Show the records behind a finding", range(len(findings)),
                        format_func=lambda i: labels[i])
    keys = set(findings.loc[pick, "_keys"])
    st.info(findings.loc[pick, "Likely cause and next step"])
    subset = out.results[out.results["Record Key"].isin(keys)]
    show_table(subset[["Record Key", "Status", "Risk Score", "Details"]], height=300)


def _all_results_tab(out):
    results = out.results
    f1, f2 = st.columns([2, 1])
    wanted = f1.multiselect("Show these statuses", sorted(results["Status"].unique()),
                            default=[s for s in sorted(results["Status"].unique()) if s != Status.MATCHED])
    search = f2.text_input("Search record key")
    view = results[results["Status"].isin(wanted)]
    if search:
        view = view[view["Record Key"].astype(str).str.contains(search, case=False, regex=False)]
    view = view.sort_values("Risk Score", ascending=False)
    st.caption(f"{len(view):,} records" + (f" (showing the first {MAX_ROWS_SHOWN:,}; download for all)"
                                         if len(view) > MAX_ROWS_SHOWN else ""))
    show_table(view.head(MAX_ROWS_SHOWN), height=420)
    download_buttons(view, "dataguard_results", "all_results")



def _diffs_tab(out):
    diffs = out.recon.diffs.copy()

    if diffs.empty:
        st.success("No field differences found. All compared fields match.")
        return

    st.markdown("#### Field-level differences")
    st.caption(
        "Compare actual source and target values to investigate data discrepancies."
    )

    c1, c2 = st.columns([2, 1])

    with c1:
        fields = sorted(diffs["Field"].dropna().unique().tolist())
        selected_fields = st.multiselect(
            "Filter by field",
            fields,
            default=fields,
            key="diff_fields_filter",
        )

    with c2:
        search_key = st.text_input(
            "Search record key",
            key="diff_record_search",
            placeholder="Enter a record ID",
        )

    view = diffs[diffs["Field"].isin(selected_fields)].copy()

    if search_key.strip():
        view = view[
            view["Record Key"]
            .astype(str)
            .str.contains(search_key.strip(), case=False, regex=False, na=False)
        ]

    st.metric("Field differences shown", f"{len(view):,}")

    display_columns = [
        "Record Key",
        "Field",
        "Source Value",
        "Target Value",
        "Difference",
        "Difference %",
        "Is Timing",
    ]

    available_columns = [
        column for column in display_columns if column in view.columns
    ]

    
    if view.empty:
        st.info("No differences match your selected filters.")
        return

    # Create a display-only copy; do not change reconciliation data.
    display_view = view[available_columns].head(MAX_ROWS_SHOWN).copy()

    # Format numeric differences for a clean, professional table.
    if "Difference" in display_view.columns:
        display_view["Difference"] = display_view["Difference"].map(
            lambda value: (
                f"{value:,.2f}"
                if pd.notna(value) and isinstance(value, (int, float))
                else value
            )
        )

    if "Difference %" in display_view.columns:
        display_view["Difference %"] = display_view["Difference %"].map(
            lambda value: (
                f"{value:.2f}%"
                if pd.notna(value) and isinstance(value, (int, float))
                else value
            )
        )

    show_table(display_view, height=420)


    if len(view) > MAX_ROWS_SHOWN:
        st.caption(
            f"Showing the first {MAX_ROWS_SHOWN:,} rows. "
            "Download the report to review all matching differences."
        )

    download_buttons(view, "dataguard_field_differences", "diffs")



def _health_tab(out):
    breakdown = out.health["breakdown"]
    left, right = st.columns([2, 3])
    with left:
        show_table(breakdown, height=200)
        st.caption("Score = sum of Points. Timing delays count as half a match. Matching is strict: every 1% of "
                   "records with an exception costs 3 points of the Matching part.")
        if not out.rule_scorecard.empty:
            st.markdown("**Quality rules on the source file**")
            show_table(out.rule_scorecard, height=240)
    with right:
        fig = px.bar(breakdown, x="Part", y="Value %", text="Value %", range_y=[0, 105])
        fig.update_traces(marker_color="#3b7ddd", texttemplate="%{text:.1f}%")
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")


def _save_section(ctx: Context, out):
    st.divider()
    st.markdown("#### Save this run and create tickets")
    st.caption("Every exception becomes a ticket that can be assigned and tracked. "
               "Tickets that no longer appear are closed automatically.")
    c1, c2 = st.columns([1, 2])
    threshold = c1.number_input("Alert if health score is below", 0, 100, 80)
    send_alert = c2.checkbox(
        "Send an alert if the score is below the limit",
        value=bool(configured_channels()),
        help="Needs Telegram or a webhook in your .env file. See the Health & Alerts page.")

    if st.button("Save run and create tickets", type="primary"):
        saved = ctx.workflow.save_run(
            pipeline=out.config.name, with_risk=out.results, stats=out.recon.stats,
            health_score=out.health["score"], rule_pass_rate=out.rule_pass_rate,
            total_risk=out.risk["total_risk"], user=ctx.user, note="saved from the app")
        st.success(f"Run {saved['run_id']} saved: {saved['new']} new tickets, "
                   f"{saved['still_present']} still present, {saved['reopened']} re-opened, "
                   f"{saved['auto_resolved']} resolved automatically. Open the Exceptions page to work on them.")
        if send_alert:
            result = alert_if_needed(out.config.name, out.health["score"], out.health["label"],
                                     threshold, out.recon.stats["exceptions"], ctx.fmt(out.risk["total_risk"]))
            if result is None:
                st.info(f"Health score is {out.health['score']}, above the limit of {threshold}. No alert sent.")
            else:
                st.warning(f"Alert result: {result}")


def render(ctx: Context):
    page_header("Reconciliation",
                "Compare two systems, see which differences matter most, and find out why they happen.")

    configs = get_pipeline_configs()
    mode = st.radio("Data source", ["Use a configured pipeline", "Upload my own files"], horizontal=True)

    if mode == "Use a configured pipeline":
        name = st.selectbox("Pipeline", list(configs))
        cfg = pipeline_config(name)
        source, target = _load_configured_files(name)
        st.caption(cfg.description)
        with st.expander("How this pipeline compares the data"):
            st.write(f"**Key:** `{cfg.key_source}` (source) and `{cfg.key_target}` (target)"
                     + (f", prefix removed with `{cfg.prefix_regex}`" if cfg.prefix_regex else ""))
            st.write("**Compared columns:** " + ", ".join(f"`{s}` to `{t}`" for s, t in cfg.column_map.items()))
            st.write(f"**Tolerance:** amounts up to {cfg.abs_tolerance:g} apart are not errors.")
            if cfg.timing_rules:
                st.write("**Timing rules:** " + ", ".join(f"{a} then {b}" for a, b in cfg.timing_rules))
            st.write(f"**Files:** `{cfg.source_file}` ({len(source):,} rows) and "
                     f"`{cfg.target_file}` ({len(target):,} rows)")
    else:
        cfg, source, target = _upload_ui()

    if cfg is None:
        return

    with st.expander("Priority settings"):
        p1, p2 = st.columns(2)
        high = p1.number_input("High priority when risk score is at least", 0.0, value=float(DEFAULT_HIGH), step=100.0)
        medium = p2.number_input("Medium priority when risk score is at least", 0.0, value=float(DEFAULT_MEDIUM), step=50.0)

    if st.button("Run reconciliation", type="primary"):
        try:
            with st.spinner("Comparing records..."):
                st.session_state["recon_out"] = run_pipeline(cfg, source, target, high, medium)
        except ValueError as error:
            st.error(str(error))
            return

    out = st.session_state.get("recon_out")
    if out is None:
        st.info("Press **Run reconciliation** to start.")
        return

    st.divider()
    st.subheader(f"Results for: {out.config.name}")
    for warning in out.warnings:
        st.warning(warning)
    _kpis(ctx, out)

    tabs = st.tabs(["Priority list", "Why it happened", "All results", "Field differences", "Health breakdown"])
    with tabs[0]:
        _priority_tab(ctx, out)
    with tabs[1]:
        _root_cause_tab(ctx, out)
    with tabs[2]:
        _all_results_tab(out)
    with tabs[3]:
        _diffs_tab(out)
    with tabs[4]:
        _health_tab(out)

    _save_section(ctx, out)
