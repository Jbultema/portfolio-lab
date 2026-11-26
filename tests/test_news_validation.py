import json
from pathlib import Path

import pandas as pd
import pytest

from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.engine import replay
from portfolio_lab.news_validation import validate


def make_fixture(root, report, *, falsify_return=False):
    (root / "sources").mkdir(parents=True)
    (root / "targets").mkdir()
    report.mkdir()
    index = pd.bdate_range("2020-01-06", periods=12)
    prices = pd.DataFrame({"SPY": range(100, 112), "QQQ": range(100, 112), "SHY": 100.}, index=index)
    prices.to_parquet(root / "prices.parquet")
    policies = [{"id": f"test_{a}", "floor": 0., "risk_asset": a} for a in ("SPY", "QQQ")]
    registry = {"kind": "news_proxy_etf_screen", "authority": "research_only", "action_authorized": False,
                "policies": policies, "primary_start": str(index[0].date()), "purge_sessions": 0,
                "partitions": {k: [str(index[i].date()), str(index[i + 3].date())]
                               for k, i in (("development", 0), ("validation", 4), ("holdout_diagnostic", 8))},
                "scenarios": [{"id": "base", "publication_lag": 14, "execution_lag": 1, "cost_bps": 10}],
                "limitations": ["synthetic unit-test fixture; not performance evidence"]}
    (root / "registry.json").write_text(json.dumps(registry))
    (root / "status.json").write_text("[]")
    (root / "sources/acquisition.json").write_text("{}")
    returns = {}
    for policy in policies:
        target = prices * 0.
        target[policy["risk_asset"]] = 1.
        target.to_parquet(root / "targets" / f"{policy['id']}_lag14.parquet")
        returns[policy["id"]] = replay(prices, target, pd.Series(0., index=index)).returns
    source_meta = {"kind": "news_proxy_etf_screen", "authority": "research_only", "action_authorized": False,
                   "point_in_time_qualified": False, "rss_strategy_backtest": False,
                   "registry_sha256": digest(root / "registry.json"),
                   "artifacts": {str(p.relative_to(root)): digest(p) for p in root.rglob("*") if p.is_file()}}
    (root / "manifest.json").write_text(json.dumps(source_meta))
    frame = pd.DataFrame(returns)
    if falsify_return:
        frame.iloc[4, 0] += .1
    frame.to_parquet(report / "returns_base.parquet")
    (report / "development_selection.json").write_text(json.dumps({a: {"id": f"test_{a}"} for a in ("SPY", "QQQ")}))
    engine = Path(__file__).resolve().parents[1] / "src/portfolio_lab/engine.py"
    (report / "manifest.json").write_text(json.dumps({
        "input_manifest_sha256": digest(root / "manifest.json"), "engine_sha256": digest(engine),
        "artifacts": {str(p.relative_to(report)): digest(p) for p in report.rglob("*") if p.is_file()}}))


def test_selected_performance_paths_are_independently_replayed(tmp_path):
    make_fixture(tmp_path / "screen", tmp_path / "report")
    result = validate(tmp_path / "screen", tmp_path / "report", tmp_path / "audit")
    assert result["selected_scenario_replays"] == 2
    assert result["no_candidate_reselection"] and not result["action_authorized"]


def test_rebound_but_falsified_returns_fail_replay(tmp_path):
    make_fixture(tmp_path / "screen", tmp_path / "report", falsify_return=True)
    with pytest.raises(AssertionError):
        validate(tmp_path / "screen", tmp_path / "report", tmp_path / "audit")


def test_changed_performance_artifact_fails_readback(tmp_path):
    make_fixture(tmp_path / "screen", tmp_path / "report")
    (tmp_path / "report/development_selection.json").write_text("{}")
    with pytest.raises(ContractError):
        validate(tmp_path / "screen", tmp_path / "report", tmp_path / "audit")
