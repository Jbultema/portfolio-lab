from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from portfolio_lab.contracts import ContractError, frame_check


@dataclass
class Result:
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series


def replay(
    prices: pd.DataFrame,
    targets: pd.DataFrame,
    cash_returns: pd.Series,
    *,
    lag: int = 1,
    cost_bps: float = 10.0,
    terminal_events: list[dict] | None = None,
) -> Result:
    """Close t targets fill close t+lag; P&L starts strictly after that fill.

    Holdings drift between changed targets. Trade costs are funded from NAV,
    including when fully invested, using a fixed point for post-cost targets.
    """
    if (
        not isinstance(lag, (int, np.integer))
        or isinstance(lag, bool)
        or lag < 1
        or not np.isfinite(cost_bps)
        or not 0 <= cost_bps <= 100
    ):
        raise ContractError("Invalid execution lag or costs")
    frame_check(prices)
    frame_check(targets, weights=True)
    from portfolio_lab.corporate_actions import terminal_records

    terminals = terminal_records(terminal_events, prices.columns, prices.index)
    if not targets.index.equals(prices.index) or not set(targets) <= set(prices):
        raise ContractError("Execution inputs must align")
    cash = cash_returns.reindex(prices.index).to_numpy(float)
    if not np.isfinite(cash).all() or np.any(cash <= -1):
        raise ContractError("Invalid cash returns")
    p = prices.reindex(columns=targets.columns).to_numpy(float)
    desired = targets.shift(lag).fillna(0).to_numpy(float)
    held = np.zeros(p.shape[1])
    prior_target = np.zeros(p.shape[1])
    cash_value = nav = 1.0
    rows, returns, turnover, fees = [], [], [], []
    for i in range(len(p)):
        prior_nav = nav
        if i:
            cash_value *= 1.0 + cash[i]
            for j, instrument in enumerate(targets.columns):
                if instrument in terminals and terminals[instrument][0] == prices.index[i] and held[j] > 1e-12:
                    if not np.isfinite(p[i - 1, j]) or p[i - 1, j] <= 0:
                        raise ContractError("Terminal settlement lacks a previous adjusted share price")
                    cash_value += held[j] / p[i - 1, j] * terminals[instrument][1]
                    held[j] = 0.
            valid = np.isfinite(p[i]) & np.isfinite(p[i - 1]) & (p[i - 1] > 0)
            if np.any((held > 1e-12) & ~valid):
                raise ContractError(f"Unpriced holding on {prices.index[i]}")
            growth = np.ones(p.shape[1])
            np.divide(p[i], p[i - 1], out=growth, where=valid)
            held *= growth
        pre = held.sum() + cash_value
        if pre == 0:
            rows.append(np.zeros_like(held))
            returns.append(-1. if prior_nav > 0 else 0.)
            turnover.append(0.)
            fees.append(0.)
            nav = 0.
            continue
        target = desired[i].copy()
        for j, instrument in enumerate(targets.columns):
            if instrument in terminals and terminals[instrument][0] <= prices.index[i]:
                target[j] = 0.
        traded = fee = 0.0
        if not np.allclose(target, prior_target, rtol=0, atol=1e-12):
            if np.any(((target > 1e-12) | (held > 1e-12)) & ~np.isfinite(p[i])):
                raise ContractError(f"Unpriced trade on {prices.index[i]}")
            post = pre
            for _ in range(16):
                post = pre - cost_bps / 10000 * np.abs(target * post - held).sum()
            assets = target * post
            traded = np.abs(assets - held).sum() / pre
            fee = pre - post
            held = assets
            cash_value = post - held.sum()
        nav = held.sum() + cash_value
        if not np.isfinite(nav) or nav <= 0 or cash_value < -1e-9:
            raise ContractError("Self-financing invariant failed")
        rows.append(held / nav)
        returns.append(nav / prior_nav - 1)
        turnover.append(traded)
        fees.append(fee / pre)
        prior_target = target.copy()
    index = prices.index
    r = pd.Series(returns, index=index)
    return Result(
        r,
        r.add(1).cumprod(),
        pd.DataFrame(rows, index=index, columns=targets.columns),
        pd.Series(turnover, index=index),
        pd.Series(fees, index=index),
    )


def metrics(returns: pd.Series, turnover: pd.Series | None = None) -> dict:
    r = returns.dropna()
    if not len(r):
        return {}
    e = r.add(1).cumprod()
    dd = e.div(e.cummax().clip(lower=1)) - 1
    vol = r.std() * np.sqrt(252)
    underwater = longest = 0
    for v in dd:
        underwater = underwater + 1 if v < -1e-10 else 0
        longest = max(longest, underwater)
    return {
        "cagr": float(e.iloc[-1] ** (252 / len(r)) - 1),
        "max_drawdown": float(dd.min()),
        "sharpe": float(r.mean() * 252 / vol) if vol > 1e-12 else 0.0,
        "volatility": float(vol),
        "total_return": float(e.iloc[-1] - 1),
        "es95_daily": float(r[r <= r.quantile(0.05)].mean()),
        "maximum_underwater_sessions": longest,
        "annual_turnover": float(turnover.reindex(r.index).mean() * 252)
        if turnover is not None
        else 0.0,
        "sessions": len(r),
    }
