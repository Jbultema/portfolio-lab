from __future__ import annotations

import itertools
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.allocation import Policy, allocate, consolidate, followups, policies, regimes
from portfolio_lab.contracts import digest, load_panel
from portfolio_lab.engine import Result, metrics, replay

PERIODS = {
    "development": (None, "2011-12-31"),
    "validation": ("2012-01-01", "2018-12-31"),
    "later_diagnostic": ("2019-01-01", "2023-12-31"),
    "recent_diagnostic": ("2024-01-01", None),
    "current_transition": ("2026-06-01", None),
    "full": (None, None),
}
EPISODES = {
    "gfc": ("2007-07-01", "2009-06-30"),
    "euro": ("2011-04-01", "2012-03-31"),
    "china_oil": ("2015-06-01", "2016-06-30"),
    "q4_2018": ("2018-09-01", "2019-03-31"),
    "covid": ("2020-02-01", "2020-08-31"),
    "rates": ("2022-01-01", "2023-06-30"),
    "2025": ("2025-02-01", "2025-08-31"),
    "current_unfinished": ("2026-06-01", None),
}


def measure(name: str, family: str, result: Result) -> list[dict]:
    return [
        {
            "candidate": name,
            "family": family,
            "period": period,
            **metrics(result.returns.loc[start:end], result.turnover),
        }
        for period, (start, end) in PERIODS.items()
        if len(result.returns.loc[start:end].dropna()) > 20
    ]


def choose(rows: list[dict], names: list[str]) -> str:
    frame = pd.DataFrame(rows)
    frame = frame[frame.candidate.isin(names) & frame.period.isin(["development", "validation"])]
    scores = []
    for name, group in frame.groupby("candidate"):
        if len(group) == 2:
            utility = (
                group.sharpe + 2 * group.max_drawdown + group.cagr - 0.002 * group.annual_turnover
            )
            scores.append((float(utility.min() + 0.25 * utility.mean()), name))
    if not scores:
        raise ValueError("Missing pre-2019 selection evidence")
    return max(scores)[1]


def bootstrap(excess: pd.Series, *, block: int = 63, samples: int = 1000, seed: int = 177) -> dict:
    x = excess.dropna().to_numpy()
    if len(x) < block * 2:
        return {"status": "insufficient_history"}
    rng = np.random.default_rng(seed)
    means = []
    offsets = np.arange(block)
    for _ in range(samples):
        indices = (
            (rng.integers(len(x), size=int(np.ceil(len(x) / block)))[:, None] + offsets) % len(x)
        ).ravel()[: len(x)]
        means.append(x[indices].mean() * 252)
    return {
        "status": "pointwise_not_trial_adjusted",
        "annual_log_excess": float(x.mean() * 252),
        "lower95": float(np.quantile(means, 0.025)),
        "upper95": float(np.quantile(means, 0.975)),
        "block_sessions": block,
        "samples": samples,
    }


def pbo_diagnostic(returns: pd.DataFrame) -> dict:
    values = returns.to_numpy(float)
    _, keep = np.unique(np.round(values, 12), axis=1, return_index=True)
    values = values[:, np.sort(keep)]
    blocks = np.array_split(np.arange(len(values)), 8)
    outcomes = []
    for chosen in itertools.combinations(range(8), 4):
        train = values[np.concatenate([blocks[i] for i in chosen])]
        test = values[np.concatenate([blocks[i] for i in range(8) if i not in chosen])]
        train_score = train.mean(axis=0) / np.maximum(train.std(axis=0), 1e-12)
        test_score = test.mean(axis=0) / np.maximum(test.std(axis=0), 1e-12)
        winner = int(np.argmax(train_score))
        outcomes.append(float((test_score < test_score[winner]).mean()) <= 0.5)
    return {
        "registered_paths": returns.shape[1],
        "distinct_paths": values.shape[1],
        "splits": len(outcomes),
        "probability_selected_path_below_test_median": float(np.mean(outcomes)),
        "status": "family_diagnostic_prior_trial_history_incomplete_not_promotion",
    }


