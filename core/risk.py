"""Money-at-Risk scoring.

A finance team may get thousands of exceptions. This module answers:
"which ones should we look at first?" by giving each one a money value.

    exposure   = how much money is affected by this exception
    risk score = exposure x severity weight (0 to 1)

Examples:
* Missing payment for a 5,000 order      -> exposure 5,000, severity 1.0, risk 5,000
* Amount short by 120                    -> exposure 120,   severity 0.8, risk 96
* Duplicate payment of 800 (2 copies)    -> exposure 800,   severity 0.7, risk 560
* Settlement delay on a 3,000 order      -> exposure 3,000, severity 0.2, risk 600
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.reconciliation import Status

SEVERITY = {
    Status.MISSING_TARGET: 1.0,
    Status.MISSING_SOURCE: 0.9,
    Status.MISMATCH: 0.8,
    Status.DUP_TARGET: 0.7,
    Status.DUP_SOURCE: 0.6,
    Status.MISSING_KEY_SOURCE: 0.6,
    Status.MISSING_KEY_TARGET: 0.6,
    Status.TIMING: 0.2,
    Status.MATCHED: 0.0,
}

PRIORITY_ORDER = ["High", "Medium", "Low"]


def _first_number(*values) -> pd.Series:
    """First non-missing value across several Series, row by row."""
    out = values[0].copy()
    for other in values[1:]:
        out = out.where(out.notna(), other)
    return out


def add_risk(results: pd.DataFrame, high_threshold: float = 5000.0,
             medium_threshold: float = 1000.0) -> pd.DataFrame:
    """Add Exposure, Severity, Risk Score and Priority columns.

    ``high_threshold`` and ``medium_threshold`` are risk-score levels in the
    currency of your data.
    """
    out = results.copy()
    if out.empty:
        for col in ["Exposure", "Severity", "Risk Score", "Priority"]:
            out[col] = pd.Series(dtype="float64" if col != "Priority" else "object")
        return out

    status = out["Status"]
    src = pd.to_numeric(out["Source Amount"], errors="coerce")
    tgt = pd.to_numeric(out["Target Amount"], errors="coerce")
    diff = pd.to_numeric(out["Amount Difference"], errors="coerce").abs()
    copies = pd.to_numeric(out["Extra Copies"], errors="coerce").fillna(0)

    # the amount of the record that exists, whichever side it is on
    any_amount = _first_number(src, tgt).abs().fillna(0.0)

    exposure = pd.Series(0.0, index=out.index)

    # one-sided records: the whole amount is unaccounted for
    one_sided = status.isin([
        Status.MISSING_TARGET, Status.MISSING_SOURCE,
        Status.MISSING_KEY_SOURCE, Status.MISSING_KEY_TARGET,
    ])
    exposure[one_sided] = any_amount[one_sided]

        # Duplicates: count only the extra copies, not the full
    # aggregated amount of every copy.
    is_dup_target = status == Status.DUP_TARGET
    is_dup_source = status == Status.DUP_SOURCE

    target_count = pd.to_numeric(
        out["Target Count"], errors="coerce"
    ).replace(0, np.nan)

    source_count = pd.to_numeric(
        out["Source Count"], errors="coerce"
    ).replace(0, np.nan)

    target_per_copy = tgt.abs() / target_count
    source_per_copy = src.abs() / source_count

    exposure[is_dup_target] = (
        target_per_copy * copies
    )[is_dup_target].fillna(0.0)

    exposure[is_dup_source] = (
        source_per_copy * copies
    )[is_dup_source].fillna(0.0)

    # mismatches: the money gap if there is one, otherwise the whole record
    is_mismatch = status == Status.MISMATCH
    has_gap = diff.notna() & (diff > 0)
    exposure[is_mismatch & has_gap] = diff[is_mismatch & has_gap]
    exposure[is_mismatch & ~has_gap] = any_amount[is_mismatch & ~has_gap]

    # timing delays: the money is only late, so it counts in full but is weighted low
    exposure[status == Status.TIMING] = any_amount[status == Status.TIMING]

    severity = status.map(SEVERITY).fillna(0.5)
    risk = (exposure * severity).round(2)

    out["Exposure"] = exposure.round(2)
    out["Severity"] = severity
    out["Risk Score"] = risk

    priority = np.select(
        [status.eq(Status.MATCHED), risk >= high_threshold, risk >= medium_threshold],
        ["None", "High", "Medium"],
        default="Low",
    )
    out["Priority"] = priority
    return out


def risk_summary(with_risk: pd.DataFrame) -> dict:
    """Headline money numbers for a reconciliation run."""
    exceptions = with_risk[with_risk["Status"] != Status.MATCHED]
    if exceptions.empty:
        return {"total_risk": 0.0, "total_exposure": 0.0, "high": 0,
                "medium": 0, "low": 0, "top20_share": 0.0}

    total_risk = float(exceptions["Risk Score"].sum())
    top20 = float(exceptions.nlargest(20, "Risk Score")["Risk Score"].sum())
    return {
        "total_risk": total_risk,
        "total_exposure": float(exceptions["Exposure"].sum()),
        "high": int((exceptions["Priority"] == "High").sum()),
        "medium": int((exceptions["Priority"] == "Medium").sum()),
        "low": int((exceptions["Priority"] == "Low").sum()),
        "top20_share": (top20 / total_risk * 100.0) if total_risk else 0.0,
    }


def risk_by_status(with_risk: pd.DataFrame) -> pd.DataFrame:
    """Total risk and count per exception type."""
    exceptions = with_risk[with_risk["Status"] != Status.MATCHED]
    if exceptions.empty:
        return pd.DataFrame(columns=["Status", "Records", "Exposure", "Risk Score"])
    return (
        exceptions.groupby("Status", as_index=False)
        .agg(Records=("Record Key", "count"),
             Exposure=("Exposure", "sum"),
             **{"Risk Score": ("Risk Score", "sum")})
        .sort_values("Risk Score", ascending=False)
        .reset_index(drop=True)
    )
