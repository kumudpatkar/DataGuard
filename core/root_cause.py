"""Root-cause detector.

Finding 1,000 mismatches is easy. Understanding WHY they happen is what saves
time. This module looks for patterns in the exceptions, for example:

* "57 orders: Completed in the order system but Pending in payments"  -> settlement delay
* "45 amount gaps are all exactly 2.4% lower"                         -> gateway fee
* "35% of COD orders are missing in payments vs 4% overall"           -> COD is not synced
* "12 duplicate payments exist only in the payment system"            -> webhook retries

Each finding comes with the number of records, the money at risk and a
suggested next step.
"""
from __future__ import annotations

import pandas as pd

from core.reconciliation import ReconConfig, Status
from core.utils import normalize_key

FINDING_COLUMNS = [
    "Finding",
    "What we found",
    "Records",
    "Share of exceptions %",
    "Money at risk",
    "Likely cause and next step",
    "Confidence",
]

MIN_RECORDS = 3  # a pattern needs at least this many records to be reported


def _confidence(records: int, consistency: float) -> str:
    """High when many records agree, Medium when the pattern is smaller or weaker."""
    if records >= 10 and consistency >= 0.7:
        return "High"
    if records >= MIN_RECORDS and consistency >= 0.4:
        return "Medium"
    return "Low"


def _finding(title, text, keys, risk_lookup, total_exceptions, action, consistency):
    keys = list(dict.fromkeys(keys))  # unique, keep order
    records = len(keys)
    risk = float(sum(risk_lookup.get(k, 0.0) for k in keys))
    return {
        "Finding": title,
        "What we found": text,
        "Records": records,
        "Share of exceptions %": round(records / total_exceptions * 100.0, 1) if total_exceptions else 0.0,
        "Money at risk": round(risk, 2),
        "Likely cause and next step": action,
        "Confidence": _confidence(records, consistency),
        "_keys": keys,
    }


def _dimension_findings(with_risk, source, cfg, status, label, risk_lookup, total_exc):
    """Find an attribute value (country, payment method...) over-represented in one exception type."""
    findings = []
    flagged_keys = set(with_risk.loc[with_risk["Status"] == status, "Record Key"])
    if len(flagged_keys) < MIN_RECORDS or source is None or source.empty:
        return findings

    src = source.copy()
    src["_key"] = normalize_key(src[cfg.key_source], cfg.prefix_regex)
    src = src[src["_key"].notna()].drop_duplicates("_key")
    src["_flagged"] = src["_key"].isin(flagged_keys)
    if src["_flagged"].sum() < MIN_RECORDS:
        return findings

    skip = {cfg.key_source, "_key", "_flagged", *cfg.column_map.keys()}
    overall_rate = src["_flagged"].mean()
    best = None

    for col in src.columns:
        if col in skip:
            continue
        if not (pd.api.types.is_object_dtype(src[col]) or pd.api.types.is_string_dtype(src[col])):
            continue
        if not 2 <= src[col].nunique() <= 30:
            continue

        grouped = src.groupby(col)["_flagged"].agg(["sum", "count"])
        grouped = grouped[grouped["sum"] >= MIN_RECORDS]
        if grouped.empty:
            continue
        grouped["rate"] = grouped["sum"] / grouped["count"]
        grouped["lift"] = grouped["rate"] / overall_rate if overall_rate else 0.0

        value = grouped["lift"].idxmax()
        row = grouped.loc[value]
        if row["lift"] >= 2.0 and (best is None or row["lift"] > best["lift"]):
            best = {"col": col, "value": value, "rate": row["rate"],
                    "count": int(row["sum"]), "total": int(row["count"]),
                    "lift": row["lift"]}

    if best:
        keys = src.loc[(src[best["col"]] == best["value"]) & src["_flagged"], "_key"].tolist()
        findings.append(_finding(
            title=f"{status} is concentrated in {best['col']} = {best['value']}",
            text=(f"{best['rate'] * 100:.0f}% of orders with {best['col']} = '{best['value']}' "
                  f"have the issue '{status}', compared with {overall_rate * 100:.0f}% overall "
                  f"({best['count']} of {best['total']} records)."),
            keys=keys, risk_lookup=risk_lookup, total_exceptions=total_exc,
            action=(f"The problem is not random. Check how '{best['value']}' records are sent "
                    f"between the two systems (integration, file export, or manual step)."),
            consistency=min(1.0, best["rate"] + 0.2),
        ))
    return findings


