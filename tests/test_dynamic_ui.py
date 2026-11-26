import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from portfolio_lab.contracts import ContractError
from portfolio_lab.dynamic_ui import comparison, load_evidence


def test_dynamic_comparison_is_anchored_to_unchanged_trade():
    frame = pd.DataFrame([{"candidate": "a", "role": "raw", "cagr": .15, "max_drawdown": -.12},
                          {"candidate": "trade_primary", "role": "raw", "cagr": .2, "max_drawdown": -.2},
                          {"candidate": "a", "role": "matched_trade", "cagr": .16, "max_drawdown": -.1}])
    frame = frame.assign(sharpe=1., average_risky_exposure=.7, annual_turnover=2.)
    table = comparison(frame, "a")
    assert table.iloc[1]["CAGR vs Trade"] == pytest.approx(-.05)
    assert table.iloc[1]["DD improvement"] == pytest.approx(.08)
    with pytest.raises(ContractError):
        comparison(frame[frame.candidate.eq("a")], "a")


def test_dynamic_report_pointer_is_hash_bound(tmp_path):
    (tmp_path / "manifest.json").write_text("{}")
    pointer = tmp_path / "latest.json"
    pointer.write_text(json.dumps({"report": str(tmp_path), "manifest_sha256": "0" * 64}))
    with pytest.raises(ContractError, match="pointer mismatch"):
        load_evidence(pointer)


def test_missing_dynamic_research_is_not_an_invented_allocation(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_LAB_DYNAMIC", str(tmp_path / "missing.json"))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py")).run()
    assert not app.exception
    assert "Verified dynamic research unavailable" in app.error[0].value
