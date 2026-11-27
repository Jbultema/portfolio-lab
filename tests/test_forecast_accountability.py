"""Prospective records cannot be manufactured from backfills or duplicated labels."""

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.briefing import calendar
from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.forecast_accountability import record, score, summarize

CAPTURE = datetime(2026, 1, 12, 22, tzinfo=UTC)
LATER = datetime(2026, 4, 30, 22, tzinfo=UTC)


@pytest.fixture
def fixture(tmp_path):
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"as_of_session": "2026-01-12", "action_authorized": False,
        "authority": "interpretation_only", "bots": [], "fresh_specialists": 0,
        "facts": [{"id": "SPY.trend.63", "observed_session": "2026-01-12",
            "available_after_utc": "2026-01-12T21:15:00+00:00", "role": "monitor"}],
        "information_cutoff_utc": "2026-01-12T21:15:00+00:00"}))
    claim = {"model": "frozen-risk-v1", "thesis": "Predeclared 21-session downside event.",
        "ticker": "SPY", "horizon": 5, "threshold": -.05, "probability": .3,
        "data_end": "2026-01-12", "evidence_sha256": digest(pack), "mode": "prospective", "fact_ids": ["SPY.trend.63"]}
    index = calendar().sessions_in_range("2025-01-02", "2026-04-30")
    prices = pd.DataFrame({"SPY": np.linspace(100., 125., len(index))}, index=index)
    root = tmp_path / "journal"
    return pack, claim, prices, root


def test_capture_maturity_and_base_rate_do_not_use_future_information(fixture):
    pack, claim, prices, root = fixture
    record(root, claim, evidence=pack, now=CAPTURE)
    pending = score(root, prices, now=CAPTURE)[0]
    assert pending["status"] == "pending"
    assert pending["entry_session"] == "2026-01-13"
    assert pending["maturity_session"] == "2026-01-21"
    result = score(root, prices, now=LATER)[0]
    assert result["status"] == "matured_uncalibrated"
    assert result["brier"] == pytest.approx(.09)
    prices.loc["2026-02-01":] *= 2
    after = score(root, prices, now=LATER)[0]
    assert result["brier"] == after["brier"]
    assert result["historical_base_rate"] == after["historical_base_rate"]


def test_backfill_cannot_be_called_prospective(fixture):
    pack, claim, prices, root = fixture
    with pytest.raises(ContractError, match="backfill"):
        record(root, claim, evidence=pack, now=LATER)
    record(root, claim | {"mode": "historical_reconstruction"}, evidence=pack, now=LATER)
    result = score(root, prices, now=LATER)[0]
    assert result["status"] == "reconstruction_not_prospective"
    assert result["performance_eligible"] is False


@pytest.mark.parametrize("changes", [{"probability": float("nan")}, {"horizon": True},
    {"probability": 1.1}, {"ticker": "=FORMULA"}, {"captured_at_utc": "2025-01-01"},
    {"fact_ids": []}, {"fact_ids": ["unknown_fact"]}])
def test_invalid_forecast_claims_are_not_accepted(fixture, changes):
    pack, claim, _, root = fixture
    with pytest.raises(ContractError):
        record(root, claim | changes, evidence=pack, now=CAPTURE)


def test_missing_session_cannot_shorten_a_forecast_horizon(fixture):
    pack, claim, prices, root = fixture
    record(root, claim, evidence=pack, now=CAPTURE)
    result = score(root, prices.drop(pd.Timestamp("2026-01-16")), now=LATER)[0]
    assert result["status"] == "missing_scoring_prices"


def test_duplicating_record_under_another_name_cannot_inflate_evidence(fixture):
    pack, claim, prices, root = fixture
    path = record(root, claim, evidence=pack, now=CAPTURE)
    (root / "duplicate.json").write_bytes(path.read_bytes())
    with pytest.raises(ContractError, match="Corrupt"):
        score(root, prices, now=LATER)


def test_forecast_archives_evidence_and_rejects_tampering(fixture):
    pack, claim, prices, root = fixture
    record(root, claim, evidence=pack, now=CAPTURE)
    pack.write_text("{}")
    assert score(root, prices, now=LATER)[0]["status"] == "matured_uncalibrated"
    next((root / "evidence").glob("*.json")).write_text("{}")
    with pytest.raises(ContractError, match="Corrupt"):
        score(root, prices, now=LATER)


def test_repeated_overlapping_claims_do_not_create_independent_evidence(fixture):
    pack, claim, prices, root = fixture
    record(root, claim, evidence=pack, now=CAPTURE)
    result = score(root, prices, now=LATER)[0]
    summary = summarize([result, result | {"id": "other"}, result | {"id": "third"}])[0]
    assert summary["matured_claims"] == 3
    assert summary["nonoverlapping_claims"] == 1
    assert summary["status"] == "immature"
    assert summary["action_authorized"] is False
