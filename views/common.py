"""Helpers shared by every page of the app."""
from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core import config
from core.reconciliation import ReconConfig
from core.retail import load_retail
from core.utils import money, plain_money
from core.workflow import Workflow

# Colors used in charts and badges, kept in one place
STATUS_COLORS = {
    "Matched": "#2e9e6b",
    "Timing Difference": "#e0a800",
    "Mismatch": "#d9534f",
    "Missing in Target": "#b02a37",
    "Missing in Source": "#8e44ad",
    "Duplicate in Target": "#e67e22",
    "Duplicate in Source": "#d35400",
    "Missing Key in Source": "#7f8c8d",
    "Missing Key in Target": "#95a5a6",
}
PRIORITY_COLORS = {"High": "#d9534f", "Medium": "#e0a800", "Low": "#2e9e6b", "None": "#9aa0a6"}


@dataclass
class Context:
    """Settings chosen in the sidebar, passed to every page."""
    user: str
    symbol: str            # currency symbol for reconciliation (order) data
    currency: str          # GBP or INR for the retail data
    gbp_to_inr: float
    workflow: Workflow

    def fmt(self, value) -> str:
        """Money for reconciliation data (no conversion)."""
        return plain_money(value, self.symbol)

    def retail_money(self, value) -> str:
        """Money for retail data (GBP, optionally shown in INR)."""
        return money(value, self.currency, self.gbp_to_inr)


@st.cache_resource
def get_workflow() -> Workflow:
    return Workflow()


@st.cache_data(show_spinner="Loading and cleaning retail data...")
def get_retail():
    """Use the full data/data.csv if present, otherwise the sample that ships with the project."""
    path = config.RETAIL_FULL_FILE if config.RETAIL_FULL_FILE.exists() else config.RETAIL_SAMPLE_FILE
    df, info = load_retail(path)
    info["file"] = path.name
    info["is_sample"] = path == config.RETAIL_SAMPLE_FILE
    return df, info


@st.cache_data
def get_pipeline_configs() -> dict:
    import yaml
    with open(config.PIPELINE_CONFIG, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return {p["name"]: p for p in raw.get("pipelines", [])}


def pipeline_config(name: str) -> ReconConfig:
    return ReconConfig.from_dict(get_pipeline_configs()[name])


def show_table(df: pd.DataFrame, height: int = 380, **kwargs):
    st.dataframe(df, width="stretch", hide_index=True, height=height, **kwargs)


def download_buttons(df: pd.DataFrame, filename: str, key: str):
    """CSV and Excel download side by side."""
    left, right, _ = st.columns([1, 1, 4])
    left.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                         f"{filename}.csv", "text/csv", key=f"{key}_csv")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="DataGuard")
    right.download_button("Download Excel", buffer.getvalue(), f"{filename}.xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          key=f"{key}_xlsx")


def score_color(score: float) -> str:
    return "#2e9e6b" if score >= 90 else "#e0a800" if score >= 75 else "#d9534f"


def badge(text: str, color: str) -> str:
    return (f"<span style='background:{color};color:white;padding:2px 10px;"
            f"border-radius:12px;font-size:0.85rem;font-weight:600'>{text}</span>")



def page_header(title: str, subtitle: str):
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(
                135deg,
                #DDF4FF 0%,
                #C7EBFC 55%,
                #B9E5FA 100%
            );
            border: 1px solid #C5E8F8;
            border-radius: 18px;
            padding: 28px 30px;
            margin-bottom: 24px;
            box-shadow: 0 6px 22px rgba(56, 139, 180, 0.12);
        ">
            <div style="
                color: #28617C;
                font-size: 0.72rem;
                font-weight: 800;
                letter-spacing: 0.14em;
                margin-bottom: 8px;
            ">
                DATA INTELLIGENCE PLATFORM
            </div>
            <div style="
                color: #10243A;
                font-size: 2rem;
                font-weight: 800;
                letter-spacing: -0.04em;
                line-height: 1.2;
            ">
                {title}
            </div>
            <div style="
                color: #29475D;
                font-size: 0.95rem;
                line-height: 1.6;
                margin-top: 10px;
            ">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
