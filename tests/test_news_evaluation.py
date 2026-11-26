import numpy as np
import pandas as pd
import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.news_evaluation import (
    controls,
    family_check,
    load_screen,
    paired_block,
    select_development,
)


def test_development_selection_cannot_use_holdout_performance():
    rows, specs = [], {}
    for asset in ("SPY", "QQQ"):
        for period in ("development", "holdout_diagnostic"):
            for name, cagr, dd in [(f"buy_hold_{asset}", .1, -.4), (f"a_{asset}", .1, -.2), (f"b_{asset}", .09, -.3)]:
                rows.append({"scenario": "base", "period": period, "id": name, "cagr": cagr, "max_drawdown": dd})
                if not name.startswith("buy"):
                    specs[name] = {"risk_asset": asset, "kind": "risk_budget"}
    table = pd.DataFrame(rows)
    first = select_development(table, specs)
    table.loc[table.period.eq("holdout_diagnostic") & table.id.str.startswith("b_"), "cagr"] = 100
    assert select_development(table, specs) == first
    assert first["SPY"]["id"] == "a_SPY"


def test_multiple_comparison_check_is_deterministic_and_counts_all_variants():
    rng = np.random.default_rng(1)
    x = pd.DataFrame(rng.normal(0, .01, (300, 4)))
    a = family_check(x, reps=25)
    assert a == family_check(x, reps=25)
    assert a["candidates"] == 4 and 0 < a["family_pvalue"] <= 1


def test_paired_bootstrap_and_small_sample():
    index = pd.bdate_range("2020-01-01", periods=300)
    s = pd.Series(.001, index=index)
    result = paired_block(s, s * 0, reps=25)
    assert np.isclose(result["lower95"], .252)
    assert paired_block(s.iloc[:10], s.iloc[:10])["status"] == "insufficient_observations"


def test_price_controls_do_not_depend_on_future_prices():
    index = pd.bdate_range("2018-01-01", periods=300)
    p = pd.DataFrame(np.arange(300) + 100., index=index, columns=["SPY"])
    for asset in ("QQQ", "SHY", "XLK", "XLY", "XLI", "XLF", "XLP", "XLV", "XLU"):
        p[asset] = p.SPY
    a = controls(p)
    p.iloc[250:] *= 100
    b = controls(p)
    for name in a:
        pd.testing.assert_frame_equal(a[name].iloc[:250], b[name].iloc[:250])
        assert np.allclose(a[name].sum(axis=1), 1)


def test_proxy_input_cannot_claim_live_authority(tmp_path):
    import json

    (tmp_path / "manifest.json").write_text(json.dumps({"kind": "news_proxy_etf_screen", "action_authorized": True}))
    with pytest.raises(ContractError):
        load_screen(tmp_path)


def test_monthly_price_control_waits_for_the_comparable_vintage_decision():
    index = pd.bdate_range("2018-01-01", periods=300)
    p = pd.DataFrame(100., index=index, columns=["SPY", "QQQ", "SHY", "XLK", "XLY", "XLI", "XLF", "XLP", "XLV", "XLU"])
    p.iloc[250:, 0] = 50.
    decisions = index[[220, 270, 290]]
    targets = controls(p, decisions)
    assert targets["price_only_monthly_SPY_floor0"].SPY.iloc[269] == 1
    assert targets["price_only_monthly_SPY_floor0"].SPY.iloc[270] == 0
    assert targets["price_only_SPY_floor0"].SPY.iloc[269] == 0