def overlap_evidence(results: dict[str, Result], spy_returns: pd.Series) -> pd.DataFrame:
    rows = []
    for a, b in itertools.combinations(results, 2):
        ar, br = results[a].returns, results[b].returns
        cols = sorted(set(results[a].weights) | set(results[b].weights))
        aw = results[a].weights.reindex(columns=cols, fill_value=0)
        bw = results[b].weights.reindex(columns=cols, fill_value=0)
        tail = spy_returns <= spy_returns.quantile(0.10)
        # Residualize against market beta for descriptive, not selection, evidence.
        design = np.c_[np.ones(len(spy_returns)), spy_returns.fillna(0)]
        residuals = [
            s.to_numpy() - design @ np.linalg.lstsq(design, s.to_numpy(), rcond=None)[0]
            for s in (ar, br)
        ]
        rows.append(
            {
                "left": a,
                "right": b,
                "return_correlation": ar.corr(br),
                "market_tail_correlation": ar[tail].corr(br[tail]),
                "market_beta_residual_correlation": float(np.corrcoef(residuals)[0, 1]),
                "mean_security_weight_overlap": float(np.minimum(aw, bw).sum(axis=1).mean()),
                "simultaneous_loss_share": float((ar.lt(0) & br.lt(0)).mean()),
            }
        )
    return pd.DataFrame(rows)


