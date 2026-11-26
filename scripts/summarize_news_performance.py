"""Sealed news-screen synthesis and fixed cross-market transport, not further tuning."""

import argparse
import json
from pathlib import Path

import pandas as pd

from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.engine import metrics, replay
from portfolio_lab.news_evaluation import family_check, load_screen, partition_mask, write_json


def run(root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    stages = {"current_history": root / "reports/news_proxy_performance_release_20261125",
              "released_vintages": root / "reports/news_vintage_performance_20261125",
              "maturity_followup": root / "reports/news_maturity_performance_20261125"}
    frames, summaries, perf, records = {}, {}, {}, []
    for label, folder in stages.items():
        manifest = json.loads((folder / "manifest.json").read_text())
        for name, expected in manifest["artifacts"].items():
            file = (folder / name).resolve()
            if not file.is_relative_to(folder.resolve()) or digest(file) != expected:
                raise ContractError("Cannot synthesize a changed performance archive")
        frames[label] = pd.read_parquet(folder / "returns_base.parquet")
        summaries[label] = json.loads((folder / "summary.json").read_text())
        perf[label] = pd.read_csv(folder / "performance.csv")
        for asset, selected in summaries[label]["development_selections"].items():
            rows = perf[label][perf[label].id.eq(selected["id"]) & perf[label].scenario.eq("base")]
            records += [{"study": label, "asset": asset, **r} for r in rows.to_dict("records")]
    pd.DataFrame(records).to_csv(output / "selected_comparison.csv", index=False)
    screen = root.parent / "fundamental-event-trader/reports/news_maturity_screen_20261125"
    _, registry, _ = load_screen(screen)
    # This is a fixed, explicitly post-discovery transport check, not another search.
    assets = ["RSP", "IWM", "EFA", "EEM", "XLV", "XLP", "XLE"]
    selected = summaries["maturity_followup"]["development_selections"]["SPY"]["id"]
    protocol = {"kind": "fixed_news_budget_cross_market_transport", "action_authorized": False,
                "source_policy": selected, "source_selection": "2014-2018 development only",
                "assets": assets, "parameter_changes": False, "candidate_reselection": False,
                "historical_holdout_is_not_unseen": True,
                "source_manifest_sha256": digest(screen / "manifest.json"),
                "scenarios": [{"id": "base", "lag": 1, "cost_bps": 10.},
                              {"id": "execution2", "lag": 2, "cost_bps": 10.},
                              {"id": "execution5", "lag": 5, "cost_bps": 10.},
                              {"id": "cost25", "lag": 1, "cost_bps": 25.}]}
    write_json(output / "transport_protocol.json", protocol)
    bundle = Path(registry["bundle"])
    bm = json.loads((bundle / "manifest.json").read_text())
    if digest(bundle / "manifest.json") != registry["bundle_manifest_sha256"] or digest(bundle / "prices.parquet") != bm["artifacts"]["prices.parquet"]:
        raise ContractError("Transport price history changed")
    wide = pd.read_parquet(bundle / "prices.parquet")
    budget = pd.read_parquet(screen / "targets" / f"{selected}_lag0.parquet").SPY
    if not budget.index.equals(wide.index):
        raise ContractError("Transport budget clock mismatch")
    if wide[assets + ["SHY"]].isna().any().any():
        raise ContractError("Transport cannot fill unavailable asset histories")
    mask = partition_mask(wide.index, registry["partitions"]["holdout_diagnostic"], purge=registry["purge_sessions"])
    zero = pd.Series(0., index=wide.index)
    transport = []
    transport_paths = {}
    for asset in assets:
        prices = wide[[asset, "SHY"]]
        candidate = prices * 0.
        candidate[asset], candidate["SHY"] = budget, 1 - budget
        bh = prices * 0.
        bh[asset] = 1.
        trend = prices[asset].ge(prices[asset].rolling(200).mean()).astype(float)
        trend = trend.where(~prices.index.to_period("W-SUN").duplicated()).ffill()
        price_target = prices * 0.
        price_target[asset], price_target["SHY"] = .5 + .5 * trend, .5 - .5 * trend
        for scenario in protocol["scenarios"]:
            for name, target in {"news_budget": candidate, "buy_hold": bh, "price_only_floor50": price_target}.items():
                result = replay(prices, target, zero, lag=scenario["lag"], cost_bps=scenario["cost_bps"])
                transport_paths[f"{asset}_{name}_{scenario['id']}"] = result.returns
                for period, bounds in {"full": [registry["primary_start"], registry["primary_end"]],
                                       "holdout_diagnostic": registry["partitions"]["holdout_diagnostic"]}.items():
                    keep = partition_mask(prices.index, bounds, purge=registry["purge_sessions"] if period == "holdout_diagnostic" else 0)
                    transport.append({"asset": asset, "scenario": scenario["id"], "policy": name, "period": period,
                                      **metrics(result.returns.loc[keep], result.turnover.loc[keep])})
    td = pd.DataFrame(transport)
    td.to_csv(output / "transport.csv", index=False)
    pd.DataFrame(transport_paths).to_parquet(output / "transport_returns.parquet")
    excess = {}
    for label in ("released_vintages", "maturity_followup"):
        specs = pd.read_csv(stages[label] / "performance.csv")
        candidates = set(specs.loc[specs.kind.eq("candidate"), "id"])
        for name in candidates:
            asset = "QQQ" if "_QQQ_" in name else "SPY"
            excess[name] = frames[label].loc[mask, name] - frames[label].loc[mask, f"buy_hold_{asset}"]
    stats = family_check(pd.DataFrame(excess))
    write_json(output / "joint_released_vintage_statistics.json", stats)
    base = td[td.scenario.eq("base") & td.period.eq("holdout_diagnostic")]
    paired = base.pivot(index="asset", columns="policy", values="cagr")
    score = {"tested_policy_variants": sum(s["tested_policies"] for s in summaries.values()),
             "policy_scenario_runs": sum(s["scenario_runs"] for s in summaries.values()),
             "transport_assets": len(assets), "transport_candidate_scenario_runs": len(assets) * len(protocol["scenarios"]),
             "transport_holdout_cagr_beats_buyhold": int(paired.news_budget.gt(paired.buy_hold).sum()),
             "joint_released_vintage_family_check": stats, "action_authorized": False,
             "first_holdout_session": str(wide.index[mask][0].date()), "last_session": str(wide.index[mask][-1].date())}
    write_json(output / "summary.json", score)
    write_json(output / "manifest.json", {"authority": "research_only", "action_authorized": False,
                                           "code_sha256": digest(Path(__file__)),
                                           "input_performance_manifests": {k: digest(p / "manifest.json") for k, p in stages.items()},
                                           "artifacts": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}})
    print(json.dumps(score, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.output)
