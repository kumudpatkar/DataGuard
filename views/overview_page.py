
"""Overview page: one screen that shows how trustworthy the data is today."""
from __future__ import annotations
import pandas as pd

import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from core.pipeline import load_pipeline_files, run_pipeline
from core.retail import kpi_trust, revenue_bridge
from views.common import (
    Context,
    badge,
    get_pipeline_configs,
    get_retail,
    page_header,
    pipeline_config,
    score_color,
    show_table,
)


def _run_demo(ctx: Context):
    name = list(get_pipeline_configs())[0]
    cfg = pipeline_config(name)
    source, target = load_pipeline_files(cfg)
    out = run_pipeline(cfg, source, target)

    ctx.workflow.save_run(
        name,
        out.results,
        out.recon.stats,
        out.health["score"],
        out.rule_pass_rate,
        out.risk["total_risk"],
        user=ctx.user,
        note="demo run",
    )

def _reconciliation_summary(stats: dict):
    """Display reconciliation counts from the actual reconciliation engine."""
    st.markdown("### Reconciliation summary")
    st.caption("Record counts from the latest reconciliation run.")

    items = [
        ("Matched", "matched"),
        ("Mismatches", "mismatch"),
        ("Timing differences", "timing"),
        ("Missing in target", "missing_in_target"),
        ("Missing in source", "missing_in_source"),
        ("Duplicates in source", "duplicate_source"),
        ("Duplicates in target", "duplicate_target"),
        ("Records with missing keys", "missing_key"),
    ]

    rows = [
        {"Reconciliation status": label, "Records": int(stats.get(key, 0))}
        for label, key in items
    ]

    show_table(pd.DataFrame(rows), height=330)


