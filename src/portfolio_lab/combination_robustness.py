"""Post-run sensitivity diagnostics; no new allocations or winner selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.combination_stress import joint_intervals, verify
from portfolio_lab.contracts import digest
from portfolio_lab.engine import metrics
from portfolio_lab.research import EPISODES


def rolling_pair(candidate, reference, *, horizon=252, step=21):
    if not candidate.index.equals(reference.index):
        raise ValueError("Rolling comparisons require identical observed sessions")
    rows = []
    for end in range(horizon, len(candidate) + 1, step):
        left = end - horizon
        a, b = metrics(candidate.iloc[left:end]), metrics(reference.iloc[left:end])
        rows.append({"end": str(candidate.index[end - 1].date()),
                     "cagr_change": a["cagr"] - b["cagr"],
                     "drawdown_change": a["max_drawdown"] - b["max_drawdown"]})
    return rows


def episode_mask(index, start, end):
    return (index >= pd.Timestamp(start)) & (True if end is None else index <= pd.Timestamp(end))


def run(source, output):
    verify(source)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {"source": str(source.resolve()), "source_manifest_sha256": digest(source / "manifest.json"),
        "code_sha256": digest(Path(__file__)), "bootstrap_blocks": [21, 63, 126], "resamples": 1000,
        "rolling_horizons": [252, 756], "rolling_step": 21,
        "purpose": "post_run_sensitivity_not_unseen_confirmation; no new policy or selection",
        "portfolio_allocation_allowed": False}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    returns = pd.read_parquet(source / "returns.parquet")
    registry = json.loads((source / "registry.json").read_text())
    intervals, rolling, omissions = [], [], []
    for lag, cost in ((1, 25), (5, 50)):
        curves = {n: returns[f"conditional_events|{n}|lag{lag}|cost{cost}"].loc["2025-01-02":].dropna() for n in registry["conditional"]}
        combinations = [n for n in curves if n.startswith("probe__")]
        for reference in ("own_parent", "same_parent_cash", "development_risk_matched_trade"):
            excess = {}
            for name in combinations:
                _, parent, share, _ = name.split("__", 3)
                ref = parent if reference == "own_parent" else f"parent_cash__{parent}__{share}" if reference == "same_parent_cash" else f"risk_match__{name}"
                reference_returns = returns[f"conditional_events|{ref}|lag{lag}|cost{cost}"].loc[curves[name].index]
                excess[name] = np.log1p(curves[name]) - np.log1p(reference_returns)
            for block in protocol["bootstrap_blocks"]:
                intervals.extend([r | {"reference": reference, "lag": lag, "cost_bps": cost}
                                  for r in joint_intervals(pd.DataFrame(excess), block=block)])
    core_names = [n for n in registry["core"] if n not in {"trade_primary", "buy_hold_SPY", "buy_hold_QQQ"}]
    for scope, names, start in (("core_history", core_names, "2012-01-03"),
                                 ("conditional_events", combinations, "2025-01-02")):
        trade = returns[f"{scope}|trade_primary|lag1|cost25"].loc[start:].dropna()
        for name in names:
            candidate = returns[f"{scope}|{name}|lag1|cost25"].loc[trade.index]
            for horizon in protocol["rolling_horizons"]:
                rows = rolling_pair(candidate, trade, horizon=horizon)
                if rows:
                    rolling.append({"scope": scope, "candidate": name, "horizon": horizon, "overlapping_windows": len(rows),
                        "higher_return_fraction": float(np.mean([r["cagr_change"] > 0 for r in rows])),
                        "smaller_drawdown_fraction": float(np.mean([r["drawdown_change"] > 0 for r in rows])),
                        "both_better_fraction": float(np.mean([r["cagr_change"] > 0 and r["drawdown_change"] > 0 for r in rows])),
                        "median_cagr_change": float(np.median([r["cagr_change"] for r in rows]))})
            if scope != "core_history":
                continue
            for episode, (left, right) in EPISODES.items():
                omit = episode_mask(trade.index, left, right)
                if omit.sum() < 21:
                    continue
                a, b = metrics(candidate.loc[~omit]), metrics(trade.loc[~omit])
                omissions.append({"candidate": name, "omitted_episode": episode, "omitted_sessions": int(omit.sum()),
                                  "cagr_change": a["cagr"] - b["cagr"], "drawdown_change": a["max_drawdown"] - b["max_drawdown"]})
    for name, rows in (("event_reference_sensitivity", intervals), ("rolling_windows", rolling), ("omit_crisis_dates", omissions)):
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    checks = []
    table = pd.DataFrame(intervals)
    for (reference, block, lag, cost), group in table.groupby(["reference", "block_sessions", "lag", "cost_bps"]):
        checks.append({"reference": reference, "block": int(block), "lag": int(lag), "cost_bps": int(cost),
                       "comparisons": len(group), "positive_lower95": int(group.lower95.gt(0).sum()),
                       "positive_adjusted_p_below05": int((group.annual_log_excess.gt(0) & group.within_slate_max_abs_mean_p.lt(.05)).sum())})
    summary = {"purpose": protocol["purpose"], "event_uncertainty_checks": checks,
        "limitations": ["post_run_sensitivity_not_an_untouched_holdout", "rolling_windows_overlap_not_independent",
                        "omitted_dates_are_frozen_path_diagnostics_not_executable_counterfactuals",
                        "existing_survivorship_and_release_vintage_limits_unchanged"],
        "portfolio_allocation_allowed": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    verify(source)
    if protocol["code_sha256"] != digest(Path(__file__)):
        raise ValueError("Sensitivity code changed during execution")
    (output / "manifest.json").write_text(json.dumps({"authority": "research_only", "portfolio_allocation_allowed": False,
        "source_manifest_sha256": protocol["source_manifest_sha256"],
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
