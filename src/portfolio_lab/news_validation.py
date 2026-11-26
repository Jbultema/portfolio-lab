"""Independent report replay/readback and matched-price-clock ablations; no tuning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.engine import metrics, replay
from portfolio_lab.news_evaluation import load_screen, partition_mask, write_json


def validate(screen: Path, report: Path, output: Path):
    source_meta, registry, prices = load_screen(screen)
    meta = json.loads((report / "manifest.json").read_text())
    if meta["input_manifest_sha256"] != digest(screen / "manifest.json"):
        raise ContractError("Performance report references different research inputs")
    for name, expected in meta["artifacts"].items():
        file = (report / name).resolve()
        if not file.is_relative_to(report.resolve()) or digest(file) != expected:
            raise ContractError("Performance artifact failed readback")
    if meta["engine_sha256"] != digest(Path(__file__).with_name("engine.py")):
        raise ContractError("Execution engine changed since performance run")
    output.mkdir(parents=True, exist_ok=False)
    selections = json.loads((report / "development_selection.json").read_text())
    specs = {s["id"]: s for s in registry["policies"]}
    zero = pd.Series(0., index=prices.index)
    checks, ablations = [], []
    for scenario in registry["scenarios"]:
        archived = pd.read_parquet(report / f"returns_{scenario['id']}.parquet")
        for asset, selection in selections.items():
            name = selection["id"]
            targets = pd.read_parquet(screen / "targets" / f"{name}_lag{scenario['publication_lag']}.parquet")
            replayed = replay(prices, targets, zero, lag=scenario["execution_lag"], cost_bps=scenario["cost_bps"])
            pd.testing.assert_series_equal(replayed.returns, archived[name], check_names=False, rtol=1e-12, atol=1e-12)
            checks.append({"scenario": scenario["id"], "id": name, "exact_replay": True})
            # QQQ candidates use SPY market structure, not QQQ's own moving average.
            # Remove news while keeping the market clock, decision cadence and floor.
            trend = prices.SPY.ge(prices.SPY.rolling(200, min_periods=200).mean()).astype(float)
            if registry.get("uses_historical_released_vintages"):
                v = pd.read_parquet(screen / "vintage_features.parquet")
                if "data_status" in v:
                    v = v[v.data_status.eq("fresh")]
                offsets = prices.index.searchsorted(pd.to_datetime(v.assumed_available_at).dt.tz_convert(None).dt.normalize())
                decisions = prices.index[offsets[offsets < len(prices)]]
                trend = trend.where(trend.index.isin(decisions)).ffill().fillna(1.)
            else:
                trend = trend.where(~prices.index.to_period("W-SUN").duplicated()).ffill().fillna(1.)
            floor = specs[name]["floor"]
            budget = floor + (1 - floor) * trend
            w = prices * 0.
            w[asset], w["SHY"] = budget, 1 - budget
            control = replay(prices, w, zero, lag=scenario["execution_lag"], cost_bps=scenario["cost_bps"])
            for partition, bounds in registry["partitions"].items():
                mask = partition_mask(prices.index, bounds, purge=registry["purge_sessions"] if partition != "development" else 0)
                candidate = metrics(replayed.returns.loc[mask], replayed.turnover.loc[mask])
                benchmark = metrics(control.returns.loc[mask], control.turnover.loc[mask])
                ablations.append({"scenario": scenario["id"], "period": partition, "id": name,
                                  "control": "SPY_trend_same_cadence_same_risk_asset_same_floor",
                                  "candidate_cagr": candidate["cagr"], "control_cagr": benchmark["cagr"],
                                  "cagr_difference": candidate["cagr"] - benchmark["cagr"],
                                  "candidate_max_drawdown": candidate["max_drawdown"],
                                  "control_max_drawdown": benchmark["max_drawdown"],
                                  "first_scored_session": str(prices.index[mask][0].date()),
                                  "last_scored_session": str(prices.index[mask][-1].date())})
    pd.DataFrame(ablations).to_csv(output / "same_clock_ablation.csv", index=False)
    # Full candidate family count is retained: this audit does not select a new winner.
    summary = {"status": "passed_readback_and_selected_path_replay", "action_authorized": False,
               "source_manifest_sha256": digest(screen / "manifest.json"),
               "performance_manifest_sha256": digest(report / "manifest.json"),
               "registered_policies": len(specs), "selected_scenario_replays": len(checks),
               "comparison_semantics": "Price-containing rules permit a news-removal ablation; pure-news rules are compared with, not algebraically reduced to, the matched price-only rule.",
               "exact_replay_checks": checks, "no_candidate_reselection": True,
               "uses_historical_released_vintages": bool(registry.get("uses_historical_released_vintages")),
               "limitations": registry["limitations"]}
    if source_meta.get("uses_historical_released_vintages"):
        acquisition = json.loads((screen / "sources/acquisition.json").read_text())
        requests = {item["sha256"]: item for item in acquisition["requests"] if item.get("http_status") == 200}
        vintages = pd.read_parquet(screen / "vintage_features.parquet")
        expected = registry["source_definitions"]["uncertainty"]["vintages"]
        if vintages.vintage.tolist() != expected or not set(vintages.vintage_sha256) <= set(requests):
            raise ContractError("Incomplete or unbound historical-vintage census")
        for row in vintages.itertuples():
            if pd.Timestamp(row.last_observation) > pd.Timestamp(row.vintage):
                raise ContractError("Future observation in released-vintage feature")
            if pd.Timestamp(row.assumed_available_at) < pd.Timestamp(row.vintage, tz="UTC") + pd.Timedelta(days=2):
                raise ContractError("Premature historical-vintage availability")
        summary["verified_vintages"] = len(vintages)
    if not np.isfinite(pd.DataFrame(ablations).select_dtypes("number")).all().all():
        raise ContractError("Nonfinite performance diagnostic")
    write_json(output / "audit.json", summary)
    write_json(output / "manifest.json", {"authority": "research_only", "action_authorized": False,
                                           "code_sha256": digest(Path(__file__)),
                                           "artifacts": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.screen, args.report, args.output), indent=2))


if __name__ == "__main__":
    main()
