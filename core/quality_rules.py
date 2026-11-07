"""Data quality rules engine.

Rules are small dictionaries, so they can live in a YAML file (config/rules.yaml)
and be run many at a time:

    {"column": "Quantity", "type": "positive"}
    {"column": "Status",   "type": "allowed_values", "allowed_values": ["Open", "Closed"]}

Supported rule types
--------------------
required        value must not be empty
positive        value must be a number greater than 0
non_negative    value must be a number of 0 or more
unique          value must not repeat
allowed_values  value must be one of a list
range           number must be between "min" and "max"
regex           text must fully match "pattern"
date_format     value must be a date in "format" (for example %Y-%m-%d)
cross_column    "column" must equal  left[0] <operator> left[1]  (within "tolerance")
referential     value must exist in another table (pass it in ``references``)

``suggest_rules`` can also look at a file and propose rules automatically.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ISSUE_COLUMNS = ["Row", "Column", "Rule", "Value", "Issue", "Severity", "Rule Name"]

RULE_TYPES = [
    "required", "positive", "non_negative", "unique", "allowed_values",
    "range", "regex", "date_format", "cross_column", "referential",
]

OPERATORS = {
    "multiply": lambda a, b: a * b,
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "divide": lambda a, b: a / b.replace(0, np.nan),
}


def _blank(values: pd.Series) -> pd.Series:
    """True for missing or whitespace-only values."""
    return values.isna() | values.astype("string").str.strip().eq("").fillna(True)


def _invalid_mask(df: pd.DataFrame, rule: dict, references: dict | None):
    """Return (invalid_mask, issue_text) for one rule, or (None, message) if it cannot run."""
    column = rule["column"]
    rule_type = rule["type"]
    values = df[column]

    if rule_type == "required":
        return _blank(values), "Value is required but empty"

    if rule_type == "positive":
        numeric = pd.to_numeric(values, errors="coerce")
        return numeric.isna() | (numeric <= 0), "Value must be a number greater than 0"

    if rule_type == "non_negative":
        numeric = pd.to_numeric(values, errors="coerce")
        return numeric.isna() | (numeric < 0), "Value must be a number of 0 or more"

    if rule_type == "unique":
        return values.notna() & values.duplicated(keep=False), "Value is not unique"

    if rule_type == "allowed_values":
        allowed = [str(v) for v in rule.get("allowed_values", [])]
        invalid = values.notna() & ~values.astype(str).isin(allowed)
        return invalid, f"Value is not one of: {', '.join(allowed)}"

    if rule_type == "range":
        low, high = rule.get("min"), rule.get("max")
        numeric = pd.to_numeric(values, errors="coerce")
        invalid = values.notna() & numeric.isna()
        if low is not None:
            invalid |= numeric < float(low)
        if high is not None:
            invalid |= numeric > float(high)
        return invalid, f"Value must be between {low} and {high}"

    if rule_type == "regex":
        pattern = rule.get("pattern", ".*")
        text = values.astype("string")
        ok = text.str.fullmatch(pattern).fillna(False)
        return values.notna() & ~ok, f"Value does not match pattern {pattern}"

    if rule_type == "date_format":
        fmt = rule.get("format", "%Y-%m-%d")
        parsed = pd.to_datetime(values, format=fmt, errors="coerce")
        return values.notna() & parsed.isna(), f"Value is not a valid date in format {fmt}"

    if rule_type == "cross_column":
        left = rule.get("left", [])
        operator = rule.get("operator", "multiply")
        if len(left) != 2 or operator not in OPERATORS or any(c not in df.columns for c in left):
            return None, "cross_column needs two existing columns in 'left' and a valid operator"
        a = pd.to_numeric(df[left[0]], errors="coerce")
        b = pd.to_numeric(df[left[1]], errors="coerce")
        expected = OPERATORS[operator](a, b)
        actual = pd.to_numeric(values, errors="coerce")
        tolerance = float(rule.get("tolerance", 0.01))
        comparable = expected.notna() & actual.notna()
        invalid = comparable & ((actual - expected).abs() > tolerance)
        return invalid, f"{column} should equal {left[0]} {operator} {left[1]}"

    if rule_type == "referential":
        name = rule.get("reference")
        ref_column = rule.get("reference_column", column)
        if not references or name not in references or ref_column not in references[name].columns:
            return None, f"Reference table '{name}' with column '{ref_column}' was not provided"
        valid = set(references[name][ref_column].dropna().astype(str))
        return values.notna() & ~values.astype(str).isin(valid), f"Value not found in {name}.{ref_column}"

    return None, f"Unknown rule type '{rule_type}'"


def run_quality_rules_engine(df: pd.DataFrame, rules: list[dict],
                             references: dict | None = None) -> pd.DataFrame:
    """Run one or many rules and return one row per failed value.

    ``Row`` is the row number as it appears in the CSV file the data came from
    (the header is row 1, so the first data row is row 2).
    """
    issues: list[dict] = []
    file_rows = np.arange(len(df)) + 2

    for rule in rules:
        column = rule["column"]
        rule_type = rule["type"]
        name = rule.get("name", f"{column} {rule_type}")
        severity = rule.get("severity", "Medium")

        if column not in df.columns:
            issues.append({"Row": None, "Column": column, "Rule": rule_type, "Value": None,
                           "Issue": "Column not found", "Severity": severity, "Rule Name": name})
            continue

        invalid, message = _invalid_mask(df, rule, references)

        if invalid is None:  # the rule could not run, tell the user instead of ignoring it
            issues.append({"Row": None, "Column": column, "Rule": rule_type, "Value": None,
                           "Issue": message, "Severity": severity, "Rule Name": name})
            continue

        invalid = invalid.fillna(False).to_numpy(dtype=bool)
        if not invalid.any():
            continue

        failed_values = df[column].to_numpy()[invalid]
        for row_number, value in zip(file_rows[invalid], failed_values):
            issues.append({
                "Row": int(row_number), "Column": column, "Rule": rule_type,
                "Value": str(value), "Issue": message,
                "Severity": severity, "Rule Name": name,
            })

    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def rule_scorecard(df: pd.DataFrame, rules: list[dict], issues: pd.DataFrame) -> pd.DataFrame:
    """One row per rule: how many rows failed and what percent passed."""
    rows = []
    total = len(df)
    for rule in rules:
        name = rule.get("name", f"{rule['column']} {rule['type']}")
        failed = 0
        if not issues.empty:
            failed = int(((issues["Rule Name"] == name) & issues["Row"].notna()).sum())
        rows.append({
            "Rule Name": name,
            "Column": rule["column"],
            "Type": rule["type"],
            "Severity": rule.get("severity", "Medium"),
            "Failed Rows": failed,
            "Pass Rate %": round((total - failed) / total * 100.0, 2) if total else 100.0,
        })
    return pd.DataFrame(rows)


def overall_pass_rate(scorecard: pd.DataFrame) -> float:
    """Average pass rate across rules (100 if there are no rules)."""
    if scorecard.empty:
        return 100.0
    return float(scorecard["Pass Rate %"].mean())


# ---------------------------------------------------------------------------
# rules in YAML files
# ---------------------------------------------------------------------------

def load_rule_sets(path: Path) -> dict:
    """Read config/rules.yaml and return {name: {"description": ..., "rules": [...]}}."""
    if not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return {
        item["name"]: {"description": item.get("description", ""), "rules": item.get("rules", [])}
        for item in raw.get("rule_sets", [])
    }


def rules_to_yaml(name: str, rules: list[dict], description: str = "") -> str:
    """Turn rules into YAML text the user can paste into config/rules.yaml."""
    return yaml.safe_dump(
        {"rule_sets": [{"name": name, "description": description, "rules": rules}]},
        sort_keys=False, allow_unicode=True,
    )


# ---------------------------------------------------------------------------
# automatic rule suggestions
# ---------------------------------------------------------------------------

AMOUNT_WORDS = ("price", "amount", "cost", "total", "revenue", "sales", "fee")
QUANTITY_WORDS = ("qty", "quantity", "units", "count")
ID_WORDS = ("id", "no", "number", "code", "ref")
DATE_WORDS = ("date", "time", "created", "updated")


def suggest_rules(df: pd.DataFrame, max_allowed_values: int = 10) -> list[dict]:
    """Look at the data and propose sensible rules, each with a reason."""
    suggestions: list[dict] = []
    n = len(df)
    if n == 0:
        return suggestions

    for column in df.columns:
        series = df[column]
        lowered = str(column).lower()
        non_null = series.dropna()
        missing_pct = series.isna().mean() * 100

        if missing_pct == 0:
            suggestions.append({"column": column, "type": "required",
                                "reason": "Column is never empty in this file."})

        numeric = pd.to_numeric(series, errors="coerce")
        is_numeric = len(non_null) > 0 and numeric.notna().sum() >= 0.95 * len(non_null)

        if is_numeric:
            clean = numeric.dropna()
            if any(w in lowered for w in AMOUNT_WORDS + QUANTITY_WORDS) and not any(
                lowered.endswith(w) for w in ("id",)
            ):
                if (clean > 0).all():
                    suggestions.append({"column": column, "type": "positive",
                                        "reason": f"All values are above 0 (min {clean.min():g})."})
                elif (clean >= 0).all():
                    suggestions.append({"column": column, "type": "non_negative",
                                        "reason": "No negative values in this file."})

        looks_like_id = any(lowered.endswith(w) for w in ID_WORDS)
        if looks_like_id:
            suggestions.append({"column": column, "type": "unique",
                                "reason": "Column looks like an identifier; its values should be unique."})

        if not is_numeric and any(w in lowered for w in DATE_WORDS) and len(non_null):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
                parsed = pd.to_datetime(non_null.astype(str), format=fmt, errors="coerce")
                if parsed.notna().mean() >= 0.98:
                    suggestions.append({"column": column, "type": "date_format", "format": fmt,
                                        "reason": f"Nearly all values look like dates in {fmt}."})
                    break

        if (not is_numeric and 2 <= series.nunique() <= max_allowed_values
                and n >= 20 and not any(w in lowered for w in DATE_WORDS)):
            values = sorted(non_null.astype(str).unique().tolist())
            suggestions.append({"column": column, "type": "allowed_values", "allowed_values": values,
                                "reason": f"Only {len(values)} different values appear."})

    return suggestions
