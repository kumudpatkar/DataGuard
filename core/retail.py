"""Retail transaction logic.

Fixes the confusing "which Total Sales is right?" problem of the first version
by splitting every invoice line into a clear type (Product, Postage, Fees ...)
and by showing a revenue bridge that adds up to the net total.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.utils import read_any

# Stock codes that are NOT products. They are real money, but they should not
# appear in "top products".
POSTAGE_CODES = {"POST", "DOT", "C2", "CARRIAGE"}
FEE_CODES = {"AMAZONFEE", "BANK CHARGES", "CRUK", "B"}
MANUAL_CODES = {"M", "ADJUST", "ADJUST2"}
DISCOUNT_CODES = {"D"}
SAMPLE_CODES = {"S"}

LINE_PRODUCT = "Product"
LINE_POSTAGE = "Postage & Shipping"
LINE_FEES = "Fees & Charges"
LINE_MANUAL = "Manual Adjustment"
LINE_DISCOUNT = "Discount"
LINE_SAMPLES = "Samples"
LINE_GIFT = "Gift Voucher"

REQUIRED_COLUMNS = ["InvoiceNo", "StockCode", "Quantity", "InvoiceDate", "UnitPrice"]


def classify_line(stock_codes: pd.Series) -> pd.Series:
    """Label each invoice line as Product, Postage, Fees, and so on."""
    code = stock_codes.astype("string").str.strip().str.upper()
    out = pd.Series(LINE_PRODUCT, index=stock_codes.index, dtype="object")
    out[code.isin(POSTAGE_CODES).fillna(False)] = LINE_POSTAGE
    out[code.isin(FEE_CODES).fillna(False)] = LINE_FEES
    out[code.isin(MANUAL_CODES).fillna(False)] = LINE_MANUAL
    out[code.isin(DISCOUNT_CODES).fillna(False)] = LINE_DISCOUNT
    out[code.isin(SAMPLE_CODES).fillna(False)] = LINE_SAMPLES
    out[code.str.startswith("GIFT_").fillna(False)] = LINE_GIFT
    return out


def clean_retail(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Clean raw retail data. Returns (clean dataframe, information about the cleaning)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(
            "The retail file is missing required columns: " + ", ".join(missing)
            + ". Expected columns: InvoiceNo, StockCode, Description, Quantity, "
              "InvoiceDate, UnitPrice, CustomerID, Country."
        )

    df = raw.copy()
    original_rows = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    duplicates_removed = original_rows - len(df)

    for column in ("InvoiceNo", "StockCode", "Description", "Country", "CustomerID"):
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = df[column].astype("string").str.strip()

    df["CustomerID"] = df["CustomerID"].str.replace(r"\.0$", "", regex=True)

    dates = pd.to_datetime(df["InvoiceDate"], format="%m/%d/%Y %H:%M", errors="coerce")
    if dates.isna().any():
        fallback = pd.to_datetime(df.loc[dates.isna(), "InvoiceDate"], errors="coerce")
        dates = dates.where(dates.notna(), fallback)
    df["InvoiceDate"] = dates

    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["UnitPrice"] = pd.to_numeric(df["UnitPrice"], errors="coerce")
    df["SalesAmount"] = df["Quantity"] * df["UnitPrice"]

    df["IsCancellation"] = df["InvoiceNo"].str.startswith("C").fillna(False).astype(bool)
    df["LineType"] = classify_line(df["StockCode"])
    df["CustomerKnown"] = df["CustomerID"].notna()

    # why a row needs a human look (a negative quantity is normal on a cancellation)
    reasons = pd.DataFrame({
        "Missing date": df["InvoiceDate"].isna(),
        "Missing quantity or price": df["Quantity"].isna() | df["UnitPrice"].isna(),
        "Missing description": df["Description"].isna(),
        "Zero or negative price": df["UnitPrice"].le(0).fillna(False),
        "Negative quantity without cancellation": df["Quantity"].lt(0).fillna(False) & ~df["IsCancellation"],
    })
    df["NeedsReview"] = reasons.any(axis=1)
    df["ReviewReason"] = _reason_text(reasons)

    info = {
        "original_rows": int(original_rows),
        "duplicates_removed": int(duplicates_removed),
        "rows": int(len(df)),
    }
    return df, info


def _reason_text(reasons: pd.DataFrame) -> pd.Series:
    """Join the true reasons of each row into one text, without a slow row-by-row apply."""
    text = pd.Series("", index=reasons.index, dtype="object")
    for column in reasons.columns:
        flag = reasons[column]
        text = text.where(~flag, text + np.where(text.str.len() > 0, "; ", "") + column)
    return text


def load_retail(path) -> tuple[pd.DataFrame, dict]:
    """Read and clean a retail file (CSV or Excel)."""
    raw = read_any(path, dtype={"InvoiceNo": str, "StockCode": str, "CustomerID": str},
                   low_memory=False) if str(path).lower().endswith(".csv") else read_any(path)
    return clean_retail(raw)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def revenue_bridge(df: pd.DataFrame) -> pd.DataFrame:
    """A bridge from gross product sales to net revenue that adds up exactly.

    Every invoice line lands in exactly one row, so the Net Revenue row always
    equals the sum of all sales, the same number everywhere in the app.
    """
    sales = df["SalesAmount"].fillna(0.0)
    is_product = df["LineType"] == LINE_PRODUCT

    gross = sales[is_product & ~df["IsCancellation"] & (df["Quantity"] > 0)].sum()
    returns = sales[is_product & df["IsCancellation"]].sum()
    postage = sales[df["LineType"] == LINE_POSTAGE].sum()
    fees = sales[df["LineType"] == LINE_FEES].sum()
    adjustments = sales[df["LineType"].isin(
        [LINE_MANUAL, LINE_DISCOUNT, LINE_SAMPLES, LINE_GIFT])].sum()
    total = sales.sum()
    other = total - (gross + returns + postage + fees + adjustments)

    rows = [
        ("Gross product sales", gross, "Product lines sold (not cancelled)"),
        ("Returns and cancellations", returns, "Cancelled invoices (negative)"),
        ("Postage and shipping", postage, "Charged to customers, not a product"),
        ("Fees and charges", fees, "Marketplace and bank fees"),
        ("Manual adjustments, discounts, samples, vouchers", adjustments, "Booked by hand"),
        ("Other product adjustments", other, "Stock write-offs and corrections"),
        ("Net revenue", total, "Everything above added together"),
    ]
    return pd.DataFrame(rows, columns=["Step", "Amount", "Note"])


def kpi_trust(df: pd.DataFrame) -> dict:
    """How much of the sales value can be trusted?

    A sale is "trusted" when it has an identified customer and no review flag.
    The score tells a manager how much to rely on customer-level KPIs.
    """
    sold = df[(df["SalesAmount"] > 0) & ~df["IsCancellation"]]
    total_value = float(sold["SalesAmount"].sum())
    if total_value <= 0:
        return {"trust_pct": 0.0, "level": "Low", "unidentified_value": 0.0,
                "unidentified_pct": 0.0, "review_value": 0.0, "review_pct": 0.0,
                "total_value": 0.0}

    unidentified = float(sold.loc[~sold["CustomerKnown"], "SalesAmount"].sum())
    review = float(sold.loc[sold["NeedsReview"], "SalesAmount"].sum())
    trusted = float(sold.loc[sold["CustomerKnown"] & ~sold["NeedsReview"], "SalesAmount"].sum())
    trust_pct = trusted / total_value * 100.0

    level = "High" if trust_pct >= 90 else "Medium" if trust_pct >= 75 else "Low"
    return {
        "trust_pct": trust_pct,
        "level": level,
        "unidentified_value": unidentified,
        "unidentified_pct": unidentified / total_value * 100.0,
        "review_value": review,
        "review_pct": review / total_value * 100.0,
        "total_value": total_value,
    }


def line_type_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Rows and money per line type."""
    return (
        df.groupby("LineType", as_index=False)
        .agg(Rows=("InvoiceNo", "size"), Sales=("SalesAmount", "sum"))
        .sort_values("Sales", ascending=False)
        .reset_index(drop=True)
    )


