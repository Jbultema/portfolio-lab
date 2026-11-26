"""Funded common-clock validation and crisis-omission tests of native cash rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.combination_stress import bound, joint_intervals
from portfolio_lab.contracts import ContractError, digest, frame_check
from portfolio_lab.engine import metrics, replay


def run(source, output):
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("kind") != "native_staged_cash_v1" or manifest.get("portfolio_allocation_allowed") is not False:
        raise ContractError("Require explicitly unadmitted fixed native study")
    for name, identity in manifest["artifacts"].items():
        bound(source, name, identity)
    for name, identity in manifest["sources"].items():
        if digest(Path(name)) != identity:
            raise ContractError("Native source changed after study")
    prices = pd.read_parquet(source / "prices.parquet")
    cash = pd.read_parquet(source / "cash.parquet").iloc[:, 0]
    frame_check(prices)
    targets = {spec["name"]: pd.read_parquet(source / spec["weights_file"]) for spec in manifest["candidates"]}
    for target in targets.values():
        frame_check(target, weights=True)
    specs = {spec["name"]: spec for spec in manifest["candidates"]}
    for ticker in ("SPY", "QQQ"):
        targets["buy_hold_"+ticker] = pd.DataFrame({ticker: 1.}, index=prices.index)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {"kind": "native_cash_validation_v1", "native_manifest_sha256": digest(source / "manifest.json"),
        "cost_bps": [10, 25, 50], "lag_sessions": [1, 3], "selection": "none_all_fixed_variants",
        "clock": "target_close_t_fill_close_t_plus_lag_hold_units_fund_costs",
        "source_selection_bias": "modern_selected_stocks_and_previously_seen_history",
        "start": str(prices.index[0].date()), "end": str(prices.index[-1].date()),
        "warmup": "shared_first_complete_252_sessions_of_all_market_credit_breadth_inputs",
        "promotion_allowed": False}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    rows, curves, omissions = [], {}, []
    for lag in (1, 3):
        for cost in (10, 25, 50):
            for name, target in targets.items():
                result = replay(prices, target, cash, lag=lag, cost_bps=cost)
                curves[f"{name}|lag{lag}|cost{cost}"] = result.returns
                for period, left, right in (("full", None, None), ("pre2019", None, "2018-12-31"),
                    ("later", "2019-01-01", None), ("recent", "2024-01-01", None)):
                    rows.append({"candidate": name, "lag": lag, "cost_bps": cost, "period": period,
                        **metrics(result.returns.loc[left:right], result.turnover)})
    curves = pd.DataFrame(curves)
    uncertainty = []
    for parent in sorted({spec["parent"] for spec in specs.values()}):
        reference = curves[f"{parent}__unchanged|lag1|cost25"]
        names = [name for name, spec in specs.items() if spec["parent"] == parent and spec["kind"] == "native_staged"]
        excess = pd.DataFrame({name: np.log1p(curves[f"{name}|lag1|cost25"]) - np.log1p(reference) for name in names})
        for block in (21, 63, 126):
            uncertainty.extend([row | {"parent": parent} for row in joint_intervals(excess, block=block)])
        for name in names:
            r = curves[f"{name}|lag1|cost25"]
            for omitted, left, right in (("2020", "2020-01-01", "2020-12-31"),
                ("2022", "2022-01-01", "2022-12-31"), ("gfc", "2008-01-01", "2009-06-30")):
                keep = ~((r.index >= left) & (r.index <= right))
                omissions.append({"candidate": name, "parent": parent, "omitted": omitted,
                    "discontinuous_nontradable_diagnostic": True,
                    "annual_log_excess": float((np.log1p(r.loc[keep])-np.log1p(reference.loc[keep])).mean()*252)})
    pd.DataFrame(rows).to_csv(output / "performance.csv", index=False)
    pd.DataFrame(uncertainty).to_csv(output / "uncertainty.csv", index=False)
    pd.DataFrame(omissions).to_csv(output / "episode_omissions.csv", index=False)
    curves.to_parquet(output / "returns.parquet")
    summary = protocol | {"paths": len(curves.columns), "new_native_rules": sum(spec["kind"] == "native_staged" for spec in specs.values()),
        "positive_slate_adjusted_comparisons": sum(r["lower95"] > 0 and r["within_slate_max_abs_mean_p"] < .05 for r in uncertainty),
        "uncertainty_limit": "within_parent_slate_not_whole_program_adjustment",
        "action_authorized": False, "portfolio_allocation_allowed": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    (output / "manifest.json").write_text(json.dumps({"sources": {str(Path(__file__)): digest(Path(__file__))},
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2)+"\n")
    print(json.dumps(summary, indent=2))
    print(pd.DataFrame(rows).query("lag == 1 and cost_bps == 25 and period == 'full'")[["candidate", "cagr", "max_drawdown"]].to_string(index=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
