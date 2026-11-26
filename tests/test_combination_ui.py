import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from portfolio_lab.combination_ui import appraisal, comparison_table, load_evidence
from portfolio_lab.contracts import ContractError


def test_comparison_is_relative_to_unchanged_trade_not_top_row():
    rows = pd.DataFrame([
        {"candidate": "other", "cagr": .10, "max_drawdown": -.1},
        {"candidate": "trade_primary", "cagr": .15, "max_drawdown": -.2},
    ]).assign(sharpe=1., average_risky_exposure=.8, annual_turnover=2.)
    table = comparison_table(rows)
    assert table.loc["other", "CAGR vs Trade"] == pytest.approx(-.05)
    assert table.loc["other", "DD improvement vs Trade"] == pytest.approx(.1)
    with pytest.raises(ContractError):
        comparison_table(rows.iloc[:1])


def test_manifest_pointer_cannot_be_substituted(tmp_path):
    (tmp_path / "manifest.json").write_text("{}")
    pointer = tmp_path / "latest.json"
    pointer.write_text(json.dumps({"report": str(tmp_path), "manifest_sha256": "0" * 64}))
    with pytest.raises(ContractError, match="pointer mismatch"):
        load_evidence(pointer)


def test_appraisal_does_not_call_larger_drawdown_an_improvement():
    rows = pd.DataFrame([{"candidate": "trade_primary", "cagr": .2, "max_drawdown": -.1},
                         {"candidate": "blend", "cagr": .15, "max_drawdown": -.12},
                         {"candidate": "cash", "cagr": .13, "max_drawdown": -.08}])
    messages = appraisal(rows, blend="blend", cash="cash")
    assert "-5.00" in messages[0] and "-2.00" in messages[0]
    assert "+2.00" in messages[1] and "-4.00" in messages[1]


def test_missing_evidence_is_visible_and_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLIO_LAB_STRESS", str(tmp_path / "absent.json"))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py")).run()
    assert not app.exception
    assert "Verified combination evidence unavailable" in app.error[0].value
