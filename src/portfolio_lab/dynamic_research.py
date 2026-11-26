"""Frozen multi-round dynamic-allocation research on captured specialist exports."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.audit import audit
from portfolio_lab.combination_stress import (
    add_probe_prices,
    bound,
    joint_intervals,
    load_probes,
    shock_loss,
)
from portfolio_lab.combination_stress import (
    verify as verify_source,
)
from portfolio_lab.contracts import ContractError, digest, load_panel
from portfolio_lab.dynamic_allocation import (
    PRIMARY,
    combine,
    consolidate,
    exposure_controls,
    features,
    followups,
    route,
    specifications,
    stabilize,
)
from portfolio_lab.engine import metrics, replay
from portfolio_lab.governance import policy_hash
from portfolio_lab.research import EPISODES

KIND = "dynamic_specialist_research_v1"
PERIODS = {"development": (None, "2011-12-31"), "selection_a": ("2012-01-01", "2015-12-31"),
           "selection_b": ("2016-01-01", "2018-12-31"), "diagnostic_2019_2023": ("2019-01-01", "2023-12-31"),
           "recent_2024_plus": ("2024-01-01", None), "current_transition": ("2026-06-01", None),
           "post_selection_2019_plus": ("2019-01-01", None), "full": (None, None)}
EVENT_PERIODS = {"development": ("2023-01-03", "2024-06-28"), "evaluation_2025_plus": ("2025-01-02", None),
                 "current_transition": ("2026-06-01", None)}
SCENARIOS = [(1, 25), (1, 10), (5, 50)]
COMBINATIONS = ("union", "intersection", "stress_context", "online63", "online126", "defensive_union")


def code_hashes():
    root = Path(__file__).parent
    return {name: digest(root / name) for name in ("dynamic_allocation.py", "dynamic_research.py", "combination_stress.py")}


def freeze(source, output):
    summary = verify_source(source)
    original = json.loads((source / "protocol.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    protocol = {"kind": KIND, "created_at_utc": datetime.now(UTC).isoformat(), "source": str(source.resolve()),
        "source_manifest_sha256": digest(source / "manifest.json"), "inputs": original["core_bundles"] + [original["conditional_probes"], original["archived_allocator"]],
        "code_sha256": code_hashes(), "financial_policy_sha256": policy_hash(), "round1": specifications(),
        "round2": "Top two families by median selection_a score, best member per family; 3/5-session confirmation x daily/weekly cadence; 10-session minimum hold. Available in simulation from 2016 only.",
        "round3": "Top two distinct families by median selection_b score; six predefined combinations. Available from 2019 only.",
        "round3_mechanisms": list(COMBINATIONS),
        "selection_score": "Half of annual-log-growth-plus-half-DD utility advantage vs Trade; half of annual log excess of Trade-exposure-capped candidate vs exact same-exposure Trade. No post-2018 outcomes select families or parents.",
        "selection_a": ["2012-01-01", "2015-12-31"], "selection_b": ["2016-01-01", "2018-12-31"],
        "scenarios": SCENARIOS, "feature_clock": "Native child shadow outcomes at next close and 25bps; routing features and outcomes through prior completed close; final execution delay applied once to combined close-known targets.",
        "controls": ["unchanged Trade Bot", "same proposed Trade budget with alternative budget in cash",
                     "candidate capped to Trade native invested exposure", "exact same-exposure Trade control",
                     "event-free price-only ablation for conditional event rules"],
        "event_probes": ["event__executed_net_common_repurchase_h126_event_only",
                         "structural__working_capital_repair_h126", "structural__liquidity_repair_h126"],
        "event_families": ["gated_event_sleeve", "event_conditioned_router"], "event_budgets": [.25, .50],
        "event_selection": "none; 12 fixed conditional probes, no promotion or full-history claims",
        "source_as_of_close": summary["as_of_close"],
        "limitations": summary["limitations"] + ["historical_periods_previously_inspected_not_pristine_holdouts",
            "family_selection_is_retrospective_research_not_historical_live_deployment",
            "no_official_macro_event_release_history_added", "accounting_activity_is_probe_target_activity_not_a_complete_news_event_tape",
            "native_internal_risk_controls_remain_but_raw_router_can_raise_aggregate_exposure_vs_Trade; capped_control_reported"],
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    (output / "protocol.sha256").write_text(digest(output / "protocol.json") + "\n")
    return {"kind": KIND, "round1": 36, "maximum_core_candidates": 50, "conditional_candidates": 12}


def utility(returns):
    m = metrics(returns)
    return float(np.log1p(returns).mean() * 252 + .5 * m["max_drawdown"])


def select_parents(specs, results, window):
    start, end = window
    trade = results["trade_primary", "raw"].loc[start:end]
    rows = []
    for spec in specs:
        raw = results[spec["name"], "raw"].loc[start:end]
        capped = results[spec["name"], "capped"].loc[start:end]
        matched = results[spec["name"], "matched_trade"].loc[start:end]
        if len(raw) < 252 or raw.index[0] < pd.Timestamp(spec["available_from"]):
            continue
        score = .5 * (utility(raw) - utility(trade)) + .5 * (np.log1p(capped).sub(np.log1p(matched)).mean() * 252)
        rows.append({"name": spec["name"], "family": spec["family"], "score": float(score)})
    ranking = pd.DataFrame(rows)
    if ranking.empty or ranking.family.nunique() < 2:
        raise ContractError("Two eligible historical families are required for follow-ups")
    family_scores = ranking.groupby("family").score.median().sort_values(ascending=False)
    selected = []
    for family in family_scores.index[:2]:
        best = ranking[ranking.family.eq(family)].sort_values(["score", "name"], ascending=[False, True]).iloc[0]["name"]
        selected.append(next(s for s in specs if s["name"] == best))
    return selected, {"window": window, "family_scores": family_scores.to_dict(), "members": rows,
                      "selected": [s["name"] for s in selected], "later_outcomes_used": False}


def availability(budgets, start):
    out = budgets.copy()
    out.loc[out.index < start] = 0.
    out.loc[out.index < start, "trade_primary"] = 1.
    return out


def event_rule(spec, probe, basket, shadow, basket_shadow, trade_returns, context, *, without_events=False):
    index = context.index
    budgets = pd.DataFrame(0., index=index, columns=[*PRIMARY, "event_probe"])
    budgets.trade_primary = 1.
    horizon = 63
    if spec["family"] == "gated_event_sleeve":
        reference = basket_shadow if without_events else shadow
        strength = np.log1p(reference).sub(np.log1p(trade_returns)).shift(1).rolling(horizon).mean() * 252
        active = (basket if without_events else probe).sum(axis=1).shift(1)
        enabled = strength.gt(.02) & active.ge(.2)
        budgets.loc[enabled, "trade_primary"] = 1 - spec["max_alternative"]
        budgets.loc[enabled, "event_probe"] = spec["max_alternative"]
    else:
        activity = probe.sum(axis=1).shift(1)
        enabled = activity.gt(activity.rolling(126, min_periods=126).mean() + .05)
        if without_events:
            enabled[:] = True
        rotate = enabled & context.leadership_short.gt(.02) & context.breadth_short.ge(5 / 9)
        rebound = enabled & ~rotate & context.dd63.lt(-.05) & context.return5.gt(.01) & context.above10.eq(True)
        for condition, name in ((rotate, "rotation_primary"), (rebound, "swing_primary")):
            budgets.loc[condition, "trade_primary"] = 1 - spec["max_alternative"]
            budgets.loc[condition, name] = spec["max_alternative"]
    return availability(stabilize(budgets, confirm=3, minimum_hold=10, cadence="weekly"), "2023-01-03")


def run(output):
    if (output / "registry.json").exists():
        raise FileExistsError("Measured research outputs are immutable; use a fresh directory")
    cfg = json.loads((output / "protocol.json").read_text())
    if (digest(output / "protocol.json") != (output / "protocol.sha256").read_text().strip()
            or cfg["code_sha256"] != code_hashes() or cfg["financial_policy_sha256"] != policy_hash()):
        raise ContractError("Frozen protocol or code changed")
    source = Path(cfg["source"])
    if digest(source / "manifest.json") != cfg["source_manifest_sha256"]:
        raise ContractError("Source study changed")
    verify_source(source)
    original = json.loads((source / "protocol.json").read_text())
    for item in cfg["inputs"]:
        if digest(Path(item["path"]) / "manifest.json") != item["manifest_sha256"]:
            raise ContractError("Captured input manifest changed")
    prices, native, cash, metadata = load_panel([Path(p["path"]) for p in original["core_bundles"]])
    native = {n: t.reindex(columns=prices.columns, fill_value=0.) for n, t in native.items()}
    context = features(prices)
    shadow = pd.DataFrame({n: replay(prices, native[n], cash, lag=1, cost_bps=25, terminal_events=metadata["terminal_events"]).returns for n in PRIMARY})
    specs, budgets, targets, results, metrics_rows, episodes, curves, counts, switches, exposures, shocks = [], {}, {}, {}, [], [], {}, [], [], [], []
    start_date = str(prices.index[0].date())
    baseline_targets = {n: native[n] for n in PRIMARY}
    archived = Path(original["archived_allocator"]["path"])
    if audit(archived)["errors"]:
        raise ContractError("Archived allocator failed its native evidence audit")
    baseline_targets["portfolio_lab_frozen"] = pd.read_parquet(archived / "selected_targets.parquet").reindex(index=prices.index, columns=prices.columns, fill_value=0.)
    baseline_targets.update({f"trade_cash_{share}": native["trade_primary"] * share / 100 for share in (75, 90)})
    for ticker in ("SPY", "QQQ"):
        t = prices * 0.
        t[:] = 0.
        t[ticker] = 1.
        baseline_targets[f"buy_hold_{ticker}"] = t

    def execute(scope, name, role, target, p, yields, periods, known_from, lag=1, cost=25, round_number=0):
        terminal = [t for t in metadata["terminal_events"] if t["security_id"] in p and pd.Timestamp(t["settlement_session"]) in p.index]
        result = replay(p, target, yields, lag=lag, cost_bps=cost, terminal_events=terminal)
        for period, (left, right) in periods.items():
            effective_start = pd.Timestamp(left) if left is not None else p.index[0]
            if effective_start < pd.Timestamp(known_from):
                continue
            selected = result.returns.loc[left:right]
            if len(selected) >= 21:
                metrics_rows.append({"scope": scope, "candidate": name, "role": role, "round": round_number,
                    "period": period, "lag": lag, "cost_bps": cost, **metrics(selected, result.turnover),
                    "average_risky_exposure": float(result.weights.sum(axis=1).loc[selected.index].mean())})
        if (lag, cost) in {(1, 25), (5, 50)}:
            for episode, (left, right) in EPISODES.items():
                r = result.returns.loc[left:right]
                if pd.Timestamp(left) >= max(p.index[0], pd.Timestamp(known_from)) and len(r) >= 21:
                    episodes.append({"scope": scope, "candidate": name, "role": role, "episode": episode,
                        "lag": lag, "cost_bps": cost, **metrics(r, result.turnover)})
        key = f"{scope}|{name}|{role}|lag{lag}|cost{cost}"
        curves[key] = result.returns
        if lag == 1 and cost == 25:
            for shock in ("broad_gap20", "ai_gap35", "ai_gap60", "liquidity_gap"):
                shocks.append({"scope": scope, "candidate": name, "role": role, "shock": shock,
                               "position_date": str(p.index[-1].date()), "no_modeled_response": True,
                               "frozen_position_return": shock_loss(result.weights.iloc[-1], shock)})
        counts.append({"scope": scope, "candidate": name, "role": role, "lag": lag, "cost_bps": cost})
        return result.returns

    def evaluate_core(spec, budget, lag=1, cost=25):
        name = spec["name"]
        target = targets[name]
        capped, matched = exposure_controls(target, native["trade_primary"])
        book = {"raw": target, "cash_ablation": native["trade_primary"].mul(budget.trade_primary, axis=0),
                "capped": capped, "matched_trade": matched}
        for role, frame in book.items():
            r = execute("core", name, role, frame, prices, cash, PERIODS, spec["available_from"], lag, cost, spec["round"])
            if lag == 1 and cost == 25:
                results[name, role] = r

    for name, target in baseline_targets.items():
        results[name, "raw"] = execute("core", name, "raw", target, prices, cash, PERIODS, start_date)
    for spec in cfg["round1"]:
        spec = spec | {"available_from": start_date}
        b = route(shadow, cash, context, spec)
        budgets[spec["name"]], targets[spec["name"]] = b, consolidate(native, b, prices)
        specs.append(spec)
        evaluate_core(spec, b)
    parents, selection_a = select_parents(specs, results, cfg["selection_a"])
    (output / "selection_a.json").write_text(json.dumps(selection_a, indent=2) + "\n")
    print(json.dumps({"round": 1, "candidates": len(specs), "selected_on_2012_2015_only": selection_a["selected"]}), flush=True)
    for parent in parents:
        for spec in followups(parent):
            spec = spec | {"available_from": "2016-01-01"}
            b = availability(route(shadow, cash, context, spec), spec["available_from"])
            budgets[spec["name"]], targets[spec["name"]] = b, consolidate(native, b, prices)
            specs.append(spec)
            evaluate_core(spec, b)
    parents, selection_b = select_parents(specs, results, cfg["selection_b"])
    (output / "selection_b.json").write_text(json.dumps(selection_b, indent=2) + "\n")
    print(json.dumps({"round": 2, "candidates": len(specs), "selected_on_2016_2018_only": selection_b["selected"]}), flush=True)
    for mechanism in cfg["round3_mechanisms"]:
        a, b = parents
        spec = {"name": f"r3_{mechanism}", "family": "combination", "round": 3, "mechanism": mechanism,
                "parents": [a["name"], b["name"]], "available_from": "2019-01-01"}
        allocation = combine(budgets[a["name"]], budgets[b["name"]], context,
                             results[a["name"], "raw"], results[b["name"], "raw"], shadow.trade_primary, mechanism)
        allocation = availability(allocation, spec["available_from"])
        budgets[spec["name"]], targets[spec["name"]] = allocation, consolidate(native, allocation, prices)
        specs.append(spec)
        evaluate_core(spec, allocation)
    (output / "registry.json").write_text(json.dumps({"core": specs, "conditional_events": cfg["event_probes"],
        "selection_uses_only_through_2018": True, "portfolio_allocation_allowed": False}, indent=2) + "\n")
    for lag, cost in SCENARIOS[1:]:
        for name, target in baseline_targets.items():
            execute("core", name, "raw", target, prices, cash, PERIODS, start_date, lag, cost)
        for spec in specs:
            evaluate_core(spec, budgets[spec["name"]], lag, cost)
        print(json.dumps({"core_execution": {"lag": lag, "cost_bps": cost}, "core_candidates": len(specs)}), flush=True)
    event_prices, event_targets, _ = load_probes(Path(original["conditional_probes"]["path"]))
    ep, _ = add_probe_prices(prices, event_prices)
    ecash, econtext = cash.loc[ep.index], context.loc[ep.index]
    enative = {n: native[n].reindex(index=ep.index, columns=ep.columns, fill_value=0.) for n in PRIMARY}
    etrade = replay(ep, enative["trade_primary"], ecash, cost_bps=25).returns
    event_specs, event_books, event_budgets, event_ablations = [], {}, {}, {}
    for probe in cfg["event_probes"]:
        target = event_targets[probe].reindex(index=ep.index, columns=ep.columns, fill_value=0.)
        basket = ep * 0.
        basket[:] = 0.
        for ticker in event_prices:
            basket[ticker] = .1 if not (probe.startswith("structural") and ticker == "JPM") else 0.
        er = replay(ep, target, ecash, cost_bps=25).returns
        br = replay(ep, basket, ecash, cost_bps=25).returns
        for family in cfg["event_families"]:
            for share in cfg["event_budgets"]:
                spec = {"name": f"{family}__{int(100 * share)}__{probe}", "family": family, "probe": probe,
                        "max_alternative": share, "available_from": "2023-01-03", "round": 1}
                n = spec["name"]
                b = event_rule(spec, target, basket, er, br, etrade, econtext)
                ab = event_rule(spec, target, basket, er, br, etrade, econtext, without_events=True)
                event_books[n] = consolidate(enative | {"event_probe": target}, b, ep)
                event_ablations[n] = consolidate(enative | {"event_probe": basket}, ab, ep)
                event_budgets[n] = b
                event_specs.append(spec)
    (output / "event_registry.json").write_text(json.dumps(event_specs, indent=2) + "\n")
    for lag, cost in SCENARIOS:
        execute("conditional_events", "trade_primary", "raw", enative["trade_primary"], ep, ecash, EVENT_PERIODS, "2023-01-03", lag, cost)
        for spec in event_specs:
            name = spec["name"]
            capped, matched = exposure_controls(event_books[name], enative["trade_primary"])
            book = {"raw": event_books[name], "cash_ablation": enative["trade_primary"].mul(event_budgets[name].trade_primary, axis=0),
                    "capped": capped, "matched_trade": matched, "no_event_ablation": event_ablations[name]}
            for role, target in book.items():
                execute("conditional_events", name, role, target, ep, ecash, EVENT_PERIODS, "2023-01-03", lag, cost)
        print(json.dumps({"conditional_execution": {"lag": lag, "cost_bps": cost}, "conditional_candidates": len(event_specs)}), flush=True)
    for name, budget in budgets.items():
        spec = next(s for s in specs if s["name"] == name)
        active = budget.loc[spec["available_from"]:]
        changes = active.diff().abs().sum(axis=1).gt(1e-10)
        switches.append({"candidate": name, "round": spec["round"], "switches": int(changes.sum()),
                         "annual_switches": float(changes.mean() * 252),
                         "alternative_budget_fraction_sessions": float(active[list(PRIMARY)[1:]].sum(axis=1).gt(1e-10).mean()),
                         **{f"mean_{n}": float(active[n].mean()) for n in PRIMARY}})
        exposures.append({"candidate": name, "fraction_target_exposure_above_Trade": float(targets[name].sum(axis=1).loc[active.index].gt(native["trade_primary"].sum(axis=1).loc[active.index] + 1e-9).mean())})
    intervals = []
    for scope, candidates, period, left in (("core", [s["name"] for s in specs], "post_selection_2019_plus", "2019-01-01"),
                                           ("conditional_events", [s["name"] for s in event_specs], "evaluation_2025_plus", "2025-01-02")):
        for lag, cost in ((1, 25), (5, 50)):
            references = [("trade_primary", "raw", "raw"), ("same_exposure", "capped", "matched_trade"), ("cash_ablation", "raw", "cash_ablation")]
            if scope == "conditional_events":
                references.append(("no_event_ablation", "raw", "no_event_ablation"))
            for reference, candidate_role, reference_role in references:
                differences = {}
                for name in candidates:
                    a = curves[f"{scope}|{name}|{candidate_role}|lag{lag}|cost{cost}"].loc[left:]
                    other = "trade_primary" if reference == "trade_primary" else name
                    b = curves[f"{scope}|{other}|{reference_role}|lag{lag}|cost{cost}"].loc[a.index]
                    differences[name] = np.log1p(a).sub(np.log1p(b))
                for block in (21, 63, 126):
                    intervals.extend([r | {"scope": scope, "period": period, "reference": reference, "lag": lag, "cost_bps": cost}
                                      for r in joint_intervals(pd.DataFrame(differences), block=block)])
    for name, rows in (("performance", metrics_rows), ("episodes", episodes), ("uncertainty", intervals),
                       ("switching", switches), ("exposure_audit", exposures), ("frozen_shocks", shocks), ("executed_paths", counts)):
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    pd.DataFrame(curves).to_parquet(output / "returns.parquet")
    pd.concat(budgets, axis=1).to_parquet(output / "budgets.parquet")
    pd.concat(event_budgets, axis=1).to_parquet(output / "event_budgets.parquet")
    summary = {"kind": KIND, "as_of_close": str(prices.index[-1].date()), "core_start": start_date,
        "core_candidates": len(specs), "rounds": 3, "conditional_candidates": len(event_specs),
        "portfolio_paths_including_controls_and_stresses": len(counts), "source_manifest_sha256": cfg["source_manifest_sha256"],
        "family_followups": selection_a["selected"], "combination_parents": selection_b["selected"],
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False, "limitations": cfg["limitations"]}
    if cfg["code_sha256"] != code_hashes() or cfg["financial_policy_sha256"] != policy_hash():
        raise ContractError("Financial code changed during measurement")
    verify_source(source)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"kind": KIND, "authority": "research_only", "portfolio_allocation_allowed": False,
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    verify(output)
    return summary


def verify(root):
    meta = json.loads((root / "manifest.json").read_text())
    required = {"protocol.json", "protocol.sha256", "registry.json", "event_registry.json", "summary.json", "performance.csv", "returns.parquet", "budgets.parquet"}
    if (meta.get("kind") != KIND or meta.get("authority") != "research_only"
            or meta.get("portfolio_allocation_allowed") is not False or not required <= meta["artifacts"].keys()):
        raise ContractError("Incomplete or unauthorized dynamic research evidence")
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
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
