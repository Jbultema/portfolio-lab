import json

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.adaptive_allocation import (
    FAMILIES,
    PRIMARY,
    SECTORS,
    allocation_controls,
    current_features,
    followups,
    holding_scores,
    online_predictions,
    prepare,
    project,
    route,
    specifications,
    stabilize,
    targets,
)
from portfolio_lab.adaptive_research import COMBOS, combine, select, verify
from portfolio_lab.contracts import ContractError


@pytest.fixture
def history():
    index = pd.bdate_range("2010-01-01", periods=550)
    rng = np.random.default_rng(143)
    columns = ["SPY", "QQQ", *SECTORS]
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.0003, .012, (550, 11)), axis=0)), index=index, columns=columns)
    child = pd.DataFrame(rng.normal(.0004, .009, (550, 3)), index=index, columns=PRIMARY)
    native = {name: prices * 0. for name in PRIMARY}
    for name, ticker, exposure in zip(PRIMARY, ("QQQ", "SPY", "XLP"), (.3, .7, .9), strict=True):
        native[name][ticker] = exposure
    return prices, native, pd.Series(.00005, index=index), child


@pytest.mark.parametrize("family", FAMILIES)
def test_all_routers_are_prefix_invariant(history, family):
    prices, native, cash, child = history
    spec = next(s for s in specifications() if s["family"] == family)
    full = route(prepare(prices, native, cash, child), spec)
    cut = 450
    before = route(prepare(prices.iloc[:cut], {n: t.iloc[:cut] for n, t in native.items()}, cash.iloc[:cut], child.iloc[:cut]), spec)
    pd.testing.assert_frame_equal(full.iloc[:cut], before)
    prices2, child2 = prices.copy(), child.copy()
    prices2.iloc[cut:] *= np.arange(2, 102)[:, None]
    child2.iloc[cut:] = .3
    after = route(prepare(prices2, native, cash, child2), spec)
    pd.testing.assert_frame_equal(full.iloc[:cut], after.iloc[:cut])
    assert targets(native, full).sum(axis=1).le(1 + 1e-10).all()


def test_online_model_uses_only_mature_post_fill_labels(history):
    prices, native, cash, child = history
    data = prepare(prices, native, cash, child)
    full, errors, logs = online_predictions(data["context"], data["exposures"], child, 10)
    assert logs and all(row["no_future_label"] for row in logs)
    for row in logs:
        fit = prices.index.get_loc(row["fit_close"])
        last = prices.index.get_loc(row["last_feature_close"])
        end = prices.index.get_loc(row["last_label_close"])
        assert end == last + 6 and end <= fit
    changed = child.copy()
    changed.iloc[451:] = .8
    perturbed, _, _ = online_predictions(data["context"], data["exposures"], changed, 10)
    pd.testing.assert_frame_equal(full.iloc[:451], perturbed.iloc[:451])
    assert errors.dropna().ge(0).all().all()


def test_current_close_features_do_not_require_extra_signal_lag(history):
    prices, _, _, _ = history
    before = current_features(prices)
    changed = prices.copy()
    changed.iloc[400, changed.columns.get_loc("QQQ")] *= 1.1
    after = current_features(changed)
    pd.testing.assert_frame_equal(before.iloc[:400], after.iloc[:400])
    assert before.leadership21.iloc[400] != after.leadership21.iloc[400]


def test_idle_cash_topup_keeps_trade_positions_without_borrowing(history):
    prices, native, cash, child = history
    for name, ticker in zip(PRIMARY, ("QQQ", "SPY", "XLP"), strict=True):
        prices[ticker] = np.exp(np.arange(len(prices)) * (.003 if name == "rotation_primary" else .001)) * 100
    spec = next(s for s in specifications() if s["family"] == "idle_cash" and s["share"] == .5)
    coeff = route(prepare(prices, native, cash, child), spec)
    assert coeff.trade_primary.eq(1).all()
    assert coeff.rotation_primary.gt(0).any()
    assert coeff.sum(axis=1).gt(1).any()
    actual = targets(native, coeff)
    assert actual.QQQ.eq(.3).all()
    assert actual.sum(axis=1).le(.65 + 1e-10).all()


def test_no_alternative_is_mandatory(history):
    prices, native, cash, child = history
    child[:] = 0.
    spec = next(s for s in specifications() if s["family"] == "risk_normalized")
    allocation = route(prepare(prices, native, cash, child), spec)
    assert allocation.trade_primary.eq(1).all()


def test_daily_projection_overrides_minimum_hold(history):
    prices, native, _, _ = history
    native = {n: t.iloc[:12].copy() for n, t in native.items()}
    native["trade_primary"].iloc[3:, native["trade_primary"].columns.get_loc("QQQ")] = .9
    proposals = pd.DataFrame([[1., .8, 0.]] * 12, index=prices.index[:12], columns=PRIMARY)
    spec = {"confirm": 1, "hold": 21, "cadence": "daily", "cost_gate": False}
    result = stabilize(proposals, native, pd.Series(.1, index=proposals.index), spec)
    assert result.iloc[0].swing_primary == .8
    assert result.iloc[3].swing_primary < .15
    assert targets(native, result).sum(axis=1).le(1 + 1e-10).all()


