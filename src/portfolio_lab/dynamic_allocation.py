"""Causal, sparse specialist routers. No compulsory diversification or leverage."""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from portfolio_lab.allocation import regimes
from portfolio_lab.contracts import ContractError, frame_check

PRIMARY = ("trade_primary", "swing_primary", "rotation_primary")
FAMILIES = ("relative_skill", "conditional_skill", "leadership", "rebound", "stress_defender", "sparse_weights")
SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")


def specifications():
    rows = []
    for family, horizon, fraction in product(FAMILIES, (63, 126), (.25, .50, 1.)):
        rows.append({"name": f"{family}_h{horizon}_a{int(fraction * 100)}", "family": family,
                     "lookback": horizon, "max_alternative": fraction, "confirm": 1,
                     "minimum_hold": 5, "cadence": "weekly", "round": 1, "parent": ""})
    return rows


def followups(parent):
    return [parent | {"name": f"r2_{parent['family']}_c{confirm}_{cadence}", "confirm": confirm,
                       "minimum_hold": 10, "cadence": cadence, "round": 2, "parent": parent["name"]}
            for confirm, cadence in product((3, 5), ("daily", "weekly"))]


def features(prices):
    """Only prior completed closes enter routing evidence."""
    spy = prices.SPY
    returns = prices.pct_change(fill_method=None)
    sector_returns = prices[list(SECTORS)].pct_change(63, fill_method=None)
    sectors_short = prices[list(SECTORS)].pct_change(21, fill_method=None)
    result = pd.DataFrame(index=prices.index)
    result["state"] = regimes(prices).state
    result["pressure"] = regimes(prices).pressure
    result["breadth"] = sector_returns.gt(0).mean(axis=1).where(sector_returns.notna().all(axis=1))
    result["breadth_short"] = sectors_short.gt(0).mean(axis=1).where(sectors_short.notna().all(axis=1))
    result["leadership"] = sector_returns.mean(axis=1) - prices.QQQ.pct_change(63, fill_method=None)
    result["leadership_short"] = sectors_short.mean(axis=1) - prices.QQQ.pct_change(21, fill_method=None)
    result["dd63"] = spy.div(spy.rolling(63, min_periods=63).max()).sub(1)
    result["return5"] = spy.pct_change(5, fill_method=None)
    result["above10"] = spy.gt(spy.ewm(span=10, adjust=False, min_periods=10).mean())
    result["above21"] = spy.gt(spy.rolling(21, min_periods=21).mean())
    result["vol_ratio"] = returns.SPY.rolling(21).std().div(returns.SPY.rolling(126).std())
    return result.shift(1)


def stabilize(proposals, *, confirm=1, minimum_hold=5, cadence="weekly"):
    """A scheduled trade requires persistent proposals; no backward-filled regimes."""
    if confirm < 1 or minimum_hold < 1 or cadence not in {"daily", "weekly"}:
        raise ContractError("Invalid routing persistence")
    frame_check(proposals, weights=True)
    values = proposals.to_numpy(float)
    current = np.zeros(len(proposals.columns))
    current[proposals.columns.get_loc("trade_primary")] = 1.
    rows, pending, count, last_change = [], None, 0, -minimum_hold
    for i, day in enumerate(proposals.index):
        proposal = values[i]
        signature = (tuple(np.flatnonzero(proposal > 1e-10)), proposal.sum() < 1 - 1e-10)
        if pending == signature:
            count += 1
        else:
            pending, count = signature, 1
        scheduled = cadence == "daily" or i == 0 or day.weekday() == 4
        if scheduled and count >= confirm and i - last_change >= minimum_hold:
            if not np.allclose(current, proposal, rtol=0, atol=1e-10):
                current, last_change = proposal.copy(), i
        rows.append(current.copy())
    out = pd.DataFrame(rows, index=proposals.index, columns=proposals.columns)
    frame_check(out, weights=True)
    return out


