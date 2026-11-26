"""Post-hoc long-history falsification of the short-sample price-only control."""
from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.combination_stress import bound, joint_intervals
from portfolio_lab.contracts import ContractError, digest, load_panel
from portfolio_lab.dynamic_allocation import (
    PRIMARY,
    consolidate,
    exposure_controls,
    features,
    stabilize,
)
from portfolio_lab.dynamic_research import PERIODS, SCENARIOS, code_hashes
from portfolio_lab.dynamic_research import verify as verify_source
from portfolio_lab.engine import metrics, replay
from portfolio_lab.governance import policy_hash


def specs():
    return [{"name": f"price_context_a{int(share * 100)}_c{confirm}", "share": share, "confirm": confirm}
            for share, confirm in product((.25, .5, 1.), (3, 5))]


def budgets(context, spec):
    frame = pd.DataFrame(0., index=context.index, columns=PRIMARY)
    frame.trade_primary = 1.
    rotate = context.leadership_short.gt(.02) & context.breadth_short.ge(5 / 9)
    rebound = ~rotate & context.dd63.lt(-.05) & context.return5.gt(.01) & context.above10.eq(True)
    for condition, name in ((rotate, "rotation_primary"), (rebound, "swing_primary")):
        frame.loc[condition, "trade_primary"] = 1 - spec["share"]
        frame.loc[condition, name] = spec["share"]
    return stabilize(frame, confirm=spec["confirm"], minimum_hold=10, cadence="weekly")


def freeze(source, output):
    verify_source(source)
    output.mkdir(parents=True, exist_ok=False)
    cfg = {"kind": "price_context_followup_v1", "source": str(source.resolve()), "source_manifest_sha256": digest(source / "manifest.json"),
        "specifications": specs(), "code_sha256": digest(Path(__file__)), "financial_policy_sha256": policy_hash(),
        "dependency_code_sha256": code_hashes(),
        "selection": "none; post_hoc_followup_triggered_by_one_short_sample_stress_ablation; not_new_holdout_evidence",
        "portfolio_allocation_allowed": False, "scenarios": SCENARIOS}
    (output / "protocol.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (output / "protocol.sha256").write_text(digest(output / "protocol.json") + "\n")
    return {"frozen_cases": len(specs()), "portfolio_allocation_allowed": False}


def run(output):
    if (output / "summary.json").exists():
        raise FileExistsError("Immutable follow-up output already measured")
    cfg = json.loads((output / "protocol.json").read_text())
    if (digest(output / "protocol.json") != (output / "protocol.sha256").read_text().strip()
            or cfg["code_sha256"] != digest(Path(__file__)) or cfg["financial_policy_sha256"] != policy_hash()
            or cfg["dependency_code_sha256"] != code_hashes()):
        raise ContractError("Follow-up protocol or code changed")
    source = Path(cfg["source"])
    verify_source(source)
    if cfg["source_manifest_sha256"] != digest(source / "manifest.json"):
        raise ContractError("Follow-up source changed")
    source_cfg = json.loads((source / "protocol.json").read_text())
    for item in source_cfg["inputs"]:
        if digest(Path(item["path"]) / "manifest.json") != item["manifest_sha256"]:
            raise ContractError("Captured input manifest changed")
    core = [Path(item["path"]) for item in source_cfg["inputs"][:3]]
    prices, native, cash, meta = load_panel(core)
    native = {n: frame.reindex(columns=prices.columns, fill_value=0.) for n, frame in native.items()}
    context = features(prices)
    curves, rows, intervals, paths = {}, [], [], 0
    budget_book = {spec["name"]: budgets(context, spec) for spec in specs()}
    for lag, cost in SCENARIOS:
        kwargs = {"lag": lag, "cost_bps": cost, "terminal_events": meta["terminal_events"]}
        baseline = replay(prices, native["trade_primary"], cash, **kwargs)
        for name, allocation in budget_book.items():
            target = consolidate(native, allocation, prices)
            capped, matched = exposure_controls(target, native["trade_primary"])
            for role, frame in {"raw": target, "capped": capped, "matched_trade": matched,
                                "cash_ablation": native["trade_primary"].mul(allocation.trade_primary, axis=0)}.items():
                result = replay(prices, frame, cash, **kwargs)
                curves[f"{name}|{role}|lag{lag}|cost{cost}"] = result.returns
                paths += 1
                for period, (left, right) in PERIODS.items():
                    r = result.returns.loc[left:right]
                    if len(r) >= 21:
                        rows.append({"candidate": name, "role": role, "period": period, "lag": lag, "cost_bps": cost,
                                     **metrics(r, result.turnover)})
        curves[f"trade_primary|raw|lag{lag}|cost{cost}"] = baseline.returns
        for period, (left, right) in PERIODS.items():
            rows.append({"candidate": "trade_primary", "role": "raw", "period": period, "lag": lag, "cost_bps": cost,
                         **metrics(baseline.returns.loc[left:right], baseline.turnover)})
        for reference in ("trade_primary", "matched_trade", "cash_ablation"):
            excess = {}
            for name in budget_book:
                role = "capped" if reference == "matched_trade" else "raw"
                a = curves[f"{name}|{role}|lag{lag}|cost{cost}"].loc["2019-01-01":]
                b = baseline.returns.loc[a.index] if reference == "trade_primary" else curves[f"{name}|{reference}|lag{lag}|cost{cost}"].loc[a.index]
                excess[name] = np.log1p(a).sub(np.log1p(b))
            for block in (21, 63, 126):
                intervals.extend([row | {"reference": reference, "lag": lag, "cost_bps": cost}
                                  for row in joint_intervals(pd.DataFrame(excess), block=block)])
    pd.DataFrame(rows).to_csv(output / "performance.csv", index=False)
    pd.DataFrame(intervals).to_csv(output / "uncertainty.csv", index=False)
    pd.DataFrame(curves).to_parquet(output / "returns.parquet")
    pd.concat(budget_book, axis=1).to_parquet(output / "budgets.parquet")
    summary = {"cases": len(budget_book), "candidate_control_execution_paths": paths,
        "shared_baseline_execution_paths": 3, "selection": cfg["selection"], "portfolio_allocation_allowed": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    verify_source(source)
    if (cfg["code_sha256"] != digest(Path(__file__)) or cfg["financial_policy_sha256"] != policy_hash()
            or cfg["dependency_code_sha256"] != code_hashes()):
        raise ContractError("Financial code changed during follow-up")
    (output / "manifest.json").write_text(json.dumps({"kind": cfg["kind"], "authority": "research_only", "portfolio_allocation_allowed": False,
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    verify(output)
    return summary


def verify(root):
    meta = json.loads((root / "manifest.json").read_text())
    if (meta.get("kind") != "price_context_followup_v1" or meta.get("authority") != "research_only"
            or meta.get("portfolio_allocation_allowed") is not False
            or not {"protocol.json", "performance.csv", "summary.json", "returns.parquet"} <= meta["artifacts"].keys()):
        raise ContractError("Unauthorized follow-up")
    for name, expected in meta["artifacts"].items():
        bound(root, name, expected)
    return json.loads((root / "summary.json").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "verify"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.source, args.output) if args.command == "freeze" else run(args.output) if args.command == "run" else verify(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
