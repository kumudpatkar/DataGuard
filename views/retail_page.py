"""Retail Analytics page: a trustworthy view of the sales data."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.retail import (column_profile, completeness, kpi_trust, line_type_summary, monthly_sales,
                         revenue_bridge, sales_by_country, top_products)
from views.common import Context, badge, download_buttons, get_retail, page_header, show_table

PAGE_SIZES = [25, 50, 100, 250]


def _convert(ctx: Context):
    """(factor, symbol) so charts show GBP or INR the same way as the text."""
    return (ctx.gbp_to_inr, "₹") if ctx.currency == "INR" else (1.0, "£")


def _filters(df):
    c1, c2 = st.columns([2, 2])
    countries = sorted(df["Country"].dropna().unique())
    chosen = c1.multiselect("Country", countries, placeholder="All countries")
    dates = df["InvoiceDate"].dropna()
    date_range = None
    if not dates.empty:
        date_range = c2.date_input("Invoice date range", value=(dates.min().date(), dates.max().date()),
                                   min_value=dates.min().date(), max_value=dates.max().date())
    view = df
    if chosen:
        view = view[view["Country"].isin(chosen)]
    if date_range and len(date_range) == 2:
        start, end = date_range
        view = view[(view["InvoiceDate"].dt.date >= start) & (view["InvoiceDate"].dt.date <= end)]
    return view


def _bridge_tab(ctx: Context, view):
    factor, symbol = _convert(ctx)
    bridge = revenue_bridge(view)
    plot = bridge.copy()
    plot["Amount"] = plot["Amount"] * factor

    fig = go.Figure(go.Waterfall(
        x=plot["Step"], y=plot["Amount"],
        measure=["relative"] * (len(plot) - 1) + ["total"],
        text=[f"{symbol}{v:,.0f}" for v in plot["Amount"]], textposition="outside",
        connector={"line": {"color": "gray"}},
        increasing={"marker": {"color": "#2e9e6b"}}, decreasing={"marker": {"color": "#d9534f"}},
        totals={"marker": {"color": "#3b7ddd"}},
    ))
    fig.update_layout(height=430, margin=dict(l=0, r=0, t=20, b=0), showlegend=False,
                      xaxis=dict(tickangle=-20))
    st.plotly_chart(fig, width="stretch")

    table = bridge.copy()
    table["Amount"] = table["Amount"].map(ctx.retail_money)
    show_table(table, height=290)
    st.info("**Why this matters.** Gross sales, returns, postage and fees are shown separately and add up "
            "exactly to Net revenue. This is the single number used everywhere in DataGuard, so two "
            "screens can never show two different totals.")


def _trends_tab(ctx: Context, view):
    factor, symbol = _convert(ctx)
    monthly = monthly_sales(view)
    if monthly.empty:
        st.info("No dated sales in the selected range.")
        return
    plot = monthly.copy()
    for col in ("Gross Sales", "Returns", "Net Sales"):
        plot[col] = plot[col] * factor
    fig = px.line(plot, x="Month", y=["Gross Sales", "Net Sales", "Returns"], markers=True,
                  labels={"value": f"Amount ({symbol})", "variable": ""},
                  color_discrete_map={"Gross Sales": "#3b7ddd", "Net Sales": "#2e9e6b", "Returns": "#d9534f"})
    fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    show_table(plot, height=260)
    st.caption("The last month in the data is often incomplete. Do not read it as a drop in sales.")


def _products_tab(ctx: Context, view):
    factor, symbol = _convert(ctx)
    left, right = st.columns(2)
    with left:
        n = st.slider("Top products", 5, 25, 10)
        products = top_products(view, n)
        products["Sales"] = products["Sales"] * factor
        fig = px.bar(products.iloc[::-1], x="Sales", y="Description", orientation="h",
                     labels={"Sales": f"Sales ({symbol})", "Description": ""})
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption("Postage, fees and manual adjustments are excluded, so only real products appear.")
    with right:
        countries = sales_by_country(view, 12)
        countries["Sales"] = countries["Sales"] * factor
        st.markdown("**Sales by country**")
        fig = px.bar(countries.iloc[::-1], x="Sales", y="Country", orientation="h",
                     labels={"Sales": f"Sales ({symbol})", "Country": ""})
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=34, b=0))
        st.plotly_chart(fig, width="stretch")


def _trust_tab(ctx: Context, view):
    trust = kpi_trust(view)
    color = {"High": "#2e9e6b", "Medium": "#e0a800", "Low": "#d9534f"}[trust["level"]]
    st.markdown(f"### KPI trust score: {trust['trust_pct']:.1f}% &nbsp; {badge(trust['level'], color)}",
                unsafe_allow_html=True)
    st.write("This is the share of sales value that has an identified customer and passes the basic checks. "
             "It tells you how far you can rely on customer-level numbers such as repeat purchases.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Sales value with no customer ID", ctx.retail_money(trust["unidentified_value"]),
              f"{trust['unidentified_pct']:.1f}% of sales", delta_color="off", border=True)
    c2.metric("Sales value flagged for review", ctx.retail_money(trust["review_value"]),
              f"{trust['review_pct']:.1f}% of sales", delta_color="off", border=True)
    c3.metric("Data completeness", f"{completeness(view):.1f}%", border=True)

    left, right = st.columns(2)
    with left:
        st.markdown("**Money by line type**")
        summary = line_type_summary(view)
        summary["Sales"] = summary["Sales"].map(ctx.retail_money)
        show_table(summary, height=290)
    with right:
        st.markdown("**Why rows need review**")
        reasons = view.loc[view["NeedsReview"], "ReviewReason"].value_counts().reset_index()
        reasons.columns = ["Reason", "Rows"]
        if reasons.empty:
            st.success("No rows need review.")
        else:
            show_table(reasons, height=290)


def _explorer_tab(view):
    f1, f2, f3 = st.columns([2, 1, 1])
    search = f1.text_input("Search description, invoice, stock code or customer")
    types = f2.multiselect("Line type", sorted(view["LineType"].unique()))
    only_flagged = f3.checkbox("Only rows needing review")

    data = view
    if search:
        s = search.strip()
        mask = (data["Description"].str.contains(s, case=False, regex=False, na=False)
                | data["InvoiceNo"].str.contains(s, case=False, regex=False, na=False)
                | data["StockCode"].str.contains(s, case=False, regex=False, na=False)
                | data["CustomerID"].str.contains(s, case=False, regex=False, na=False))
        data = data[mask]
    if types:
        data = data[data["LineType"].isin(types)]
    if only_flagged:
        data = data[data["NeedsReview"]]

    p1, p2 = st.columns([1, 1])
    size = p1.selectbox("Rows per page", PAGE_SIZES, index=1)
    pages = max(1, -(-len(data) // size))
    page = p2.number_input("Page", 1, pages, 1)
    st.caption(f"{len(data):,} rows. Page {page} of {pages}.")
    columns = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice",
               "SalesAmount", "CustomerID", "Country", "LineType", "ReviewReason"]
    show_table(data[columns].iloc[(page - 1) * size: page * size], height=420)
    if len(data) <= 100_000:
        download_buttons(data[columns], "retail_filtered", "retail_explorer")
    else:
        st.caption("Narrow the filters to 100,000 rows or fewer to enable downloads.")


def render(ctx: Context):
    page_header("Retail Analytics", "Sales with a clear revenue bridge, product and country views, "
                                    "and a score that shows how far the numbers can be trusted.")
    df, info = get_retail()
    if info["is_sample"]:
        st.info(f"Showing the sample file ({len(df):,} rows). To analyse your complete file, place it at "
                "`data/data.csv` and restart the app.")
    else:
        st.caption(f"{info['file']}: {info['original_rows']:,} rows read, {info['duplicates_removed']:,} exact "
                   f"duplicates removed, {info['rows']:,} rows analysed.")

    view = _filters(df)
    if view.empty:
        st.warning("No rows match the filters.")
        return

    bridge = revenue_bridge(view).set_index("Step")["Amount"]
    sold = view[~view["IsCancellation"] & (view["Quantity"] > 0)]
    trust = kpi_trust(view)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Net revenue", ctx.retail_money(bridge["Net revenue"]), border=True)
    k2.metric("Gross product sales", ctx.retail_money(bridge["Gross product sales"]), border=True)
    k3.metric("Invoices", f"{sold['InvoiceNo'].nunique():,}", border=True)
    k4.metric("Identified customers", f"{view['CustomerID'].nunique():,}", border=True)
    k5.metric("KPI trust", f"{trust['trust_pct']:.0f}%", trust["level"], delta_color="off", border=True)

    tabs = st.tabs(["Revenue bridge", "Trends", "Products and countries", "Data trust",
                    "Explorer", "Column profile"])
    with tabs[0]:
        _bridge_tab(ctx, view)
    with tabs[1]:
        _trends_tab(ctx, view)
    with tabs[2]:
        _products_tab(ctx, view)
    with tabs[3]:
        _trust_tab(ctx, view)
    with tabs[4]:
        _explorer_tab(view)
    with tabs[5]:
        show_table(column_profile(view[["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate",
                                        "UnitPrice", "CustomerID", "Country"]]), height=330)
