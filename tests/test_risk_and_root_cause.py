import pandas as pd
import pytest

from core import config
from core.pipeline import load_pipeline_files, run_pipeline
from core.reconciliation import ReconConfig, Status
from core.risk import add_risk, risk_summary


def _row(status, src=None, tgt=None, diff=None, copies=0):
    return {"Record Key": "k", "Status": status, "Source Count": 1, "Target Count": 1,
            "Source Amount": src, "Target Amount": tgt, "Amount Difference": diff,
            "Extra Copies": copies, "Fields Different": "", "Details": ""}


def risk_of(row):
    return add_risk(pd.DataFrame([row])).iloc[0]


def test_missing_in_target_exposes_full_amount():
    r = risk_of(_row(Status.MISSING_TARGET, src=5000.0))
    assert r["Exposure"] == 5000.0 and r["Risk Score"] == 5000.0


def test_amount_mismatch_exposes_only_the_gap():
    r = risk_of(_row(Status.MISMATCH, src=1000.0, tgt=880.0, diff=120.0))
    assert r["Exposure"] == 120.0
    assert r["Risk Score"] == pytest.approx(96.0)


def test_duplicate_exposes_extra_copies():
    r = risk_of(_row(Status.DUP_TARGET, tgt=800.0, copies=2))
    assert r["Exposure"] == 1600.0
    assert r["Risk Score"] == pytest.approx(1120.0)


def test_timing_delay_is_weighted_low():
    r = risk_of(_row(Status.TIMING, src=3000.0, tgt=3000.0, diff=0.0))
    assert r["Risk Score"] == pytest.approx(600.0)


def test_matched_has_no_risk():
    r = risk_of(_row(Status.MATCHED, src=100.0, tgt=100.0, diff=0.0))
    assert r["Risk Score"] == 0 and r["Priority"] == "None"


def test_summary_handles_no_exceptions():
    assert risk_summary(add_risk(pd.DataFrame([_row(Status.MATCHED, 1.0, 1.0, 0.0)])))["total_risk"] == 0


@pytest.fixture(scope="module")
def demo_output():
    cfg = ReconConfig.from_yaml(config.PIPELINE_CONFIG)
    source, target = load_pipeline_files(cfg)
    return run_pipeline(cfg, source, target)


def test_root_cause_finds_the_planted_patterns(demo_output):
    titles = " | ".join(demo_output.findings["Finding"])
    assert "Settlement or sync delay" in titles
    assert "percentage gap" in titles
    assert "payment_method = COD" in titles
    assert "Placeholder value" in titles
    assert "Duplicate records only in the target" in titles


def test_gateway_fee_is_detected_as_2_point_4_percent(demo_output):
    row = demo_output.findings[demo_output.findings["Finding"].str.contains("percentage gap")].iloc[0]
    assert "2.4%" in row["What we found"]


def test_health_score_is_between_0_and_100(demo_output):
    assert 0 <= demo_output.health["score"] <= 100
    assert demo_output.health["breakdown"]["Points"].sum() == pytest.approx(demo_output.health["score"], abs=0.2)
