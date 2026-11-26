import copy
import json

import numpy as np
import pandas as pd
import pytest
from test_contracts import bundle

from portfolio_lab.contracts import ContractError, digest, load_bundle
from portfolio_lab.engine import replay
from portfolio_lab.event_context import (
    archive_news,
    current_fingerprint,
    fingerprint,
    unavailable,
    validate_context,
)


def context():
    return {"schema_version": 2, "system": "fundamental-event-trader", "status": "blocked",
            "authority": "research_only", "action_authorized": False,
            "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False,
            "captured_at_utc": "2026-11-25T22:00:00Z", "target_holdings": {}, "recent_events": []}


def test_blocked_specialist_is_operational_evidence_not_a_position():
    assert validate_context(context())["status"] == "blocked"


def test_failed_provider_is_unavailable_not_a_cash_allocation(tmp_path):
    payload = unavailable("qualification_check_failed")
    assert validate_context(payload)["status"] == "unavailable"
    assert payload["target_holdings"] == {}
    assert payload["tested_on_real_data"] is None
    assert current_fingerprint(tmp_path)["status"] == "unavailable"


def test_scheduler_fingerprint_changes_for_new_data_not_just_capture_time():
    original = context()
    later = {**original, "captured_at_utc": "2026-11-25T23:00:00Z"}
    assert fingerprint(original) == fingerprint(later)
    later["dataset_manifest_sha256"] = "new-data"
    assert fingerprint(original) != fingerprint(later)


@pytest.mark.parametrize("key,value", [("portfolio_allocation_allowed", True), ("action_authorized", True),
                                      ("status", "live"), ("target_holdings", {"SPY": 1.})])
def test_event_context_cannot_bypass_authority_boundaries(key, value):
    payload = context()
    payload[key] = value
    with pytest.raises(ContractError):
        validate_context(payload)


def test_future_event_cannot_enter_interpretation_context():
    payload = context()
    payload["recent_events"] = [{"security_id": "A", "cik": "1", "accession": "a",
                                 "available_at": "2026-11-26T22:00:00Z", "score": 1., "source_sha256": "a" * 64}]
    with pytest.raises(ContractError, match="Future"):
        validate_context(payload)


@pytest.mark.parametrize("weights", [{"A": float("nan")}, {"A": float("inf")}, {"A": -0.1}, {"A": 1.1}, {"A": True}])
def test_invalid_shadow_weights_cannot_enter_the_daily_report(weights):
    payload = context() | {"status": "research_shadow", "target_holdings": weights}
    with pytest.raises(ContractError, match="target weights"):
        validate_context(payload)


def test_naive_capture_time_is_not_qualified_operational_evidence():
    with pytest.raises(ContractError, match="capture time"):
        validate_context(context() | {"captured_at_utc": "2026-11-25T22:00:00"})


def test_record_count_cannot_become_a_profitability_claim():
    payload = context() | {"prospective_shadow": {"recorded_sessions": 60, "action_authorized": False,
                                                "automatic_promotion_allowed": False, "profitability_established": True}}
    with pytest.raises(ContractError, match="observation count"):
        validate_context(payload)


def test_shadow_journal_update_changes_refresh_identity():
    payload = context() | {"prospective_shadow": {"latest_record_sha256": "one"}}
    changed = context() | {"prospective_shadow": {"latest_record_sha256": "two"}}
    assert fingerprint(payload) != fingerprint(changed)


def public_news():
    return {"schema_version": 1, "authority": "observation_only", "action_authorized": False,
            "captured_at_utc": "2026-11-25T21:00:00Z",
            "historical_strategy_evidence": False, "status": "partial", "refresh_due": False,
            "items": [{"url": "https://www.example.com/story", "published_at_utc": "2026-11-25T20:00Z",
                       "first_seen_at_utc": "2026-11-25T21:00Z", "version_first_seen_at_utc": "2026-11-25T21:00Z",
                       "available_at_utc": "2026-11-25T21:00Z"}]}


def test_current_news_can_be_available_while_historical_strategy_is_blocked():
    payload = context() | {"news": public_news()}
    assert validate_context(payload)["status"] == "blocked"
    assert payload["news"]["status"] == "partial"


@pytest.mark.parametrize("change", ["authority", "future", "naive", "credentials"])
def test_news_cannot_bypass_authority_availability_or_source_url_checks(change):
    payload = context() | {"news": public_news()}
    if change == "authority":
        payload["news"]["historical_strategy_evidence"] = True
    elif change == "future":
        payload["news"]["items"][0]["version_first_seen_at_utc"] = "2026-11-26T21:00Z"
    elif change == "naive":
        payload["news"]["items"][0]["first_seen_at_utc"] = "2026-11-25T21:00"
    else:
        payload["news"]["items"][0]["url"] = "https://user:password@www.example.com/story"
    with pytest.raises(ContractError):
        validate_context(payload)