def run(paths: list[Path], output: Path) -> Path:
    from portfolio_lab.governance import policy_hash

    initial_source_hash = policy_hash()
    output.mkdir(parents=True, exist_ok=False)
    prices, targets, cash, metadata = load_panel(paths)
    core = {
        "trade-bot",
        "swing-trader",
        "rotation-trader",
    }
    systems = {b["system"] for b in metadata["bundles"]}
    if not core <= systems or systems - core - {"fundamental-event-trader"}:
        raise ValueError(
            "The three core specialists are required; only the qualified event specialist may be added"
        )
    states = regimes(prices)
    states.to_csv(output / "market_state.csv", index_label="date")
    pd.DataFrame(metadata["sources"]).to_csv(output / "price_sources.csv", index=False)
    rows, results, target_book, budget_book, spec_book = [], {}, {}, {}, {}
    registry = []

    def evaluate(name, family, target):
        result = replay(prices, target, cash, terminal_events=metadata["terminal_events"])
        results[name], target_book[name] = result, target
        rows.extend(measure(name, family, result))
        return result

    # Specialists compete individually; alternatives cannot inflate their repo's meta budget.
    for name, target in targets.items():
        evaluate(name, "specialist", target)
    primary = [b["primary_expert"] for b in metadata["bundles"]]
    primary_targets = {n: targets[n] for n in primary}
    returns = pd.DataFrame({n: results[n].returns for n in primary})
    fixed_control_specs = []
    for share in (0.50, 0.75, 0.90):
        budget = pd.DataFrame((1 - share) / (len(primary) - 1), index=prices.index, columns=primary)
        budget["trade_primary"] = share
        name = f"fixed_trade{int(100 * share)}_blend"
        target, _ = consolidate(primary_targets, budget, states, Policy(name, "equal"))
        evaluate(name, "post_initial_simple_control", target)
        fixed_control_specs.append(
            {
                "name": name,
                "trade_weight": share,
                "remaining_weights": "equal",
                "status": "simple_control_added_after_initial_read_not_blind_discovery",
            }
        )
    (output / "fixed_blend_controls.json").write_text(
        json.dumps(fixed_control_specs, indent=2, sort_keys=True) + "\n"
    )
    for ticker in ("SPY", "QQQ"):
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w[ticker] = 1.0
        evaluate(f"buy_hold_{ticker}", "benchmark", w)
    evaluate("cash", "benchmark", pd.DataFrame(0.0, index=prices.index, columns=prices.columns))
    for scale in (0.5, 0.75):
        evaluate(f"trade_static{int(scale * 100)}", "benchmark", targets["trade_primary"] * scale)

    def register_round(specs, number):
        frozen = [asdict(s) for s in specs]
        (output / f"round_{number}_frozen.json").write_text(
            json.dumps(frozen, indent=2, sort_keys=True) + "\n"
        )
        for spec in specs:
            budgets = allocate(returns, states, spec)
            target, diagnostics = consolidate(primary_targets, budgets, states, spec)
            evaluate(spec.name, spec.family, target)
            spec_book[spec.name], budget_book[spec.name] = spec, budgets
            registry.append(asdict(spec))
            diagnostics.to_parquet(output / f"{spec.name}_exposure.parquet")
        print(f"Round {number}: {len(specs)} policies evaluated", flush=True)

    register_round(policies(), 1)
    checkpoints = []
    for round_number in (2, 3):
        children = []
        for family in ("inverse_vol", "conditional", "trailing_utility"):
            names = [n for n, s in spec_book.items() if s.family == family]
            winner = choose(rows, names)
            checkpoints.append(
                {
                    "after_round": round_number - 1,
                    "family": family,
                    "selected": winner,
                    "selection_periods": "through_2018_only",
                }
            )
            children.extend(followups(spec_book[winner], round_number))
        register_round(children, round_number)
    family_winners = [
        choose(rows, [n for n, s in spec_book.items() if s.family == f])
        for f in ("inverse_vol", "conditional", "trailing_utility")
    ]
    combinations = [
        replace(
            spec_book[n],
            name=f"combination_{i}_{mode}",
            family="combination",
            defense=mode == "protection",
            technology_cap=0.60 if mode == "concentration" else 1.0,
            parent=n,
            round=4,
        )
        for i, n in enumerate(family_winners, 1)
        for mode in ("protection", "concentration")
    ]
    register_round(combinations, 4)
    selected = choose(rows, list(spec_book))
    # Child challengers are chosen only on historical development/validation.
    chosen_children = []
    for system in sorted(set(e["system"] for e in metadata["experts"].values())):
        names = [
            n
            for n, e in metadata["experts"].items()
            if e["system"] == system and e["role"] != "rejected_diagnostic"
        ]
        chosen_children.append(choose(rows, names))
    budgets = pd.DataFrame(1 / len(chosen_children), index=prices.index, columns=chosen_children)
    target, _ = consolidate(
        {n: targets[n] for n in chosen_children},
        budgets,
        states,
        Policy("child_challenger_blend", "equal"),
    )
    evaluate("child_challenger_blend", "nested_child_selection", target)

    selection = {
        "selected": selected,
        "family_winners": family_winners,
        "selected_children": chosen_children,
        "selection_cutoff": "2018-12-31",
        "later_history_previously_opened": True,
        "automatic_promotion_allowed": False,
        "authority": "research_only",
    }
    (output / "frozen_selection.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n"
    )
    pd.DataFrame(checkpoints).to_csv(output / "round_checkpoints.csv", index=False)
    pd.DataFrame(registry).to_csv(output / "trial_registry.csv", index=False)
    pbo = pbo_diagnostic(pd.DataFrame({n: results[n].returns for n in spec_book}))
    (output / "pbo.json").write_text(json.dumps(pbo, indent=2, sort_keys=True) + "\n")
    # Annual outer replay. Twenty-one-session gap prevents boundary outcomes entering selection.
    wf = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    wf_rows = []
    for year in range(2019, prices.index.max().year + 1):
        past = prices.index[prices.index < pd.Timestamp(f"{year}-01-01")]
        if len(past) < 756:
            continue
        cutoff = past[-22]
        names = list(spec_book)
        scores = [
            (metrics(results[n].returns.loc[cutoff - pd.DateOffset(years=5) : cutoff])["sharpe"], n)
            for n in names
        ]
        name = max(scores)[1]
        mask = prices.index.year == year
        wf.loc[mask] = target_book[name].loc[mask]
        wf_rows.append(
            {
                "year": year,
                "training_end": str(cutoff.date()),
                "candidate": name,
                "embargo_sessions": 21,
            }
        )
    wf_result = replay(prices, wf, cash, terminal_events=metadata["terminal_events"])
    wf_result.returns = wf_result.returns.where(wf_result.returns.index >= "2019-01-01")
    results["annual_walk_forward"] = wf_result
    target_book["annual_walk_forward"] = wf
    rows.extend(measure("annual_walk_forward", "outer_selection_diagnostic", wf_result))
    pd.DataFrame(wf_rows).to_csv(output / "walk_forward_selections.csv", index=False)

    # Development-only average risk match, never selected on later drawdowns.
    selected_risk = results[selected].returns.loc[:"2011-12-31"].std()
    reference_risk = results["trade_primary"].returns.loc[:"2011-12-31"].std()
    scale = min(1.0, selected_risk / max(reference_risk, 1e-12))
    evaluate("risk_matched_trade", "benchmark", targets["trade_primary"] * scale)
    intervals = []
    for name in sorted(set([selected, "equal_blend", *family_winners, "child_challenger_blend"])):
        for reference in ("trade_primary", "equal_blend", "risk_matched_trade"):
            for period in ("later_diagnostic", "recent_diagnostic"):
                start, end = PERIODS[period]
                excess = np.log1p(results[name].returns.loc[start:end]) - np.log1p(
                    results[reference].returns.loc[start:end]
                )
                intervals.append(
                    {
                        "candidate": name,
                        "reference": reference,
                        "period": period,
                        **bootstrap(excess),
                    }
                )
    pd.DataFrame(intervals).to_csv(output / "bootstrap.csv", index=False)
    overlaps = overlap_evidence(
        {n: results[n] for n in primary}, prices.SPY.pct_change(fill_method=None).fillna(0)
    )
    overlaps.to_csv(output / "orthogonality.csv", index=False)
    episodes = [
        {
            "candidate": name,
            "episode": episode,
            **metrics(result.returns.loc[start:end], result.turnover),
        }
        for name, result in results.items()
        for episode, (start, end) in EPISODES.items()
        if len(result.returns.loc[start:end].dropna()) > 20
    ]
    pd.DataFrame(episodes).to_csv(output / "episodes.csv", index=False)
    conditionals = [
        {
            "candidate": name,
            "state": state,
            "sessions": int(mask.sum()),
            "annualized_arithmetic_return_not_cagr": float(result.returns[mask].mean() * 252),
            "daily_loss_share": float(result.returns[mask].lt(0).mean()),
        }
        for name, result in results.items()
        for state in ("normal", "transition", "stress", "uncertain")
        if (mask := states.state.shift(1).eq(state) & result.returns.notna()).any()
    ]
    pd.DataFrame(conditionals).to_csv(output / "state_conditioned.csv", index=False)
    stress_rows = []
    for name in dict.fromkeys([selected, "trade_primary", "equal_blend", "child_challenger_blend"]):
        for lag, cost in ((1, 10), (2, 10), (4, 10), (1, 25), (2, 50)):
            r = replay(prices, target_book[name], cash, lag=lag, cost_bps=cost, terminal_events=metadata["terminal_events"])
            stress_rows.append(
                {
                    "candidate": name,
                    "lag_sessions": lag,
                    "cost_bps": cost,
                    **metrics(r.returns, r.turnover),
                }
            )
    pd.DataFrame(stress_rows).to_csv(output / "execution_stress.csv", index=False)
    pd.DataFrame(rows).to_csv(output / "metrics.csv", index=False)
    pd.DataFrame({n: r.returns for n, r in results.items()}).to_parquet(output / "returns.parquet")
    results[selected].weights.to_parquet(output / "selected_executed_weights.parquet")
    target_book[selected].to_parquet(output / "selected_targets.parquet")
    budget_book[selected].to_parquet(output / "selected_budgets.parquet")
    selected_budget = budget_book[selected]
    changes = selected_budget.diff().fillna(selected_budget).abs().sum(axis=1).gt(1e-12)
    explanation = selected_budget.loc[changes].copy()
    explanation["market_state"] = states.state.loc[changes]
    explanation["family"] = spec_book[selected].family
    explanation["training_rule"] = "realized_prior_sessions_only_shrunk_toward_equal"
    explanation.to_csv(output / "allocation_decisions.csv", index_label="date")
    newest = {
        "as_of_close": metadata["common_end"],
        "selected_research_policy": selected,
        "budgets": budget_book[selected].iloc[-1].to_dict(),
        "target_holdings": target_book[selected].iloc[-1][lambda x: x > 1e-10].to_dict(),
        "cash": float(1 - target_book[selected].iloc[-1].sum()),
        "market_state": states.iloc[-1].to_dict(),
        "authority": "research_only",
        "action": "NO ACTION",
        "automatic_promotion_allowed": False,
        "fundamental_event_specialist": "qualified_comparative_research_only" if "fundamental-event-trader" in systems else "not_admitted_no_qualified_bundle",
        "technology_measure": "conservative instrument-level proxy; overlapping ETFs not constituent lookthrough",
    }
    (output / "current_state.json").write_text(json.dumps(newest, indent=2, sort_keys=True) + "\n")
    report = render_report(pd.DataFrame(rows), selection, metadata, scale, intervals)
    report += f"\nAllocator-family PBO diagnostic: {pbo['probability_selected_path_below_test_median']:.1%}, {pbo['distinct_paths']} distinct paths from {pbo['registered_paths']} specifications. Prior trial history is incomplete; this is not promotion evidence.\n"
    (output / "report.md").write_text(report)
    code_hash = policy_hash()
    if code_hash != initial_source_hash:
        raise RuntimeError(
            "Source changed during the research run; outputs are incomplete and cannot be shadowed"
        )
    manifest = {
        "schema_version": 1,
        "environment": {
            name: version(name) for name in (
                "numpy", "pandas", "pyarrow", "plotly", "streamlit", "exchange-calendars"
            )
        },
        "created_at_utc": datetime.now(UTC).isoformat(),
        "authority": "research_only",
        "automatic_promotion_allowed": False,
        "execution": "close-known targets; next-session close fill; holdings drift; 10bps on risky traded notional; costs funded from NAV",
        "metadata": metadata,
        "policy_source_sha256": code_hash,
        "policy_source_scope": "financial_policy_v1",
        "selection": selection,
        "risk_match_development_scale": scale,
        "risk_match_method": "development_realized_volatility_ratio_approximate_not_exact_after_rescaling_costs",
        "registered_allocator_trials": len(registry),
        "prior_trial_history_complete": False,
        "prior_research": {
            "rotation_variants": 4400,
            "trade_adaptive_variants": 112,
            "orthogonal_survey": 167,
            "nonprice_survey": 88,
            "other_trade_and_swing_trials": "not_fully_enumerated; no trial-adjusted promotion claim",
        },
        "artifacts": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        f"Completed {len(results)} paths, {len(registry)} allocator trials; no promotion",
        flush=True,
    )
    return output / "report.md"


