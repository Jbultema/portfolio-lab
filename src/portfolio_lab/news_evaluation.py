"""Research-only news-proxy performance screen through the existing execution engine.

This is not an admitted specialist, an RSS article backtest, or a new allocator policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.engine import metrics, replay


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load_screen(root):
    meta = json.loads((root / "manifest.json").read_text())
    if (meta.get("kind") != "news_proxy_etf_screen" or meta.get("action_authorized") is not False
            or meta.get("point_in_time_qualified") is not False or meta.get("rss_strategy_backtest") is not False):
        raise ContractError("Not an explicitly limited news-proxy screen")
    if not {"registry.json", "prices.parquet", "status.json", "sources/acquisition.json"} <= set(meta.get("artifacts", {})):
        raise ContractError("Incomplete bound news-screen evidence")
    for name, expected in meta["artifacts"].items():
        file = (root / name).resolve()
        if not file.is_relative_to(root.resolve()) or digest(file) != expected:
            raise ContractError("News-screen input integrity failed")
    registry = json.loads((root / "registry.json").read_text())
    if digest(root / "registry.json") != meta["registry_sha256"]:
        raise ContractError("News-screen frozen protocol changed")
    if (registry.get("kind") != meta["kind"] or registry.get("authority") != "research_only"
            or registry.get("action_authorized") is not False):
        raise ContractError("Invalid news-screen research authority")
    return meta, registry, pd.read_parquet(root / "prices.parquet")


def controls(prices, monthly_dates=None):
    result = {}
    for name, allocations in {
        "buy_hold_SPY": {"SPY": 1.}, "buy_hold_QQQ": {"QQQ": 1.}, "buy_hold_SHY": {"SHY": 1.},
        "initial_mix_SPY75_SHY25": {"SPY": .75, "SHY": .25},
        "initial_mix_QQQ75_SHY25": {"QQQ": .75, "SHY": .25},
        "static_sector_basket": {k: 1 / 7 for k in ("XLK", "XLY", "XLI", "XLF", "XLP", "XLV", "XLU")},
    }.items():
        w = prices * 0.
        for asset, value in allocations.items():
            w[asset] = value
        result[name] = w
    weeks = prices.index.to_period("W-SUN")
    first = ~weeks.duplicated()
    for asset in ("SPY", "QQQ"):
        state = prices[asset].ge(prices[asset].rolling(200, min_periods=200).mean()).astype(float)
        state = state.where(first).ffill()
        for floor in (0., .5):
            budget = floor + (1 - floor) * state
            w = prices * 0.
            w[asset] = budget
            w.SHY = 1 - budget
            result[f"price_only_{asset}_floor{int(floor * 100)}"] = w
            if monthly_dates is not None:
                raw = prices[asset].ge(prices[asset].rolling(200, min_periods=200).mean()).astype(float)
                monthly = raw.where(raw.index.isin(monthly_dates)).ffill().fillna(1.)
                budget = floor + (1 - floor) * monthly
                w = prices * 0.
                w[asset], w["SHY"] = budget, 1 - budget
                result[f"price_only_monthly_{asset}_floor{int(floor * 100)}"] = w
    return result


def partition_mask(index, bounds, *, purge=0):
    mask = (index >= bounds[0]) & (index <= bounds[1])
    positions = np.flatnonzero(mask)
    if len(positions):
        mask[positions[:purge]] = False
    return mask


def paired_block(candidate, benchmark, *, seed=20261125, reps=1000, block=63):
    values = (candidate - benchmark).dropna().to_numpy(float)
    if len(values) < 3 * block:
        return {"status": "insufficient_observations"}
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(values) - block + 1, size=(reps, int(np.ceil(len(values) / block))))
    offsets = np.arange(block)
    sampled = values[(starts[..., None] + offsets).reshape(reps, -1)[:, :len(values)]]
    means = sampled.mean(axis=1) * 252
    return {"status": "descriptive_retrospective_research", "block_sessions": block, "replications": reps,
            "annual_mean_excess": float(values.mean() * 252),
            "lower95": float(np.quantile(means, .025)), "upper95": float(np.quantile(means, .975))}


def select_development(table, specifications):
    development = table[table.scenario.eq("base") & table.period.eq("development")].set_index("id")
    selections = {}
    for asset in ("SPY", "QQQ"):
        candidates = [name for name, spec in specifications.items()
                      if spec["risk_asset"] == asset and spec["kind"] == "risk_budget" and name in development.index]
        benchmark = development.loc[f"buy_hold_{asset}"]
        scores = {name: float(development.loc[name, "cagr"] - benchmark.cagr
                             + .25 * (development.loc[name, "max_drawdown"] - benchmark.max_drawdown))
                  for name in candidates}
        if not scores:
            raise ContractError("No eligible development policies")
        winner = sorted(scores, key=lambda name: (-scores[name], name))[0]
        selections[asset] = {"id": winner, "development_score": scores[winner], "selection_partition": "development_only"}
    return selections


def family_check(excess: pd.DataFrame, *, seed=20261125, reps=500, block=63):
    """Centered maximum-mean-excess test; dependent/time-varying returns remain a limitation."""
    x = excess.to_numpy(float)
    if len(x) < 3 * block or x.shape[1] == 0:
        return {"status": "insufficient_observations"}
    means = x.mean(axis=0)
    centered = x - means
    observed = float(max(0., means.max()))
    rng, count = np.random.default_rng(seed), 0
    for _ in range(reps):
        starts = rng.integers(0, len(x) - block + 1, size=int(np.ceil(len(x) / block)))
        ix = (starts[:, None] + np.arange(block)).reshape(-1)[:len(x)]
        count += float(max(0., centered[ix].mean(axis=0).max())) >= observed
    return {"status": "descriptive_centered_max_mean_excess", "candidates": x.shape[1],
            "block_sessions": block, "replications": reps, "family_pvalue": (count + 1) / (reps + 1),
            "best_observed_annual_mean_excess": observed * 252,
            "limitations": "Retrospective hypotheses, reused market data and stationarity assumptions; not a deployability test"}


def evaluate(root: Path, output: Path):
    initial_code = digest(Path(__file__))
    initial_engine = digest(Path(__file__).with_name("engine.py"))
    meta, registry, full_prices = load_screen(root)
    output.mkdir(parents=True, exist_ok=False)
    (output / "evaluator.py.source.txt").write_bytes(Path(__file__).read_bytes())
    (output / "engine.py.source.txt").write_bytes(Path(__file__).with_name("engine.py").read_bytes())
    write_json(output / "protocol_copy.json", registry)
    # Preserve a real warmup before scored start; do not reset at each market episode.
    scored_start = registry["primary_start"]
    prices = full_prices.loc[:registry["primary_end"]]
    zero_cash = pd.Series(0., index=prices.index)
    monthly_dates = None
    if registry.get("uses_historical_released_vintages"):
        v = pd.read_parquet(root / "vintage_features.parquet")
        positions = prices.index.searchsorted(pd.to_datetime(v.assumed_available_at).dt.tz_convert(None).dt.normalize())
        monthly_dates = prices.index[positions[positions < len(prices)]]
    targets = controls(prices, monthly_dates)
    specifications = {spec["id"]: spec for spec in registry["policies"]}
    rows, returns_by_scenario, turnovers_by_scenario = [], {}, {}
    target_meta = pd.DataFrame(json.loads((root / "status.json").read_text()))
    for scenario in registry["scenarios"]:
        sid = scenario["id"]
        returns, turnovers = {}, {}
        for name in specifications:
            file = root / "targets" / f"{name}_lag{scenario['publication_lag']}.parquet"
            if file.is_file():
                if str(file.relative_to(root)) not in meta["artifacts"]:
                    raise ContractError("Unbound research target")
                targets[name] = pd.read_parquet(file)
            else:
                targets.pop(name, None)
        for name, weights in targets.items():
            if not weights.index.equals(prices.index):
                raise ContractError("Research targets do not align to observed prices")
            result = replay(prices, weights, zero_cash, lag=scenario["execution_lag"], cost_bps=scenario["cost_bps"])
            returns[name], turnovers[name] = result.returns, result.turnover
        ret, turns = pd.DataFrame(returns), pd.DataFrame(turnovers)
        returns_by_scenario[sid], turnovers_by_scenario[sid] = ret, turns
        ret.to_parquet(output / f"returns_{sid}.parquet")
        turns.to_parquet(output / f"turnover_{sid}.parquet")
        periods = {"full": [scored_start, registry["primary_end"]], **registry["partitions"],
                   "post_news_index_publication": [registry.get("public_signal_start", "2020-04-14"), registry["primary_end"]]}
        for period, bounds in periods.items():
            mask = partition_mask(ret.index, bounds, purge=registry["purge_sessions"] if period in {"validation", "holdout_diagnostic"} else 0)
            for name in ret:
                rows.append({"scenario": sid, "period": period, "id": name,
                             "kind": "candidate" if name in specifications else "control",
                             **metrics(ret.loc[mask, name], turns.loc[mask, name])})
        print(json.dumps({"scenario_completed": sid, "candidates": sum(name in specifications for name in ret)}), flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(output / "performance.csv", index=False)
    base = table[table.scenario.eq("base")]
    selections = select_development(table, specifications)
    write_json(output / "development_selection.json", selections)
    ret = returns_by_scenario["base"]
    turns = turnovers_by_scenario["base"]
    regime_rows = []
    stress = pd.Series(False, index=ret.index)
    for regime, bounds in registry["regimes"].items():
        if bounds[1] < scored_start:
            continue
        mask = partition_mask(ret.index, [max(bounds[0], scored_start), bounds[1]])
        stress |= mask
        for name in ret:
            regime_rows.append({"regime": regime, "id": name, **metrics(ret.loc[mask, name], turns.loc[mask, name])})
    regular = ~stress & (ret.index >= scored_start)
    for label, mask in {"regular_complement": regular, "stress_concatenated": stress}.items():
        for name in ret:
            record = metrics(ret.loc[mask, name], turns.loc[mask, name])
            # Concatenated disjoint sessions are not a continuous achievable equity path.
            record.pop("cagr", None)
            record.pop("max_drawdown", None)
            regime_rows.append({"regime": label, "id": name, **record})
    pd.DataFrame(regime_rows).to_csv(output / "regimes.csv", index=False)
    mask = partition_mask(ret.index, registry["partitions"]["holdout_diagnostic"], purge=registry["purge_sessions"])
    excess = {}
    for name, spec in specifications.items():
        if name in ret:
            benchmark = "static_sector_basket" if spec["kind"] == "sector_rotation" else f"buy_hold_{spec['risk_asset']}"
            excess[name] = ret.loc[mask, name] - ret.loc[mask, benchmark]
    stats = {"family": family_check(pd.DataFrame(excess)), "selected": {}}
    for asset, selection in selections.items():
        name = selection["id"]
        stats["selected"][name] = {
            "vs_buy_hold": paired_block(ret.loc[mask, name], ret.loc[mask, f"buy_hold_{asset}"]),
            "vs_price_only": paired_block(ret.loc[mask, name], ret.loc[mask, f"price_only_{asset}_floor0"]),
        }
    write_json(output / "statistics.json", stats)
    yearly = []
    for year in sorted(set(ret.index.year)):
        year_mask = (ret.index.year == year) & (ret.index >= scored_start)
        if not year_mask.any():
            continue
        for name in ret:
            yearly.append({"year": year, "id": name, **metrics(ret.loc[year_mask, name], turns.loc[year_mask, name])})
    pd.DataFrame(yearly).to_csv(output / "yearly.csv", index=False)
    timing = []
    lead_times = []
    for asset, selection in selections.items():
        name = selection["id"]
        primary_lag = next(s["publication_lag"] for s in registry["scenarios"] if s["id"] == "base")
        weights = pd.read_parquet(root / "targets" / f"{name}_lag{primary_lag}.parquet")
        exposure = weights[asset].shift(1)
        episodes = exposure.lt(.75) & ~exposure.shift(1).lt(.75)
        onset_dates = exposure.index[episodes]
        for regime, bounds in registry["regimes"].items():
            if bounds[0] < scored_start:
                continue
            start = exposure.index.searchsorted(pd.Timestamp(bounds[0]))
            if start >= len(exposure):
                continue
            if exposure.iloc[start] < .75:
                eligible = onset_dates[onset_dates <= exposure.index[start]]
                date = eligible[-1] if len(eligible) else None
                status = "already_defensive_at_peak"
            else:
                eligible = onset_dates[(onset_dates > exposure.index[start]) & (onset_dates <= pd.Timestamp(bounds[1]))]
                date = eligible[0] if len(eligible) else None
                status = "defensive_after_peak" if date is not None else "no_hard_defense_in_window"
            lead_times.append({"id": name, "regime": regime, "peak_reference": bounds[0],
                               "defense_fill": str(date.date()) if date is not None else None,
                               "calendar_days_before_peak": (pd.Timestamp(bounds[0]) - date).days if date is not None else None,
                               "status": status, "threshold": "risk asset target below 75%; descriptive retrospective label"})
        for date in exposure.index[episodes & (exposure.index >= scored_start)]:
            i = prices.index.get_loc(date)
            if i + 63 >= len(prices):
                continue
            # These labels are outcomes only; no target generation consumes them.
            path = prices[asset].iloc[i:i + 64] / prices[asset].iloc[i]
            timing.append({"id": name, "risk_off_date": str(date.date()), "asset": asset,
                           "forward63_return": float(path.iloc[-1] - 1),
                           "forward63_min_return": float(path.min() - 1),
                           "forward63_max_return": float(path.max() - 1),
                           "false_alarm_up5_without_down5": bool(path.iloc[-1] > 1.05 and path.min() > .95)})
    pd.DataFrame(timing).to_csv(output / "risk_off_episodes.csv", index=False)
    pd.DataFrame(lead_times).to_csv(output / "lead_times.csv", index=False)
    hurdles = {}
    for asset, selection in selections.items():
        selected = base[base.id.eq(selection["id"]) & base.period.eq("holdout_diagnostic")].iloc[0]
        bh = base[base.id.eq(f"buy_hold_{asset}") & base.period.eq("holdout_diagnostic")].iloc[0]
        pt = base[base.id.eq(f"price_only_{asset}_floor0") & base.period.eq("holdout_diagnostic")].iloc[0]
        hurdles[asset] = {"holdout_cagr_plus1pp": bool(selected.cagr >= bh.cagr + .01),
                          "holdout_drawdown_within2pp": bool(selected.max_drawdown >= bh.max_drawdown - .02),
                          "beats_price_only_cagr": bool(selected.cagr > pt.cagr),
                          "beats_price_only_drawdown": bool(selected.max_drawdown >= pt.max_drawdown),
                          "positive_block_interval_vs_buyhold": bool(stats["selected"][selection["id"]]["vs_buy_hold"].get("lower95", -1) > 0),
                          "live_admission": False}
    summary = {
        "kind": "news_proxy_etf_screen", "authority": "research_only", "action_authorized": False,
        "rss_strategy_backtest": False, "point_in_time_qualified": False,
        "registered_policies": len(specifications), "tested_policies": len(excess),
        "scenario_runs": sum(len([c for c in frame if c in specifications]) for frame in returns_by_scenario.values()),
        "price_start": str(prices.index[0].date()), "price_end": str(prices.index[-1].date()),
        "scored_start": scored_start, "development_selections": selections,
        "selected_hurdles": hurdles,
        "source_status": json.loads((root / "sources/acquisition.json").read_text())["sources"],
        "coverage": target_meta.to_dict("records"), "limitations": registry["limitations"],
        "input_manifest_sha256": digest(root / "manifest.json"),
    }
    write_json(output / "summary.json", summary)
    lines = ["# News-Proxy Investment Performance Screen", "",
             "Research only. Not an RSS article-strategy backtest; no automatic admission.", "",
             f"{summary['tested_policies']} policies; {summary['scenario_runs']} candidate/scenario runs. "
             f"Prices through {summary['price_end']}. Primary scored period begins {scored_start}.", "",
             "Rules/selection/partitions/scenarios frozen before return evaluation. Holdout is a retrospective chronological diagnostic, not newly unseen data.", "",
             "## Development-Selected Policies", "",
             "| Asset | Policy | Period | CAGR | Max DD |", "|---|---|---|---:|---:|"]
    for asset, selection in selections.items():
        for name in (f"buy_hold_{asset}", f"initial_mix_{asset}75_SHY25", f"price_only_{asset}_floor0", selection["id"]):
            for period in ("full", "validation", "holdout_diagnostic"):
                r = base[base.id.eq(name) & base.period.eq(period)].iloc[0]
                lines.append(f"| {asset} | {name} | {period} | {r.cagr:.2%} | {r.max_drawdown:.2%} |")
    lines += ["", "## Interpretation Limits", ""] + [f"- {s}" for s in registry["limitations"]]
    lines += ["", "Full rankings, stress periods, execution/cost sensitivity, paired-block intervals, a family-wise screen and risk-off outcomes are in the adjacent CSV/JSON artifacts.", ""]
    (output / "report.md").write_text("\n".join(lines))
    if initial_code != digest(Path(__file__)) or initial_engine != digest(Path(__file__).with_name("engine.py")):
        raise ContractError("Research/evaluation code changed during execution; rerun required")
    write_json(output / "manifest.json", {"kind": summary["kind"], "authority": "research_only", "action_authorized": False,
                                           "input_manifest_sha256": summary["input_manifest_sha256"],
                                           "evaluator_sha256": initial_code,
                                           "engine_sha256": initial_engine,
                                           "artifacts": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.screen, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "coverage"}, indent=2))


if __name__ == "__main__":
    main()
