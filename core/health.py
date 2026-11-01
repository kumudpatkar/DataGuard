"""Data health score (0 to 100).

One number a manager can watch over time. It combines four things:

    Matching       60%   how many records agree between the two systems
    Completeness   15%   how many required cells are filled in
    Rules          15%   how many quality rules pass
    Uniqueness     10%   how few duplicate records there are

Matching is deliberately strict, because a reconciliation with 1 in 6 records
in error is not healthy. A timing delay counts as half a match, and every 1%
of records with an exception costs 3 points of the Matching part:

    99% match -> 97     95% match -> 85     90% match -> 70     80% match -> 40

A falling score is an early warning that something broke upstream.
"""
from __future__ import annotations

import pandas as pd

WEIGHTS = {"Matching": 0.60, "Completeness": 0.15, "Rules": 0.15, "Uniqueness": 0.10}
MATCH_PENALTY = 3.0  # points lost from the Matching part per 1% of records with exceptions


def label_for(score: float) -> str:
    if score >= 90:
        return "Healthy"
    if score >= 75:
        return "Needs attention"
    return "At risk"


def data_completeness(df: pd.DataFrame | None, columns: list[str] | None = None) -> float:
    """Percent of filled cells in the chosen columns (all columns if none given)."""
    if df is None or df.empty:
        return 100.0
    cols = [c for c in (columns or df.columns) if c in df.columns]
    cells = len(df) * len(cols)
    if cells == 0:
        return 100.0
    blank = df[cols].isna().sum().sum()
    return float((cells - blank) / cells * 100.0)


def health_score(stats: dict, completeness: float = 100.0, rule_pass_rate: float = 100.0) -> dict:
    """Combine the four parts into one score and show how each contributed."""
    total = stats.get("total_records", 0)
    if total:
        effective_match = (stats["matched"] + 0.5 * stats.get("timing", 0)) / total * 100.0
        matching = max(0.0, 100.0 - MATCH_PENALTY * (100.0 - effective_match))
        duplicate_records = stats.get("duplicate_source", 0) + stats.get("duplicate_target", 0)
        uniqueness = max(0.0, 100.0 - duplicate_records / total * 100.0)
    else:
        matching, uniqueness = 100.0, 100.0

    parts = {
        "Matching": matching,
        "Completeness": completeness,
        "Rules": rule_pass_rate,
        "Uniqueness": uniqueness,
    }
    score = sum(parts[name] * weight for name, weight in WEIGHTS.items())

    breakdown = pd.DataFrame({
        "Part": list(parts.keys()),
        "Value %": [round(v, 2) for v in parts.values()],
        "Weight %": [int(WEIGHTS[k] * 100) for k in parts],
        "Points": [round(parts[k] * WEIGHTS[k], 2) for k in parts],
    })
    return {"score": round(score, 1), "label": label_for(score), "breakdown": breakdown}
