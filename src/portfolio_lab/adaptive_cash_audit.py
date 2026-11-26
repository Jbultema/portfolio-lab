"""Post-hoc falsification of cash controls already replayed in the frozen study."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.adaptive_research import verify
from portfolio_lab.combination_stress import bound, joint_intervals
from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.engine import metrics


def run(source, output):
    verify(source)
    curves = pd.read_parquet(source / "returns.parquet")
    specs = json.loads((source / "registry.json").read_text())["core"]
    rows, rolling, removals = [], [], []
    for lag, cost in ((1, 25), (5, 50)):
        reference = curves[f"core|trade_primary|raw|lag{lag}|cost{cost}"]
        for period, start in (("full", None), ("post_selection_2019_plus", "2019-01-01")):
            eligible = [s for s in specs if start is not None or s["round"] == 1]
            excess = pd.DataFrame({s["name"]: np.log1p(curves[f"core|{s['name']}|cash_ablation|lag{lag}|cost{cost}"].loc[start:]) - np.log1p(reference.loc[start:]) for s in eligible})
            for block in (21, 63, 126):
                rows.extend([r | {"lag": lag, "cost_bps": cost, "period": period, "reference": "unchanged_trade", "post_hoc_control_analysis": True}
                             for r in joint_intervals(excess, block=block)])
        if (lag, cost) != (1, 25):
            continue
        for spec in specs:
            name = spec["name"]
            cash = curves[f"core|{name}|cash_ablation|lag{lag}|cost{cost}"].loc["2019-01-01":]
            base = reference.loc[cash.index]
            differential = np.log1p(cash) - np.log1p(base)
            for horizon in (252, 756):
                sample = differential.rolling(horizon, min_periods=horizon).sum().dropna() * 252 / horizon
                rolling.append({"candidate": name, "sessions": horizon, "fraction_positive": float(sample.gt(1e-10).mean()),
                    "fraction_excess_above_10bps": float(sample.gt(.001).mean()),
                    "fraction_numerically_flat": float(sample.abs().le(1e-10).mean()),
                    "median_annual_log_excess": float(sample.median()), "worst_annual_log_excess": float(sample.min()),
                    "overlapping_not_independent_windows": len(sample)})
            for omitted, left, right in (("rates_episode", "2022-01-01", "2023-06-30"), ("calendar_2022", "2022-01-01", "2022-12-31"),
                                          ("calendar_2020", "2020-01-01", "2020-12-31")):
                keep = ~((cash.index >= left) & (cash.index <= right))
                for role, values in (("cash_control", cash), ("unchanged_trade", base)):
                    removals.append({"candidate": name, "role": role, "omitted": omitted, "discontinuous_not_a_tradable_strategy": True,
                        **metrics(values.loc[keep]), "annual_log_excess_vs_trade": float(differential.loc[keep].mean() * 252)})
    output.mkdir(parents=True, exist_ok=False)
    for name, records in (("uncertainty", rows), ("rolling_consistency", rolling), ("episode_omissions", removals)):
        pd.DataFrame(records).to_csv(output / f"{name}.csv", index=False)
    passing = [r for r in rows if r["lower95"] > 0 and r["within_slate_max_abs_mean_p"] < .05]
    result = {"kind": "adaptive_cash_control_audit_v1", "source": str(source.resolve()),
        "source_manifest_sha256": digest(source / "manifest.json"), "audit_code_sha256": digest(Path(__file__)),
        "new_policy_specifications": 0, "new_execution_paths": 0, "post_hoc_control_analysis": True,
        "positive_adjusted_comparisons": len(passing), "whole_program_selection_corrected": False,
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    verify_audit(output)
    return result


def verify_audit(root):
    manifest = json.loads((root / "manifest.json").read_text())
    required = {"summary.json", "uncertainty.csv", "rolling_consistency.csv", "episode_omissions.csv"}
    if not required <= manifest["artifacts"].keys():
        raise ContractError("Incomplete cash-control audit")
    for name, identity in manifest["artifacts"].items():
        bound(root, name, identity)
    summary = json.loads((root / "summary.json").read_text())
    if summary.get("kind") != "adaptive_cash_control_audit_v1" or summary.get("portfolio_allocation_allowed") is not False:
        raise ContractError("Wrong or authorized cash-control audit")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
