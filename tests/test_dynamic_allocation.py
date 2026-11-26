import json

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.dynamic_allocation import (
    FAMILIES,
    PRIMARY,
    SECTORS,
    combine,
    consolidate,
    exposure_controls,
    features,
    route,
    specifications,
    stabilize,
)
from portfolio_lab.dynamic_research import availability, event_rule, select_parents, verify


@pytest.fixture
def history():
    index = pd.bdate_range("2010-01-01", periods=450)
    rng = np.random.default_rng(21)
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.0003, .01, (450, 11)), axis=0)),
                          index=index, columns=["SPY", "QQQ", *SECTORS])
    child = pd.DataFrame(rng.normal(.0004, .009, (450, 3)), index=index, columns=PRIMARY)
    return prices, child, pd.Series(.00005, index=index)


@pytest.mark.parametrize("family", FAMILIES)
def test_routers_cannot_see_future_outcomes_or_prices(history, family):
    prices, child, cash = history
    spec = next(s for s in specifications() if s["family"] == family and s["max_alternative"] == 1.)
    before = route(child, cash, features(prices), spec)
    changed, moved = child.copy(), prices.copy()
    changed.iloc[300:] = .5
    moved.iloc[300:] *= np.arange(1, len(moved) - 299)[:, None]
    after = route(changed, cash, features(moved), spec)
    pd.testing.assert_frame_equal(before.iloc[:301], after.iloc[:301])
    pd.testing.assert_frame_equal(before.iloc[:250], route(child.iloc[:250], cash.iloc[:250], features(prices.iloc[:250]), spec))
    assert before.ge(0).all().all() and before.sum(axis=1).le(1 + 1e-9).all()


def test_no_mandatory_alternative_allocation_and_full_switch_is_possible(history):
    prices, child, cash = history
    child[:] = 0.
    spec = next(s for s in specifications() if s["family"] == "relative_skill" and s["max_alternative"] == 1.)
    result = route(child, cash, features(prices), spec)
    assert result.trade_primary.eq(1).all()
    child.swing_primary = .003
    result = route(child, cash, features(prices), spec)
    assert result.swing_primary.eq(1).any()
    assert result.trade_primary.eq(0).any()


def test_confirmation_tracks_support_not_exact_continuously_varying_weights():
    index = pd.bdate_range("2020-01-01", periods=12)
    p = pd.DataFrame({"trade_primary": np.linspace(.9, .7, 12), "swing_primary": np.linspace(.1, .3, 12)}, index=index)
    b = stabilize(p, confirm=3, minimum_hold=1, cadence="daily")
    assert b.iloc[:2].swing_primary.eq(0).all()
    assert b.iloc[2].swing_primary > 0


def test_whipsaw_confirmation_and_hold_are_both_respected():
    index = pd.bdate_range("2020-01-01", periods=12)
    p = pd.DataFrame({"trade_primary": 0., "swing_primary": 1.}, index=index)
    p.iloc[4:] = [1., 0.]
    b = stabilize(p, confirm=3, minimum_hold=5, cadence="daily")
    assert b.iloc[:2].trade_primary.eq(1).all()
    assert b.iloc[2:7].swing_primary.eq(1).all()
    assert b.iloc[7:].trade_primary.eq(1).all()


def test_exact_exposure_controls_handle_zero_trade_budget_and_do_not_lever():
    index = pd.bdate_range("2020-01-01", periods=3)
    trade = pd.DataFrame([[.2, 0], [0, 0], [.8, 0]], columns=["A", "B"], index=index)
    target = pd.DataFrame([[0, .8], [0, .5], [0, .2]], columns=trade.columns, index=index)
    capped, matched = exposure_controls(target, trade)
    np.testing.assert_allclose(capped.sum(axis=1), matched.sum(axis=1))
    np.testing.assert_allclose(capped.sum(axis=1), [.2, 0., .2])
    assert matched.sum(axis=1).le(trade.sum(axis=1) + 1e-10).all()


