import pandas as pd
import pytest

from portfolio_lab.combination_robustness import episode_mask, rolling_pair


def test_rolling_pair_compares_same_sessions_and_does_not_fabricate_windows():
    index = pd.date_range("2020-01-02", periods=300, freq="B")
    a = pd.Series(.001, index=index)
    b = pd.Series(.0005, index=index)
    rows = rolling_pair(a, b)
    assert len(rows) == 3
    assert all(r["cagr_change"] > 0 and r["drawdown_change"] == 0 for r in rows)
    assert rolling_pair(a.iloc[:100], b.iloc[:100]) == []
    with pytest.raises(ValueError, match="identical observed sessions"):
        rolling_pair(a, b.iloc[1:])


def test_unfinished_episode_has_open_end_not_an_invalid_date_comparison():
    dates = pd.date_range("2026-05-29", periods=4, freq="B")
    assert list(episode_mask(dates, "2026-06-01", None)) == [False, True, True, True]
