
"""Data health score (0 to 100).

Combines four dimensions:

    Matching       60%
    Completeness   15%
    Rules          15%
    Uniqueness     10%

When row-level metrics are available, Matching and Uniqueness
use actual source/target row counts and extra duplicate copies.

Legacy stats remain supported for backward compatibility.
"""
from __future__ import annotations

import pandas as pd

WEIGHTS = {
    "Matching": 0.60,
    "Completeness": 0.15,
    "Rules": 0.15,
    "Uniqueness": 0.10,
}

MATCH_PENALTY = 3.0


def label_for(score: float) -> str:
    if score >= 90:
        return "Healthy"
    if score >= 75:
        return "Needs attention"
    return "At risk"


def data_completeness(
    df: pd.DataFrame | None,
    columns: list[str] | None = None,
) -> float:
    """Calculate the percentage of filled cells."""
    if df is None or df.empty:
        return 100.0

    cols = [c for c in (columns or df.columns) if c in df.columns]
    cells = len(df) * len(cols)

    if cells == 0:
        return 100.0

    blank = df[cols].isna().sum().sum()
    return float((cells - blank) / cells * 100.0)


def health_score(
    stats: dict,
    completeness: float = 100.0,
    rule_pass_rate: float = 100.0,
) -> dict:
    """Calculate health score and return its component breakdown."""

    has_row_metrics = (
        "source_rows" in stats
        and "target_rows" in stats
    )

    if has_row_metrics:
        # New row-level calculation.
        total = max(
            stats["source_rows"],
            stats["target_rows"],
        )

        if total > 0:
            effective_match = (
                stats["matched"]
                + 0.5 * stats.get("timing", 0)
            ) / total * 100.0

            matching = max(
                0.0,
                100.0 - MATCH_PENALTY * (100.0 - effective_match),
            )

            extra_duplicates = (
                stats.get("source_extra_duplicate_copies", 0)
                + stats.get("target_extra_duplicate_copies", 0)
            )

            uniqueness = max(
                0.0,
                100.0 - extra_duplicates / total * 100.0,
            )
        else:
            matching = 0.0
            uniqueness = 0.0

    else:
        # Legacy calculation for backward compatibility.
        total = stats.get("total_records", 0)

        if total > 0:
            effective_match = (
                stats["matched"]
                + 0.5 * stats.get("timing", 0)
            ) / total * 100.0

            matching = max(
                0.0,
                100.0 - MATCH_PENALTY * (100.0 - effective_match),
            )

            duplicate_records = (
                stats.get("duplicate_source", 0)
                + stats.get("duplicate_target", 0)
            )

            uniqueness = max(
                0.0,
                100.0 - duplicate_records / total * 100.0,
            )
        else:
            matching = 100.0
            uniqueness = 100.0

    parts = {
        "Matching": matching,
        "Completeness": completeness,
        "Rules": rule_pass_rate,
        "Uniqueness": uniqueness,
    }

    score = sum(
        parts[name] * weight
        for name, weight in WEIGHTS.items()
    )

    breakdown = pd.DataFrame({
        "Part": list(parts.keys()),
        "Value %": [round(value, 2) for value in parts.values()],
        "Weight %": [
            int(WEIGHTS[name] * 100)
            for name in parts
        ],
        "Points": [
            round(parts[name] * WEIGHTS[name], 2)
            for name in parts
        ],
    })

    return {
        "score": round(score, 1),
        "label": label_for(score),
        "breakdown": breakdown,
    }