def find_root_causes(with_risk: pd.DataFrame, diffs: pd.DataFrame,
                     source: pd.DataFrame | None, cfg: ReconConfig) -> pd.DataFrame:
    """Return a table of detected patterns, biggest money first."""
    if with_risk.empty:
        return pd.DataFrame(columns=FINDING_COLUMNS)

    exceptions = with_risk[with_risk["Status"] != Status.MATCHED]
    total_exc = len(exceptions)
    if total_exc == 0:
        return pd.DataFrame(columns=FINDING_COLUMNS)

    risk_lookup = dict(zip(with_risk["Record Key"], with_risk["Risk Score"]))
    findings: list[dict] = []

    # ---- 1. status patterns (delays and conflicts) -------------------------------
    if cfg.status_column and not diffs.empty:
        status_diffs = diffs[diffs["Field"] == cfg.status_column]

        timing = status_diffs[status_diffs["Is Timing"]]
        if len(timing) >= MIN_RECORDS:
            for (sv, tv), grp in timing.groupby(["Source Value", "Target Value"]):
                findings.append(_finding(
                    title="Settlement or sync delay",
                    text=f"{len(grp)} records are '{sv}' in the source but still '{tv}' in the target.",
                    keys=grp["Record Key"], risk_lookup=risk_lookup, total_exceptions=total_exc,
                    action=("Probably a timing delay, not an error. Re-run after the next settlement "
                            "cycle. If they stay open for days, ask the payment provider why."),
                    consistency=1.0,
                ))

        conflicts = status_diffs[~status_diffs["Is Timing"]]
        if len(conflicts) >= MIN_RECORDS:
            pair = conflicts.groupby(["Source Value", "Target Value"]).size().sort_values(ascending=False)
            (sv, tv), count = pair.index[0], int(pair.iloc[0])
            grp = conflicts[(conflicts["Source Value"] == sv) & (conflicts["Target Value"] == tv)]
            findings.append(_finding(
                title="Status conflict",
                text=f"{count} records are '{sv}' in the source but '{tv}' in the target.",
                keys=grp["Record Key"], risk_lookup=risk_lookup, total_exceptions=total_exc,
                action="The two systems disagree about the order state. Check which system is correct "
                       "and whether a cancellation or refund was not synced.",
                consistency=count / len(conflicts),
            ))

    # ---- 2. amount patterns -------------------------------------------------------------
    if cfg.amount_column and not diffs.empty:
        amount_diffs = diffs[(diffs["Field"] == cfg.amount_column) & diffs["Difference"].notna()]
        if len(amount_diffs) >= MIN_RECORDS:
            pct = amount_diffs["Difference %"].round(1)
            pct_counts = pct.value_counts()
            top_pct, top_count = pct_counts.index[0], int(pct_counts.iloc[0])
            share = top_count / len(amount_diffs)

            absolute = amount_diffs["Difference"].round(2).value_counts()
            top_abs, abs_count = absolute.index[0], int(absolute.iloc[0])

            if top_count >= MIN_RECORDS and share >= 0.25 and abs(top_pct) > 0:
                grp = amount_diffs[pct == top_pct]
                direction = "lower" if top_pct > 0 else "higher"
                findings.append(_finding(
                    title="Consistent percentage gap (likely a fee)",
                    text=(f"{top_count} of {len(amount_diffs)} amount differences are exactly "
                          f"{abs(top_pct):.1f}% {direction} in the target."),
                    keys=grp["Record Key"], risk_lookup=risk_lookup, total_exceptions=total_exc,
                    action=("A fixed percentage usually means a gateway or processing fee deducted "
                            "before settlement. Confirm the rate with the provider and record the "
                            "fee separately so it stops appearing as a mismatch."),
                    consistency=share,
                ))
            elif abs_count >= MIN_RECORDS and abs_count / len(amount_diffs) >= 0.25:
                grp = amount_diffs[amount_diffs["Difference"].round(2) == top_abs]
                findings.append(_finding(
                    title="Consistent fixed amount gap",
                    text=f"{abs_count} amount differences are all exactly {abs(top_abs):,.2f}.",
                    keys=grp["Record Key"], risk_lookup=risk_lookup, total_exceptions=total_exc,
                    action="A fixed amount usually means a flat charge, shipping fee or tax rule "
                           "applied in only one system.",
                    consistency=abs_count / len(amount_diffs),
                ))

    # ---- 3. placeholder values in other fields (for example a default customer id) ------
    if not diffs.empty:
        other = diffs[~diffs["Field"].isin([cfg.amount_column, cfg.status_column])]
        for field_name, grp in other.groupby("Field"):
            counts = grp["Target Value"].value_counts()
            value, count = counts.index[0], int(counts.iloc[0])
            if count >= MIN_RECORDS and count / len(grp) >= 0.5:
                findings.append(_finding(
                    title=f"Placeholder value in '{field_name}'",
                    text=f"{count} records have the same value '{value}' in the target "
                         f"for '{field_name}'.",
                    keys=grp.loc[grp["Target Value"] == value, "Record Key"],
                    risk_lookup=risk_lookup, total_exceptions=total_exc,
                    action="The same value appearing repeatedly is usually a default or test value. "
                           "Find which process writes it.",
                    consistency=count / len(grp),
                ))

    # ---- 4. duplicates and one-sided records ------------------------------------------------
    for status, title, action in (
        (Status.DUP_TARGET, "Duplicate records only in the target",
         "Often a retry or webhook delivered twice. Add a unique reference (idempotency key) "
         "and remove the extra copies."),
        (Status.DUP_SOURCE, "Duplicate records in the source",
         "Duplicate orders in the source system. Check order creation and import jobs."),
        (Status.MISSING_SOURCE, "Records in the target with no matching order",
         "Payments without an order: test payments, refunds or orders created outside the "
         "order system. Review before they are written off."),
        (Status.MISSING_KEY_TARGET, "Target records with no key",
         "These cannot be matched at all. Fix the export so every record carries its order id."),
        (Status.MISSING_KEY_SOURCE, "Source records with no key",
         "These cannot be matched at all. Fix the export so every record carries its order id."),
    ):
        group = with_risk[with_risk["Status"] == status]
        if len(group) >= 1 and (len(group) >= MIN_RECORDS or status in
                                (Status.MISSING_KEY_SOURCE, Status.MISSING_KEY_TARGET)):
            findings.append(_finding(
                title=title,
                text=f"{len(group)} records. Total exposure {group['Exposure'].sum():,.2f}.",
                keys=group["Record Key"], risk_lookup=risk_lookup, total_exceptions=total_exc,
                action=action, consistency=1.0,
            ))

    # ---- 5. concentration in an attribute (country, payment method, ...) -----------------
    for status in (Status.MISSING_TARGET, Status.MISMATCH, Status.TIMING):
        findings += _dimension_findings(with_risk, source, cfg, status, status,
                                        risk_lookup, total_exc)

    if not findings:
        return pd.DataFrame(columns=FINDING_COLUMNS)

    table = pd.DataFrame(findings).sort_values("Money at risk", ascending=False).reset_index(drop=True)
    return table


def keys_for_finding(table: pd.DataFrame, row_index: int) -> list:
    """The record keys behind one finding (kept in a hidden column)."""
    if table.empty or "_keys" not in table.columns:
        return []
    return table.loc[row_index, "_keys"]
