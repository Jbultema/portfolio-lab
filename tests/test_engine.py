import numpy as np
import pandas as pd
import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.engine import metrics, replay


def test_no_same_close_fill_and_no_return_before_next_close():
    dates = pd.bdate_range("2020-01-01", periods=4)
    prices = pd.DataFrame({"A": [100.0, 200.0, 220.0, 242.0]}, index=dates)
    target = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=dates)
    r = replay(prices, target, pd.Series(0.0, index=dates), cost_bps=0)
    np.testing.assert_allclose(r.returns, [0, 0, 0.1, 0.1])


def test_holdings_drift_without_free_rebalancing():
    dates = pd.bdate_range("2020-01-01", periods=4)
    prices = pd.DataFrame(
        {"A": [100.0, 100.0, 200.0, 400.0], "B": [100.0, 100.0, 100.0, 100.0]}, index=dates
    )
    targets = pd.DataFrame(0.5, index=dates, columns=prices.columns)
    r = replay(prices, targets, pd.Series(0.0, index=dates), cost_bps=0)
    assert r.equity.iloc[-1] == pytest.approx(2.5)
    assert r.weights.A.iloc[-1] == pytest.approx(0.8)
    assert r.turnover.iloc[2:].eq(0).all()


def test_full_investment_funds_costs_and_liquidation_is_costed():
    dates = pd.bdate_range("2020-01-01", periods=5)
    prices = pd.DataFrame(100.0, index=dates, columns=["A"])
    targets = pd.DataFrame({"A": [1.0, 1.0, 0.0, 0.0, 0.0]}, index=dates)
    r = replay(prices, targets, pd.Series(0.0, index=dates), cost_bps=10)
    assert r.equity.iloc[1] == pytest.approx(1 / 1.001)
    assert r.equity.iloc[-1] == pytest.approx(0.999 / 1.001)
    assert r.weights.sum(axis=1).le(1 + 1e-12).all()


def test_cash_yield_is_not_delayed_as_a_signal():
    dates = pd.bdate_range("2020-01-01", periods=5)
    prices = pd.DataFrame(100.0, index=dates, columns=["A"])
    r = replay(prices, prices * 0, pd.Series(0.001, index=dates))
    assert r.equity.iloc[-1] == pytest.approx(1.001**4)


@pytest.mark.parametrize(
    "kind", ["missing_hold", "negative", "leverage", "nan_target", "same_close", "negative_cost"]
)
def test_bad_inputs_fail_closed(kind):
    dates = pd.bdate_range("2020-01-01", periods=5)
    p = pd.DataFrame(100.0, index=dates, columns=["A"])
    t = pd.DataFrame(1.0, index=dates, columns=["A"])
    lag, cost = 1, 10
    if kind == "missing_hold":
        p.iloc[3] = np.nan
    elif kind == "negative":
        t.iloc[1] = -0.1
    elif kind == "leverage":
        t.iloc[1] = 1.1
    elif kind == "nan_target":
        t.iloc[1] = np.nan
    elif kind == "same_close":
        lag = 0
    else:
        cost = -1
    with pytest.raises(ContractError):
        replay(p, t, pd.Series(0.0, index=dates), lag=lag, cost_bps=cost)


def test_engine_prefix_invariance():
    dates = pd.bdate_range("2020-01-01", periods=120)
    rng = np.random.default_rng(42)
    p = pd.DataFrame(
        100 * np.exp(rng.normal(0, 0.01, (120, 3)).cumsum(axis=0)), index=dates, columns=list("ABC")
    )
    t = pd.DataFrame(rng.dirichlet([1, 1, 1, 1], 120)[:, :3], index=dates, columns=list("ABC"))
    cash = pd.Series(0.0001, index=dates)
    full = replay(p, t, cash)
    truncated = replay(p.iloc[:83], t.iloc[:83], cash.iloc[:83])
    pd.testing.assert_series_equal(full.returns.iloc[:83], truncated.returns)


def test_initial_loss_counts_in_drawdown():
    m = metrics(pd.Series([-0.1, 0.05]))
    assert m["max_drawdown"] == pytest.approx(-0.1)


@pytest.mark.parametrize("lag,cost", [(1.5, 10), (True, 10), (1, float("nan")), (1, float("inf"))])
def test_execution_settings_are_finite_and_integral(lag, cost):
    dates = pd.bdate_range("2020-01-01", periods=4)
    p = pd.DataFrame(100.0, index=dates, columns=["A"])
    with pytest.raises(ContractError):
        replay(p, p * 0, pd.Series(0.0, index=dates), lag=lag, cost_bps=cost)