def test_hourly_news_due_state_changes_scheduler_identity_without_a_new_session():
    payload = context() | {"news": public_news()}
    later = copy.deepcopy(payload)
    later["news"]["refresh_due"] = True
    assert fingerprint(payload) != fingerprint(later)


def test_news_archive_copies_only_bound_public_evidence(tmp_path):
    root = tmp_path / "event"
    folder = root / "data/news/captures/test"
    folder.mkdir(parents=True)
    (folder / "items.json").write_text("[]")
    meta = {"kind": "public_news_observation", "action_authorized": False,
            "historical_strategy_evidence": False, "artifacts": {"items.json": digest(folder / "items.json")}}
    (folder / "manifest.json").write_text(json.dumps(meta))
    payload = {"news": {"archive_report": str(folder), "manifest_sha256": digest(folder / "manifest.json")}}
    destination = tmp_path / "capture"
    copied = archive_news(payload, root, destination)
    assert copied["fundamental-news/items.json"] == digest(folder / "items.json")
    assert (destination / "fundamental-news/manifest.json").is_file()
    (folder / "items.json").write_text("changed")
    with pytest.raises(ContractError, match="integrity"):
        archive_news(payload, root, tmp_path / "rejected")
    payload["news"]["archive_report"] = str(tmp_path)
    with pytest.raises(ContractError, match="outside"):
        archive_news(payload, root, tmp_path / "outside")


def test_common_engine_realizes_bankruptcy_instead_of_losing_the_position():
    dates = pd.bdate_range("2020-01-02", periods=6)
    price = pd.DataFrame({"DEAD": [100., 100., 100., np.nan, np.nan, np.nan], "SPY": 100.}, index=dates)
    target = pd.DataFrame({"DEAD": .5, "SPY": 0.}, index=dates)
    terminal = [{"security_id": "DEAD", "settlement_session": str(dates[3].date()), "value_per_adjusted_share": 0.}]
    result = replay(price, target, pd.Series(0., index=dates), cost_bps=0., terminal_events=terminal)
    assert result.equity.iloc[-1] == pytest.approx(.5)
    assert result.weights.DEAD.iloc[-1] == 0.
    with pytest.raises(ContractError, match="Unpriced"):
        replay(price, target, pd.Series(0., index=dates), cost_bps=0.)


def test_common_terminal_recovery_does_not_leak_to_earlier_returns():
    dates = pd.bdate_range("2020-01-02", periods=6)
    price = pd.DataFrame({"DEAD": [100., 100., 100., np.nan, np.nan, np.nan]}, index=dates)
    target = pd.DataFrame(.5, index=dates, columns=["DEAD"])
    terminal = [{"security_id": "DEAD", "settlement_session": str(dates[3].date()), "value_per_adjusted_share": 40.}]
    a = replay(price, target, pd.Series(0., index=dates), cost_bps=0., terminal_events=terminal)
    changed = copy.deepcopy(terminal)
    changed[0]["value_per_adjusted_share"] = 0.
    b = replay(price, target, pd.Series(0., index=dates), cost_bps=0., terminal_events=changed)
    assert a.equity.iloc[-1] == pytest.approx(.7)
    pd.testing.assert_series_equal(a.returns.iloc[:3], b.returns.iloc[:3])


def test_event_bundle_requires_bound_qualification_and_terminal_evidence(tmp_path):
    root = bundle(tmp_path / "event", system="fundamental-event-trader")
    with pytest.raises(ContractError, match="requires data/research"):
        load_bundle(root)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["source_inputs"] = {"dataset_manifest": "dataset", "research_manifest": "research"}
    evidence = {"qualified_real_dataset": True, "native_research_audit": "passed_research_integrity",
                "fixture_only": False, "data_kind": "real_historical", "portfolio_allocation_allowed": False,
                "automatic_promotion_allowed": False, "code_sha256": "test", "dataset_manifest_sha256": "dataset",
                "research_manifest_sha256": "research"}
    (root / "qualification.json").write_text(json.dumps(evidence))
    (root / "terminal_events.json").write_text("[]")
    manifest["artifacts"] |= {name: digest(root / name) for name in ("qualification.json", "terminal_events.json")}
    (root / "manifest.json").write_text(json.dumps(manifest))
    assert load_bundle(root).manifest["system"] == "fundamental-event-trader"
    evidence["fixture_only"] = True
    (root / "qualification.json").write_text(json.dumps(evidence))
    manifest["artifacts"]["qualification.json"] = digest(root / "qualification.json")
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ContractError, match="admission"):
        load_bundle(root)
