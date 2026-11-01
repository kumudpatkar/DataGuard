"""Opens every page of the Streamlit app and checks that nothing crashes."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_FILE = str(Path(__file__).resolve().parent.parent / "app.py")

PAGES = ["Overview", "Reconciliation", "Exceptions", "Quality Rules",
         "Health & Alerts", "Retail Analytics"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAGUARD_DB", str(tmp_path / "smoke.db"))
    import importlib
    from core import config, workflow
    importlib.reload(config)
    importlib.reload(workflow)
    at = AppTest.from_file(APP_FILE, default_timeout=120)
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_every_page_opens_without_errors(app, page):
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, [e.value for e in app.exception]


def test_demo_flow_run_save_and_tickets(app):
    app.sidebar.radio[0].set_value("Reconciliation").run()
    next(b for b in app.button if b.label == "Run reconciliation").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("Results for" in s.value for s in app.subheader)

    next(b for b in app.button if b.label == "Save run and create tickets").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("tickets" in s.value.lower() for s in app.success)

    app.sidebar.radio[0].set_value("Exceptions").run()
    assert not app.exception, [e.value for e in app.exception]

    app.sidebar.radio[0].set_value("Overview").run()
    assert not app.exception, [e.value for e in app.exception]
