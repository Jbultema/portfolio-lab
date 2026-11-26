import copy

import pytest

from portfolio_lab.brief_agent import validate_narrative
from portfolio_lab.contracts import ContractError
from portfolio_lab.editorial import (
    copy_issues,
    daily_note,
    render_fact_tokens,
    selection_description,
    warning_assessment,
)


@pytest.fixture
def pack():
    values = {"SPY.return.21": -.0688, "QQQ.drawdown.63": -.1655, "SPY.trend.200": -.025,
              "market.breadth": 2/3, "market.breadth.coverage": 9,
              "QQQ.return.1": -.0065, "QQQ.return.5": -.039,
              "market.breadth.change.1": 0., "market.breadth.change.21": -.1111,
              "XLP.return.21": .0591, "XLP.relative.21": .1279,
              "XLK.return.21": -.177, "XLK.relative.21": -.1082,
              "IEF.return.21": .014, "GLD.return.21": -.12, "HYG.relative_IEF.21": -.023,
              "trade-bot.cash": .526, "trade-bot.equity": .474, "trade-bot.cash.change.1": -.088,
              "trade-bot.scheduled": True, "trade-bot.vol_scale": .474}
    return {"state": "defensive_stress", "facts": [{"id": k, "value": v, "unit": "percent", "label": k} for k, v in values.items()],
            "sector_leadership": [{"ticker": "XLP", "relative_return_21": .1279}, {"ticker": "XLK", "relative_return_21": -.1082}],
            "bots": [{"system": "trade-bot", "cash": .526, "equity_risk_proxy": .474,
                      "eligible_for_comparison": True, "reason": "volatility_budget_reduced", "as_of": "2026-11-25",
                      "target_holdings": {"MSFT": .25, "META": .224}}]}


def test_note_has_a_view_and_quantified_counterevidence(pack):
    note = daily_note(pack)
    assert "sector participation holds up" in note["headline"]
    prose = " ".join(c["text"] for s in note["sections"] for c in s["claims"])
    assert "6 of 9 sectors" in prose
    assert "16.6%" in prose and "6.9%" in prose
    assert "Cash decreased 8.8 percentage points" in prose
    assert "scheduled selection review" in prose
    assert "Largest targets: MSFT 25.0%" in prose
    assert "0.0%" not in note["headline"]
    assert not copy_issues(prose)
    ids = {f["id"] for f in pack["facts"]}
    assert all(c["evidence_ids"] and set(c["evidence_ids"]) <= ids for s in note["sections"] for c in s["claims"])


def test_view_changes_when_participation_breaks(pack):
    changed = copy.deepcopy(pack)
    next(f for f in changed["facts"] if f["id"] == "market.breadth")["value"] = 2/9
    note = daily_note(changed)
    assert "extends beyond technology" in note["headline"]
    assert "Weak participation reinforces" in note["sections"][0]["claims"][1]["text"]


def test_stale_model_does_not_acquire_a_current_positioning_claim(pack):
    pack["bots"][0]["eligible_for_comparison"] = False
    pack["bots"][0]["as_of"] = "2026-11-24"
    claim = daily_note(pack)["sections"][-1]["claims"][0]["text"]
    assert "excluded" in claim and "2026-11-24" in claim
    assert "47.4%" not in claim


def test_relative_winner_is_not_described_as_an_absolute_gain(pack):
    next(f for f in pack["facts"] if f["id"] == "XLP.return.21")["value"] = -.01
    note = daily_note(pack)
    leadership = next(s for s in note["sections"] if s["heading"] == "Leadership and defensive assets")
    assert "still lost money" in leadership["claims"][0]["text"]


@pytest.mark.parametrize("phrase", ["It is important to note", "In conclusion", "a nuanced picture",
                                    "Only time will tell", "This underscores the importance of", "a game-changer"])
def test_editorial_regressions_are_detected(phrase):
    assert copy_issues(phrase)


def test_normal_financial_vocabulary_is_not_treated_as_filler():
    assert not copy_issues("Credit spreads widened while the yield curve steepened. Sector breadth improved.")


