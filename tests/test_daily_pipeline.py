
import sys
from types import SimpleNamespace

import pandas as pd

from scripts import run_daily


def setup_daily_test(monkeypatch, tmp_path, score=90.0):
    """Prepare a daily pipeline test without using the real database."""

    cfg = SimpleNamespace(name="orders_vs_payments")

    stats = {
        "source_rows": 10,
        "target_rows": 10,
        "total_records": 10,
        "matched": 9,
        "exceptions": 1,
        "match_rate": 90.0,
    }

    results = pd.DataFrame([
        {
            "Record Key": "1001",
            "Status": "Missing in Target",
            "Risk Score": 50,
        }
    ])

    findings = pd.DataFrame(
        columns=["Finding", "What we found"]
    )

    output = SimpleNamespace(
        recon=SimpleNamespace(stats=stats),
        results=results,
        exceptions=results.copy(),
        risk={"total_risk": 100.0},
        health={"score": score, "label": "Good"},
        rule_pass_rate=95.0,
        findings=findings,
    )

    saved_result = {
        "run_id": 1,
        "new": 1,
        "still_present": 0,
        "reopened": 0,
        "auto_resolved": 0,
    }

    class FakeWorkflow:
        def __init__(self):
            pass

        def save_run(self, **kwargs):
            return saved_result

    alert_calls = []

    monkeypatch.setattr(
        run_daily.ReconConfig,
        "from_yaml",
        lambda *args: cfg,
    )
    monkeypatch.setattr(
        run_daily,
        "load_pipeline_files",
        lambda cfg: (pd.DataFrame(), pd.DataFrame()),
    )
    monkeypatch.setattr(
        run_daily,
        "run_pipeline",
        lambda cfg, source, target: output,
    )
    monkeypatch.setattr(
        run_daily,
        "Workflow",
        FakeWorkflow,
    )
    monkeypatch.setattr(
        run_daily,
        "alert_if_needed",
        lambda *args: alert_calls.append(args) or {"Test": "sent"},
    )
    monkeypatch.setattr(
        run_daily,
        "plain_money",
        lambda value: f"Rs. {value}",
    )
    monkeypatch.setattr(
        run_daily.config,
        "REPORTS_DIR",
        tmp_path,
    )

    return saved_result, alert_calls


def test_daily_pipeline_saves_report_and_workflow(
    monkeypatch,
    tmp_path,
):
    saved_result, alert_calls = setup_daily_test(
        monkeypatch,
        tmp_path,
        score=90.0,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_daily.py", "--no-alert"],
    )

    exit_code = run_daily.main()

    report = (
        tmp_path
        / f"orders_vs_payments_{run_daily.date.today().isoformat()}.csv"
    )

    assert exit_code == 0
    assert report.exists()
    assert saved_result["run_id"] == 1
    assert alert_calls == []


def test_daily_pipeline_sends_alert_below_threshold(
    monkeypatch,
    tmp_path,
):
    _, alert_calls = setup_daily_test(
        monkeypatch,
        tmp_path,
        score=70.0,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_daily.py"],
    )

    exit_code = run_daily.main()

    assert exit_code == 1
    assert len(alert_calls) == 1


def test_daily_pipeline_no_alert_option_suppresses_alert(
    monkeypatch,
    tmp_path,
):
    _, alert_calls = setup_daily_test(
        monkeypatch,
        tmp_path,
        score=70.0,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_daily.py", "--no-alert"],
    )

    exit_code = run_daily.main()

    assert exit_code == 1
    assert alert_calls == []
