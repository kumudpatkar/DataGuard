import pandas as pd
import pytest

from core.reconciliation import ReconConfig, Status, reconcile


def make_cfg(**overrides):
    base = dict(
        key_source="id", key_target="id",
        column_map={"amount": "amount", "status": "status"},
        amount_column="amount", status_column="status",
        abs_tolerance=1.0, prefix_regex="^ORD-",
        timing_rules=[("Completed", "Pending")],
    )
    base.update(overrides)
    return ReconConfig(**base)


def status_of(result, key):
    row = result.results[result.results["Record Key"] == str(key)]
    return row.iloc[0]["Status"]


def test_prefix_and_whitespace_keys_match():
    src = pd.DataFrame({"id": [1001, 1002], "amount": [100.0, 200.0], "status": ["Completed"] * 2})
    tgt = pd.DataFrame({"id": ["ORD-1001", " ord-1002 "], "amount": [100.0, 200.0], "status": ["Completed"] * 2})
    result = reconcile(src, tgt, make_cfg())
    assert result.stats["matched"] == 2
    assert result.stats["exceptions"] == 0


def test_rounding_difference_is_tolerated_but_real_gap_is_not():
    src = pd.DataFrame({"id": [1, 2], "amount": [100.0, 100.0], "status": ["Completed"] * 2})
    tgt = pd.DataFrame({"id": [1, 2], "amount": [100.4, 97.0], "status": ["Completed"] * 2})
    result = reconcile(src, tgt, make_cfg(prefix_regex=None))
    assert status_of(result, 1) == Status.MATCHED
    assert status_of(result, 2) == Status.MISMATCH
    assert result.stats["within_tolerance"] == 1


def test_timing_rule_is_not_a_mismatch():
    src = pd.DataFrame({"id": [1, 2], "amount": [10.0, 10.0], "status": ["Completed", "Completed"]})
    tgt = pd.DataFrame({"id": [1, 2], "amount": [10.0, 10.0], "status": ["Pending", "Cancelled"]})
    result = reconcile(src, tgt, make_cfg(prefix_regex=None))
    assert status_of(result, 1) == Status.TIMING
    assert status_of(result, 2) == Status.MISMATCH


def test_tolerance_is_not_applied_to_other_numeric_columns():
    cfg = make_cfg(prefix_regex=None, column_map={"amount": "amount", "qty": "qty"})
    src = pd.DataFrame({"id": [1], "amount": [10.0], "qty": [5]})
    tgt = pd.DataFrame({"id": [1], "amount": [10.0], "qty": [6]})
    result = reconcile(src, tgt, cfg)
    assert status_of(result, 1) == Status.MISMATCH


def test_missing_records_both_directions():
    src = pd.DataFrame({"id": [1, 2], "amount": [10.0, 20.0], "status": ["Completed"] * 2})
    tgt = pd.DataFrame({"id": [2, 3], "amount": [20.0, 30.0], "status": ["Completed"] * 2})
    result = reconcile(src, tgt, make_cfg(prefix_regex=None))
    assert status_of(result, 1) == Status.MISSING_TARGET
    assert status_of(result, 3) == Status.MISSING_SOURCE
    assert status_of(result, 2) == Status.MATCHED


def test_duplicates_are_reported_not_dropped():
    src = pd.DataFrame({"id": [1, 2], "amount": [10.0, 20.0], "status": ["Completed"] * 2})
    tgt = pd.DataFrame({"id": [1, 1, 2], "amount": [10.0, 10.0, 20.0], "status": ["Completed"] * 3})
    result = reconcile(src, tgt, make_cfg(prefix_regex=None))
    row = result.results[result.results["Status"] == Status.DUP_TARGET].iloc[0]
    assert row["Record Key"] == "1"
    assert row["Extra Copies"] == 1
    assert status_of(result, 2) == Status.MATCHED

    