def test_reviewed_prose_can_use_verified_numbers_and_descriptive_headings(pack):
    brief = {"headline": "Technology weakness persists", "sections": [{"heading": "Technology and the broader market", "claims": [
        {"text": "QQQ's drawdown from its recent high is [[QQQ.drawdown.63]].", "evidence_ids": ["QQQ.drawdown.63"], "kind": "observation"}]}]}
    validate_narrative(brief, pack)
    facts = {f["id"]: f for f in pack["facts"]}
    text = render_fact_tokens(brief["sections"][0]["claims"][0]["text"], facts)
    assert "-16.6%" in text and "[[" not in text
    brief["sections"][0]["claims"][0]["evidence_ids"] = ["SPY.return.21"]
    with pytest.raises(ContractError, match="matching citation"):
        validate_narrative(brief, pack)


def test_filler_and_unsupported_numerical_claims_are_rejected(pack):
    brief = {"headline": "Technology weakness persists", "sections": [{"heading": "Market", "claims": [
        {"text": "It is important to note that technology is weak.", "evidence_ids": ["QQQ.drawdown.63"], "kind": "interpretation"}]}]}
    with pytest.raises(ContractError, match="editorial"):
        validate_narrative(brief, pack)
    brief["sections"][0]["claims"][0]["text"] = "QQQ fell 99%."
    with pytest.raises(ContractError, match="Numeric"):
        validate_narrative(brief, pack)


def test_missing_evidence_does_not_produce_a_generic_macro_or_price_paragraph():
    note = daily_note({"state": "insufficient_data", "facts": [], "bots": [], "sector_leadership": []})
    assert note["sections"] == []
    assert note["headline"] == "Market coverage is incomplete"


def test_slow_selection_and_absent_emergency_exit_are_explicit():
    text = selection_description({"system": "rotation-trader", "rules": {
        "cadence": "monthly", "momentum_lookbacks": [126, 252], "daily_emergency_exit": False}})
    assert "six and twelve months" in text
    assert "month-end" in text
    assert "no daily emergency-exit" in text
    assert selection_description({"system": "rotation-trader", "rules": {}}) == ""


def test_model_disagreement_is_explained_without_repeating_the_schedule(pack):
    pack["facts"] += [{"id": k, "value": v, "unit": "percent", "label": k} for k, v in {
        "rotation-trader.cash": 0., "rotation-trader.equity": 1., "XLE.return.21": -.107}.items()]
    pack["bots"].append({"system": "rotation-trader", "cash": 0., "equity_risk_proxy": 1.,
                         "eligible_for_comparison": True, "reason": "frozen_sector_allocation_held",
                         "as_of": "2026-11-25", "target_holdings": {"XLE": .5, "XLV": .5},
                         "rules": {"cadence": "monthly", "momentum_lookbacks": [126, 252], "daily_emergency_exit": False}})
    prose = " ".join(c["text"] for s in daily_note(pack)["sections"] for c in s["claims"])
    assert prose.count("There is no daily emergency-exit rule.") == 1
    assert "still targets 50.0% in XLE" in prose
    assert "model disagreement is material" in prose
    assert "realized return paths" in prose


def test_warning_appraisal_compares_base_rate_and_keeps_unmatured_outcomes_unknown():
    summary = {"signal_scorecards": [
        {"ticker": "QQQ", "horizon": 5, "signal": "early_watch", "precision": 10/27, "base_rate": 12/35, "warnings": 27, "matured": 35},
        {"ticker": "QQQ", "horizon": 5, "signal": "trade-bot_low_equity", "precision": 4/6, "recall": 4/12, "warnings": 6},
        {"ticker": "QQQ", "horizon": 5, "signal": "confirmed_stress", "warnings": 0}]}
    prose = " ".join(warning_assessment(summary))
    assert "37.0%" in prose and "34.3%" in prose and "+2.8 percentage points" in prose
    assert "little separation" in prose
    assert "6 completed origins" in prose
    assert "not yet measurable" in prose
    assert "not the return earned" in prose
    assert warning_assessment({}) == []
