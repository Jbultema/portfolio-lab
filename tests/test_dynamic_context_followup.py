import pandas as pd

from portfolio_lab.dynamic_context_followup import budgets, specs


def test_context_followup_has_no_compulsory_diversification_and_is_prefix_invariant():
    index = pd.bdate_range("2020-01-01", periods=100)
    context = pd.DataFrame({"leadership_short": 0., "breadth_short": .2, "dd63": 0., "return5": 0., "above10": False}, index=index)
    spec = specs()[-1]
    baseline = budgets(context, spec)
    assert baseline.trade_primary.eq(1).all()
    context.loc[index[50]:, "leadership_short"] = .1
    context.loc[index[50]:, "breadth_short"] = 1.
    altered = budgets(context, spec)
    pd.testing.assert_frame_equal(baseline.iloc[:50], altered.iloc[:50])
    pd.testing.assert_frame_equal(altered.iloc[:80], budgets(context.iloc[:80], spec))
    assert altered.rotation_primary.eq(1).any()
    assert len(specs()) == 6
