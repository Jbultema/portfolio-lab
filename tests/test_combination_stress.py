import json

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.combination_stress import (
    bound,
    core_specs,
    joint_intervals,
    load_probes,
    mix,
    risk_control,
    shock_loss,
    stale_target,
)
from portfolio_lab.contracts import ContractError, digest, load_bundle


@pytest.fixture
def panel():
    dates = pd.date_range("2020-01-02", periods=300, freq="B")
    a = pd.DataFrame({"NVDA": .5, "GLD": .2}, index=dates)
    b = pd.DataFrame({"NVDA": 0., "GLD": .7}, index=dates)
    return dates, {"a": a, "b": b}


def probe_fixture(root):
    root.mkdir()
    dates = pd.date_range("2020-01-02", periods=300, freq="B")
    prices = pd.DataFrame(100., index=dates, columns=["A"])
    prices.to_parquet(root / "prices.parquet")
    (prices * .001).to_parquet(root / "probe.parquet")
    meta = {"schema_version": 1, "kind": "conditional_event_probes_v1", "system": "fundamental-event-trader",
        "admitted_specialist": False, "authority": "isolated_conditional_research_only",
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False,
        "data_end": str(dates[-1].date()), "experts": [{"id": "probe", "weights_file": "probe.parquet",
            "portfolio_allocation_allowed": False, "evidence_status": "conditional_survivor_sample_not_admitted",
            "target_semantics": "close_known_risky_budgets"}],
        "artifacts": {p.name: digest(p) for p in root.iterdir()}}
    (root / "manifest.json").write_text(json.dumps(meta))
    return meta


def test_probe_is_available_only_to_isolated_stress_reader(tmp_path):
    root = tmp_path / "probe"
    probe_fixture(root)
    _, targets, meta = load_probes(root)
    assert list(targets) == ["probe"]
    assert meta["admitted_specialist"] is False
    with pytest.raises(ContractError):
        load_bundle(root)


@pytest.mark.parametrize("key,value", [("admitted_specialist", True), ("portfolio_allocation_allowed", True),
    ("automatic_promotion_allowed", True), ("authority", "research_only")])
def test_probe_cannot_self_promote(tmp_path, key, value):
    root = tmp_path / "probe"
    meta = probe_fixture(root)
    meta[key] = value
    (root / "manifest.json").write_text(json.dumps(meta))
    with pytest.raises(ContractError):
        load_probes(root)


def test_probe_integrity_and_path_escape(tmp_path):
    root = tmp_path / "probe"
    probe_fixture(root)
    (root / "probe.parquet").write_bytes(b"tampered")
    with pytest.raises(ContractError, match="integrity"):
        load_probes(root)
    outside = tmp_path / "outside"
    outside.write_text("not allowed")
    with pytest.raises(ContractError):
        bound(root, "../outside", digest(outside))


def test_mix_consolidates_names_and_preserves_unallocated_cash(panel):
    dates, targets = panel
    result = mix(targets, {"a": .75, "b": .25}, dates, ["NVDA", "GLD"])
    assert result.NVDA.eq(.375).all()
    assert np.allclose(result.GLD, .325)
    assert np.allclose(result.sum(axis=1), .7)


def test_missing_specialist_sessions_are_not_zero_filled(panel):
    dates, targets = panel
    targets["b"] = targets["b"].iloc[1:]
    with pytest.raises(ContractError, match="sessions"):
        mix(targets, {"a": .75, "b": .25}, dates, ["NVDA", "GLD"])
    with pytest.raises(ContractError, match="budget"):
        mix(targets, {"a": 1., "b": 1.}, dates, ["NVDA", "GLD"])


def test_outage_freezes_only_prior_target_then_expires_and_resumes(panel):
    dates, targets = panel
    target = targets["a"].copy()
    target.iloc[50:] = .1
    output = stale_target(target, dates[50], duration=21, grace=5)
    pd.testing.assert_frame_equal(output.iloc[:50], target.iloc[:50])
    assert output.iloc[50:55].NVDA.eq(.5).all()
    assert output.iloc[55:71].eq(0).all().all()
    pd.testing.assert_frame_equal(output.iloc[71:], target.iloc[71:])


def test_risk_control_uses_only_matured_development_and_no_prior_allocation(panel):
    dates, targets = panel
    rng = np.random.default_rng(1)
    baseline = pd.Series(rng.normal(0., .01, len(dates)), index=dates)
    candidate = baseline * .5
    training = (None, str(dates[180].date()))
    result, scale, known = risk_control(candidate, baseline, targets["a"], training)
    assert scale == pytest.approx(.5)
    assert known == dates[180]
    assert result.iloc[:180].eq(0).all().all()
    changed = candidate.copy()
    changed.iloc[181:] *= 10
    again, other_scale, _ = risk_control(changed, baseline, targets["a"], training)
    assert scale == other_scale
    pd.testing.assert_frame_equal(result, again)


def test_joint_uncertainty_identical_returns_are_not_alpha(panel):
    dates, _ = panel
    data = pd.DataFrame(0., index=dates, columns=["a", "b"])
    out = joint_intervals(data, reps=100, block=21)
    assert all(r["annual_log_excess"] == 0 and r["within_slate_max_abs_mean_p"] == 1 for r in out)
    assert all(r["not_whole_program_selection_corrected"] for r in out)


def test_frozen_position_shocks_respect_cash_and_are_not_forecasts():
    weights = pd.Series({"NVDA": .5, "SPY": .2, "GLD": .1, "IEF": .1, "BIL": 0.})
    assert shock_loss(weights, "ai_gap35") == pytest.approx(-.175 - .02 + .003 + .002)
    assert shock_loss(weights * 0., "liquidity_gap") == 0
    with pytest.raises(ContractError):
        shock_loss(weights, "unknown")


def test_core_slate_preserves_trade_baseline_and_fixed_ablations():
    specs = core_specs()
    assert len(specs) == 23
    assert len({r["name"] for r in specs}) == len(specs)
    baseline = next(r for r in specs if r["name"] == "trade_primary")
    assert baseline["budgets"] == {"trade_primary": 1.}
    assert next(r for r in specs if r["name"] == "ablate_swing_to_cash")["budgets"] == {"trade_primary": .8, "rotation_primary": .1}