def _reconciliation_section(ctx: Context):
    st.subheader("Reconciliation health")
    runs = ctx.workflow.list_runs()

    if runs.empty:
        st.info(
            "No reconciliation has been saved yet. Run the demo to see "
            "DataGuard working on realistic order and payment data, or go "
            "to **Reconciliation** to use your own files."
        )

        if st.button("Run the demo now", type="primary"):
            with st.spinner("Comparing orders with payments..."):
                _run_demo(ctx)
            st.rerun()

        return

    pipeline = st.selectbox(
        "Pipeline",
        sorted(runs["Pipeline"].unique()),
        key="overview_pipeline",
    )

    data = runs[runs["Pipeline"] == pipeline]
    latest = data.iloc[-1]

    
    # Detailed reconciliation summary — calculate only when requested.
    summary_key = f"overview_recon_stats_{pipeline}"

    if st.button(
        "Refresh detailed reconciliation summary",
        key="refresh_recon_summary",
    ):
        try:
            cfg = pipeline_config(pipeline)
            source, target = load_pipeline_files(cfg)

            with st.spinner("Calculating reconciliation details..."):
                summary_out = run_pipeline(cfg, source, target)

            st.session_state[summary_key] = summary_out.recon.stats
            st.success("Detailed reconciliation summary updated.")

        except (ValueError, FileNotFoundError) as error:
            st.error(f"Could not calculate the summary: {error}")

    if summary_key in st.session_state:
        _reconciliation_summary(st.session_state[summary_key])
    else:
        st.info(
            "Select 'Refresh detailed reconciliation summary' "
            "to calculate the record-level breakdown."
        )


    counts = ctx.workflow.status_counts(pipeline)
    open_tickets = counts.get("Open", 0) + counts.get("Investigating", 0)

    # Executive KPI cards
    c1, c2, c3, c4, c5 = st.columns(5, gap="medium")

    with c1:
        st.metric(
            label="HEALTH SCORE",
            value=f"{latest['Health Score']:.1f}/100",
            border=True,
            help="Overall data and reconciliation health score.",
        )

    with c2:
        st.metric(
            label="MONEY AT RISK",
            value=ctx.fmt(ctx.workflow.open_risk(pipeline)),
            border=True,
             help="Total saved risk score for unresolved tickets. This may differ from the current reconciliation run.",
        )

    with c3:
        st.metric(
            label="OPEN TICKETS",
            value=f"{open_tickets:,}",
            border=True,
            help="Exceptions that are open or under investigation.",
        )

    with c4:
        st.metric(
            label="MATCH RATE",
            value=f"{latest['Match Rate %']:.1f}%",
            border=True,
            help="Matched result records divided by total result records.",
        )

    with c5:
        st.metric(
            label="ROW MATCH RATE",
            value=f"{latest['Row Match Rate %']:.1f}%",
            border=True,
            help="Matched records divided by the larger source or target row count.",
        )

    # Current pipeline health status
    health_score = latest["Health Score"]
    label = (
        "Healthy"
        if health_score >= 90
        else "Needs attention"
        if health_score >= 75
        else "At risk"
    )

    st.markdown(
        f"{badge(label, score_color(health_score))} "
        f"&nbsp; Last run: {latest['Run At']} by {latest['Run By']}",
        unsafe_allow_html=True,
    )

    # High-risk exceptions and health trend
    left, right = st.columns([2, 3])

    with left:
        st.markdown("**Top open tickets by money at risk**")

        top = ctx.workflow.list_exceptions(
            pipeline, ["Open", "Investigating"]
        ).head(6)

        if top.empty:
            st.success("No open tickets.")
        else:
            display_top = top[
                ["Ticket", "Record Key", "Issue", "Risk Score", "Status"]
            ].copy()

            # Format the risk value only if it is numeric.
            # Risk Score may be a score rather than a monetary amount.
            def format_risk(value):
                if value is None:
                    return "—"

                try:
                    if value != value:  # Handle NaN
                        return "—"
                    float(value)
                except (TypeError, ValueError):
                    return str(value)

                return ctx.fmt(value)

            display_top["Risk Score"] = display_top["Risk Score"].map(
                format_risk
            )

            show_table(display_top, height=300)

    with right:
        st.markdown("**Health score over time**")

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=data["Run At"],
                y=data["Health Score"],
                mode="lines+markers",
                name="Health score",
                line=dict(
                    color="#168AAD",
                    width=3,
                    shape="spline",
                ),
                marker=dict(
                    size=8,
                    color="#168AAD",
                    line=dict(color="#FFFFFF", width=2),
                ),
                fill="tozeroy",
                fillcolor="rgba(22, 138, 173, 0.08)",
                hovertemplate=(
                    "<b>Reconciliation Health</b><br>"
                    "Run time: %{x}<br>"
                    "Health score: %{y:.1f}/100"
                    "<extra></extra>"
                ),
            )
        )

        fig.add_hline(
            y=90,
            line_dash="dash",
            line_color="#16A34A",
            annotation_text="Healthy target: 90",
            annotation_position="top left",
        )

        fig.update_layout(
            height=320,
            margin=dict(l=10, r=15, t=35, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(
                family="Arial, sans-serif",
                color="#334155",
                size=12,
            ),
            showlegend=False,
            hovermode="x unified",
            yaxis=dict(
                title="Health score",
                range=[0, 105],
                gridcolor="#E5EDF5",
                zeroline=False,
            ),
            xaxis=dict(
                title=None,
                showgrid=False,
                tickangle=-20,
            ),
        )

        st.plotly_chart(fig, width="stretch")

        if len(data) < 2:
            st.caption("Save more reconciliation runs to see a trend.")


def _retail_section(ctx: Context):
    st.subheader("Retail data trust")

    df, info = get_retail()
    bridge = revenue_bridge(df).set_index("Step")["Amount"]
    trust = kpi_trust(df)

    c1, c2, c3 = st.columns(3, gap="medium")

    with c1:
        st.metric(
            "Net revenue",
            ctx.retail_money(bridge["Net revenue"]),
            border=True,
        )

    with c2:
        st.metric(
            "Sales with no customer ID",
            f"{trust['unidentified_pct']:.1f}%",
            border=True,
            help="Share of sales value that cannot be linked to a customer.",
        )

    with c3:
        st.metric(
            "KPI trust score",
            f"{trust['trust_pct']:.0f}%",
            trust["level"],
            delta_color="off",
            border=True,
        )

    if info["is_sample"]:
        st.caption(
            f"Based on the sample file ({len(df):,} rows). "
            "Put your full file at data/data.csv to analyse everything."
        )


def render(ctx: Context):
    page_header(
        "DataGuard",
        "A data trust layer: it finds differences between systems, explains "
        "why they happen, shows how much money they put at risk, and tracks "
        "them until they are fixed.",
    )

    _reconciliation_section(ctx)

    st.divider()

    _retail_section(ctx)

    st.divider()

    with st.expander("What can I do in DataGuard?"):
        st.markdown(
            "- **Reconciliation:** compare any two files, ignore harmless "
            "differences, and see the money at risk.\n"
            "- **Why it happened:** patterns such as a fixed gateway fee or "
            "one payment method that never syncs.\n"
            "- **Exceptions:** assign, comment on and close tickets, with a "
            "full audit trail.\n"
            "- **Quality Rules:** run saved rules, get rules suggested "
            "automatically, or build your own.\n"
            "- **Health & Alerts:** a score over time, alerts, and a script "
            "for daily automation.\n"
            "- **Retail Analytics:** a revenue bridge that adds up, and a "
            "score for how far to trust the numbers."
        )
