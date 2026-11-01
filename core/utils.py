"""Small helpers used across DataGuard."""
from __future__ import annotations

import re

import pandas as pd


def find_column(df: pd.DataFrame, candidates) -> str | None:
    """Find a column by trying several likely names.

    Spaces, case and symbols are ignored, so "Order ID", "order_id" and
    "OrderID" are all treated as the same name.
    """
    if df is None or len(df.columns) == 0:
        return None

    def norm(x) -> str:
        return "".join(ch.lower() for ch in str(x) if ch.isalnum())

    lookup = {norm(c): c for c in df.columns}
    for candidate in candidates:
        key = norm(candidate)
        if key in lookup:
            return lookup[key]
    return None


def normalize_key(series: pd.Series, prefix_regex: str | None = None) -> pd.Series:
    """Make record keys comparable between two systems.

    - removes spaces and upper-cases text
    - turns 1005.0 into 1005
    - optionally removes a prefix such as "ORD-" using ``prefix_regex``
    Empty keys become missing values so they can be reported separately.
    """
    s = series.astype("string").str.strip().str.upper()
    s = s.str.replace(r"\.0$", "", regex=True)
    if prefix_regex:
        s = s.str.replace(prefix_regex, "", regex=True, flags=re.IGNORECASE)
    s = s.str.strip()
    return s.mask(s.isin(["", "NAN", "NONE", "NULL", "<NA>"]))


def read_any(source, **kwargs) -> pd.DataFrame:
    """Read a CSV or Excel file from a path or an uploaded file object.

    CSV files are tried as UTF-8 first, then Latin-1 (common for Excel exports).
    """
    name = getattr(source, "name", str(source)).lower()

    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(source, **kwargs)

    try:
        return pd.read_csv(source, **kwargs)
    except UnicodeDecodeError:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_csv(source, encoding="latin1", **kwargs)


def money(value, currency: str = "GBP", gbp_to_inr: float = 1.0) -> str:
    """Format a retail money value (GBP data, optional INR display)."""
    if value is None or pd.isna(value):
        value = 0.0
    if currency == "INR":
        return f"₹{value * gbp_to_inr:,.2f}"
    return f"£{value:,.2f}"


def plain_money(value, symbol: str = "") -> str:
    """Money formatting for generic data, with no currency conversion."""
    if value is None or pd.isna(value):
        value = 0.0
    return f"{symbol}{value:,.2f}"


def number(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "0"
