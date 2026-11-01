import pandas as pd
import pytest

from core.health import health_score
from core.retail import (LINE_FEES, LINE_POSTAGE, LINE_PRODUCT, classify_line,
                         clean_retail, kpi_trust, revenue_bridge, top_products)


@pytest.fixture
def raw():
    return pd.DataFrame({
        "InvoiceNo": ["1", "2", "3", "C4", "5", "5"],
        "StockCode": ["10001", "10002", "POST", "10001", "AMAZONFEE", "AMAZONFEE"],
        "Description": ["MUG", "BOWL", "POSTAGE", "MUG", "AMAZON FEE", "AMAZON FEE"],
        "Quantity": [10, 5, 1, -2, -1, -1],
        "InvoiceDate": ["12/1/2010 8:26"] * 6,
        "UnitPrice": [2.0, 4.0, 15.0, 2.0, 100.0, 100.0],
        "CustomerID": ["111", None, "112", "111", None, None],
        "Country": ["UK"] * 6,
    })


def test_classify_line_types():
    kinds = classify_line(pd.Series(["10001", "POST", "AMAZONFEE", "M", "D", "gift_0001_20"]))
    assert list(kinds)[:3] == [LINE_PRODUCT, LINE_POSTAGE, LINE_FEES]
    assert kinds.iloc[3] == "Manual Adjustment" and kinds.iloc[5] == "Gift Voucher"


def test_exact_duplicate_rows_are_removed(raw):
    df, info = clean_retail(raw)
    assert info["duplicates_removed"] == 1 and len(df) == 5


def test_revenue_bridge_adds_up_exactly(raw):
    df, _ = clean_retail(raw)
    bridge = revenue_bridge(df)
    net = bridge.loc[bridge["Step"] == "Net revenue", "Amount"].iloc[0]
    parts = bridge.loc[bridge["Step"] != "Net revenue", "Amount"].sum()
    assert net == pytest.approx(df["SalesAmount"].sum())
    assert parts == pytest.approx(net)


def test_top_products_exclude_postage_and_fees(raw):
    df, _ = clean_retail(raw)
    names = set(top_products(df)["Description"])
    assert names == {"MUG", "BOWL"}


def test_trust_score_reflects_unidentified_customers(raw):
    df, _ = clean_retail(raw)
    trust = kpi_trust(df)
    assert 0 < trust["trust_pct"] < 100
    assert trust["unidentified_value"] == pytest.approx(5 * 4.0)


def test_missing_columns_give_clear_error():
    with pytest.raises(ValueError, match="missing required columns"):
        clean_retail(pd.DataFrame({"a": [1]}))


def test_health_score_weights():
    stats = {"total_records": 100, "matched": 100, "timing": 0,
             "duplicate_source": 0, "duplicate_target": 0}
    assert health_score(stats, 100, 100)["score"] == 100.0
    # 95% match -> Matching part 85 -> 0.6*85 + 15 + 15 + 10 = 91
    ok = {**stats, "matched": 95}
    assert health_score(ok, 100, 100)["score"] == pytest.approx(91.0)
    # half the records wrong -> Matching part is 0 -> only the other three parts remain
    worse = {**stats, "matched": 50}
    assert health_score(worse, 100, 100)["score"] == pytest.approx(40.0)


def test_timing_delay_counts_as_half_a_match():
    stats = {"total_records": 100, "matched": 90, "timing": 10,
             "duplicate_source": 0, "duplicate_target": 0}
    # effective match 95% -> Matching part 85
    assert health_score(stats, 100, 100)["breakdown"].iloc[0]["Value %"] == pytest.approx(85.0)
