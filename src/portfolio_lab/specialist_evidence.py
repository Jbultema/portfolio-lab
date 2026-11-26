"""Mechanism inventory, funded overlap and explicit prospective review gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from portfolio_lab.contracts import ContractError, digest, load_panel
from portfolio_lab.engine import replay
from portfolio_lab.research import overlap_evidence

MECHANISMS = {
    "trade-bot": {"information": "prices", "decision": "technology_momentum_and_cash_risk", "clock": "weekly_close"},
    "swing-trader": {"information": "prices", "decision": "monthly_cross_asset_momentum", "clock": "monthly_next_open"},
    "rotation-trader": {"information": "prices", "decision": "sector_relative_leadership_and_timing", "clock": "monthly_next_open"},
    "fundamental-event-trader": {"information": "filings_and_news", "decision": "company_event_revaluation", "clock": "event_availability_next_executable_price"},
}


def qualification(evidence):
    if not isinstance(evidence, dict):
        raise ContractError("Structured specialist evidence required")
    booleans = ("public_data", "point_in_time_universe", "original_timestamps", "failed_security_treatment",
        "distinct_information", "risk_matched_incremental_benefit", "stress_tests_pass", "selection_adjustment_pass",
        "frozen_prospective_lineage")
    if any(key in evidence and type(evidence[key]) is not bool for key in booleans):
        raise ContractError("Evidence flags must be Boolean, not truthy strings")
    sessions = evidence.get("independent_matured_prospective_observations", 0)
    if type(sessions) is not int or not 0 <= sessions <= 100000:
        raise ContractError("Independent prospective observation count required")
    missing = [key for key in booleans if evidence.get(key) is not True]
    if sessions < 30:
        missing.append("at_least_30_independent_matured_prospective_observations")
    return {"status": "eligible_for_human_review" if not missing else "research_only",
        "unmet_gates": missing, "automatic_promotion_allowed": False,
        "portfolio_allocation_allowed": False, "action_authorized": False,
        "interpretation": "orthogonality_or_a_research_score_alone_never_grants_allocation_authority"}


def run(paths, output):
    prices, targets, cash, meta = load_panel(paths)
    primary = [bundle["primary_expert"] for bundle in meta["bundles"]]
    if set(primary) != {"trade_primary", "swing_primary", "rotation_primary"}:
        raise ContractError("Exactly the three qualified-for-comparison core bundles required")
    results = {name: replay(prices, targets[name], cash, cost_bps=25, lag=1,
        terminal_events=meta["terminal_events"]) for name in primary}
    evidence = overlap_evidence(results, prices.SPY.pct_change(fill_method=None).fillna(0))
    output.mkdir(parents=True, exist_ok=False)
    evidence.to_csv(output / "overlap.csv", index=False)
    summary = {"kind": "specialist_mechanism_audit_v1", "mechanisms": MECHANISMS,
        "bundle_manifest_sha256": {str(path): digest(path / "manifest.json") for path in paths},
        "sample_start": str(prices.index[0].date()), "sample_end": str(prices.index[-1].date()),
        "interpretation": "Three different price-only implementations are not three independent information sources.",
        "event_status": "distinct_information_but_no_broad_historical_admission",
        "new_repo_decision": "do_not_split_existing_price_mechanisms_into_duplicate_repositories",
        "overlap_status": "full_sample_descriptive_not_a_selection_signal",
        "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"source_sha256": digest(Path(__file__)),
        "artifacts": {p.name: digest(p) for p in output.iterdir()}}, indent=2) + "\n")
    print(evidence.to_string(index=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.bundle, args.output)
