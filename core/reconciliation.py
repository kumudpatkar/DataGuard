
"""Reconciliation engine.

Compares source and target datasets and classifies records.
Duplicate records are reported with counts, row details, and summed amounts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from core.utils import normalize_key


class Status:
    MATCHED = "Matched"
    MISMATCH = "Mismatch"
    TIMING = "Timing Difference"
    MISSING_TARGET = "Missing in Target"
    MISSING_SOURCE = "Missing in Source"
    DUP_SOURCE = "Duplicate in Source"
    DUP_TARGET = "Duplicate in Target"
    MISSING_KEY_SOURCE = "Missing Key in Source"
    MISSING_KEY_TARGET = "Missing Key in Target"


RESULT_COLUMNS = [
    "Record Key",
    "Status",
    "Source Count",
    "Target Count",
    "Source Amount",
    "Target Amount",
    "Amount Difference",
    "Extra Copies",
    "Fields Different",
    "Details",
]

DIFF_COLUMNS = [
    "Record Key",
    "Target Row",
    "Field",
    "Source Value",
    "Target Value",
    "Difference",
    "Difference %",
    "Is Timing",
]


@dataclass
class ReconConfig:
    """Settings used to compare two datasets."""

    key_source: str
    key_target: str
    column_map: dict = field(default_factory=dict)
    amount_column: str | None = None
    status_column: str | None = None
    abs_tolerance: float = 0.0
    pct_tolerance: float = 0.0
    prefix_regex: str | None = None
    timing_rules: list = field(default_factory=list)
    case_sensitive: bool = False
    name: str = "reconciliation"
    description: str = ""
    source_file: str | None = None
    target_file: str | None = None
    rule_set: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ReconConfig":
        key = data.get("key", {}) or {}
        tol = data.get("tolerance", {}) or {}

        return cls(
            key_source=key.get("source", "order_id"),
            key_target=key.get("target", key.get("source", "order_id")),
            column_map=dict(data.get("columns", {}) or {}),
            amount_column=data.get("amount_column"),
            status_column=data.get("status_column"),
            abs_tolerance=float(tol.get("absolute", 0.0)),
            pct_tolerance=float(tol.get("percent", 0.0)),
            prefix_regex=data.get("key_prefix_regex"),
            timing_rules=[
                tuple(pair)
                for pair in data.get("timing_rules", []) or []
            ],
            case_sensitive=bool(data.get("case_sensitive", False)),
            name=data.get("name", "reconciliation"),
            description=data.get("description", ""),
            source_file=data.get("source_file"),
            target_file=data.get("target_file"),
            rule_set=data.get("rule_set"),
        )

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        pipeline: str | None = None,
    ) -> "ReconConfig":
        """Load a pipeline from config/pipeline.yaml."""
        with open(path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

        pipelines = raw.get("pipelines", [])
        if not pipelines:
            raise ValueError(f"No pipelines found in {path}")

        if pipeline is None:
            return cls.from_dict(pipelines[0])

        for item in pipelines:
            if item.get("name") == pipeline:
                return cls.from_dict(item)

        raise ValueError(f"Pipeline '{pipeline}' not found in {path}")


@dataclass
class ReconResult:
    results: pd.DataFrame
    diffs: pd.DataFrame
    stats: dict
    warnings: list = field(default_factory=list)

    @property
    def exceptions(self) -> pd.DataFrame:
        return self.results[
            self.results["Status"] != Status.MATCHED
        ].copy()


def _empty_results() -> pd.DataFrame:
    return pd.DataFrame(columns=RESULT_COLUMNS)


def _is_numeric_pair(a: pd.Series, b: pd.Series) -> bool:
    """Check whether both columns contain numeric values or blanks."""
    an = pd.to_numeric(a, errors="coerce")
    bn = pd.to_numeric(b, errors="coerce")

    a_ok = (an.notna() | a.isna()).all()
    b_ok = (bn.notna() | b.isna()).all()

    return bool(
        a_ok and b_ok and (an.notna().any() or bn.notna().any())
    )


def _show(value) -> str:
    """Convert values into readable text."""
    return "<MISSING>" if pd.isna(value) else str(value)


def _compare_column(
    a,
    b,
    src_col,
    tgt_col,
    cfg: ReconConfig,
    tolerance_on: bool,
):
    """Return mismatch, timing, numeric difference and tolerated masks."""
    index = a.index
    false = pd.Series(False, index=index)

    if _is_numeric_pair(a, b):
        an = pd.to_numeric(a, errors="coerce")
        bn = pd.to_numeric(b, errors="coerce")
        diff = an - bn

        both_null = an.isna() & bn.isna()
        one_null = an.isna() ^ bn.isna()

        allowed = pd.Series(1e-9, index=index)

        if tolerance_on:
            allowed = np.maximum(allowed, cfg.abs_tolerance)

            if cfg.pct_tolerance > 0:
                allowed = np.maximum(
                    allowed,
                    an.abs() * cfg.pct_tolerance / 100.0,
                )

        within = diff.abs() <= allowed
        mismatch = one_null | (~both_null & ~within)

        tolerated = (
            ~both_null
            & ~one_null
            & (diff.abs() > 1e-9)
            & within
        )

        return mismatch, false, diff, tolerated

    sa = a.astype("string").str.strip()
    sb = b.astype("string").str.strip()

    if not cfg.case_sensitive:
        sa = sa.str.casefold()
        sb = sb.str.casefold()

    equal = (sa == sb).fillna(False) | (a.isna() & b.isna())
    mismatch = ~equal

    timing = false.copy()

    if cfg.status_column is not None and src_col == cfg.status_column:
        for source_value, target_value in cfg.timing_rules:
            sv = str(source_value).strip()
            tv = str(target_value).strip()

            if not cfg.case_sensitive:
                sv = sv.casefold()
                tv = tv.casefold()

            timing |= ((sa == sv) & (sb == tv)).fillna(False)

        timing &= mismatch

    return mismatch, timing, pd.Series(np.nan, index=index), false


def reconcile(
    source: pd.DataFrame,
    target: pd.DataFrame,
    cfg: ReconConfig,
) -> ReconResult:
    """Compare source and target data and return reconciliation results."""
    warnings: list[str] = []

    if cfg.key_source not in source.columns:
        raise ValueError(
            f"Key column '{cfg.key_source}' was not found in the source data."
        )

    if cfg.key_target not in target.columns:
        raise ValueError(
            f"Key column '{cfg.key_target}' was not found in the target data."
        )

    # Keep only mapped columns that exist in both datasets.
    column_map = {}

    for src_col, tgt_col in cfg.column_map.items():
        if src_col in source.columns and tgt_col in target.columns:
            column_map[src_col] = tgt_col
        else:
            warnings.append(
                f"Skipped column '{src_col}' -> '{tgt_col}' because it is missing."
            )

    src_amount_col = (
        cfg.amount_column
        if cfg.amount_column in source.columns
        else None
    )

    tgt_amount_col = None

    if src_amount_col:
        tgt_amount_col = column_map.get(
            src_amount_col,
            src_amount_col,
        )

        if tgt_amount_col not in target.columns:
            tgt_amount_col = None

    s = source.reset_index(drop=True).copy()
    t = target.reset_index(drop=True).copy()

    s["_key"] = normalize_key(s[cfg.key_source], cfg.prefix_regex)
    t["_key"] = normalize_key(t[cfg.key_target], cfg.prefix_regex)

    # CSV-style row numbers: row 1 is the header.
    s["_row"] = np.arange(len(s)) + 2
    t["_row"] = np.arange(len(t)) + 2

    parts: list[pd.DataFrame] = []

    # ---- records with missing keys -------------------------------------
    for frame, status, prefix, side in (
        (s, Status.MISSING_KEY_SOURCE, "S-ROW-", "source"),
        (t, Status.MISSING_KEY_TARGET, "T-ROW-", "target"),
    ):
        blank = frame[frame["_key"].isna()]

        if blank.empty:
            continue

        amount_col = (
            src_amount_col if side == "source" else tgt_amount_col
        )

        amounts = (
            pd.to_numeric(blank[amount_col], errors="coerce")
            if amount_col
            else pd.Series(np.nan, index=blank.index)
        )

        parts.append(pd.DataFrame({
            "Record Key": prefix + blank["_row"].astype(str),
            "Status": status,
            "Source Count": 1 if side == "source" else 0,
            "Target Count": 1 if side == "target" else 0,
            "Source Amount": amounts if side == "source" else np.nan,
            "Target Amount": amounts if side == "target" else np.nan,
            "Amount Difference": np.nan,
            "Extra Copies": 0,
            "Fields Different": "",
            "Details": (
                f"The {side} record on file row "
                + blank["_row"].astype(str)
                + " has no key value."
            ),
        }))

    s = s[s["_key"].notna()]
    t = t[t["_key"].notna()]

    # ---- duplicate detection and reporting -----------------------------
    s_counts = s["_key"].value_counts()
    t_counts = t["_key"].value_counts()

    dup_s = set(s_counts[s_counts > 1].index)
    dup_t = set(t_counts[t_counts > 1].index)

    # ---- duplicate statistics -----------------------------------------
    source_unique_records = int(s_counts.size)
    target_unique_records = int(t_counts.size)

    source_duplicate_keys = len(dup_s)
    target_duplicate_keys = len(dup_t)

    source_duplicate_rows = int(s_counts[s_counts > 1].sum())
    target_duplicate_rows = int(t_counts[t_counts > 1].sum())

    source_extra_duplicate_copies = int(
        (s_counts[s_counts > 1] - 1).sum()
    )
    target_extra_duplicate_copies = int(
        (t_counts[t_counts > 1] - 1).sum()
    )

    for dup_keys, frame, counts, other_counts, status, side in (
        (dup_s, s, s_counts, t_counts, Status.DUP_SOURCE, "source"),
        (dup_t, t, t_counts, s_counts, Status.DUP_TARGET, "target"),
    ):
        if not dup_keys:
            continue

        amount_col = (
            src_amount_col if side == "source" else tgt_amount_col
        )

        duplicate_rows = frame[frame["_key"].isin(dup_keys)]
        first = duplicate_rows.drop_duplicates("_key", keep="first")

        # Sum all numeric amounts for each duplicated key.
        if amount_col:
            numeric_amounts = pd.to_numeric(
                duplicate_rows[amount_col],
                errors="coerce",
            )

            duplicate_amounts = numeric_amounts.groupby(
                duplicate_rows["_key"]
            ).sum(min_count=1)

            amounts = first["_key"].map(duplicate_amounts)
        else:
            amounts = pd.Series(np.nan, index=first.index)

        own = first["_key"].map(counts).astype(int)
        other = first["_key"].map(other_counts).fillna(0).astype(int)

        # Include row numbers and individual amounts in Details.
        duplicate_details = {}

        for key, group in duplicate_rows.groupby("_key", sort=False):
            row_details = []

            for _, row in group.iterrows():
                row_number = int(row["_row"])

                if amount_col:
                    row_amount = _show(row[amount_col])
                    row_details.append(
                        f"row {row_number}: amount={row_amount}"
                    )
                else:
                    row_details.append(f"row {row_number}")

            total_values = amounts.loc[first["_key"].eq(key)]

            total_text = (
                _show(total_values.iloc[0])
                if not total_values.empty
                else "<MISSING>"
            )

            duplicate_details[key] = (
                f"Duplicate {side} records: "
                f"{'; '.join(row_details)}. "
                f"Total {side} amount: {total_text}."
            )

        details = [
            (
                f"Appears {o} times in {side}; "
                f"{x} in the other system. "
                f"{duplicate_details.get(key, '')}"
            )
            for key, o, x in zip(first["_key"], own, other)
        ]

        # IMPORTANT: append duplicate exceptions to the results.
        parts.append(pd.DataFrame({
            "Record Key": first["_key"].values,
            "Status": status,
            "Source Count": (
                own if side == "source" else other
            ).values,
            "Target Count": (
                own if side == "target" else other
            ).values,
            "Source Amount": (
    amounts.values if side == "source"
    else first["_key"].map(
        pd.to_numeric(
            s.drop_duplicates("_key", keep="first")
            .set_index("_key")[src_amount_col],
            errors="coerce",
        )
    ).values if src_amount_col else np.nan
),
"Target Amount": (
    amounts.values if side == "target"
    else first["_key"].map(
        pd.to_numeric(
            t.drop_duplicates("_key", keep="first")
            .set_index("_key")[tgt_amount_col],
            errors="coerce",
        )
    ).values if tgt_amount_col else np.nan
),
            "Amount Difference": np.nan,
            "Extra Copies": (own - 1).values,
            "Fields Different": "",
            "Details": details,
        }))

    # Exclude duplicated keys from the one-to-one merge.
    all_dups = dup_s | dup_t
    s_unique = s[~s["_key"].isin(all_dups)]
    t_unique = t[~t["_key"].isin(all_dups)]

        # ---- field-level comparison for duplicate records ----------------
    duplicate_diff_frames: list[pd.DataFrame] = []

    for key in all_dups:
        source_group = s[s["_key"] == key]
        target_group = t[t["_key"] == key]

        if source_group.empty or target_group.empty:
            continue

        source_row = source_group.iloc[0]

        for _, target_row in target_group.iterrows():
            for src_col, tgt_col in column_map.items():
                source_value = source_row[src_col]
                target_value = target_row[tgt_col]

                mismatch, timing, difference, _ = _compare_column(
                    pd.Series([source_value]),
                    pd.Series([target_value]),
                    src_col,
                    tgt_col,
                    cfg,
                    src_col == cfg.amount_column,
                )

                if not mismatch.iloc[0]:
                    continue

                numeric_difference = (
                    float(difference.iloc[0])
                    if pd.notna(difference.iloc[0])
                    else np.nan
                )

                source_numeric = pd.to_numeric(
                    pd.Series([source_value]),
                    errors="coerce",
                ).iloc[0]

                difference_pct = (
                    numeric_difference / source_numeric * 100
                    if pd.notna(numeric_difference)
                    and pd.notna(source_numeric)
                    and source_numeric != 0
                    else np.nan
                )

                duplicate_diff_frames.append(pd.DataFrame([{
                "Record Key": str(key),
                "Target Row": int(target_row["_row"]),
                "Field": src_col,
                    "Source Value": _show(source_value),
                    "Target Value": _show(target_value),
                    "Difference": numeric_difference,
                    "Difference %": difference_pct,
                    "Is Timing": bool(timing.iloc[0]),
                }]))

    duplicate_diffs = (
        pd.concat(duplicate_diff_frames, ignore_index=True)
        if duplicate_diff_frames
        else pd.DataFrame(columns=DIFF_COLUMNS)
    )

    # ---- merge the remaining records -----------------------------------
    src_cols = list(column_map.keys())
    tgt_cols = list(column_map.values())

    if src_amount_col and src_amount_col not in src_cols:
        src_cols.append(src_amount_col)

    if tgt_amount_col and tgt_amount_col not in tgt_cols:
        tgt_cols.append(tgt_amount_col)

    s_part = s_unique[["_key", "_row"] + src_cols].rename(
    columns={
        **{c: f"{c}__s" for c in src_cols},
        "_row": "_source_row",
    }
    )

    t_part = t_unique[["_key", "_row"] + tgt_cols].rename(
        columns={
        **{c: f"{c}__t" for c in tgt_cols},
        "_row": "_target_row",
    }
    )

    merged = s_part.merge(
        t_part,
        on="_key",
        how="outer",
        indicator=True,
    )

    def amount_series(frame, col, suffix):
        if col is None:
            return pd.Series(np.nan, index=frame.index)

        return pd.to_numeric(
            frame[f"{col}__{suffix}"],
            errors="coerce",
        )

    merged["_src_amt"] = amount_series(
        merged, src_amount_col, "s"
    )
    merged["_tgt_amt"] = amount_series(
        merged, tgt_amount_col, "t"
    )

    both = merged[merged["_merge"] == "both"].copy()
    left = merged[merged["_merge"] == "left_only"]
    right = merged[merged["_merge"] == "right_only"]

    # ---- records missing from one side -------------------------------
    if not left.empty:
        parts.append(pd.DataFrame({
            "Record Key": left["_key"].values,
            "Status": Status.MISSING_TARGET,
            "Source Count": 1,
            "Target Count": 0,
            "Source Amount": left["_src_amt"].values,
            "Target Amount": np.nan,
            "Amount Difference": np.nan,
            "Extra Copies": 0,
            "Fields Different": "",
            "Details": "Record exists only in the source.",
        }))

    if not right.empty:
        parts.append(pd.DataFrame({
            "Record Key": right["_key"].values,
            "Status": Status.MISSING_SOURCE,
            "Source Count": 0,
            "Target Count": 1,
            "Source Amount": np.nan,
            "Target Amount": right["_tgt_amt"].values,
            "Amount Difference": np.nan,
            "Extra Copies": 0,
            "Fields Different": "",
            "Details": "Record exists only in the target.",
        }))

    # ---- compare fields for records present on both sides -------------
    diff_frames: list[pd.DataFrame] = []
    tolerated_keys: set = set()

    if not both.empty:
        real_mismatch = pd.Series(False, index=both.index)
        timing_only = pd.Series(False, index=both.index)

        for src_col, tgt_col in column_map.items():
            a = both[f"{src_col}__s"]
            b = both[f"{tgt_col}__t"]

            tolerance_on = src_col == cfg.amount_column

            mismatch, timing, diff, tolerated = _compare_column(
                a,
                b,
                src_col,
                tgt_col,
                cfg,
                tolerance_on,
            )

            tolerated_keys |= set(
                both.loc[tolerated, "_key"]
            )

            if mismatch.any():
                hit = both.loc[mismatch]
                src_num = pd.to_numeric(
                    a[mismatch],
                    errors="coerce",
                )

                with np.errstate(divide="ignore", invalid="ignore"):
                    pct = np.where(
                        src_num != 0,
                        diff[mismatch] / src_num * 100.0,
                        np.nan,
                    )

                diff_frames.append(pd.DataFrame({
                "Record Key": hit["_key"].values,
                "Target Row": hit["_target_row"].values,
                "Field": src_col,
                    "Source Value": [
                        _show(v) for v in a[mismatch]
                    ],
                    "Target Value": [
                        _show(v) for v in b[mismatch]
                    ],
                    "Difference": diff[mismatch].values,
                    "Difference %": pct,
                    "Is Timing": timing[mismatch].values,
                }))

            real_mismatch |= mismatch & ~timing
            timing_only |= timing

        has_timing = timing_only & ~real_mismatch

        both["_status"] = Status.MATCHED
        both.loc[has_timing, "_status"] = Status.TIMING
        both.loc[real_mismatch, "_status"] = Status.MISMATCH

        diffs_all = (
            pd.concat(diff_frames, ignore_index=True)
            if diff_frames
            else pd.DataFrame(columns=DIFF_COLUMNS)
        )

        details_map = {}
        fields_map = {}

        if not diffs_all.empty:
            for key, group in diffs_all.groupby(
                "Record Key",
                sort=False,
            ):
                lines = []

                for _, row in group.iterrows():
                    line = (
                        f"{row['Field']}: "
                        f"source=[{row['Source Value']}], "
                        f"target=[{row['Target Value']}]"
                    )

                    if pd.notna(row["Difference"]):
                        line += (
                            f", difference={row['Difference']:.2f}"
                        )

                    if row["Is Timing"]:
                        line += " (timing)"

                    lines.append(line)

                details_map[key] = "; ".join(lines)
                fields_map[key] = ", ".join(
                    group["Field"].astype(str)
                )

        details_values = pd.Series(
            both["_key"].map(details_map).to_numpy(dtype=object),
            index=both.index,
            dtype=object,
        )

        matched_text = pd.Series(
            np.where(
                both["_key"].isin(tolerated_keys),
                "Matched within the allowed tolerance.",
                "All compared fields match.",
            ),
            index=both.index,
            dtype=object,
        )

        both["_details"] = details_values.where(
            details_values.notna(),
            matched_text,
        )

        fields_values = pd.Series(
            both["_key"].map(fields_map).to_numpy(dtype=object),
            index=both.index,
            dtype=object,
        )

        both["_fields"] = fields_values.fillna("")

        parts.append(pd.DataFrame({
            "Record Key": both["_key"].values,
            "Status": both["_status"].values,
            "Source Count": 1,
            "Target Count": 1,
            "Source Amount": both["_src_amt"].values,
            "Target Amount": both["_tgt_amt"].values,
            "Amount Difference": (
                both["_src_amt"] - both["_tgt_amt"]
            ).values,
            "Extra Copies": 0,
            "Fields Different": both["_fields"].values,
            "Details": both["_details"].values,
        }))

    else:
        diffs_all = pd.DataFrame(columns=DIFF_COLUMNS)

        # Include field-level differences from duplicate records.
    if not duplicate_diffs.empty:
        diffs_all = pd.concat(
            [diffs_all, duplicate_diffs],
            ignore_index=True,
        )

    # ---- final results -------------------------------------------------
    results = (
        pd.concat(parts, ignore_index=True)
        if parts
        else _empty_results()
    )[RESULT_COLUMNS]

    results = results.sort_values(
        "Record Key",
        key=lambda col: col.astype(str),
    ).reset_index(drop=True)

    stats = summarize(
        results,
        len(source),
        len(target),
        len(tolerated_keys),
    )

    # Add detailed duplicate statistics
    stats.update({
        "source_unique_records": source_unique_records,
        "target_unique_records": target_unique_records,
        "source_duplicate_keys": source_duplicate_keys,
        "target_duplicate_keys": target_duplicate_keys,
        "source_duplicate_rows": source_duplicate_rows,
        "target_duplicate_rows": target_duplicate_rows,
        "source_extra_duplicate_copies": source_extra_duplicate_copies,
        "target_extra_duplicate_copies": target_extra_duplicate_copies,
    })

    return ReconResult(
        results=results,
        diffs=diffs_all[DIFF_COLUMNS],
        stats=stats,
        warnings=warnings,
    )



def summarize(
    results: pd.DataFrame,
    source_rows: int,
    target_rows: int,
    tolerated: int = 0,
) -> dict:
    """Return headline reconciliation metrics."""
    counts = (
        results["Status"].value_counts().to_dict()
        if not results.empty
        else {}
    )

    total = len(results)
    matched = counts.get(Status.MATCHED, 0)
    row_total = max(source_rows, target_rows)

    return {
        "source_rows": int(source_rows),
        "target_rows": int(target_rows),
        "total_records": int(total),
        "matched": int(matched),
        "mismatch": int(counts.get(Status.MISMATCH, 0)),
        "timing": int(counts.get(Status.TIMING, 0)),
        "missing_in_target": int(
            counts.get(Status.MISSING_TARGET, 0)
        ),
        "missing_in_source": int(
            counts.get(Status.MISSING_SOURCE, 0)
        ),
        "duplicate_source": int(
            counts.get(Status.DUP_SOURCE, 0)
        ),
        "duplicate_target": int(
            counts.get(Status.DUP_TARGET, 0)
        ),
        "missing_key": int(
            counts.get(Status.MISSING_KEY_SOURCE, 0)
            + counts.get(Status.MISSING_KEY_TARGET, 0)
        ),
        "within_tolerance": int(tolerated),
        "exceptions": int(total - matched),

        # Existing metric: matched result records / total result records.
        "match_rate": (
            float(matched / total * 100.0)
            if total > 0
            else 0.0
        ),

        # New metric: matched records / larger input row count.
        "row_match_rate": (
            float(matched / row_total * 100.0)
            if row_total > 0
            else 0.0
        ),
    }
