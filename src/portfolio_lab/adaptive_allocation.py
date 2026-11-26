"""New sparse routing mechanisms with explicit close clocks and cash headroom."""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from portfolio_lab.allocation import regimes
from portfolio_lab.contracts import ContractError, frame_check
from portfolio_lab.dynamic_allocation import PRIMARY, SECTORS

FAMILIES = ("fast_context", "risk_normalized", "residual_alpha", "adaptive_horizon", "holdings_quality",
            "idle_cash", "defensive_opportunity", "online_context")


def specifications():
    out = []
    parameters = {"fast_context": (0, 1), "risk_normalized": (63, 126), "residual_alpha": (126, 252),
                  "adaptive_horizon": (21, 42), "holdings_quality": (21, 63), "idle_cash": (21, 63),
                  "defensive_opportunity": (63, 126), "online_context": (10, 100)}
    for family in FAMILIES:
        for parameter, share in product(parameters[family], (.25, .5)):
            out.append({"name": f"{family}_p{parameter}_a{int(100 * share)}", "family": family,
                "parameter": parameter, "share": share, "confirm": 2, "hold": 5,
                "cadence": "weekly" if family == "fast_context" else "daily", "cost_gate": False,
                "round": 1, "available_from": "2006-01-03", "parent": ""})
    return out


def followups(parent):
    return [parent | {"name": f"r2_{parent['family']}_g{int(gate)}_h{hold}", "cost_gate": gate,
        "hold": hold, "confirm": 3, "round": 2, "available_from": "2016-01-01", "parent": parent["name"]}
        for gate, hold in product((False, True), (5, 21))]


def current_features(prices):
    """End-of-close evidence. It must still execute at a later close."""
    spy = prices.SPY
    returns = prices.pct_change(fill_method=None)
    sectors = prices[list(SECTORS)]
    context = regimes(prices).copy()
    for horizon in (21, 63):
        change = sectors.pct_change(horizon, fill_method=None)
        valid = change.notna().all(axis=1)
        context[f"breadth{horizon}"] = change.gt(0).mean(axis=1).where(valid)
        context[f"leadership{horizon}"] = (change.mean(axis=1) - prices.QQQ.pct_change(horizon, fill_method=None)).where(valid)
    context["trend126"] = spy.div(spy.rolling(126, min_periods=126).mean()).sub(1)
    context["qqq_relative63"] = prices.QQQ.pct_change(63, fill_method=None) - spy.pct_change(63, fill_method=None)
    context["return5"] = spy.pct_change(5, fill_method=None)
    context["above10"] = spy.gt(spy.ewm(span=10, adjust=False, min_periods=10).mean())
    context["dd63"] = spy.div(spy.rolling(63, min_periods=63).max()).sub(1)
    context["vol_ratio"] = returns.SPY.rolling(21).std().div(returns.SPY.rolling(126).std())
    return context


def holding_scores(prices, native, cash, horizon):
    momentum = prices.pct_change(horizon, fill_method=None)
    cash_gain = np.expm1(np.log1p(cash).rolling(horizon, min_periods=horizon).sum())
    excess = momentum.sub(cash_gain, axis=0)
    vol = prices.pct_change(fill_method=None).rolling(horizon, min_periods=horizon).std() * np.sqrt(252)
    result = pd.DataFrame(index=prices.index)
    for name in PRIMARY:
        weights = native[name]
        invested = weights.sum(axis=1)
        covered = weights.where(excess.notna() & vol.notna(), 0.).sum(axis=1)
        # Zero weights ignore unavailable history; active incomplete baskets abstain.
        quality = (weights * excess.div(vol.clip(lower=.05))).sum(axis=1).div(invested.clip(lower=1e-12))
        result[name] = quality.where(invested.ge(.05) & covered.ge(.8 * invested))
    return result


def risk_scores(returns, cash, horizon):
    excess = returns.sub(cash, axis=0)
    mean = excess.rolling(horizon, min_periods=horizon).mean() * 252
    vol = excess.rolling(horizon, min_periods=horizon).std() * np.sqrt(252)
    return mean.div(vol.clip(lower=.03)) * .10