def test_confirmation_tracks_alternative_support_not_continuous_size(history):
    prices, native, _, _ = history
    p = pd.DataFrame({"trade_primary": .5, "swing_primary": np.linspace(.1, .5, len(prices)), "rotation_primary": 0.}, index=prices.index)
    spec = {"confirm": 3, "hold": 1, "cadence": "daily", "cost_gate": False}
    result = stabilize(p, native, pd.Series(.1, index=p.index), spec)
    assert result.iloc[:2].swing_primary.eq(0).all()
    assert result.iloc[2].swing_primary > 0


def test_cost_gate_does_not_block_exit_to_trade(history):
    prices, native, _, _ = history
    p = pd.DataFrame([[.5, .5, 0.]] * 10 + [[1., 0., 0.]] * 540, index=prices.index, columns=PRIMARY)
    spec = {"confirm": 1, "hold": 1, "cadence": "daily", "cost_gate": True}
    edge = pd.Series(100., index=p.index)
    edge.iloc[10:] = 0
    result = stabilize(p, native, edge, spec)
    assert result.iloc[0].swing_primary > 0
    assert result.iloc[10:].trade_primary.eq(1).all()


def test_matched_controls_handle_zero_trade_exposure(history):
    prices, native, _, _ = history
    native["trade_primary"][:] = 0.
    coeff = pd.DataFrame([[1., .5, 0.]] * len(prices), index=prices.index, columns=PRIMARY)
    raw = targets(native, coeff)
    controls = allocation_controls(raw, coeff, native)
    assert controls["capped"].sum(axis=1).eq(0).all()
    assert controls["matched_trade"].sum(axis=1).eq(0).all()
    np.testing.assert_allclose(controls["matched_spy"].SPY, raw.sum(axis=1))
    assert controls["cash_ablation"].sum(axis=1).eq(0).all()


def test_missing_active_history_abstains_instead_of_backfilling(history):
    prices, native, cash, _ = history
    prices.loc[prices.index[:200], "QQQ"] = np.nan
    quality = holding_scores(prices, native, cash, 63)
    assert quality.trade_primary.iloc[:263].isna().all()
    assert quality.trade_primary.iloc[263:].notna().all()


@pytest.mark.parametrize("bad", ([np.nan, .2, .3], [-.1, .2, .3], [1.1, 0., 0.], [1., 0.]))
def test_invalid_multipliers_fail_closed(bad):
    with pytest.raises(ContractError):
        project(bad, [.2, .7, .9])


def test_invalid_native_target_or_missing_date_fails(history):
    prices, native, cash, child = history
    native["swing_primary"] = native["swing_primary"].iloc[1:]
    with pytest.raises(ContractError, match="align"):
        prepare(prices, native, cash, child)
    with pytest.raises(ContractError, match="align"):
        targets(native, pd.DataFrame([[1., 0., 0.]] * len(prices), index=prices.index, columns=PRIMARY))


@pytest.mark.parametrize("mechanism", COMBOS)
def test_combinations_are_causal_and_unlevered(history, mechanism):
    prices, native, cash, child = history
    data = prepare(prices, native, cash, child)
    a = pd.DataFrame([[1., .5, 0.]] * len(prices), index=prices.index, columns=PRIMARY)
    b = pd.DataFrame([[.5, 0., .5]] * len(prices), index=prices.index, columns=PRIMARY)
    full = combine(a, b, data, child.swing_primary, child.rotation_primary, child.trade_primary, mechanism)
    changed = child.copy()
    changed.iloc[450:] = 1.
    after = combine(a, b, data, changed.swing_primary, changed.rotation_primary, changed.trade_primary, mechanism)
    pd.testing.assert_frame_equal(full.iloc[:450], after.iloc[:450])
    assert targets(native, full).sum(axis=1).le(1 + 1e-10).all()


def test_selection_does_not_read_later_returns():
    index = pd.bdate_range("2012-01-01", "2025-01-01")
    base = pd.Series(.0002, index=index)
    specs = [{"name": n, "family": n, "available_from": "2006-01-01"} for n in ("a", "b", "c")]
    results = {("trade_primary", "raw"): base}
    for j, name in enumerate(("a", "b", "c")):
        for role in ("raw", "capped", "matched_trade", "matched_spy"):
            results[name, role] = base + (.0001 * j if role in {"raw", "capped"} else 0)
    before = select(specs, results, ["2012-01-01", "2015-12-31"])
    for key, values in results.items():
        if key[0] == "a":
            values.loc["2016-01-01":] = .5
    after = select(specs, results, ["2012-01-01", "2015-12-31"])
    assert before == after


def test_registry_has_finite_prespecified_scope():
    specs = specifications()
    assert len(specs) == 32 and len({s["name"] for s in specs}) == 32
    assert len({s["family"] for s in specs}) == 8
    assert len(followups(specs[0])) == 4 and len(COMBOS) == 6


def test_incomplete_or_live_authorized_report_cannot_verify(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"kind": "adaptive_allocation_research_v1", "authority": "research_only", "portfolio_allocation_allowed": True, "artifacts": {}}))
    with pytest.raises(ContractError):
        verify(tmp_path)
