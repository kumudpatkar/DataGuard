"""Health & Alerts page: watch the score over time and set up alerts."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core import config
from core.alerts import build_message, configured_channels, send_alert
from core.health import WEIGHTS
from views.common import Context, page_header, score_color, show_table


def render(ctx: Context):
    page_header("Health & Alerts",
                "A falling health score is an early warning that something broke upstream.")
    runs = ctx.workflow.list_runs()

    if runs.empty:
        st.info("No runs are saved yet. Run a pipeline on the **Reconciliation** page and save it. "
                "Every saved run adds a point to the trend chart.")
    else:
        pipeline = st.selectbox("Pipeline", sorted(runs["Pipeline"].unique()))
        data = runs[runs["Pipeline"] == pipeline]
        latest = data.iloc[-1]

        c1, c2, c3, c4 = st.columns(4)
        delta = None
        if len(data) > 1:
            delta = round(float(latest["Health Score"] - data.iloc[-2]["Health Score"]), 1)
        c1.metric("Latest health score", f"{latest['Health Score']:.1f}", delta=delta, border=True)
        c2.metric("Match rate", f"{latest['Match Rate %']:.1f}%", border=True)
        c3.metric("Money at risk", ctx.fmt(latest["Money at Risk"]), border=True)
        c4.metric("Runs saved", len(data), border=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data["Run At"], y=data["Health Score"], mode="lines+markers",
                                 name="Health score", line=dict(color=score_color(latest["Health Score"]), width=3)))
        fig.add_trace(go.Scatter(x=data["Run At"], y=data["Match Rate %"], mode="lines",
                                 name="Match rate %", line=dict(dash="dot")))
        fig.add_hline(y=80, line_dash="dash", line_color="gray", annotation_text="alert limit (80)")
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(range=[0, 105]),
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")

        with st.expander("Run history"):
            show_table(data.sort_values("Run", ascending=False), height=260)

    st.divider()
    st.subheader("Alerts")
    channels = configured_channels()
    if channels:
        st.success("Configured channels: " + ", ".join(channels))
    else:
        st.warning("No alert channel is configured. Add Telegram or a webhook URL to your `.env` file "
                   "(see `.env.example`), then restart the app.")

    threshold = st.slider("Send an alert when the health score is below", 0, 100,
                          config.DEFAULT_HEALTH_ALERT_THRESHOLD)
    st.caption("Preview of the message:")
    st.code(build_message("orders_vs_payments", threshold - 5.0, "At risk", threshold, 120,
                          ctx.fmt(45000)), language="text")
    if st.button("Send a test alert", disabled=not channels):
        st.write(send_alert("DataGuard test alert. If you can read this, alerts are working."))

    st.divider()
    st.subheader("How the score is calculated")
    st.write(" + ".join(f"{name} {int(w * 100)}%" for name, w in WEIGHTS.items()))
    st.caption("Matching counts timing delays as half a match, and every 1% of records with an exception "
               "costs 3 points of the Matching part (99% match = 97, 95% = 85, 90% = 70, 80% = 40). "
               "90 and above is Healthy, 75 to 90 Needs attention, below 75 At risk.")

    with st.expander("Run automatically every day"):
        st.markdown(
            "The same analysis can run without opening the app. It saves the run, creates tickets, "
            "exports a CSV and sends an alert if the score is low.")
        st.code("python scripts/run_daily.py --pipeline orders_vs_payments --threshold 80", language="bash")
        st.markdown("**Windows Task Scheduler:** run `.venv\\Scripts\\python.exe scripts\\run_daily.py` "
                    "every morning, with \"Start in\" set to the project folder.")
        st.markdown("**Linux or macOS (cron):**")
        st.code("0 8 * * *  cd /path/to/DataGuard && .venv/bin/python scripts/run_daily.py", language="bash")
