from datetime import UTC, datetime

import pandas as pd
import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.position_context import capture, section, validate
from portfolio_lab.position_stress import specifications


def example():
    return {"schema_version": 1, "system": "position-bot", "authority": "research_only", "status": "unavailable",
            "action_authorized": False, "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False,
            "captured_at_utc": datetime.now(UTC).isoformat(), "observations": [], "remaining_gates": ["Unverified releases"]}


@pytest.mark.parametrize("field", ["action_authorized", "portfolio_allocation_allowed", "automatic_promotion_allowed"])
def test_positioning_cannot_authorize_allocation(field):
    value = example()
    value[field] = True
    with pytest.raises(ContractError):
        validate(value)


def test_missing_positioning_is_missing_not_cash(tmp_path):
    value = capture(tmp_path)
    assert value["status"] == "unavailable"
    assert "target_holdings" not in value
    assert "not an allocation vote" in section(value)


def test_position_combinations_remain_long_only():
    days = pd.date_range("2020-01-01", periods=3)
    w = pd.DataFrame({"QQQ": [.5] * 3, "GLD": [.3] * 3}, index=days)
    targets = {n: w for n in ("trade_primary", "swing_primary", "rotation_primary")}
    pos = pd.DataFrame({"QQQ": [.2] * 3, "GLD": [.8] * 3}, index=days)
    for target in specifications(targets, pos, days, w.columns).values():
        assert target.ge(0).all().all() and target.sum(axis=1).le(1 + 1e-10).all()


def test_missing_position_session_cannot_be_filled_with_cash():
    days = pd.date_range("2020-01-01", periods=3)
    w = pd.DataFrame({"QQQ": [.5] * 3}, index=days)
    with pytest.raises(ContractError, match="zero-filled"):
        specifications({n: w for n in ("trade_primary", "swing_primary", "rotation_primary")}, w.iloc[:-1], days, w.columns)
