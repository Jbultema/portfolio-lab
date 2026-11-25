from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.allocation import Policy, allocate, consolidate, followups, policies, regimes
from portfolio_lab.research import choose


def sample():
    dates = pd.bdate_range("2010-01-01", periods=450)
    rng = np.random.default_rng(151)
    returns = pd.DataFrame(
        rng.normal(0.0004, 0.012, (450, 3)),
        index=dates,
        columns=["trade_primary", "swing_primary", "rotation_primary"],
    )
    prices = pd.DataFrame({"SPY": 100 * (1 + returns.iloc[:, 0]).cumprod()}, index=dates)
    return returns, regimes(prices)


@pytest.mark.parametrize("policy", policies(), ids=lambda x: x.name)
def test_allocator_is_prefix_causal_and_long_only(policy):
    r, states = sample()
    full = allocate(r, states, policy)
    short = allocate(r.iloc[:337], states.iloc[:337], policy)
    pd.testing.assert_frame_equal(full.iloc[:337], short)
    np.testing.assert_allclose(full.sum(axis=1), 1)
    assert full.min().min() >= 0
    assert full.diff().abs().max().max() <= policy.max_step + 1e-12


def test_future_expert_return_cannot_change_past_budgets():
    r, states = sample()
    policy = Policy("test", "conditional")
    original = allocate(r, states, policy)
    r.iloc[330:, 0] = 3
    pd.testing.assert_frame_equal(original.iloc[:330], allocate(r, states, policy).iloc[:330])


def test_regime_features_are_prefix_causal():
    r, _ = sample()
    prices = pd.DataFrame({"SPY": 100 * (1 + r.iloc[:, 0]).cumprod()})
    pd.testing.assert_frame_equal(regimes(prices).iloc[:337], regimes(prices.iloc[:337]))


def test_global_cap_is_a_ceiling_not_an_extra_multiplier():
    dates = pd.bdate_range("2026-01-01", periods=3)
    targets = {"a": pd.DataFrame({"NVDA": [0.2, 0.9, 0.9], "XLV": [0.0, 0.1, 0.1]}, index=dates)}
    budgets = pd.DataFrame({"a": 1.0}, index=dates)
    states = pd.DataFrame({"pressure": 1.0}, index=dates)
    output, diagnostic = consolidate(
        targets, budgets, states, Policy("cap", "equal", defense=True, technology_cap=0.3)
    )
    assert output.NVDA.iloc[0] == pytest.approx(0.2)
    assert output.sum(axis=1).max() <= 0.5
    assert output.NVDA.max() <= 0.3
    assert diagnostic.cash.min() >= 0


def test_selection_cannot_read_later_results():
    rows = [
        {
            "candidate": n,
            "period": p,
            "sharpe": value,
            "max_drawdown": -0.1,
            "cagr": value / 10,
            "annual_turnover": 1,
        }
        for n in ("stable", "lucky")
        for p in ("development", "validation", "recent_diagnostic")
        for value in (
            [1 if n == "stable" else 0]
            if p != "recent_diagnostic"
            else [100 if n == "lucky" else -100]
        )
    ]
    assert choose(rows, ["stable", "lucky"]) == "stable"


def test_followups_have_two_rounds_and_parent_lineage():
    parent = Policy("parent", "conditional")
    second = followups(parent, 2)
    third = followups(second[0], 3)
    assert len(second) == len(third) == 3
    assert all(c.parent == parent.name and c.round == 2 for c in second)
    assert all(c.parent == second[0].name and c.round == 3 for c in third)


def test_no_partial_week_or_month_endpoint_decision():
    r, states = sample()
    policy = replace(Policy("test", "trailing_utility"), cadence="weekly")
    full = allocate(r, states, policy)
    changed = full.diff().abs().sum(axis=1).gt(1e-12)
    assert not changed[r.index.weekday != 4].any()
