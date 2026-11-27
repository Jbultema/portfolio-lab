"""Conditional positioning combinations on the funded cross-bot execution clock."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from portfolio_lab.combination_stress import add_probe_prices, bound, joint_intervals
from portfolio_lab.contracts import ContractError, digest, load_panel
from portfolio_lab.engine import metrics, replay
from portfolio_lab.operations import atomic

PERIODS = {"development": ("2012", "2016"), "validation": ("2017", "2019"),
           "test": ("2020", "2022"), "later_diagnostic": ("2023", None),
           "full": ("2012", None), "covid": ("2020-02", "2020-06"),
           "inflation": ("2022", "2022"), "recent_transition": ("2026-06", None)}


def load_position(root):
    pointer = json.loads((root / "reports/research/latest.json").read_text())
    report = Path(pointer["report"])
    if digest(report / "manifest.json") != pointer["manifest_sha256"]:
        raise ContractError("Positioning research pointer mismatch")
    meta = json.loads((report / "manifest.json").read_text())
    if (meta.get("kind") != "position_research_v1" or meta.get("authority") != "research_only"
            or meta.get("portfolio_allocation_allowed") is not False
            or meta.get("automatic_promotion_allowed") is not False):
        raise ContractError("Positioning qualification/authority mismatch")
    for name, hashed in meta["artifacts"].items():
        bound(report, name, hashed)
    return (pd.read_parquet(report / "prices.parquet"),
            pd.read_parquet(report / "selected_targets.parquet"), meta, pointer["manifest_sha256"])


def specifications(targets, position, index, columns):
    def fit(w):
        if not index.isin(w.index).all():
            raise ContractError("Missing positioning/core target cannot be zero-filled")
        result = w.reindex(index=index, columns=columns, fill_value=0.)
        if result.isna().any().any():
            raise ContractError("Missing positioning/core target cannot be zero-filled")
        return result

    trade, swing, rotation, position = (fit(targets["trade_primary"]), fit(targets["swing_primary"]),
                                         fit(targets["rotation_primary"]), fit(position))
    out = {"trade_primary": trade, "position_only": position, "swing_primary": swing, "rotation_primary": rotation}
    for share in (.10, .25, .50):
        out[f"trade{int((1-share)*100)}_position{int(share*100)}"] = trade * (1 - share) + position * share
        out[f"trade_cash_{int((1-share)*100)}"] = trade * (1 - share)
    equity_share = position.reindex(columns=["SPY", "QQQ", "IWM"], fill_value=0.).sum(axis=1)
    out["position_confirmed_trade_gate"] = trade.mul(.5 + .5 * equity_share, axis=0)
    out["fourway_70_10_10_10"] = .7 * trade + .1 * swing + .1 * rotation + .1 * position
    return out


def run(bundles, position_root, output):
    prices, targets, cash, meta = load_panel(bundles)
    p, position, position_meta, position_hash = load_position(position_root)
    prices, sources = add_probe_prices(prices, p)
    index = prices.loc["2012":].index
    prices, cash = prices.loc[index], cash.loc[index]
    slate = specifications(targets, position, index, prices.columns)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {"kind": "conditional_position_integration_v1", "rules": list(slate),
                "selection": "Frozen native positioning development/validation selection; no new portfolio selection",
                "costs_bps": [10, 25, 50], "execution_lags": [1, 3],
                "position_manifest_sha256": position_hash, "core_manifests": meta["bundle_sha256"],
                "periods": PERIODS, "public_positioning_qualified": False,
                "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    atomic(output / "protocol.json", protocol)
    rows, base = [], {}
    for cost in (10, 25, 50):
        for lag in (1, 3):
            results = {name: replay(prices, w, cash, cost_bps=cost, lag=lag) for name, w in slate.items()}
            for name, result in results.items():
                if cost == 25 and lag == 1:
                    base[name] = result.returns
                for period, (start, end) in PERIODS.items():
                    r = result.returns.loc[start:end]
                    if len(r) < 21:
                        continue
                    rows.append({"candidate": name, "cost_bps": cost, "lag": lag, "period": period,
                                 **metrics(r, result.turnover)})
            # Fit risk controls only before test; no in-test resizing to match realized risk.
            reference = results["trade_primary"].returns.loc["2012":"2019"]
            for name in ("position_only", "trade90_position10", "trade75_position25", "position_confirmed_trade_gate"):
                sample = results[name].returns.loc[reference.index]
                scale = min(1., float(sample.std() / max(reference.std(), 1e-12)))
                weight = slate["trade_primary"] * scale
                weight.loc[weight.index < "2020-01-01"] = 0.
                control = replay(prices, weight, cash, cost_bps=cost, lag=lag)
                control_name = "risk_control_for_" + name
                if cost == 25 and lag == 1:
                    base[control_name] = control.returns
                for period in ("test", "later_diagnostic"):
                    start, end = PERIODS[period]
                    rows.append({"candidate": control_name, "cost_bps": cost, "lag": lag, "period": period,
                                 "training_scale": scale, **metrics(control.returns.loc[start:end], control.turnover)})
    performance = pd.DataFrame(rows)
    performance.to_csv(output / "performance.csv", index=False)
    returns = pd.DataFrame(base)
    returns.to_parquet(output / "returns.parquet")
    returns[["trade_primary", "position_only", "swing_primary", "rotation_primary"]].corr().to_csv(output / "correlations.csv")
    candidates = [name for name in slate if name not in {"trade_primary", "swing_primary", "rotation_primary"}]
    excess = returns[candidates].sub(returns.trade_primary, axis=0).loc["2020":]
    intervals = pd.DataFrame([r for block in (21, 63, 126) for r in joint_intervals(excess, block=block)])
    intervals.to_csv(output / "uncertainty.csv", index=False)
    omissions = []
    for year in (2020, 2022):
        for name in candidates + ["trade_primary"]:
            omissions.append({"candidate": name, "omitted_year": year, **metrics(returns.loc[returns.index.year != year, name])})
    pd.DataFrame(omissions).to_csv(output / "crisis_omissions.csv", index=False)
    full = performance[(performance.period == "full") & (performance.cost_bps == 25) & (performance.lag == 1)]
    lines = ["# Positioning Integration", "", "Conditional research only. No allocation promotion.",
             f"Common sessions: {index[0].date()} to {index[-1].date()}.",
             "Funded drifting holdings, next-close fills, 25bp per traded side; common captured cash yield.",
             "Position Bot's historical release/vintage qualification remains incomplete.",
             "Native positioning used zero cash yield; these common-clock results use the same cash series for every arm.", "",
             "| Portfolio | CAGR | Maximum DD |", "|---|---:|---:|"]
    lines += [f"| {r.candidate} | {r.cagr:.2%} | {r.max_drawdown:.2%} |" for r in full.itertuples()]
    lines += ["", "Risk controls are fitted through 2019 only. Historical strategy selection is not a live investable track record.",
              "No comparison here can overcome missing original vintages or establish calibrated crash probabilities."]
    (output / "readout.md").write_text("\n".join(lines) + "\n")
    atomic(output / "manifest.json", {"kind": "conditional_position_integration_v1", "created_at_utc": datetime.now(UTC).isoformat(),
        "action_authorized": False, "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False,
        "position_qualification": position_meta["qualification"], "price_sources": sources,
        "execution_paths": (len(slate) + 4) * 6,
        "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}})
    verify(output)
    atomic(Path("reports/position-integration/latest.json"), {"report": str(output.resolve()), "manifest_sha256": digest(output / "manifest.json")})
    return output


def verify(root, expected=None):
    if expected and digest(root / "manifest.json") != expected:
        raise ContractError("Position integration manifest changed")
    meta = json.loads((root / "manifest.json").read_text())
    if (meta.get("kind") != "conditional_position_integration_v1"
            or any(meta.get(k) is not False for k in ("action_authorized", "portfolio_allocation_allowed", "automatic_promotion_allowed"))):
        raise ContractError("Position integration authority mismatch")
    for name, hashed in meta["artifacts"].items():
        bound(root, name, hashed)
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", action="append", type=Path, required=True)
    parser.add_argument("--position-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.bundle, args.position_root, args.output))


if __name__ == "__main__":
    main()
