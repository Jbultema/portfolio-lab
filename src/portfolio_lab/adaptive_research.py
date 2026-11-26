"""Second-generation dynamic allocation: frozen rules, clocks and controls."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.adaptive_allocation import (
    FAMILIES,
    PRIMARY,
    allocation_controls,
    followups,
    prepare,
    route,
    specifications,
    stabilize,
    targets,
)
from portfolio_lab.combination_stress import bound, joint_intervals, shock_loss
from portfolio_lab.contracts import ContractError, digest, frame_check, load_panel
from portfolio_lab.dynamic_research import PERIODS
from portfolio_lab.dynamic_research import verify as verify_source
from portfolio_lab.engine import metrics, replay
from portfolio_lab.governance import policy_hash
from portfolio_lab.research import EPISODES

KIND = "adaptive_allocation_research_v1"
SCENARIOS = [(1, 25), (1, 10), (1, 50), (2, 25), (5, 25), (5, 50)]
COMBOS = ("union", "agreement", "online_choice", "stress_guard", "defensive_opportunity", "trend_veto")


def dependencies():
    root = Path(__file__).parent
    files = ("adaptive_allocation.py", "adaptive_research.py", "dynamic_allocation.py", "dynamic_research.py", "combination_stress.py")
    return {n: digest(root / n) for n in files}


def freeze(source, output):
    base = verify_source(source)
    original = json.loads((source / "protocol.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    cfg = {"kind": KIND, "created_at_utc": datetime.now(UTC).isoformat(), "source": str(source.resolve()),
        "source_manifest_sha256": digest(source / "manifest.json"), "inputs": original["inputs"],
        "code_sha256": dependencies(), "financial_policy_sha256": policy_hash(), "round1": specifications(),
        "scenarios": SCENARIOS, "round3_mechanisms": COMBOS,
        "selection_a": ["2012-01-01", "2015-12-31"], "selection_b": ["2016-01-01", "2018-12-31"],
        "selection_rule": "Top two families by median utility score then best member per family; only early windows used. Eight confirmation/hold/cost-gate follow-ups from 2016, six combinations from 2019.",
        "selection_score": ".5*(annual log growth + .5*DD advantage vs Trade) + .25*annual log excess capped vs same-target-exposure Trade + .25*annual log excess raw vs matched-exposure SPY-surplus control",
        "pre2019_candidate_gate": "Only first/second-round candidates available by 2016; score > .005, DD no more than .02 worse than Trade, Sharpe at least Trade. Otherwise retain Trade. No live promotion.",
        "model_label_clock": "Five-session expert log excess s+2 through s+6 after next-close fill; at close t only training rows s<=t-6 are allowed. Refit monthly on last 756 rows, minimum 252 finite rows; transformations fit only on each training window.",
        "execution_clock": "Features may use current completed close, never future closes; target executes at next/second/fifth close; P&L starts after fill. Shadow feature outcomes fixed at next-close/25bps when execution is stressed.",
        "idle_cash": "Keep Trade's risky positions, add up to share of unused cash in a qualifying native specialist; native expert coefficient at most 1, all risky asset weights total at most 1. Notional expert multipliers may sum above 1; this is not borrowing. Daily safety projection cannot be blocked by dwell or cost gate.",
        "matched_spy": "Match candidate close-known gross invested target: scale Trade down when lower, or add the same extra investment to SPY when higher, including when Trade has zero risky target. Not exact beta or realized-exposure matching.",
        "hypotheses": list(FAMILIES), "future_dates_used_for_selection": False,
        "limitations": base["limitations"] + ["current_holdings_features_use_modern_selected_universe",
            "single_and_two_factor_alpha_estimates_are_noisy", "SPY_surplus_control_matches_target_gross_not_beta",
            "online_labels_overlap_uncertainty_inflated_but_not_independent", "idle_cash_overrides_Trade_portfolio_level_risk_budget; not_approved_for_live_use"],
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    (output / "protocol.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (output / "protocol.sha256").write_text(digest(output / "protocol.json") + "\n")
    return {"kind": KIND, "initial_candidates": 32, "maximum_candidates": 46, "execution_cases": len(SCENARIOS)}


def score_policy(results, name, window):
    start, end = window
    slices = {role: results[name, role].loc[start:end] for role in ("raw", "capped", "matched_trade", "matched_spy")}
    reference = results["trade_primary", "raw"].loc[start:end]
    m, b = metrics(slices["raw"]), metrics(reference)
    def log(r):
        return np.log1p(r).mean() * 252
    utility = log(slices["raw"]) - log(reference) + .5 * (m["max_drawdown"] - b["max_drawdown"])
    score = .5 * utility + .25 * (log(slices["capped"]) - log(slices["matched_trade"])) + .25 * (log(slices["raw"]) - log(slices["matched_spy"]))
    return {"name": name, "score": float(score), "cagr": m["cagr"], "max_drawdown": m["max_drawdown"],
            "sharpe": m["sharpe"], "trade_max_drawdown": b["max_drawdown"], "trade_sharpe": b["sharpe"]}


def select(specs, results, window):
    rows = [score_policy(results, s["name"], window) | {"family": s["family"]} for s in specs if s["available_from"] <= window[0]]
    frame = pd.DataFrame(rows)
    if frame.empty or frame.family.nunique() < 2:
        raise ContractError("Selection needs two eligible early-history families")
    medians = frame.groupby("family").score.median().sort_values(ascending=False)
    parents = []
    for family in medians.index[:2]:
        name = frame[frame.family.eq(family)].sort_values(["score", "name"], ascending=[False, True]).iloc[0]["name"]
        parents.append(next(s for s in specs if s["name"] == name))
    admitted = frame[(frame.score > .005) & (frame.max_drawdown >= frame.trade_max_drawdown - .02) & (frame.sharpe >= frame.trade_sharpe)]
    candidate = "trade_primary" if admitted.empty else admitted.sort_values(["score", "name"], ascending=[False, True]).iloc[0]["name"]
    return parents, {"window": window, "family_scores": medians.to_dict(), "members": rows,
        "selected": [p["name"] for p in parents], "gated_research_candidate": candidate, "later_outcomes_used": False}


def combine(a, b, data, returns_a, returns_b, reference, mechanism):
    proposal = (a + b) / 2
    context = data["context"]
    if mechanism == "agreement":
        same = a.iloc[:, 1:].idxmax(axis=1).eq(b.iloc[:, 1:].idxmax(axis=1))
        active = a.iloc[:, 1:].sum(axis=1).gt(0) & b.iloc[:, 1:].sum(axis=1).gt(0)
        proposal.loc[~(same & active)] = [1., 0., 0.]
    elif mechanism == "online_choice":
        ra, rb = np.log1p(returns_a).rolling(63).mean(), np.log1p(returns_b).rolling(63).mean()
        base = np.log1p(reference).rolling(63).mean()
        proposal[:] = [1., 0., 0.]
        for mask, frame in ((ra.gt(rb) & ra.gt(base), a), (rb.ge(ra) & rb.gt(base), b)):
            proposal.loc[mask] = frame.loc[mask]
    elif mechanism == "stress_guard":
        proposal = proposal.mul(1 - .5 * context.pressure.fillna(0), axis=0)
    elif mechanism == "defensive_opportunity":
        valid = data["exposures"].trade_primary.lt(.65) & context.trend126.gt(0) & context.breadth21.ge(5 / 9)
        proposal.loc[~valid] = [1., 0., 0.]
    elif mechanism == "trend_veto":
        proposal.loc[~context.trend126.gt(0)] = [1., 0., 0.]
    elif mechanism != "union":
        raise ContractError("Unknown adaptive combination")
    spec = {"cadence": "daily", "confirm": 3, "hold": 10, "cost_gate": False}
    return stabilize(proposal, data["native"], pd.Series(.05, index=proposal.index), spec)


def run(output):
    if (output / "registry.json").exists():
        raise FileExistsError("Measured outputs are immutable")
    cfg = json.loads((output / "protocol.json").read_text())
    if (digest(output / "protocol.json") != (output / "protocol.sha256").read_text().strip()
            or cfg["code_sha256"] != dependencies() or cfg["financial_policy_sha256"] != policy_hash()):
        raise ContractError("Frozen adaptive protocol or code changed")
    source = Path(cfg["source"])
    verify_source(source)
    if digest(source / "manifest.json") != cfg["source_manifest_sha256"]:
        raise ContractError("Frozen source changed")
    for item in cfg["inputs"]:
        if digest(Path(item["path"]) / "manifest.json") != item["manifest_sha256"]:
            raise ContractError("Captured input changed")
    prices, native, cash, meta = load_panel([Path(item["path"]) for item in cfg["inputs"][:3]])
    native = {n: t.reindex(columns=prices.columns, fill_value=0.) for n, t in native.items() if n in PRIMARY}
    shadow = pd.DataFrame({n: replay(prices, native[n], cash, lag=1, cost_bps=25, terminal_events=meta["terminal_events"]).returns for n in PRIMARY})
    data = prepare(prices, native, cash, shadow)
    specs, coefficients, books, results, curves = [], {}, {}, {}, {}
    rows, episodes, counts, shocks = [], [], [], []
    core_start = str(prices.index[0].date())
    baseline = {n: native[n] for n in PRIMARY}
    baseline["trade_cash_90"] = native["trade_primary"] * .9
    for ticker in ("SPY", "QQQ"):
        baseline[f"buy_hold_{ticker}"] = native["trade_primary"] * 0.
        baseline[f"buy_hold_{ticker}"][ticker] = 1.
    old = pd.read_parquet(source / "budgets.parquet")["r3_defensive_union"]
    baseline["previous_defensive_combo"] = sum(native[n].mul(old[n], axis=0) for n in PRIMARY)
    baseline["previous_defensive_cash"] = native["trade_primary"].mul(old.trade_primary, axis=0)

    def measure(name, role, target, lag, cost, spec):
        result = replay(prices, target, cash, lag=lag, cost_bps=cost, terminal_events=meta["terminal_events"])
        known = spec["available_from"]
        for period, (start, end) in PERIODS.items():
            if (start or core_start) < known:
                continue
            r = result.returns.loc[start:end]
            if len(r) >= 21:
                rows.append({"scope": "core", "candidate": name, "role": role, "round": spec["round"], "period": period,
                    "lag": lag, "cost_bps": cost, **metrics(r, result.turnover),
                    "average_risky_exposure": float(result.weights.sum(axis=1).loc[r.index].mean())})
        if (lag, cost) in {(1, 25), (5, 50)}:
            for episode, (start, end) in EPISODES.items():
                r = result.returns.loc[start:end]
                if start >= max(core_start, known) and len(r) >= 21:
                    episodes.append({"scope": "core", "candidate": name, "role": role, "episode": episode,
                        "lag": lag, "cost_bps": cost, **metrics(r, result.turnover)})
        if (lag, cost) == (1, 25):
            for shock in ("ai_gap35", "ai_gap60", "broad_gap20", "liquidity_gap"):
                shocks.append({"scope": "core", "candidate": name, "role": role, "shock": shock,
                    "position_date": str(prices.index[-1].date()), "no_modeled_response": True,
                    "frozen_position_return": shock_loss(result.weights.iloc[-1], shock)})
        curves[f"core|{name}|{role}|lag{lag}|cost{cost}"] = result.returns
        counts.append({"candidate": name, "role": role, "lag": lag, "cost_bps": cost})
        return result.returns

    def evaluate(spec, lag=1, cost=25):
        name = spec["name"]
        book = allocation_controls(books[name], coefficients[name], native)
        for role, target in book.items():
            r = measure(name, role, target, lag, cost, spec)
            if (lag, cost) == (1, 25):
                results[name, role] = r

    for name, target in baseline.items():
        reference_spec = {"available_from": "2019-01-01" if name.startswith("previous_") else core_start, "round": 0}
        results[name, "raw"] = measure(name, "raw", target, 1, 25, reference_spec)
    for spec in cfg["round1"]:
        allocation = route(data, spec)
        coefficients[spec["name"]], books[spec["name"]] = allocation, targets(native, allocation)
        specs.append(spec)
        evaluate(spec)
    parents, first = select(specs, results, cfg["selection_a"])
    (output / "selection_a.json").write_text(json.dumps(first, indent=2) + "\n")
    print(json.dumps({"round": 1, "candidates": len(specs), "selected_on_early_window": first["selected"], "gated_candidate": first["gated_research_candidate"]}), flush=True)
    for parent in parents:
        for spec in followups(parent):
            allocation = route(data, spec)
            coefficients[spec["name"]], books[spec["name"]] = allocation, targets(native, allocation)
            specs.append(spec)
            evaluate(spec)
    parents, second = select(specs, results, cfg["selection_b"])
    (output / "selection_b.json").write_text(json.dumps(second, indent=2) + "\n")
    print(json.dumps({"round": 2, "candidates": len(specs), "selected_on_early_window": second["selected"], "gated_candidate": second["gated_research_candidate"]}), flush=True)
    for mechanism in cfg["round3_mechanisms"]:
        a, b = parents
        spec = {"name": f"r3_{mechanism}", "family": "combination", "mechanism": mechanism, "round": 3,
                "available_from": "2019-01-01", "parents": [a["name"], b["name"]]}
        allocation = combine(coefficients[a["name"]], coefficients[b["name"]], data,
                             results[a["name"], "raw"], results[b["name"], "raw"], shadow.trade_primary, mechanism)
        allocation.loc[allocation.index < "2019-01-01"] = [1., 0., 0.]
        coefficients[spec["name"]], books[spec["name"]] = allocation, targets(native, allocation)
        specs.append(spec)
        evaluate(spec)
    (output / "registry.json").write_text(json.dumps({"core": specs, "portfolio_allocation_allowed": False}, indent=2) + "\n")
    (output / "event_registry.json").write_text("[]\n")
    for lag, cost in SCENARIOS[1:]:
        for name, target in baseline.items():
            measure(name, "raw", target, lag, cost, {"round": 0, "available_from": "2019-01-01" if name.startswith("previous_") else core_start})
        for spec in specs:
            evaluate(spec, lag, cost)
        print(json.dumps({"execution": {"lag": lag, "cost_bps": cost}, "candidates": len(specs)}), flush=True)
    intervals = []
    for lag, cost in ((1, 25), (5, 50)):
        for reference, role, reference_role in (("trade_primary", "raw", "raw"), ("same_exposure", "capped", "matched_trade"),
                                              ("cash_ablation", "raw", "cash_ablation"), ("SPY_surplus", "raw", "matched_spy")):
            excess = {}
            for spec in specs:
                name = spec["name"]
                a = curves[f"core|{name}|{role}|lag{lag}|cost{cost}"].loc["2019-01-01":]
                b = curves[f"core|{'trade_primary' if reference == 'trade_primary' else name}|{reference_role}|lag{lag}|cost{cost}"].loc[a.index]
                excess[name] = np.log1p(a).sub(np.log1p(b))
            for block in (21, 63, 126):
                intervals.extend([row | {"scope": "core", "reference": reference, "period": "post_selection_2019_plus", "lag": lag, "cost_bps": cost}
                                  for row in joint_intervals(pd.DataFrame(excess), block=block)])
    switches, exposure_rows = [], []
    for spec in specs:
        name = spec["name"]
        active = coefficients[name].loc[spec["available_from"]:]
        switches.append({"candidate": name, "round": spec["round"],
            "annual_switches": float(active.diff().abs().sum(axis=1).gt(1e-9).mean() * 252),
            "fraction_sessions_with_alternative": float(active.iloc[:, 1:].sum(axis=1).gt(1e-9).mean()),
            **{f"mean_multiplier_{n}": float(active[n].mean()) for n in PRIMARY}})
        exposure_rows.append({"candidate": name, "fraction_target_exposure_above_Trade": float(books[name].loc[active.index].sum(axis=1).gt(native["trade_primary"].loc[active.index].sum(axis=1) + 1e-9).mean())})
    contributions = {n: coefficients[n] * data["exposures"] for n in coefficients}
    for frame in contributions.values():
        frame_check(frame, weights=True)
    pd.concat(contributions, axis=1).to_parquet(output / "budgets.parquet")
    pd.concat(coefficients, axis=1).to_parquet(output / "coefficients.parquet")
    pd.DataFrame(curves).to_parquet(output / "returns.parquet")
    for filename, records in (("performance", rows), ("episodes", episodes), ("uncertainty", intervals), ("switching", switches),
                              ("exposure_audit", exposure_rows), ("frozen_shocks", shocks), ("executed_paths", counts), ("model_fit_audit", data["fit_logs"])):
        pd.DataFrame(records).to_csv(output / f"{filename}.csv", index=False)
    summary = {"kind": KIND, "as_of_close": str(prices.index[-1].date()), "core_start": core_start, "core_candidates": len(specs),
        "conditional_candidates": 0, "rounds": 3, "portfolio_paths_including_controls_and_stresses": len(counts),
        "scenarios": SCENARIOS, "budget_semantics": "risky_asset_contributions", "gated_pre2019_research_candidate": second["gated_research_candidate"],
        "source_manifest_sha256": cfg["source_manifest_sha256"], "online_fit_count": len(data["fit_logs"]),
        "all_online_labels_mature": all(row["no_future_label"] for row in data["fit_logs"]),
        "limitations": cfg["limitations"], "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    if cfg["code_sha256"] != dependencies() or cfg["financial_policy_sha256"] != policy_hash():
        raise ContractError("Financial source changed during research")
    verify_source(source)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"kind": KIND, "authority": "research_only", "portfolio_allocation_allowed": False,
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    verify(output)
    return summary


def verify(root):
    meta = json.loads((root / "manifest.json").read_text())
    required = {"protocol.json", "protocol.sha256", "registry.json", "summary.json", "performance.csv", "returns.parquet", "model_fit_audit.csv", "coefficients.parquet"}
    if (meta.get("kind") != KIND or meta.get("authority") != "research_only" or meta.get("portfolio_allocation_allowed") is not False
            or not required <= meta["artifacts"].keys()):
        raise ContractError("Incomplete or unauthorized adaptive research")
    for name, identity in meta["artifacts"].items():
        bound(root, name, identity)
    summary = json.loads((root / "summary.json").read_text())
    if summary.get("all_online_labels_mature") is not True or summary.get("portfolio_allocation_allowed") is not False:
        raise ContractError("Adaptive label maturity or authority check failed")
    return summary


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
