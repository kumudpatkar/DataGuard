import pandas as pd
import pytest

from core.risk import add_risk
from core.workflow import Workflow
from core.reconciliation import summarize


def make_results(keys_and_status):
    rows = [{"Record Key": k, "Status": s, "Source Count": 1, "Target Count": 0,
             "Source Amount": 100.0, "Target Amount": None, "Amount Difference": None,
             "Extra Copies": 0, "Fields Different": "", "Details": f"detail {k}"}
            for k, s in keys_and_status]
    return add_risk(pd.DataFrame(rows))


def save(wf, results, user="tester"):
    stats = summarize(results, 10, 10)
    return wf.save_run("p1", results, stats, 90.0, 100.0, 123.0, user=user)


@pytest.fixture
def wf(tmp_path):
    return Workflow(tmp_path / "test.db")


def test_first_run_creates_open_tickets(wf):
    out = save(wf, make_results([("1", "Missing in Target"), ("2", "Missing in Target")]))
    assert out["new"] == 2
    assert wf.status_counts("p1") == {"Open": 2}


def test_ticket_is_auto_resolved_when_it_disappears(wf):
    save(wf, make_results([("1", "Missing in Target"), ("2", "Missing in Target")]))
    out = save(wf, make_results([("1", "Missing in Target")]))
    assert out["auto_resolved"] == 1
    counts = wf.status_counts("p1")
    assert counts["Open"] == 1 and counts["Resolved (auto)"] == 1


def test_fixed_ticket_reopens_if_it_comes_back(wf):
    save(wf, make_results([("1", "Missing in Target")]))
    ticket = int(wf.list_exceptions("p1").iloc[0]["Ticket"])
    wf.update_exceptions([ticket], "asha", status="Fixed")
    out = save(wf, make_results([("1", "Missing in Target")]))
    assert out["reopened"] == 1
    assert wf.list_exceptions("p1").iloc[0]["Status"] == "Open"


def test_assign_comment_and_audit_trail(wf):
    save(wf, make_results([("1", "Missing in Target")]))
    ticket = int(wf.list_exceptions("p1").iloc[0]["Ticket"])
    assert wf.update_exceptions([ticket], "asha", status="Investigating", assigned_to="Ravi") == 1
    wf.add_comment(ticket, "asha", "Asked the payment provider")
    row = wf.list_exceptions("p1").iloc[0]
    assert row["Status"] == "Investigating" and row["Assigned To"] == "Ravi"
    assert wf.list_comments(ticket).iloc[0]["Comment"] == "Asked the payment provider"
    log = " ".join(wf.audit_log()["Action"])
    assert "Updated ticket" in log and "Commented" in log


def test_invalid_status_is_rejected(wf):
    save(wf, make_results([("1", "Missing in Target")]))
    with pytest.raises(ValueError):
        wf.update_exceptions([1], "asha", status="Banana")


def test_run_history_is_kept(wf):
    save(wf, make_results([("1", "Missing in Target")]))
    save(wf, make_results([("1", "Missing in Target")]))
    assert len(wf.list_runs("p1")) == 2
