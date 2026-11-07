import pandas as pd

from core.config import RULES_CONFIG
from core.quality_rules import (load_rule_sets, overall_pass_rate, rule_scorecard,
                                run_quality_rules_engine, suggest_rules)


def test_required_rule_finds_blank_values():
    df = pd.DataFrame({"Name": ["Asha", None, ""]})
    result = run_quality_rules_engine(df, [{"column": "Name", "type": "required"}])
    assert len(result) == 2
    assert result.iloc[0]["Column"] == "Name"


def test_positive_rule_finds_zero_and_text():
    df = pd.DataFrame({"Amount": [250.0, 100.0, 0.0, "abc"]})
    result = run_quality_rules_engine(df, [{"column": "Amount", "type": "positive"}])
    assert set(result["Value"]) == {"0.0", "abc"}


def test_unique_rule_flags_all_repeats():
    df = pd.DataFrame({"OrderID": [1001, 1002, 1002, 1003]})
    result = run_quality_rules_engine(df, [{"column": "OrderID", "type": "unique"}])
    assert len(result) == 2
    assert set(result["Value"]) == {"1002"}


def test_allowed_values_rule():
    df = pd.DataFrame({"Status": ["Open", "Closed", "Weird"]})
    rule = {"column": "Status", "type": "allowed_values", "allowed_values": ["Open", "Closed"]}
    result = run_quality_rules_engine(df, [rule])
    assert list(result["Value"]) == ["Weird"]


def test_row_numbers_match_csv_rows():
    df = pd.DataFrame({"Amount": [5, 0]})
    result = run_quality_rules_engine(df, [{"column": "Amount", "type": "positive"}])
    assert int(result.iloc[0]["Row"]) == 3   # header is row 1, so the 2nd data row is row 3


def test_range_regex_and_date_rules():
    df = pd.DataFrame({
        "Age": [10, 200], "Code": ["AB12", "xx"], "Day": ["2026-01-05", "05/01/2026"],
    })
    rules = [
        {"column": "Age", "type": "range", "min": 0, "max": 120},
        {"column": "Code", "type": "regex", "pattern": r"[A-Z]{2}\d{2}"},
        {"column": "Day", "type": "date_format", "format": "%Y-%m-%d"},
    ]
    result = run_quality_rules_engine(df, rules)
    assert sorted(result["Value"]) == ["05/01/2026", "200", "xx"]


def test_cross_column_rule():
    df = pd.DataFrame({"Qty": [2, 3], "Price": [10.0, 5.0], "Total": [20.0, 99.0]})
    rule = {"column": "Total", "type": "cross_column", "left": ["Qty", "Price"], "operator": "multiply"}
    result = run_quality_rules_engine(df, [rule])
    assert list(result["Value"]) == ["99.0"]


def test_referential_rule():
    df = pd.DataFrame({"Customer": ["C1", "C9"]})
    refs = {"customers": pd.DataFrame({"Customer": ["C1", "C2"]})}
    rule = {"column": "Customer", "type": "referential", "reference": "customers"}
    result = run_quality_rules_engine(df, [rule], references=refs)
    assert list(result["Value"]) == ["C9"]


def test_rules_that_cannot_run_are_reported_not_ignored():
    df = pd.DataFrame({"A": [1]})
    result = run_quality_rules_engine(df, [
        {"column": "Missing", "type": "required"},
        {"column": "A", "type": "nonsense"},
    ])
    issues = set(result["Issue"])
    assert "Column not found" in issues
    assert any("Unknown rule type" in i for i in issues)


def test_scorecard_pass_rate():
    df = pd.DataFrame({"Amount": [1, 2, 0, 4]})
    rules = [{"column": "Amount", "type": "positive", "name": "Amount above zero"}]
    issues = run_quality_rules_engine(df, rules)
    card = rule_scorecard(df, rules, issues)
    assert card.iloc[0]["Failed Rows"] == 1
    assert overall_pass_rate(card) == 75.0


def test_rule_sets_load_from_yaml():
    sets = load_rule_sets(RULES_CONFIG)
    assert "orders" in sets and "retail_transactions" in sets
    assert all("column" in r and "type" in r for r in sets["orders"]["rules"])


def test_suggest_rules_finds_sensible_rules():
    df = pd.DataFrame({
        "order_id": range(1, 31),
        "order_amount": [10.5] * 30,
        "status": ["Open", "Closed"] * 15,
        "order_date": ["2026-01-01"] * 30,
    })
    types = {(s["column"], s["type"]) for s in suggest_rules(df)}
    assert ("order_id", "unique") in types
    assert ("order_amount", "positive") in types
    assert ("status", "allowed_values") in types
    assert ("order_date", "date_format") in types



def test_suggest_rules_flags_duplicate_id_columns():
    df = pd.DataFrame({
        "order_id": [1001, 1002, 1002, 1003],
        "amount": [100, 200, 300, 400],
    })

    suggestions = suggest_rules(df)

    assert any(
        rule["column"] == "order_id" and rule["type"] == "unique"
        for rule in suggestions
    )