def residual_scores(returns, cash, prices, horizon):
    x = prices.SPY.pct_change(fill_method=None).sub(cash)
    z = prices.QQQ.pct_change(fill_method=None) - prices.SPY.pct_change(fill_method=None)
    vx, vz = x.rolling(horizon).var(), z.rolling(horizon).var()
    cxz = x.rolling(horizon).cov(z)
    determinant = vx * vz - cxz.pow(2)
    out = pd.DataFrame(index=prices.index)
    for name in PRIMARY:
        y = returns[name] - cash
        cxy, czy = y.rolling(horizon).cov(x), y.rolling(horizon).cov(z)
        b1 = (cxy * vz - czy * cxz).div(determinant.where(determinant > 1e-14))
        b2 = (czy * vx - cxy * cxz).div(determinant.where(determinant > 1e-14))
        alpha = y.rolling(horizon).mean() - b1 * x.rolling(horizon).mean() - b2 * z.rolling(horizon).mean()
        noise = (y.rolling(horizon).var() - b1 * cxy - b2 * czy).clip(lower=1e-12).pow(.5)
        out[name] = (alpha * 252 * horizon / (horizon + 126)).where(alpha.div(noise / np.sqrt(horizon)).gt(.5))
    return out


def online_predictions(context, exposures, returns, ridge, *, horizon=5, window=756, minimum=252):
    """Features at s predict returns s+2..s+h+1, after the next-close fill.

    At decision i, only labels ending at or before i enter the fit. Transforms
    are learned on that fit's past training rows. No full-panel standardization.
    """
    columns = ["trend126", "qqq_relative63", "leadership21", "breadth21", "vol_ratio", "pressure"]
    x = context[columns].copy()
    x["trade_invested"] = exposures.trade_primary
    values = x.to_numpy(float)
    labels = np.log1p(returns[list(PRIMARY)[1:]]).sub(np.log1p(returns.trade_primary), axis=0).rolling(horizon).sum().shift(-(horizon + 1)).to_numpy(float)
    predictions = np.full((len(x), 2), np.nan)
    errors = np.full_like(predictions, np.nan)
    params, logs = None, []
    for i, day in enumerate(x.index):
        last = i - horizon - 1
        scheduled = i == 0 or day.month != x.index[i - 1].month
        if last >= minimum and (params is None or scheduled):
            indices = np.arange(max(0, last - window + 1), last + 1)
            valid = np.isfinite(values[indices]).all(axis=1) & np.isfinite(labels[indices]).all(axis=1)
            indices = indices[valid]
            if len(indices) >= minimum:
                mean = values[indices].mean(axis=0)
                scale = np.maximum(values[indices].std(axis=0), .01)
                design = np.column_stack([np.ones(len(indices)), np.clip((values[indices] - mean) / scale, -5, 5)])
                penalty = np.eye(design.shape[1]) * ridge
                penalty[0, 0] *= .1
                inverse = np.linalg.inv(design.T @ design + penalty)
                coefficients = inverse @ design.T @ labels[indices]
                noise = ((labels[indices] - design @ coefficients) ** 2).mean(axis=0)
                params = mean, scale, inverse, coefficients, noise
                logs.append({"fit_close": str(day.date()), "last_feature_close": str(x.index[indices[-1]].date()),
                    "last_label_close": str(x.index[indices[-1] + horizon + 1].date()), "samples": len(indices),
                    "horizon": horizon, "ridge": ridge, "no_future_label": indices[-1] + horizon + 1 <= i})
        if params is not None and np.isfinite(values[i]).all():
            mean, scale, inverse, coefficients, noise = params
            row = np.r_[1., np.clip((values[i] - mean) / scale, -5, 5)]
            predictions[i] = row @ coefficients
            errors[i] = np.sqrt(noise * max(0., row @ inverse @ row) * horizon)
    names = list(PRIMARY)[1:]
    return pd.DataFrame(predictions, index=x.index, columns=names), pd.DataFrame(errors, index=x.index, columns=names), logs


def project(row, exposures):
    row = np.asarray(row, dtype=float).copy()
    exposures = np.asarray(exposures, dtype=float)
    if exposures.shape != (3,) or not np.isfinite(exposures).all() or np.any(exposures < 0) or np.any(exposures > 1 + 1e-10):
        raise ContractError("Invalid native risky exposure")
    if row.shape != (3,) or not np.isfinite(row).all() or np.any(row < 0) or np.any(row > 1 + 1e-12):
        raise ContractError("Invalid specialist notional multiplier")
    base, alternatives = row[0] * exposures[0], float(row[1:] @ exposures[1:])
    if base + alternatives > 1:
        row[1:] *= max(0., 1 - base) / max(alternatives, 1e-12)
    return row


