from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Policy:
    name: str
    family: str
    lookback: int = 756
    shrinkage: int = 126
    cadence: str = "monthly"
    max_step: float = 0.20
    defense: bool = False
    protection_floor: float = 0.5
    technology_cap: float = 1.0
    parent: str = ""
    round: int = 1


TECHNOLOGY = frozenset(
    {"QQQ", "XLK", "SMH", "SOXX", "IGV", "NVDA", "AVGO", "MSFT", "META", "AMZN", "PLTR"}
)


def regimes(prices: pd.DataFrame) -> pd.DataFrame:
    spy = prices["SPY"]
    r = spy.pct_change(fill_method=None)
    dd = spy.div(spy.rolling(63, min_periods=21).max()) - 1
    ratio = r.rolling(21).std().div(r.rolling(126).std())
    trend = spy.div(spy.rolling(126).mean()) - 1
    pressure = (
        (-dd / 0.15).clip(0, 1) * 0.45
        + (ratio.sub(1) / 0.75).clip(0, 1) * 0.30
        + trend.lt(0).astype(float) * 0.25
    ).fillna(0)
    state = pd.Series("uncertain", index=prices.index)
    ready = trend.notna() & ratio.notna()
    state.loc[ready] = "normal"
    state.loc[ready & pressure.ge(0.35)] = "transition"
    state.loc[ready & pressure.ge(0.65)] = "stress"
    return pd.DataFrame(
        {"state": state, "pressure": pressure, "drawdown63": dd, "vol_ratio": ratio}
    )


def policies() -> list[Policy]:
    output = [Policy("equal_blend", "equal", round=0)]
    for family in ("inverse_vol", "conditional", "trailing_utility"):
        for lookback in (252, 756):
            for shrinkage in (63, 252):
                output.append(
                    Policy(f"{family}_l{lookback}_s{shrinkage}", family, lookback, shrinkage)
                )
    output += [
        Policy("equal_defense", "equal", defense=True),
        Policy("equal_techcap60", "equal", technology_cap=0.60),
    ]
    return output


def followups(parent: Policy, round_number: int) -> list[Policy]:
    base = asdict(parent)
    changes = (
        [{"max_step": 0.10}, {"cadence": "weekly"}, {"defense": True}]
        if round_number == 2
        else [{"shrinkage": 504}, {"lookback": 1260}, {"technology_cap": 0.60}]
    )
    return [
        Policy(
            **(
                base
                | delta
                | {
                    "name": f"{parent.family}_r{round_number}_v{i}",
                    "parent": parent.name,
                    "round": round_number,
                }
            )
        )
        for i, delta in enumerate(changes, 1)
    ]


def allocate(expert_returns: pd.DataFrame, states: pd.DataFrame, policy: Policy) -> pd.DataFrame:
    """Estimate only realized one-session utilities; no un-matured forward labels.

    The training window ends before the current close. State is the state at
    the prior interval's beginning; conditional means shrink toward all-state
    means and final budgets toward equal weights.
    """
    n = len(expert_returns.columns)
    equal = np.full(n, 1 / n)
    prior = equal.copy()
    budgets = np.tile(equal, (len(expert_returns), 1))
    dates = expert_returns.index
    state_array = states.state.to_numpy()
    values = expert_returns.to_numpy()
    for i, date in enumerate(dates):
        scheduled = (
            date.weekday() == 4
            if policy.cadence == "weekly"
            else (i == 0 or date.month != dates[i - 1].month)
        )
        if scheduled and i >= 126 and policy.family != "equal":
            left = max(1, i - policy.lookback)
            history = values[left:i]
            mean, variance = history.mean(axis=0), history.var(axis=0)
            if policy.family == "inverse_vol":
                raw = 1 / np.maximum(np.sqrt(variance), 0.003)
                proposed = raw / raw.sum()
            else:
                if policy.family == "conditional":
                    mask = state_array[left - 1 : i - 1] == state_array[i]
                    count = int(mask.sum())
                    if count:
                        mean = (history[mask].sum(axis=0) + policy.shrinkage * mean) / (
                            count + policy.shrinkage
                        )
                        variance = (
                            history[mask].var(axis=0) * count + policy.shrinkage * variance
                        ) / (count + policy.shrinkage)
                utility = np.clip((mean - 2 * variance) * 252, -0.5, 0.5)
                raw = np.exp(utility * 3)
                proposed = raw / raw.sum()
            proposed = 0.5 * equal + 0.5 * proposed
            delta = proposed - prior
            step = min(1.0, policy.max_step / max(np.abs(delta).max(), 1e-12))
            prior = prior + delta * step
        budgets[i] = prior
    return pd.DataFrame(budgets, index=dates, columns=expert_returns.columns)


def consolidate(
    targets: dict[str, pd.DataFrame], budgets: pd.DataFrame, states: pd.DataFrame, policy: Policy
) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = sorted(set().union(*(set(targets[n]) for n in budgets)))
    combined = pd.DataFrame(0.0, index=budgets.index, columns=columns)
    for name in budgets:
        combined += targets[name].reindex(columns=columns, fill_value=0).mul(budgets[name], axis=0)
    before = combined.sum(axis=1)
    # One global cap, not an additional copy of each specialist's native haircut.
    if policy.defense:
        cap = 1 - (1 - policy.protection_floor) * states.pressure
        combined = combined.mul(np.minimum(1, cap / combined.sum(axis=1).clip(lower=1e-12)), axis=0)
    technology = [c for c in columns if c in TECHNOLOGY]
    tech_before = combined[technology].sum(axis=1)
    combined.loc[:, technology] *= np.minimum(
        1, policy.technology_cap / tech_before.clip(lower=1e-12)
    ).to_numpy()[:, None]
    combined = combined.clip(lower=0)
    diagnostic = pd.DataFrame(
        {
            "risk_before_global_caps": before,
            "risk_after_global_caps": combined.sum(axis=1),
            "cash": 1 - combined.sum(axis=1),
            "technology_proxy_weight": combined[technology].sum(axis=1),
        },
        index=budgets.index,
    )
    return combined, diagnostic