def test_net_holdings_and_missing_target_sessions(history):
    prices, _, _ = history
    a = prices * 0.
    a.SPY = .5
    b = a.copy()
    b.SPY = .8
    budget = pd.DataFrame({"trade_primary": .5, "swing_primary": .5}, index=prices.index)
    target = consolidate({"trade_primary": a, "swing_primary": b}, budget, prices)
    assert np.allclose(target.SPY, .65)
    with pytest.raises(ContractError, match="Missing targets"):
        consolidate({"trade_primary": a.iloc[1:], "swing_primary": b}, budget, prices)


def test_selected_policy_has_no_backdated_availability(history):
    prices, _, _ = history
    b = pd.DataFrame({"trade_primary": 0., "swing_primary": 1.}, index=prices.index)
    result = availability(b, "2011-01-01")
    assert result.loc[:"2010-12-31", "trade_primary"].eq(1).all()
    assert result.loc["2011-01-01":, "swing_primary"].eq(1).all()


def test_selection_does_not_inspect_later_performance():
    index = pd.bdate_range("2012-01-01", "2025-01-01")
    base = pd.Series(.0002, index=index)
    specs = [{"name": n, "family": n, "available_from": "2006-01-01"} for n in ("a", "b", "c")]
    book = {("trade_primary", "raw"): base}
    for j, n in enumerate(("a", "b", "c")):
        for role in ("raw", "capped", "matched_trade"):
            book[n, role] = base + (j * .0001 if role != "matched_trade" else 0)
    before, _ = select_parents(specs, book, ("2012-01-01", "2015-12-31"))
    for key, values in book.items():
        if key[0] == "a":
            values.loc["2016-01-01":] = .5
    after, _ = select_parents(specs, book, ("2012-01-01", "2015-12-31"))
    assert [s["name"] for s in before] == [s["name"] for s in after]


def test_online_combination_is_causal(history):
    prices, returns, _ = history
    a = pd.DataFrame({"trade_primary": .5, "swing_primary": .5, "rotation_primary": 0.}, index=prices.index)
    b = a.copy()
    b.swing_primary, b.rotation_primary = 0., .5
    before = combine(a, b, features(prices), returns.swing_primary, returns.rotation_primary, returns.trade_primary, "online63")
    changed = returns.copy()
    changed.iloc[300:] = 1.
    after = combine(a, b, features(prices), changed.swing_primary, changed.rotation_primary, changed.trade_primary, "online63")
    pd.testing.assert_frame_equal(before.iloc[:301], after.iloc[:301])


def test_incomplete_or_authorized_research_cannot_verify(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"kind": "dynamic_specialist_research_v1", "authority": "research_only", "portfolio_allocation_allowed": True, "artifacts": {}}))
    with pytest.raises(ContractError):
        verify(tmp_path)


def test_event_router_is_causal_and_absence_of_evidence_defaults_to_trade(history):
    prices, returns, _ = history
    prices.index = returns.index = pd.bdate_range("2023-01-02", periods=len(prices))
    probe = pd.DataFrame({"A": .1}, index=prices.index)
    basket = probe * 10
    spec = {"family": "gated_event_sleeve", "max_alternative": .5}
    before = event_rule(spec, probe, basket, returns.swing_primary, returns.rotation_primary, returns.trade_primary, features(prices))
    assert before.event_probe.eq(0).all()
    changed = probe.copy()
    changed.iloc[300:] = .9
    after = event_rule(spec, changed, basket, returns.swing_primary, returns.rotation_primary, returns.trade_primary, features(prices))
    pd.testing.assert_frame_equal(before.iloc[:301], after.iloc[:301])


def test_intersection_does_not_override_agreed_cash_defense(history):
    prices, returns, _ = history
    a = pd.DataFrame({"trade_primary": .5, "swing_primary": 0., "rotation_primary": 0.}, index=prices.index)
    b = a.copy()
    combined = combine(a, b, features(prices), returns.swing_primary, returns.rotation_primary, returns.trade_primary, "intersection")
    assert combined.iloc[-1].sum() == .5