def targets(native, coefficients):
    if not coefficients.index.equals(native[PRIMARY[0]].index) or list(coefficients) != list(PRIMARY):
        raise ContractError("Missing or unordered specialist coefficients")
    if not np.isfinite(coefficients.to_numpy()).all() or coefficients.lt(0).any().any() or coefficients.gt(1 + 1e-10).any().any():
        raise ContractError("Invalid specialist notional multipliers")
    out = native[PRIMARY[0]] * 0.
    for name in PRIMARY:
        if not native[name].index.equals(coefficients.index) or not native[name].columns.equals(out.columns):
            raise ContractError("Specialist frames must align exactly")
        out += native[name].mul(coefficients[name], axis=0)
    frame_check(out, weights=True)
    return out


def stabilize(proposals, native, expected_edge, spec):
    """Confirmation, cost gate and mandatory daily long-only safety projection."""
    index = proposals.index
    exposure = pd.DataFrame({n: native[n].sum(axis=1) for n in PRIMARY}, index=index)
    current = np.array([1., 0., 0.])
    pending, consecutive, last_change, rows = None, 0, -100, []
    arrays = {n: native[n].to_numpy(float) for n in PRIMARY}
    for i, day in enumerate(index):
        current = project(current, exposure.iloc[i].to_numpy())
        proposed = project(proposals.iloc[i].to_numpy(), exposure.iloc[i].to_numpy())
        signature = tuple(np.flatnonzero(proposed[1:] > 1e-10))
        consecutive = consecutive + 1 if signature == pending else 1
        pending = signature
        scheduled = spec["cadence"] == "daily" or i == 0 or day.weekday() == 4
        if scheduled and consecutive >= spec["confirm"] and i - last_change >= spec["hold"]:
            allow = True
            if spec["cost_gate"] and proposed[1:].sum() > 1e-10:
                trade = sum((proposed[j] - current[j]) * arrays[n][i] for j, n in enumerate(PRIMARY))
                cost = np.abs(trade).sum() * .0025 * 2
                benefit = max(0., float(expected_edge.iloc[i])) * proposed[1:].sum() * spec["hold"] / 252
                allow = benefit > cost + .0001
            if allow and not np.allclose(proposed, current, atol=1e-10, rtol=0):
                current, last_change = proposed, i
        rows.append(current.copy())
    result = pd.DataFrame(rows, index=index, columns=PRIMARY)
    targets(native, result)
    return result


def prepare(prices, native, cash, child_returns):
    if not cash.index.equals(prices.index) or not child_returns.index.equals(prices.index):
        raise ContractError("Causal observations must align to captured closes")
    for name in PRIMARY:
        frame_check(native[name], weights=True)
        if not native[name].index.equals(prices.index) or not native[name].columns.equals(prices.columns):
            raise ContractError("Native targets must align to captured prices")
    context = current_features(prices)
    exposures = pd.DataFrame({n: native[n].sum(axis=1) for n in PRIMARY})
    return {"prices": prices, "native": native, "cash": cash, "returns": child_returns,
            "context": context, "exposures": exposures, "cache": {}, "fit_logs": []}


