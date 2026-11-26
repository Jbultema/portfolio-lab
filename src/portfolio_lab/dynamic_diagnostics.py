"""Descriptive stability checks, never allocation selection or new policy tuning."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.combination_robustness import episode_mask, rolling_pair
from portfolio_lab.contracts import digest
from portfolio_lab.dynamic_research import verify
from portfolio_lab.engine import metrics
from portfolio_lab.research import EPISODES


def run(source, output):
    summary = verify(source)
    output.mkdir(parents=True, exist_ok=False)
    source_identity = digest(source / "manifest.json")
    protocol = {"source": str(source.resolve()), "source_manifest_sha256": source_identity,
                "code_sha256": digest(Path(__file__)), "purpose": "descriptive_post_run_stability_not_new_strategy_selection",
                "rolling_sessions": [252, 756], "step": 21, "portfolio_allocation_allowed": False}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    returns = pd.read_parquet(source / "returns.parquet")
    registry = json.loads((source / "registry.json").read_text())["core"]
    events = json.loads((source / "event_registry.json").read_text())
    rows, omissions, distinct = [], [], {}
    for scope, specs, start in (("core", registry, "2019-01-01"), ("conditional_events", events, "2025-01-02")):
        base = returns[f"{scope}|trade_primary|raw|lag1|cost25"].loc[start:].dropna()
        hashes = {}
        for spec in specs:
            name = spec["name"]
            raw = returns[f"{scope}|{name}|raw|lag1|cost25"].loc[base.index]
            identity = hashlib.sha256(np.round(raw.to_numpy(), 12).tobytes()).hexdigest()
            hashes.setdefault(identity, []).append(name)
            for reference, a_role, b_role in (("trade_primary", "raw", "raw"), ("same_exposure", "capped", "matched_trade")):
                a = returns[f"{scope}|{name}|{a_role}|lag1|cost25"].loc[base.index]
                b = base if reference == "trade_primary" else returns[f"{scope}|{name}|{b_role}|lag1|cost25"].loc[base.index]
                for horizon in protocol["rolling_sessions"]:
                    comparisons = rolling_pair(a, b, horizon=horizon)
                    if not comparisons:
                        continue
                    rows.append({"scope": scope, "candidate": name, "reference": reference, "horizon": horizon,
                        "overlapping_windows": len(comparisons),
                        "higher_return_fraction": float(np.mean([r["cagr_change"] > 1e-8 for r in comparisons])),
                        "smaller_drawdown_fraction": float(np.mean([r["drawdown_change"] > 1e-8 for r in comparisons])),
                        "both_better_fraction": float(np.mean([r["cagr_change"] > 1e-8 and r["drawdown_change"] > 1e-8 for r in comparisons])),
                        "median_cagr_change": float(np.median([r["cagr_change"] for r in comparisons]))})
            if scope == "core":
                for episode, (left, right) in EPISODES.items():
                    if pd.Timestamp(left) < base.index[0]:
                        continue
                    mask = episode_mask(base.index, left, right)
                    if mask.sum() < 21:
                        continue
                    x, y = metrics(raw.loc[~mask]), metrics(base.loc[~mask])
                    omissions.append({"candidate": name, "episode_removed": episode,
                        "cagr_change": x["cagr"] - y["cagr"], "drawdown_change": x["max_drawdown"] - y["max_drawdown"]})
        distinct[scope] = {"registered_candidates": len(specs), "distinct_rounded_return_paths": len(hashes),
                           "exactly_Trade_returns": [s["name"] for s in specs if np.allclose(returns[f"{scope}|{s['name']}|raw|lag1|cost25"].loc[base.index], base, atol=1e-12, rtol=0)],
                           "duplicate_groups": [group for group in hashes.values() if len(group) > 1]}
    pd.DataFrame(rows).to_csv(output / "rolling_windows.csv", index=False)
    pd.DataFrame(omissions).to_csv(output / "omit_crisis_dates.csv", index=False)
    result = {"as_of_close": summary["as_of_close"], "distinctness": distinct,
        "purpose": protocol["purpose"], "portfolio_allocation_allowed": False,
        "limitations": ["overlapping_windows_not_independent_trials", "omitted_dates_are_frozen_path_not_executable_counterfactuals",
                        "rounded_return_path_distinctness_is_not_number_of_independent_hypotheses"]}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    verify(source)
    if source_identity != digest(source / "manifest.json") or protocol["code_sha256"] != digest(Path(__file__)):
        raise ValueError("Diagnostic source changed")
    (output / "manifest.json").write_text(json.dumps({"source_manifest_sha256": source_identity,
        "portfolio_allocation_allowed": False, "authority": "research_only",
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
