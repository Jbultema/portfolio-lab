from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_missing_adaptive_research_does_not_fall_through_to_old_study(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_LAB_ADAPTIVE", str(tmp_path / "missing.json"))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py")).run()
    assert not app.exception
    assert "Verified dynamic research unavailable" in app.error[0].value