def route(data, spec):
    context, native, returns = data["context"], data["native"], data["returns"]
    horizon, family, share = spec["parameter"], spec["family"], spec["share"]
    index, cache = context.index, data["cache"]
    proposal = pd.DataFrame(0., index=index, columns=PRIMARY)
    proposal.trade_primary = 1.
    edges = pd.Series(.05, index=index)

    def cached(kind, value, fn):
        key = kind, value
        if key not in cache:
            cache[key] = fn()
        return cache[key]

    quality = cached("holdings", 21 if family == "fast_context" else horizon if family in {"holdings_quality", "idle_cash"} else 63,
        lambda: holding_scores(data["prices"], native, data["cash"], 21 if family == "fast_context" else horizon if family in {"holdings_quality", "idle_cash"} else 63))
    if family == "fast_context":
        observed = context.shift(horizon)
        rotate = observed.leadership21.gt(.02) & observed.breadth21.ge(5 / 9)
        rebound = ~rotate & observed.dd63.lt(-.05) & observed.return5.gt(.01) & observed.above10.eq(True)
        for mask, name in ((rotate, "rotation_primary"), (rebound, "swing_primary")):
            proposal.loc[mask, "trade_primary"] = 1 - share
            proposal.loc[mask, name] = share
    elif family == "online_context":
        key = "ridge", horizon
        if key not in cache:
            prediction, error, logs = online_predictions(context, data["exposures"], returns, horizon)
            cache[key] = prediction - .5 * error
            data["fit_logs"].extend(logs)
        score = cache[key]
        winner = score.fillna(-np.inf).idxmax(axis=1)
        for name in list(PRIMARY)[1:]:
            mask = winner.eq(name) & score[name].gt(.0005)
            proposal.loc[mask, "trade_primary"] = 1 - share
            proposal.loc[mask, name] = share
            edges.loc[mask] = score.loc[mask, name] * 252 / 5
    else:
        if family in {"holdings_quality", "idle_cash", "defensive_opportunity"}:
            score = quality.copy()
        elif family == "residual_alpha":
            score = cached("residual", horizon, lambda: residual_scores(returns, data["cash"], data["prices"], horizon)).copy()
        elif family == "risk_normalized":
            score = cached("risk", horizon, lambda: risk_scores(returns, data["cash"], horizon)).copy()
        elif family == "adaptive_horizon":
            fast = cached("risk", horizon, lambda: risk_scores(returns, data["cash"], horizon))
            slow = cached("risk", 126, lambda: risk_scores(returns, data["cash"], 126))
            change = context.vol_ratio.gt(1.3) | (np.sign(context.leadership21).ne(np.sign(context.leadership63)) & context.leadership21.abs().gt(.02))
            score = slow.copy()
            score.loc[change] = fast.loc[change]
        else:
            raise ContractError("Unknown adaptive routing family")
        if family == "defensive_opportunity":
            wealth = returns.add(1).cumprod()
            health = wealth.div(wealth.rolling(horizon, min_periods=horizon).max()).sub(1)
            score = score.where(health.sub(health.trade_primary, axis=0).gt(.03))
        winner = score[list(PRIMARY)[1:]].fillna(-np.inf).idxmax(axis=1)
        for name in list(PRIMARY)[1:]:
            positive = score[name].gt(0) & data["exposures"][name].gt(.05)
            if family in {"idle_cash", "defensive_opportunity"}:
                mask = positive & winner.eq(name) & data["exposures"].trade_primary.lt(.65) & context.breadth21.ge(5 / 9) & context.trend126.gt(0)
            else:
                hurdle = .02 if family not in {"holdings_quality"} else .10
                mask = positive & winner.eq(name) & score[name].gt(score.trade_primary.fillna(0) + hurdle)
            if family == "idle_cash":
                headroom = (1 - data["exposures"].trade_primary) * share
                proposal.loc[mask, name] = np.minimum(1., headroom.loc[mask] / data["exposures"].loc[mask, name])
            else:
                proposal.loc[mask, "trade_primary"] = 1 - share
                proposal.loc[mask, name] = share
            edges.loc[mask] = score.loc[mask, name].clip(lower=0, upper=.5)
    result = stabilize(proposal, native, edges, spec)
    if spec["available_from"] > str(index[0].date()):
        result.loc[result.index < spec["available_from"]] = [1., 0., 0.]
    return result


def allocation_controls(raw, coefficients, native):
    trade = native["trade_primary"]
    amount, reference = raw.sum(axis=1), trade.sum(axis=1)
    capped = raw.mul(np.minimum(1., reference / amount.clip(lower=1e-12)), axis=0)
    matched = trade.mul(capped.sum(axis=1).div(reference.clip(lower=1e-12)), axis=0)
    spy_match = trade.mul(np.minimum(1., amount / reference.clip(lower=1e-12)), axis=0)
    spy_match["SPY"] += (amount - reference).clip(lower=0)
    cash_only = trade.mul(coefficients.trade_primary, axis=0)
    for frame in (raw, capped, matched, spy_match, cash_only):
        frame_check(frame, weights=True)
    return {"raw": raw, "capped": capped, "matched_trade": matched, "cash_ablation": cash_only, "matched_spy": spy_match}