def route(child_returns, cash, context, spec):
    """Use shadow child outcomes through t-1, never future relative performance."""
    if not child_returns.index.equals(context.index) or not cash.index.equals(context.index):
        raise ContractError("Causal router inputs must share actual sessions")
    if not set(PRIMARY) <= set(child_returns) or not np.isfinite(child_returns[list(PRIMARY)]).all().all():
        raise ContractError("Router needs finite observed specialist outcomes")
    family, horizon, fraction = spec["family"], spec["lookback"], spec["max_alternative"]
    if family not in FAMILIES or not 0 <= fraction <= 1:
        raise ContractError("Unknown or invalid routing policy")
    log_excess = np.log1p(child_returns[list(PRIMARY)]).sub(np.log1p(cash), axis=0).shift(1)
    means = log_excess.rolling(horizon, min_periods=horizon).mean() * 252
    variance = log_excess.rolling(horizon, min_periods=horizon).var() * 252
    utility = means - variance
    downside = log_excess.clip(upper=0).pow(2).rolling(horizon, min_periods=horizon).mean().pow(.5)
    proposal = pd.DataFrame(0., index=context.index, columns=PRIMARY)
    proposal.trade_primary = 1.
    values = log_excess.to_numpy()
    states = context.state.to_numpy()
    outcome_states = context.state.shift(1).to_numpy()
    for i in range(horizon + 1, len(proposal)):
        if not np.isfinite(utility.iloc[i]).all():
            continue
        selected, share = None, fraction
        if family == "relative_skill":
            best = utility.iloc[i, 1:].idxmax()
            if utility.at[proposal.index[i], best] > max(.02, utility.iloc[i, 0] + .02):
                selected = best
        elif family == "conditional_skill":
            left = max(1, i - horizon * 4)
            history = values[left:i + 1]
            mask = outcome_states[left:i + 1] == states[i]
            if mask.sum() >= 21:
                relative = history[:, 1:] - history[:, [0]]
                # A zero-skill prior shrinks state-specific incremental advantage.
                scores = relative[mask].sum(axis=0) / (mask.sum() + 63) * 252
                best = int(np.argmax(scores))
                if scores[best] > .02:
                    selected = PRIMARY[best + 1]
        elif family == "leadership":
            short = horizon == 63
            leadership = context.iloc[i]["leadership_short" if short else "leadership"]
            breadth = context.iloc[i]["breadth_short" if short else "breadth"]
            if leadership > .02 and breadth >= 5 / 9:
                selected = "rotation_primary"
        elif family == "rebound":
            row = context.iloc[i]
            repaired = row["above10" if horizon == 63 else "above21"]
            if row.dd63 < -.05 and row.return5 > .01 and row.vol_ratio > 1.1 and repaired:
                selected = "swing_primary"
        elif family == "stress_defender":
            if states[i] in {"transition", "stress"}:
                best = downside.iloc[i, 1:].idxmin()
                if downside.iloc[i][best] < .8 * downside.iloc[i, 0] and means.iloc[i][best] > 0:
                    selected = best
                else:
                    selected = "cash"
        else:
            edge = utility.iloc[i, 1:].sub(utility.iloc[i, 0])
            active = edge[edge > .02]
            if len(active):
                scores = np.exp(np.minimum(active.to_numpy() * 5, 10))
                total = min(fraction, float(active.max() / (.10 + active.max())))
                proposal.iloc[i] = 0.
                proposal.iloc[i, 0] = 1 - total
                for name, weight in zip(active.index, scores / scores.sum() * total, strict=True):
                    proposal.at[proposal.index[i], name] = weight
            continue
        if selected is not None:
            proposal.iloc[i] = 0.
            proposal.iloc[i, 0] = 1 - share
            if selected != "cash":
                proposal.at[proposal.index[i], selected] = share
    return stabilize(proposal, confirm=spec["confirm"], minimum_hold=spec["minimum_hold"], cadence=spec["cadence"])


def consolidate(native, budgets, prices):
    out = pd.DataFrame(0., index=prices.index, columns=prices.columns)
    frame_check(budgets, weights=True)
    for name in budgets:
        if not budgets.index.equals(native[name].index):
            raise ContractError("Missing targets cannot be fabricated by a router")
        out += native[name].reindex(columns=prices.columns, fill_value=0).mul(budgets[name], axis=0)
    frame_check(out, weights=True)
    return out


def exposure_controls(target, trade):
    """Cap candidate risk to Trade's known exposure, then match it exactly."""
    if not target.index.equals(trade.index) or not target.columns.equals(trade.columns):
        raise ContractError("Exposure controls require identical captured dimensions")
    amount, reference = target.sum(axis=1), trade.sum(axis=1)
    cap = np.minimum(1., reference / amount.clip(lower=1e-12))
    capped = target.mul(cap, axis=0)
    matched = trade.mul(capped.sum(axis=1).div(reference.clip(lower=1e-12)), axis=0)
    return capped, matched


def combine(a, b, context, returns_a, returns_b, trade_returns, mechanism):
    if mechanism == "intersection":
        same = a.drop(columns="trade_primary").idxmax(axis=1).eq(b.drop(columns="trade_primary").idxmax(axis=1))
        active = a.drop(columns="trade_primary").sum(axis=1).gt(0) & b.drop(columns="trade_primary").sum(axis=1).gt(0)
        both_cash = a.sum(axis=1).lt(1 - 1e-10) & b.sum(axis=1).lt(1 - 1e-10)
        both_cash &= a.drop(columns="trade_primary").sum(axis=1).eq(0) & b.drop(columns="trade_primary").sum(axis=1).eq(0)
        agreed = (same & active) | both_cash
        proposals = (a + b) / 2
        proposals.loc[~agreed] = 0.
        proposals.loc[~agreed, "trade_primary"] = 1.
    elif mechanism in {"online63", "online126"}:
        horizon = 63 if mechanism == "online63" else 126
        observed = pd.DataFrame({"a": returns_a, "b": returns_b, "trade": trade_returns})
        score = np.log1p(observed).shift(1).rolling(horizon, min_periods=horizon).mean()
        proposals = a * 0.
        proposals.trade_primary = 1.
        choose_a = score.a.gt(score.b) & score.a.gt(score.trade + .02 / 252)
        choose_b = score.b.ge(score.a) & score.b.gt(score.trade + .02 / 252)
        proposals.loc[choose_a] = a.loc[choose_a]
        proposals.loc[choose_b] = b.loc[choose_b]
    elif mechanism == "stress_context":
        proposals = a.copy()
        mask = context.state.eq("stress")
        proposals.loc[mask] = b.loc[mask]
    elif mechanism in {"union", "defensive_union"}:
        proposals = (a + b) / 2
        if mechanism == "defensive_union":
            proposals = proposals.mul(1 - .5 * context.pressure.fillna(0), axis=0)
    else:
        raise ContractError("Unknown router combination")
    return stabilize(proposals, minimum_hold=10, cadence="weekly")
