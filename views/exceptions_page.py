"""Exceptions page: assign, discuss and close tickets."""
from __future__ import annotations

import plotly.express as px
import streamlit as st
import pandas as pd

from core.workflow import ACTIVE_STATUSES, STATUSES
from views.common import PRIORITY_COLORS, Context, page_header, show_table


def render(ctx: Context):
    page_header("Exceptions",
                "Every exception is a ticket. Assign an owner, discuss it, and close it. "
                "Every change is recorded.")
    wf = ctx.workflow

    all_tickets = wf.list_exceptions()
    if all_tickets.empty:
        st.info("There are no tickets yet. Go to **Reconciliation**, run a pipeline, and press "
                "**Save run and create tickets**. Or press the button below to try it with the demo data.")
        if st.button("Run the demo pipeline and create tickets", type="primary"):
            from core.pipeline import load_pipeline_files, run_pipeline
            from views.common import get_pipeline_configs, pipeline_config
            name = list(get_pipeline_configs())[0]
            cfg = pipeline_config(name)
            source, target = load_pipeline_files(cfg)
            out = run_pipeline(cfg, source, target)
            wf.save_run(name, out.results, out.recon.stats, out.health["score"], out.rule_pass_rate,
                        out.risk["total_risk"], user=ctx.user, note="demo")
            st.rerun()
        return

    # ---------------------------------------------------------------- filters
    pipelines = sorted(all_tickets["Pipeline"].unique())
    f1, f2, f3, f4 = st.columns(4)
    pipeline = f1.selectbox("Pipeline", pipelines)
    statuses = f2.multiselect("Status", STATUSES, default=list(ACTIVE_STATUSES))
    priorities = f3.multiselect("Priority", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    owners = sorted(x for x in all_tickets["Assigned To"].unique() if x)
    owner = f4.selectbox("Owner", ["Anyone"] + owners)

    tickets = wf.list_exceptions(pipeline, statuses, priorities, None if owner == "Anyone" else owner)

    counts = wf.status_counts(pipeline)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open", counts.get("Open", 0), border=True)
    m2.metric("Investigating", counts.get("Investigating", 0), border=True)
    m3.metric("Closed (fixed, ignored, auto)",
              counts.get("Fixed", 0) + counts.get("Ignored", 0) + counts.get("Resolved (auto)", 0), border=True)
    m4.metric("Money still at risk", ctx.fmt(wf.open_risk(pipeline)), border=True)

    if tickets.empty:
        st.success("No tickets match these filters.")
        return

    # ----------------------------------------------------------- ticket table
    st.markdown("**Select one or more tickets, then apply an action below.**")
    columns = ["Ticket", "Record Key", "Issue", "Priority", "Risk Score", "Status", "Assigned To", "Details"]
    event = st.dataframe(tickets[columns], width="stretch", hide_index=True, height=360,
                         on_select="rerun", selection_mode="multi-row", key="ticket_table")
    selected_rows = event.selection.rows if event and event.selection else []
    selected_ids = [int(tickets.iloc[i]["Ticket"]) for i in selected_rows]

    with st.container(border=True):
        st.markdown(f"**Bulk action** ({len(selected_ids)} selected)")
        a1, a2, a3 = st.columns([1, 1, 1])
        new_status = a1.selectbox("Set status", ["(no change)"] + STATUSES)
        new_owner = a2.text_input("Assign to", placeholder="Name of the owner")
        a3.write("")
        a3.write("")
        if a3.button("Apply to selected", disabled=not selected_ids):
            changed = wf.update_exceptions(
                selected_ids, ctx.user,
                status=None if new_status == "(no change)" else new_status,
                assigned_to=new_owner.strip() if new_owner.strip() else None)
            st.success(f"{changed} ticket(s) updated.")
            st.rerun()

    # ---------------------------------------------------------- ticket detail
    st.markdown("#### Ticket detail")
    ticket_id = st.selectbox(
        "Open a ticket", tickets["Ticket"].tolist(),
        index=(tickets["Ticket"].tolist().index(selected_ids[0]) if selected_ids else 0),
        format_func=lambda t: f"#{t}  -  {tickets.loc[tickets['Ticket'] == t, 'Record Key'].iloc[0]}  "
                              f"({tickets.loc[tickets['Ticket'] == t, 'Issue'].iloc[0]})")
    row = tickets[tickets["Ticket"] == ticket_id].iloc[0]

    left, right = st.columns([3, 2])
    with left:
        st.write(f"**Issue:** {row['Issue']}   |   **Priority:** {row['Priority']}   |   "
                 f"**Status:** {row['Status']}   |   **Owner:** {row['Assigned To'] or 'not assigned'}")
        st.write(f"**Money at risk:** {ctx.fmt(row['Risk Score'])} (exposure {ctx.fmt(row['Exposure'])})")
        st.write(f"**What is wrong:** {row['Details']}")
        st.caption(f"First seen in run {row['First Run']}, last seen in run {row['Last Run']}, "
                   f"updated {row['Updated']}")
    with right:
        st.markdown("**Comments**")
        comments = wf.list_comments(int(ticket_id))
        if comments.empty:
            st.caption("No comments yet.")
        else:
            for _, c in comments.iterrows():
                st.markdown(f"**{c['Who']}** <span style='color:gray;font-size:0.8rem'>{c['When']}</span>  \n{c['Comment']}",
                            unsafe_allow_html=True)
        with st.form(f"comment_form_{ticket_id}", clear_on_submit=True):
            text = st.text_area("Add a comment", height=80, label_visibility="collapsed",
                                placeholder="Write what you found or what you did...")
            if st.form_submit_button("Add comment"):
                wf.add_comment(int(ticket_id), ctx.user, text)
                st.rerun()

       
    
    # ------------------------------------------------------ resolution notes
   
    st.markdown("#### Resolution notes")
    st.caption(
        "Record why this ticket was fixed or ignored. "
        "Saving a note does not change the ticket status."
    )

    saved_note = row.get("Resolution Note", "")
    if pd.isna(saved_note):
        saved_note = ""

    with st.form(f"resolution_form_{ticket_id}", clear_on_submit=False):
        resolution_note = st.text_area(
            "Resolution note",
            value=str(saved_note),
            height=120,
            placeholder=(
                "Example: Compared the payment gateway record, "
                "confirmed the amount discrepancy, and documented the correction."
            ),
            key=f"resolution_note_{ticket_id}",
        )

        save_resolution = st.form_submit_button("Save resolution note")

        
        if save_resolution:
            if not resolution_note.strip():
                st.warning("Please enter a resolution note before saving.")
            else:
                try:
                    success = wf.save_resolution_note(
                        int(ticket_id),
                        ctx.user,
                        resolution_note,
                    )

                    if success:
                        st.success("Resolution note saved successfully.")
                    else:
                        st.error(
                            "Save failed: ticket was not found in the database."
                        )

                except Exception as exc:
                    st.error(f"Error saving resolution note: {exc}")



    # ------------------------------------------------------------ extra views
    with st.expander("Tickets by priority"):
        chart = tickets.groupby("Priority", as_index=False).agg(Tickets=("Ticket", "count"),
                                                                Risk=("Risk Score", "sum"))
        fig = px.bar(chart, x="Priority", y="Risk", color="Priority", text="Tickets",
                     color_discrete_map=PRIORITY_COLORS)
        fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

    with st.expander("Audit log (who changed what, and when)"):
        show_table(wf.audit_log(300), height=300)
