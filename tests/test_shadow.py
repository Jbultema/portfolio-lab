import json

import exchange_calendars as xcals
import pandas as pd
import pytest

from portfolio_lab.audit import evaluate_shadow
from portfolio_lab.contracts import ContractError, json_hash
from portfolio_lab.research import pbo_diagnostic


def sessions():
    return xcals.get_calendar("XNYS", start="2026-11-20", end="2026-12-21").sessions


def record(folder, captured="2026-11-25T23:00:00+00:00"):
    folder.mkdir()
    payload = {
        "lineage": "frozen",
        "captured_at_utc": captured,
        "signal": {"target_holdings": {"SPY": 0.5}},
        "expiry_after_executed_sessions": 5,
    }
    payload["record_sha256"] = json_hash(payload)
    (folder / "2026-11-25.json").write_text(json.dumps(payload))
    return folder


def test_shadow_never_backdates_fill_to_historical_signal_day(tmp_path):
    dates = pd.bdate_range("2026-11-20", "2026-11-25")
    prices = pd.DataFrame(100.0, index=dates, columns=["SPY"])
    result = evaluate_shadow(record(tmp_path / "shadow"), prices, pd.Series(0.0, index=dates))
    assert result["status"] == "pending_future_execution"


def test_shadow_after_close_fills_later_and_expires_without_refresh(tmp_path):
    dates = sessions()
    prices = pd.DataFrame(100.0, index=dates, columns=["SPY"])
    result = evaluate_shadow(record(tmp_path / "shadow"), prices, pd.Series(0.0, index=dates))
    assert pd.Timestamp(result["first_execution"]) > pd.Timestamp("2026-11-25")
    assert result["metrics"]["total_return"] < 0
    assert result["action_authorized"] is False


def test_corrupt_shadow_fails(tmp_path):
    folder = record(tmp_path / "shadow")
    payload = json.loads((folder / "2026-11-25.json").read_text())
    payload["signal"]["target_holdings"]["SPY"] = 1.0
    (folder / "2026-11-25.json").write_text(json.dumps(payload))
    dates = sessions()
    with pytest.raises(ContractError, match="Corrupt"):
        evaluate_shadow(
            folder, pd.DataFrame(100.0, index=dates, columns=["SPY"]), pd.Series(0.0, index=dates)
        )


def test_pbo_deduplicates_equivalent_paths():
    dates = pd.bdate_range("2010-01-01", periods=800)
    import numpy as np

    rng = np.random.default_rng(2)
    a, b = rng.normal(0, 0.01, (2, 800))
    result = pbo_diagnostic(pd.DataFrame({"a": a, "duplicate_a": a, "b": b}, index=dates))
    assert result["distinct_paths"] == 2
    assert result["splits"] == 70


def test_capture_after_early_close_waits_until_next_session(tmp_path):
    dates = sessions()
    result = evaluate_shadow(
        record(tmp_path / "shadow", captured="2026-11-27T19:00:00+00:00"),
        pd.DataFrame(100.0, index=dates, columns=["SPY"]),
        pd.Series(0.0, index=dates),
    )
    assert result["first_execution"] == "2026-11-30"


def test_shadow_rejects_invented_holiday_session(tmp_path):
    dates = pd.bdate_range("2026-11-20", periods=20)
    with pytest.raises(ContractError, match="actual NYSE"):
        evaluate_shadow(
            record(tmp_path / "shadow"),
            pd.DataFrame(100.0, index=dates, columns=["SPY"]),
            pd.Series(0.0, index=dates),
        )


def test_shadow_latest_capture_wins_same_execution_close(tmp_path):
    folder = record(tmp_path / "shadow", captured="2026-11-25T23:00:00+00:00")
    path = folder / "2026-11-25.json"
    payload = json.loads(path.read_text())
    payload["captured_at_utc"] = "2026-11-27T17:00:00+00:00"
    payload["signal"]["target_holdings"] = {"SPY": 0.0}
    payload["record_sha256"] = json_hash(
        {k: v for k, v in payload.items() if k != "record_sha256"}
    )
    # Deliberately sort the newer capture first by filename.
    (folder / "000-newer.json").write_text(json.dumps(payload))
    dates = sessions()
    result = evaluate_shadow(
        folder, pd.DataFrame(100.0, index=dates, columns=["SPY"]),
        pd.Series(0.0, index=dates),
    )
    assert result["metrics"]["total_return"] == 0.0