def top_products(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top products by sales. Fees, postage and adjustments are excluded."""
    products = df[(df["LineType"] == LINE_PRODUCT) & ~df["IsCancellation"]
                  & (df["Quantity"] > 0) & df["Description"].notna()]
    return (
        products.groupby("Description", as_index=False)
        .agg(Sales=("SalesAmount", "sum"), Units=("Quantity", "sum"))
        .sort_values("Sales", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def sales_by_country(df: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    sold = df[~df["IsCancellation"] & (df["Quantity"] > 0)]
    return (
        sold.groupby("Country", as_index=False)
        .agg(Sales=("SalesAmount", "sum"))
        .sort_values("Sales", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def monthly_sales(df: pd.DataFrame) -> pd.DataFrame:
    """Gross sales, returns and net sales per month."""
    dated = df.dropna(subset=["InvoiceDate"]).copy()
    if dated.empty:
        return pd.DataFrame(columns=["Month", "Gross Sales", "Returns", "Net Sales"])
    dated["Month"] = dated["InvoiceDate"].dt.to_period("M").dt.to_timestamp()
    gross = dated[(~dated["IsCancellation"]) & (dated["Quantity"] > 0)]
    returns = dated[dated["IsCancellation"]]
    out = pd.DataFrame({
        "Gross Sales": gross.groupby("Month")["SalesAmount"].sum(),
        "Returns": returns.groupby("Month")["SalesAmount"].sum(),
    }).fillna(0.0)
    out["Net Sales"] = dated.groupby("Month")["SalesAmount"].sum()
    return out.reset_index().sort_values("Month")


def column_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Missing values and unique counts per column."""
    total = len(df)
    rows = []
    for column in df.columns:
        missing = int(df[column].isna().sum())
        rows.append({
            "Column": column,
            "Data Type": str(df[column].dtype),
            "Missing Values": missing,
            "Missing %": round(missing / total * 100, 2) if total else 0.0,
            "Unique Values": int(df[column].nunique()),
        })
    return pd.DataFrame(rows)


def completeness(df: pd.DataFrame, columns=None) -> float:
    """Percent of non-empty cells in the original data columns."""
    cols = columns or ["InvoiceNo", "StockCode", "Description", "Quantity",
                       "InvoiceDate", "UnitPrice", "CustomerID", "Country"]
    cols = [c for c in cols if c in df.columns]
    cells = len(df) * len(cols)
    if cells == 0:
        return 0.0
    return float((cells - df[cols].isna().sum().sum()) / cells * 100.0)
