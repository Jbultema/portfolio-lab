import copy
import json

import pandas as pd
import pytest

from portfolio_lab.desk_research import macro_insights, macro_rows, macro_synthesis, research_lenses


def context(identifier="CPILFESL", end="2026-10-01"):
    dates = pd.date_range(end=end, periods=25, freq="MS")
    return {"captured_at_utc": "2026-11-25T21:30:00+00:00", "series": [
        {"id": identifier, "name": identifier, "observations": [
            {"observation_date": str(d.date()), "value": 100 * 1.002 ** n} for n, d in enumerate(dates)]}]}


def test_macro_transforms_use_observation_frequency_and_native_units():
    insights = macro_insights(context())
    yoy, pace = [i for i in insights if i["series"] == "CPILFESL"]
    assert yoy["value"] == pytest.approx(1.002 ** 12 - 1)
    assert pace["value"] == pytest.approx(yoy["value"])
    assert all(i["value"] is None for i in insights if i["series"] != "CPILFESL")


def test_macro_stale_data_cannot_generate_current_insight():
    old = context(end="2025-01-01")
    assert next(r for r in macro_rows(old) if r["Series"] == "CPILFESL")["Coverage"] == "stale"
    assert all(i["value"] is None for i in macro_insights(old))


def test_macro_future_observations_ignored():
    base = context()
    changed = copy.deepcopy(base)
    changed["series"][0]["observations"].append({"observation_date": "2026-12-01", "value": 10000})
    assert macro_rows(changed) == macro_rows(base)
    assert macro_insights(changed) == macro_insights(base)


def test_macro_duplicate_dates_fail_closed():
    bad = context()
    bad["series"][0]["observations"].append(bad["series"][0]["observations"][-1])
    with pytest.raises(ValueError, match="Duplicate"):
        macro_rows(bad)


def test_missing_comparison_month_cannot_be_mistaken_for_three_month_annualization():
    missing = context()
    del missing["series"][0]["observations"][-4]
    yoy, pace = [i for i in macro_insights(missing) if i["series"] == "CPILFESL"]
    assert pace["value"] is None
    assert pace["unavailable_reason"] == "missing_calendar_comparison_or_duplicate_month"
    assert yoy["value"] == pytest.approx(1.002 ** 12 - 1)


def test_missing_intermediate_month_does_not_shift_comparison_dates():
    missing = context()
    del missing["series"][0]["observations"][-2]
    yoy, pace = [i for i in macro_insights(missing) if i["series"] == "CPILFESL"]
    assert yoy["value"] == pytest.approx(1.002 ** 12 - 1)
    assert pace["value"] == pytest.approx(yoy["value"])


def test_nonfinite_observation_cannot_enter_macro_insights():
    bad = context()
    bad["series"][0]["observations"][-1]["value"] = float("inf")
    values = [i["value"] for i in macro_insights(bad) if i["value"] is not None]
    assert all(abs(v) < 100 for v in values)


def test_macro_synthesis_never_invents_missing_cycles():
    messages = macro_synthesis(context())
    assert [m["cycle"] for m in messages] == ["Inflation"]
    assert "year-on-year" in messages[0]["text"]
    assert macro_synthesis(context(end="2020-01-01")) == []


def test_missing_cluster_evidence_is_not_a_neutral_or_supportive_vote():
    research = research_lenses({"facts": []})
    assert all(c["status"] == "unavailable" for c in research["clusters"])
    assert all(t["status"] == "unavailable" for t in research["theses"])
    assert "probability" not in json.dumps(research)


def test_stress_structure_requires_broad_confirmation():
    def pack(trend):
        return {"facts": [{"id": "QQQ.drawdown.63", "value": -.15}, {"id": "SPY.trend.200", "value": trend}]}
    assert research_lenses(pack(-.02))["clusters"][0]["status"] == "adverse"
    assert research_lenses(pack(.02))["clusters"][0]["status"] == "mixed"


def test_context_is_not_a_price_replay_input():
    import inspect

    from portfolio_lab.briefing import build_pack

    assert list(inspect.signature(build_pack).parameters) == ["specialists", "day"]
    assert "current-vintage" in __import__("portfolio_lab.desk_research", fromlist=["macro_insights"]).macro_insights.__doc__
