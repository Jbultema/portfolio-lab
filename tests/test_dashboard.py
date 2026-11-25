from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_without_evidence_does_not_invent_portfolio(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PORTFOLIO_LAB_REPORT", raising=False)
    app = AppTest.from_file(str(path)).run()
    assert not app.exception
    assert app.warning[0].value == "No evaluated portfolio"


def test_dashboard_with_missing_or_corrupt_evidence_fails_closed(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py"
    monkeypatch.setenv("PORTFOLIO_LAB_REPORT", str(tmp_path / "not-real"))
    app = AppTest.from_file(str(path)).run()
    assert not app.exception
    assert "Evidence unavailable" in app.error[0].value
