"""Descriptive falsification of an already-frozen adaptive allocation study.

This module does not select policies or change any frozen strategy parameters.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_lab.adaptive_research import verify
from portfolio_lab.allocation import regimes
from portfolio_lab.contracts import ContractError, digest, load_panel
from portfolio_lab.dynamic_research import verify as verify_previous
from portfolio_lab.engine import metrics


def annual_log_excess(a, b):
    return float((np.log1p(a) - np.log1p(b)).mean() * 252)


def diagnose(source, output):
    summary = verify(source)
    cfg = json.loads((source / "protocol.json").read_text())
    previous = Path(cfg["source"])
    verify_previous(previous)
    curves = pd.read_parquet(source / "returns.parquet")
    before = pd.read_parquet(previous / "returns.parquet")
    registry = json.loads((source / "registry.json").read_text())["core"]
    coefficients = pd.read_parquet(source / "coefficients.parquet")
    contributions = pd.read_parquet(source / "budgets.parquet")
    fits = pd.read_csv(source / "model_fit_audit.csv")
    identities = []
    for lag, cost in ((1, 25), (1, 10), (5, 50)):
        for name in ("trade_primary", "swing_primary", "rotation_primary"):
            key = f"core|{name}|raw|lag{lag}|cost{cost}"
            pd.testing.assert_series_equal(curves[key], before[key], check_names=False)
            identities.append({"candidate": name, "lag": lag, "cost_bps": cost, "exact_previous_returns_match": True,
                "new_index_name": curves.index.name, "previous_index_name": before.index.name,
                "index_name_metadata_ignored_not_dates_or_values": True})
    mature = (pd.to_datetime(fits.last_label_close) <= pd.to_datetime(fits.fit_close)).all()
    if not mature or not fits.no_future_label.all():
        raise ContractError("Future labels in frozen model audit")
    if any(contributions[name].sum(axis=1).gt(1 + 1e-10).any() for name in contributions.columns.get_level_values(0).unique()):
        raise ContractError("Borrowing in target contribution audit")
    paths = [Path(item["path"]) for item in cfg["inputs"][:3]]
    prices, _, _, _ = load_panel(paths)
    state = regimes(prices).state.shift(1)
    spy = prices.SPY.pct_change(fill_method=None)
    annual, rolling, regime, audits = [], [], [], []
    for spec in registry:
        name = spec["name"]
        def key(role, candidate=name):
            return f"core|{candidate}|{role}|lag1|cost25"
        start = max(spec["available_from"], "2019-01-01")
        raw = curves[key("raw")].loc[start:]
        trade = curves["core|trade_primary|raw|lag1|cost25"].loc[raw.index]
        spy_control = curves[key("matched_spy")].loc[raw.index]
        cash_control = curves[key("cash_ablation")].loc[raw.index]
        cap = curves[key("capped")].loc[raw.index]
        matched = curves[key("matched_trade")].loc[raw.index]
        for year in sorted(raw.index.year.unique()):
            mask = raw.index.year == year
            for role, values in (("raw", raw), ("trade", trade), ("matched_spy", spy_control), ("cash_ablation", cash_control), ("capped", cap), ("matched_trade", matched)):
                annual.append({"candidate": name, "family": spec["family"], "role": role, "year": int(year), **metrics(values.loc[mask])})
        for reference, a, b in (("trade", raw, trade), ("matched_spy", raw, spy_control), ("cash_ablation", raw, cash_control), ("same_exposure", cap, matched)):
            differential = np.log1p(a) - np.log1p(b)
            for horizon in (252, 756):
                windows = differential.rolling(horizon, min_periods=horizon).sum().dropna() * 252 / horizon
                rolling.append({"candidate": name, "family": spec["family"], "reference": reference, "sessions": horizon,
                    "overlapping_windows": len(windows), "fraction_positive": float(windows.gt(0).mean()),
                    "median_annual_log_excess": float(windows.median()), "worst_annual_log_excess": float(windows.min()),
                    "best_annual_log_excess": float(windows.max()), "not_independent_trials": True})
        for label in ("normal", "transition", "stress"):
            dates = raw.index[state.loc[raw.index].eq(label)]
            regime.append({"candidate": name, "family": spec["family"], "prior_close_market_state": label, "sessions": len(dates),
                "annualized_log_excess_vs_trade": annual_log_excess(raw.loc[dates], trade.loc[dates]),
                "annualized_log_excess_vs_spy_control": annual_log_excess(raw.loc[dates], spy_control.loc[dates]),
                "discontinuous_state_attribution_not_a_tradable_strategy": True})
        x = spy.loc[raw.index]
        alt = coefficients[name].iloc[:, 1:].sum(axis=1).loc[raw.index]
        exposure = contributions[name].sum(axis=1).loc[raw.index]
        audits.append({"candidate": name, "family": spec["family"],
            "fraction_alternative_sessions": float(alt.gt(1e-10).mean()), "mean_risky_target": float(exposure.mean()),
            "maximum_risky_target": float(exposure.max()),
            "notional_sum_above_one_sessions_not_borrowing": int(coefficients[name].loc[raw.index].sum(axis=1).gt(1 + 1e-10).sum()),
            "univariate_realized_spy_beta": float(raw.cov(x) / x.var()),
            "trade_univariate_realized_spy_beta": float(trade.cov(x) / x.var()),
            "annual_log_excess_vs_trade": annual_log_excess(raw, trade),
            "annual_log_excess_vs_spy_control": annual_log_excess(raw, spy_control),
            "annual_log_excess_capped_vs_trade_matched": annual_log_excess(cap, matched)})
    output.mkdir(parents=True, exist_ok=False)
    for name, rows in (("baseline_identity", identities), ("calendar_years", annual), ("rolling_consistency", rolling), ("regime_attribution", regime), ("risk_and_activity", audits)):
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    result = {"kind": "adaptive_allocation_descriptive_diagnostics_v1", "source": str(source.resolve()),
        "source_manifest_sha256": digest(source / "manifest.json"), "diagnostic_code_sha256": digest(Path(__file__)),
        "as_of_close": summary["as_of_close"], "exact_baseline_identity_checks": len(identities),
        "all_model_labels_mature": bool(mature), "descriptive_not_selection": True,
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