def render_report(frame, selection, metadata, scale, intervals):
    names = [
        "trade_primary",
        "swing_primary",
        "rotation_primary",
        "buy_hold_SPY",
        "buy_hold_QQQ",
        "trade_static75",
        "fixed_trade50_blend",
        "fixed_trade75_blend",
        "fixed_trade90_blend",
        "risk_matched_trade",
        "equal_blend",
        *selection["family_winners"],
        selection["selected"],
        "child_challenger_blend",
        "annual_walk_forward",
    ]
    lines = [
        "# Portfolio Lab: Common-Clock Research",
        "",
        f"Observed common sessions: {metadata['common_start']} through {metadata['common_end']}.",
        "",
        "Research only. No promoted strategy, broker connection, or automatic trade authority.",
        "All later periods have already been observed in earlier studies; they are diagnostic, not pristine holdouts.",
        "Targets fill the following session close; returns begin after that fill. Holdings drift and trading costs are self-financed.",
        "Common replay is NOT a replacement for native next-open or lagged-close metrics. Trade Bot native controls are re-clocked at signal close.",
        "Technology is a selected modern-stock universe; ETF classifications and current survivors also limit inference.",
        "",
        "| candidate | full CAGR | max DD | 2019-23 CAGR | 2024+ CAGR | June 2026+ return |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in dict.fromkeys(names):
        group = frame[frame.candidate.eq(name)].set_index("period")
        if group.empty:
            continue
        full = group.loc["full"]
        lines.append(
            f"| {name} | {full.cagr:.2%} | {full.max_drawdown:.2%} | {group.loc['later_diagnostic', 'cagr']:.2%} | {group.loc['recent_diagnostic', 'cagr']:.2%} | {group.loc['current_transition', 'total_return']:.2%} |"
        )
    selected = selection["selected"]
    comparisons = [
        r for r in intervals if r["candidate"] == selected and r["reference"] == "equal_blend"
    ]
    lines += [
        "",
        f"Frozen through-2018 selected allocator: `{selected}`. This is a research selection, not approval.",
        f"Development-only volatility-ratio control uses {scale:.1%} of the Trade Bot target sleeve; matching is approximate after replay costs and drift.",
        "Annual walk-forward full metrics begin in 2019; other full metrics begin at the common start.",
        "",
        "## Incremental Evidence Versus Fixed Equal Blend",
    ]
    for row in comparisons:
        lines.append(
            f"- {row['period']}: annual log-return difference {row['annual_log_excess']:+.2%}; pointwise 95% block interval [{row['lower95']:+.2%}, {row['upper95']:+.2%}]."
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- Separate standalone alpha from diversification and from simply holding less risk.",
        "- Global protection is an exposure ceiling, not multiplication of every child's risk haircut.",
        "- Budget estimators use matured one-day returns only, shrink toward equal weights, and limit allocation changes.",
        "- No regime is labeled with future drawdowns during allocation. Crisis dates enter evaluation only.",
        "- Family followups use development/validation only; outer annual selection has a 21-session gap. This does not erase previously opened history.",
        "- Bootstrap intervals are pointwise; historical trial history is incomplete and no statistical promotion claim is allowed.",
        "- current_state.json is an unactionable research candidate, not personal portfolio advice.",
        "- A missing or stale specialist cannot silently become a zero-return observation; incomplete sessions are rejected.",
        "- Technology exposure is an instrument proxy, not exact ETF constituent overlap.",
        "- Fundamental Event Trader remains excluded until point-in-time data qualification passes.",
        "",
        "See episodes.csv, execution_stress.csv, orthogonality.csv, bootstrap.csv, and frozen registries for falsification evidence.",
    ]
    return "\n".join(lines) + "\n"
