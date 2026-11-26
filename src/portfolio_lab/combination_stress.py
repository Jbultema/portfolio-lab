"""Same-clock cross-bot falsification and isolated, unadmitted event combinations."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from portfolio_lab.allocation import TECHNOLOGY, Policy, allocate, regimes
from portfolio_lab.audit import audit
from portfolio_lab.contracts import ContractError, digest, frame_check, load_panel
from portfolio_lab.engine import metrics, replay
from portfolio_lab.governance import policy_hash
from portfolio_lab.research import EPISODES, PERIODS

KIND = "cross_specialist_stress_v1"
PRIMARY = ("trade_primary", "swing_primary", "rotation_primary")


def bound(root, name, expected):
    file = (root / name).resolve()
    if not file.is_relative_to(root.resolve()) or not file.is_file() or digest(file) != expected:
        raise ContractError(f"Research artifact integrity failed: {name}")
    return file


def load_probes(root):
    meta = json.loads((root / "manifest.json").read_text())
    if (meta.get("kind") != "conditional_event_probes_v1" or meta.get("admitted_specialist") is not False
            or meta.get("authority") != "isolated_conditional_research_only"
            or meta.get("portfolio_allocation_allowed") is not False
            or meta.get("automatic_promotion_allowed") is not False):
        raise ContractError("Only explicitly unadmitted conditional probes accepted here")
    for file, expected in meta["artifacts"].items():
        bound(root, file, expected)
    prices = pd.read_parquet(bound(root, "prices.parquet", meta["artifacts"]["prices.parquet"]))
    frame_check(prices)
    targets = {}
    for expert in meta["experts"]:
        if (expert.get("portfolio_allocation_allowed") is not False
                or expert.get("evidence_status") != "conditional_survivor_sample_not_admitted"
                or expert.get("target_semantics") != "close_known_risky_budgets"
                or expert["id"] in targets):
            raise ContractError("Conditional probe identity or authority mismatch")
        target = pd.read_parquet(bound(root, expert["weights_file"], meta["artifacts"][expert["weights_file"]]))
        frame_check(target, weights=True)
        if not target.index.equals(prices.index) or not set(target) <= set(prices):
            raise ContractError("Probe targets and captured prices do not align")
        if (target.gt(1e-12) & prices.reindex(columns=target.columns).isna()).any().any():
            raise ContractError("Unpriced event probe")
        targets[expert["id"]] = target
    if not targets or str(prices.index[-1].date()) != meta["data_end"]:
        raise ContractError("Empty or misdated conditional panel")
    return prices, targets, meta


def core_specs():
    out = [{"name": n, "kind": "standalone", "budgets": {n: 1.}} for n in PRIMARY]
    out += [{"name": f"buy_hold_{n}", "kind": "benchmark", "ticker": n} for n in ("SPY", "QQQ")]
    out += [{"name": f"trade_cash_{int(100 * share)}", "kind": "cash_control", "budgets": {"trade_primary": share}}
            for share in (.75, .90)]
    out += [{"name": f"trade_{int(100 * share)}_{other.split('_')[0]}", "kind": "fixed_blend",
             "budgets": {"trade_primary": share, other: 1 - share}}
            for other, share in product(("swing_primary", "rotation_primary"), (.90, .75, .50))]
    out += [{"name": name, "kind": "fixed_blend", "budgets": dict(zip(PRIMARY, shares, strict=True))}
            for name, shares in (("threeway_80_10_10", (.8, .1, .1)), ("threeway_60_20_20", (.6, .2, .2)),
                                 ("threeway_equal", (1/3, 1/3, 1/3)))]
    out += [{"name": f"allocator_{family}", "kind": "allocator", "family": family} for family in ("conditional", "inverse_vol")]
    out += [{"name": "ablate_swing_to_cash", "kind": "ablation", "budgets": {"trade_primary": .8, "rotation_primary": .1}},
            {"name": "ablate_rotation_to_cash", "kind": "ablation", "budgets": {"trade_primary": .8, "swing_primary": .1}}]
    out += [{"name": n, "kind": "trade_challenger", "budgets": {n: 1.}} for n in ("trade_gentle_protection", "trade_staged_recovery")]
    out.append({"name": "portfolio_lab_frozen", "kind": "archived_allocator"})
    return out


def mix(targets, budgets, index, columns):
    if any(not np.isfinite(v) or v < 0 for v in budgets.values()) or sum(budgets.values()) > 1 + 1e-10:
        raise ContractError("Invalid cross-specialist budget")
    out = pd.DataFrame(0., index=index, columns=columns)
    for name, weight in budgets.items():
        if not index.isin(targets[name].index).all():
            raise ContractError("Missing specialist sessions cannot be zero-filled")
        frame = targets[name].reindex(index=index, columns=columns, fill_value=0.)
        if frame.isna().any().any():
            raise ContractError("Missing specialist target cannot be replaced by zero")
        out += frame * weight
    frame_check(out, weights=True)
    return out


def risk_control(candidate_returns, baseline_returns, baseline_target, training):
    sample = candidate_returns.loc[training[0]:training[1]]
    reference = baseline_returns.loc[sample.index]
    if len(sample) < 126 or not np.isfinite(sample).all() or not np.isfinite(reference).all():
        raise ContractError("Insufficient finite development evidence for risk control")
    scale = min(1., float(sample.std() / max(reference.std(), 1e-12)))
    target = baseline_target * scale
    known_at = sample.index[-1]
    target.loc[target.index < known_at] = 0.
    return target, scale, known_at


def add_probe_prices(core, event):
    common = core.index.intersection(event.index)
    if len(common) < 252:
        raise ContractError("Insufficient actual overlapping sessions")
    base = core.loc[common].copy()
    evidence = []
    for ticker in event:
        if ticker in base:
            delta = (base[ticker].pct_change(fill_method=None) - event.loc[common, ticker].pct_change(fill_method=None)).abs().dropna()
            if not len(delta) or delta.max() > .03:
                raise ContractError(f"Event/core price disagreement: {ticker}")
            evidence.append({"ticker": ticker, "chosen": "unchanged_core", "max_return_disagreement": float(delta.max())})
        else:
            base[ticker] = event.loc[common, ticker]
            evidence.append({"ticker": ticker, "chosen": "event_captured_source", "max_return_disagreement": 0.})
    return base, evidence


def stale_target(target, start, *, duration=21, grace=5):
    if duration < grace or grace < 0:
        raise ContractError("Invalid modeled signal outage")
    out = target.copy()
    position = out.index.searchsorted(pd.Timestamp(start))
    if position == 0 or position >= len(out):
        raise ContractError("Outage needs a prior captured target")
    finish = min(position + duration, len(out))
    out.iloc[position:min(position + grace, finish)] = out.iloc[position - 1].to_numpy()
    out.iloc[min(position + grace, finish):finish] = 0.
    return out


def joint_intervals(excess, *, block=63, reps=1000, seed=20261126):
    values = excess.to_numpy(float)
    if not np.isfinite(values).all() or len(values) < 3 * block:
        return []
    rng = np.random.default_rng(seed)
    means = np.empty((reps, values.shape[1]))
    for i in range(reps):
        starts = rng.integers(0, len(values) - block + 1, size=int(np.ceil(len(values) / block)))
        indices = (starts[:, None] + np.arange(block)).ravel()[:len(values)]
        means[i] = values[indices].mean(axis=0) * 252
    observed = values.mean(axis=0) * 252
    maximum = np.abs(means - observed).max(axis=1)
    return [{"candidate": n, "annual_log_excess": float(observed[j]),
             "lower95": float(np.quantile(means[:, j], .025)), "upper95": float(np.quantile(means[:, j], .975)),
             "within_slate_max_abs_mean_p": float((1 + (maximum >= abs(observed[j])).sum()) / (reps + 1)),
             "block_sessions": block, "samples": reps, "not_whole_program_selection_corrected": True}
            for j, n in enumerate(excess)]


def period_rows(result, periods):
    return [{"period": name, **metrics(result.returns.loc[start:end], result.turnover)}
            for name, (start, end) in periods.items() if len(result.returns.loc[start:end]) >= 21]


def shock_loss(weights, kind):
    if kind not in {"broad_gap20", "ai_gap35", "ai_gap60", "inflation_rates", "liquidity_gap"}:
        raise ContractError("Unknown frozen-position shock")
    moves = pd.Series(-.20, index=weights.index)
    if kind in {"ai_gap35", "ai_gap60"}:
        moves[:] = -.10 if kind == "ai_gap35" else -.15
        moves.loc[moves.index.isin(TECHNOLOGY | {"AAPL"})] = -.35 if kind == "ai_gap35" else -.60
    elif kind == "liquidity_gap":
        moves[:] = -.25
    for ticker, move in ({"GLD": .03, "IEF": .02} if kind in {"ai_gap35", "broad_gap20"}
                         else {"GLD": 0., "IEF": 0.} if kind == "ai_gap60"
                         else {"GLD": -.05, "IEF": -.15} if kind == "inflation_rates"
                         else {"GLD": -.15, "IEF": -.10}).items():
        if ticker in moves:
            moves[ticker] = move
    if "BIL" in moves:
        moves["BIL"] = 0.
    return float(weights.dot(moves))


def freeze(paths, event_root, archived, output):
    prices, targets, cash, meta = load_panel(paths)
    calendar = xcals.get_calendar("XNYS", start=prices.index[0] - pd.Timedelta(days=7), end=prices.index[-1] + pd.Timedelta(days=7))
    expected = calendar.sessions_in_range(prices.index[0], prices.index[-1]).tz_localize(None)
    if not prices.index.equals(expected):
        raise ContractError("Common history must contain each actual NYSE session, without filled holidays")
    if {m["system"] for m in meta["bundles"]} != {"trade-bot", "swing-trader", "rotation-trader"}:
        raise ContractError("Exactly the three existing core specialists required")
    event_prices, event_targets, _ = load_probes(event_root)
    _, price_checks = add_probe_prices(prices, event_prices)
    checked = audit(archived)
    if checked["errors"]:
        raise ContractError("Archived Portfolio Lab allocator failed its original audit")
    archived_target = pd.read_parquet(archived / "selected_targets.parquet")
    if not prices.index.isin(archived_target.index).all() or not set(archived_target) <= set(prices):
        raise ContractError("Archived allocator and current common clock do not overlap completely")
    if not set(PRIMARY) <= set(targets):
        raise ContractError("Missing unchanged primary strategy")
    output.mkdir(parents=True, exist_ok=False)
    protocol = {"kind": KIND, "created_at_utc": datetime.now(UTC).isoformat(),
        "core_bundles": [{"path": str(p.resolve()), "manifest_sha256": digest(p / "manifest.json")} for p in paths],
        "conditional_probes": {"path": str(event_root.resolve()), "manifest_sha256": digest(event_root / "manifest.json")},
        "archived_allocator": {"path": str(archived.resolve()), "manifest_sha256": digest(archived / "manifest.json")},
        "core_specs": core_specs(), "event_probes": sorted(event_targets),
        "event_shares": [.10, .25], "event_parents": ["trade_primary", "portfolio_lab_frozen"],
        "core_scenarios": [{"lag": lag, "cost_bps": cost} for lag, cost in product((1, 2, 5), (10, 25, 50))],
        "event_scenarios": [{"lag": lag, "cost_bps": cost} for lag, cost in ((1, 10), (1, 25), (2, 25), (5, 25), (5, 50))],
        "core_start": str(prices.index[0].date()), "core_end": str(prices.index[-1].date()),
        "core_training_end": "2011-12-31", "event_training": ["2023-01-03", "2024-06-28"],
        "event_periods": {"full_overlap": ["2023-01-03", None], "development": ["2023-01-03", "2024-06-28"],
                          "evaluation_2025_plus": ["2025-01-02", None], "current_transition": ["2026-06-01", None]},
        "risk_controls": "Trade Bot scaled by development-only realized volatility ratio, capped at 1; no evaluation risk fit",
        "event_parent_cash_controls": "parent scaled by one minus event budget, leaving event share cash",
        "execution": "close-known targets; actual next/second/fifth observed close fill; returns after fill; self-financing consolidated trades; one captured common cash series",
        "frozen_native_child_targets": True,
        "price_source_policy": "core series retained unchanged; new event instruments only within observed overlap; no pre-inception or pre-coverage padding",
        "price_checks": price_checks, "policy_hash": policy_hash(), "runner_sha256": digest(Path(__file__)),
        "outages": {"duration_sessions": 21, "last_target_grace_sessions": 5,
                    "starts": ["2008-09-12", "2020-02-21", "2022-01-03", "2026-06-01"],
                    "parents": ["trade_primary", "threeway_80_10_10", "threeway_equal"]},
        "shock_types": ["broad_gap20", "ai_gap35", "ai_gap60", "inflation_rates", "liquidity_gap"],
        "shock_semantics": "instantaneous shocks to latest executed holdings, no modeled native response, scenarios not forecasts or historical evidence",
        "selection": "none; fixed full slate reported, no best evaluation policy promoted",
        "limitations": ["modern_selected_stock_universe_not_survivorship_free", "common_core_history_starts_2006_not_dotcom",
                        "conditional_events_start_2023_not_old_crises", "later_history_previously_inspected",
                        "cross_bot_signals_share_price_information", "common_close_execution_not_native_open_execution",
                        "conditional_event_probes_unadmitted", "no_whole_historical_program_multiple_testing_claim"],
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    (output / "protocol.sha256").write_text(digest(output / "protocol.json") + "\n")
    return protocol


def core_targets(prices, specialists, cash, archived):
    targets = {}
    expert_returns = pd.DataFrame({n: replay(prices, specialists[n], cash, cost_bps=25).returns for n in PRIMARY})
    states = regimes(prices)
    for spec in core_specs():
        name = spec["name"]
        if "budgets" in spec:
            targets[name] = mix(specialists, spec["budgets"], prices.index, prices.columns)
        elif spec["kind"] == "benchmark":
            target = prices * 0.
            target[:] = 0.
            target[spec["ticker"]] = 1.
            targets[name] = target
        elif spec["kind"] == "archived_allocator":
            targets[name] = pd.read_parquet(archived / "selected_targets.parquet").reindex(index=prices.index, columns=prices.columns, fill_value=0.)
        else:
            budgets = allocate(expert_returns, states, Policy(name, spec["family"], lookback=756, shrinkage=252))
            target = pd.DataFrame(0., index=prices.index, columns=prices.columns)
            for n in PRIMARY:
                target += specialists[n].reindex(columns=prices.columns, fill_value=0).mul(budgets[n], axis=0)
            targets[name] = target
        frame_check(targets[name], weights=True)
    return targets


def run(output):
    if (output / "summary.json").exists() or (output / "registry.json").exists():
        raise FileExistsError("Use a fresh immutable research output")
    if digest(output / "protocol.json") != (output / "protocol.sha256").read_text().strip():
        raise ContractError("Frozen protocol changed")
    cfg = json.loads((output / "protocol.json").read_text())
    if cfg["runner_sha256"] != digest(Path(__file__)) or cfg["policy_hash"] != policy_hash() or cfg["core_specs"] != core_specs():
        raise ContractError("Frozen financial code changed")
    for item in [*cfg["core_bundles"], cfg["conditional_probes"], cfg["archived_allocator"]]:
        if digest(Path(item["path"]) / "manifest.json") != item["manifest_sha256"]:
            raise ContractError("Frozen input manifest changed")
    paths = [Path(p["path"]) for p in cfg["core_bundles"]]
    prices, native, cash, meta = load_panel(paths)
    if audit(Path(cfg["archived_allocator"]["path"]))["errors"]:
        raise ContractError("Archived allocator artifacts changed after freezing")
    event_prices, event_targets, event_meta = load_probes(Path(cfg["conditional_probes"]["path"]))
    targets = core_targets(prices, native, cash, Path(cfg["archived_allocator"]["path"]))
    event_prices, checks = add_probe_prices(prices, event_prices)
    if checks != cfg["price_checks"]:
        raise ContractError("Frozen price-source comparison changed")
    parent_targets = {n: targets[n].reindex(index=event_prices.index, columns=event_prices.columns, fill_value=0.) for n in cfg["event_parents"]}
    conditional = dict(parent_targets)
    for parent, share in product(cfg["event_parents"], cfg["event_shares"]):
        conditional[f"parent_cash__{parent}__{int(share * 100)}"] = parent_targets[parent] * (1 - share)
        for probe, target in event_targets.items():
            name = f"probe__{parent}__{int(share * 100)}__{probe}"
            conditional[name] = parent_targets[parent] * (1 - share) + target.reindex(index=event_prices.index, columns=event_prices.columns, fill_value=0.) * share
    for name, target in event_targets.items():
        conditional[name] = target.reindex(index=event_prices.index, columns=event_prices.columns, fill_value=0.)
    (output / "registry.json").write_text(json.dumps({"core": list(targets), "conditional": list(conditional),
        "selection": "none", "portfolio_allocation_allowed": False}, indent=2) + "\n")
    rows, episodes, intervals, shocks, fits, counts, curves, primary_weights = [], [], [], [], [], [], {}, {}
    outage_baselines = {}
    for scope, p, target_book, yield_series, scenarios, periods, training in (
        ("core_history", prices, targets, cash, cfg["core_scenarios"], PERIODS, (None, cfg["core_training_end"])),
        ("conditional_events", event_prices, conditional, cash.reindex(event_prices.index), cfg["event_scenarios"], cfg["event_periods"], tuple(cfg["event_training"])),
    ):
        terminals = [r for r in meta["terminal_events"] if r["security_id"] in p and pd.Timestamp(r["settlement_session"]) in p.index]
        for scenario in scenarios:
            kwargs = dict(lag=scenario["lag"], cost_bps=scenario["cost_bps"], terminal_events=terminals)
            results = {name: replay(p, target, yield_series, **kwargs) for name, target in target_book.items()}
            eligible = [n for n in results if n.startswith("probe__")] if scope == "conditional_events" else [s["name"] for s in core_specs() if s["kind"] in {"fixed_blend", "allocator", "archived_allocator", "ablation"}]
            tb_target = targets["trade_primary"].reindex(index=p.index, columns=p.columns, fill_value=0.)
            baseline = results["trade_primary"]
            for name in eligible:
                control_target, scale, known_at = risk_control(results[name].returns, baseline.returns, tb_target, training)
                control = f"risk_match__{name}"
                results[control] = replay(p, control_target, yield_series, **kwargs)
                fits.append({"scope": scope, "candidate": name, **scenario, "trade_scale": scale,
                             "training_end": training[1], "known_at_close": str(known_at.date()), "evaluation_used": False})
            for name, result in results.items():
                rows.extend([{"scope": scope, "candidate": name, **scenario, **row,
                              "average_risky_exposure": float(result.weights.sum(axis=1).loc[periods[row['period']][0]:periods[row['period']][1]].mean())}
                             for row in period_rows(result, periods)
                             if not name.startswith("risk_match__") or (periods[row["period"]][0] is not None and pd.Timestamp(periods[row["period"]][0]) > pd.Timestamp(training[1]))])
                if scenario in ({"lag": 1, "cost_bps": 25}, {"lag": 5, "cost_bps": 50}):
                    for episode, (start, end) in EPISODES.items():
                        if (start < str(p.index[0].date()) or len(result.returns.loc[start:end]) < 21
                                or (name.startswith("risk_match__") and start <= training[1])):
                            continue
                        episodes.append({"scope": scope, "candidate": name, "episode": episode, **scenario,
                                         **metrics(result.returns.loc[start:end], result.turnover)})
                    key = f"{scope}|{name}|lag{scenario['lag']}|cost{scenario['cost_bps']}"
                    curves[key] = result.returns
                if scenario == {"lag": 1, "cost_bps": 25}:
                    if scope == "core_history" and name in cfg["outages"]["parents"]:
                        outage_baselines[name] = result.returns.copy()
                    primary_weights[f"{scope}|{name}"] = result.weights.iloc[-1].to_dict()
                    for kind in cfg["shock_types"]:
                        shocks.append({"scope": scope, "candidate": name, "shock": kind,
                                       "frozen_position_return": shock_loss(result.weights.iloc[-1], kind),
                                       "position_date": str(p.index[-1].date()), "no_modeled_response": True})
            if scenario in ({"lag": 1, "cost_bps": 25}, {"lag": 5, "cost_bps": 50}):
                for period in (("later_diagnostic", "recent_diagnostic") if scope == "core_history" else ("evaluation_2025_plus",)):
                    start, end = periods[period]
                    for reference in ("trade_primary", "risk_matched"):
                        excess = pd.DataFrame({name: np.log1p(results[name].returns.loc[start:end]) - np.log1p(results[f"risk_match__{name}" if reference == "risk_matched" else reference].returns.loc[start:end]) for name in eligible})
                        intervals.extend([r | {"scope": scope, "reference": reference, "period": period, **scenario}
                                          for r in joint_intervals(excess)])
            counts.append({"scope": scope, **scenario, "paths": len(results)})
            print(json.dumps(counts[-1]), flush=True)
    # Modeled loss of signal availability, never a fabricated observed return.
    outages = []
    for parent, start, missing in product(cfg["outages"]["parents"], cfg["outages"]["starts"], PRIMARY):
        budget = {"trade_primary": 1.} if parent == "trade_primary" else {n: (.8 if n == "trade_primary" else .1) for n in PRIMARY} if parent == "threeway_80_10_10" else dict.fromkeys(PRIMARY, 1/3)
        if missing not in budget:
            continue
        changed = dict(native)
        changed[missing] = stale_target(native[missing], start, duration=21, grace=5)
        target = mix(changed, budget, prices.index, prices.columns)
        result = replay(prices, target, cash, lag=1, cost_bps=25, terminal_events=meta["terminal_events"])
        position = prices.index.searchsorted(pd.Timestamp(start))
        end = prices.index[min(position + 63, len(prices) - 1)]
        actual = metrics(result.returns.loc[start:end], result.turnover)
        normal = metrics(outage_baselines[parent].loc[start:end])
        outages.append({"parent": parent, "missing_specialist": missing, "outage_start": start,
                        **actual, "normal_total_return": normal["total_return"],
                        "total_return_change": actual["total_return"] - normal["total_return"],
                        "normal_max_drawdown": normal["max_drawdown"],
                        "drawdown_change": actual["max_drawdown"] - normal["max_drawdown"]})
    for name, frame in (("performance", rows), ("episodes", episodes), ("uncertainty", intervals), ("frozen_position_shocks", shocks), ("development_risk_fits", fits), ("scenario_counts", counts), ("signal_outages", outages)):
        pd.DataFrame(frame).to_csv(output / f"{name}.csv", index=False)
    pd.DataFrame(curves).to_parquet(output / "returns.parquet")
    (output / "latest_executed_weights.json").write_text(json.dumps(primary_weights, indent=2) + "\n")
    (output / "event_research_summary.json").write_text(json.dumps(json.loads((Path(cfg["conditional_probes"]["path"]) / "research_summary.json").read_text()), indent=2) + "\n")
    summary = {"kind": KIND, "as_of_close": str(prices.index[-1].date()), "core_start": str(prices.index[0].date()),
        "core_registered_cases": len(targets), "conditional_registered_cases": len(conditional),
        "portfolio_paths_including_controls_and_stresses": sum(c["paths"] for c in counts),
        "operational_outage_paths": len(outages), "event_probes": len(event_targets),
        "event_admitted": False, "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False,
        "limitations": cfg["limitations"], "execution": cfg["execution"], "selection": "none"}
    if cfg["policy_hash"] != policy_hash() or cfg["runner_sha256"] != digest(Path(__file__)):
        raise ContractError("Financial source changed during stress tests")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    manifest = {"kind": KIND, "authority": "research_only", "portfolio_allocation_allowed": False,
                "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify(output)
    return summary


def verify(output):
    meta = json.loads((output / "manifest.json").read_text())
    if meta.get("kind") != KIND or meta.get("portfolio_allocation_allowed") is not False:
        raise ContractError("Stress evidence cannot authorize allocation")
    for name, expected in meta["artifacts"].items():
        bound(output, name, expected)
    return json.loads((output / "summary.json").read_text())


def publish(output, pointer):
    verify(output)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_suffix(".tmp")
    temporary.write_text(json.dumps({"report": str(output.resolve()), "manifest_sha256": digest(output / "manifest.json")}) + "\n")
    temporary.replace(pointer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "verify"))
    parser.add_argument("--bundle", type=Path, action="append", default=[])
    parser.add_argument("--conditional-events", type=Path)
    parser.add_argument("--archived-allocator", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.bundle, args.conditional_events, args.archived_allocator, args.output)
        print(json.dumps({k: result[k] for k in ("kind", "core_start", "core_end", "portfolio_allocation_allowed")}))
    else:
        result = run(args.output) if args.command == "run" else verify(args.output)
        if args.publish:
            publish(args.output, args.publish)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