def test_duplicate_target_with_amount_mismatch_is_reported():
    src = pd.DataFrame({
        "id": [1],
        "amount": [100.0],
        "status": ["Completed"],
    })

    tgt = pd.DataFrame({
        "id": [1, 1],
        "amount": [100.0, 150.0],
        "status": ["Completed", "Completed"],
    })

    result = reconcile(src, tgt, make_cfg(prefix_regex=None))

    duplicate_rows = result.results[
        result.results["Status"] == Status.DUP_TARGET
    ]

    assert not duplicate_rows.empty
    assert duplicate_rows.iloc[0]["Record Key"] == "1"
    assert duplicate_rows.iloc[0]["Extra Copies"] == 1

    details = str(duplicate_rows.iloc[0]["Details"])
    assert "100.0" in details
    assert "150.0" in details



def test_blank_keys_are_reported():
    src = pd.DataFrame({"id": [1, None], "amount": [10.0, 5.0], "status": ["Completed"] * 2})
    tgt = pd.DataFrame({"id": [1, ""], "amount": [10.0, 5.0], "status": ["Completed"] * 2})
    result = reconcile(src, tgt, make_cfg(prefix_regex=None))
    assert result.stats["missing_key"] == 2


def test_missing_key_column_gives_clear_error():
    with pytest.raises(ValueError, match="Key column"):
        reconcile(pd.DataFrame({"x": [1]}), pd.DataFrame({"id": [1]}), make_cfg())


def test_unknown_mapped_column_is_skipped_with_warning():
    cfg = make_cfg(prefix_regex=None, column_map={"amount": "amount", "ghost": "ghost"})
    src = pd.DataFrame({"id": [1], "amount": [1.0]})
    tgt = pd.DataFrame({"id": [1], "amount": [1.0]})
    result = reconcile(src, tgt, cfg)
    assert result.warnings and "ghost" in result.warnings[0]


def test_empty_inputs_do_not_crash():
    cols = ["id", "amount", "status"]
    result = reconcile(pd.DataFrame(columns=cols), pd.DataFrame(columns=cols), make_cfg())
    assert result.stats["total_records"] == 0

def test_duplicate_target_amount_mismatch_has_field_level_details():
    src = pd.DataFrame({
        "id": [1],
        "amount": [100.0],
        "status": ["Completed"],
    })

    tgt = pd.DataFrame({
        "id": [1, 1],
        "amount": [100.0, 150.0],
        "status": ["Completed", "Completed"],
    })

    result = reconcile(src, tgt, make_cfg(prefix_regex=None))

    amount_diffs = result.diffs[
        (result.diffs["Record Key"] == "1")
        & (result.diffs["Field"] == "amount")
    ]

    assert not amount_diffs.empty

    mismatch = amount_diffs[
        (amount_diffs["Source Value"] == "100.0")
        & (amount_diffs["Target Value"] == "150.0")
    ]

    assert not mismatch.empty
    assert mismatch.iloc[0]["Difference"] == -50.0

def test_row_match_rate_with_duplicate_source_rows():
    src = pd.DataFrame({"id": [1, 1, 2]})
    tgt = pd.DataFrame({"id": [1, 2]})

    result = reconcile(src, tgt, make_cfg(prefix_regex=None))

    assert result.stats["source_rows"] == 3
    assert result.stats["target_rows"] == 2
    assert result.stats["matched"] == 1
    assert result.stats["row_match_rate"] == pytest.approx(33.33, abs=0.01)


def test_row_match_rate_when_all_rows_match():
    src = pd.DataFrame({"id": [1, 2, 3]})
    tgt = pd.DataFrame({"id": [1, 2, 3]})

    result = reconcile(src, tgt, make_cfg(prefix_regex=None))

    assert result.stats["row_match_rate"] == pytest.approx(100.0)


def test_row_match_rate_when_target_has_missing_rows():
    src = pd.DataFrame({"id": [1, 2]})
    tgt = pd.DataFrame({"id": [1]})

    result = reconcile(src, tgt, make_cfg(prefix_regex=None))

    assert result.stats["source_rows"] == 2
    assert result.stats["target_rows"] == 1
    assert result.stats["row_match_rate"] == pytest.approx(50.0)
