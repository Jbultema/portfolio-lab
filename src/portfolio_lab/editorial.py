"""Research-note copy and editorial checks; no market-state or allocation authority."""

import math
import re

from portfolio_lab.contracts import ContractError

STYLE_VERSION = "research-desk-1"
EDITORIAL_INSTRUCTIONS = """Write an investment research note for an informed individual,
not a generic AI summary. Open with the specific market assessment and its strongest
evidence. Prioritize material changes; say when the view is unchanged. Separate the
current market, tactical horizon, and longer-term thesis. Explain model behavior using
the recorded rule and schedule. Identify the strongest counterargument and observable
conditions that would change the assessment. Omit sections without usable evidence.
Use short paragraphs and specific, descriptive headings, not a compulsory numbered
template, introductory throat-clearing, a list of obvious observations, or a concluding
recap. Prefer plain financial language. Avoid hype, metaphors, vague hedges, artificial
balance, and repeated 'not X but Y' constructions. Put essential qualifications next to
the claim; consolidate general methods and risk disclosures. Do not imitate an author's
voice, copy their themes, or imply access to proprietary models.
Every claim needs evidence IDs. Insert verified values using [[fact.id]] tokens instead
of writing numbers from memory. The renderer supplies the values. Distinguish measured
returns, relative returns, model targets, and executed holdings. State missing evidence
plainly. Do not invent causes, events, probabilities, consensus estimates or trades."""

_FILLER = (
    r"\bit(?:'s| is) important to note\b", r"\bin conclusion\b", r"\bonly time will tell\b",
    r"\bever[- ](?:evolving|changing)\b", r"\bdelve(?:s|d)? into\b", r"\bgame[- ]changer\b",
    r"\b(?:navigate|navigating) (?:the |today's )?(?:complex|dynamic|market) landscape\b",
    r"\bthis (?:underscores|highlights) the importance of\b", r"\ba nuanced picture\b",
    r"\bnot (?:just|merely)\b.{0,90}\bbut (?:also|rather)\b", r"\ba testament to\b",
)
FACT_TOKEN = re.compile(r"\[\[([A-Za-z0-9_.:-]+)\]\]")
BOT_NAMES = {"trade-bot": "Trade Bot research control", "swing-trader": "Swing ETF control", "rotation-trader": "Rotation Trader"}
SECTOR_NAMES = {"XLB": "Materials", "XLE": "Energy", "XLF": "Financials", "XLI": "Industrials",
                "XLK": "Technology", "XLP": "Consumer staples", "XLU": "Utilities", "XLV": "Healthcare", "XLY": "Consumer discretionary"}
RULES = {
    "volatility_budget_reduced": "Volatility targeting is limiting exposure",
    "shadow_equity_drawdown_guard": "The strategy's drawdown guard is limiting exposure",
    "scheduled_selection_review": "Its scheduled selection review ran",
    "scheduled_selection_held": "It is holding the previous selection",
    "monthly_schedule_holding_prior_target": "Its monthly selection rule is holding the previous basket",
    "monthly_positive_12m_momentum_selection": "Its month-end review selected funds with positive twelve-month momentum",
    "frozen_sector_allocation_held": "Its sector allocation rule is holding the selected basket",
    "timing_warning_waiting_for_native_rebalance": "Its timing monitor has warned, but the rebalance rule has not changed the basket",
}


def copy_issues(text):
    """A narrow regression check, not an automated judgment of analytical quality."""
    return ["formulaic language" for pattern in _FILLER if re.search(pattern, text, re.I)]


def render_fact_tokens(text, facts):
    from portfolio_lab.briefing import display_value

    def replace(match):
        if match[1] not in facts:
            raise ContractError("Unknown narrative fact token")
        return display_value(facts[match[1]])

    return FACT_TOKEN.sub(replace, text)


def selection_description(bot):
    rules = bot.get("rules", {})
    if bot["system"] == "swing-trader" and rules.get("rebalance") == "planned_month_end":
        return "It selects at month-end using twelve-month momentum."
    if bot["system"] == "rotation-trader":
        parts = []
        if rules.get("momentum_lookbacks") == [126, 252]:
            parts.append("Its momentum inputs span six and twelve months.")
        if rules.get("cadence") == "monthly":
            parts.append("Selection is reviewed at month-end.")
        if rules.get("daily_emergency_exit") is False:
            parts.append("There is no daily emergency-exit rule.")
        return " ".join(parts)
    return ""


def warning_assessment(summary):
    """Retrospective diagnostic, kept separate from a session's causal evidence pack."""
    rows = {r["signal"]: r for r in summary.get("signal_scorecards", []) if r["ticker"] == "QQQ" and r["horizon"] == 5}
    paragraphs = []
    watch = rows.get("early_watch", {})
    if watch.get("precision") is not None and watch.get("base_rate") is not None:
        lift = watch["precision"] - watch["base_rate"]
        text = f"Early Watch was followed by a QQQ loss of at least 5% within five sessions on {watch['precision']:.1%} of its {watch['warnings']} completed warning origins. The rate across all {watch['matured']} completed origins was {watch['base_rate']:.1%}: a difference of {lift * 100:+.1f} percentage points. "
        text += "That is little separation from the background loss rate." if abs(lift) <= .05 else "Warnings concentrated subsequent losses above the background rate." if lift > 0 else "Warnings did not concentrate subsequent losses above the background rate."
        paragraphs.append(text)
    control = rows.get("trade-bot_low_equity", {})
    if control.get("precision") is not None and control.get("recall") is not None:
        paragraphs.append(f"Trade Bot's low-equity condition had a {control['precision']:.1%} subsequent-loss rate across {control['warnings']} completed origins and caught {control['recall']:.1%} of the loss origins. This measures the timing of its exposure condition against QQQ, not the return earned by its actual basket.")
    stress = rows.get("confirmed_stress", {})
    if stress and stress.get("warnings") == 0:
        paragraphs.append("Confirmed Stress has no warning origins with a completed five-session outcome in this window. Its predictive performance is not yet measurable.")
    if paragraphs:
        paragraphs.append("These are overlapping observations from one short, retrospective window. They neither validate a durable forecasting edge nor establish that any bot outperformed after costs.")
    return paragraphs


def daily_note(pack):
    """The same evidence-bound note feeds the dashboard, JSON brief and written report."""
    facts = {f["id"]: f for f in pack["facts"]}

    def number(key):
        value = facts.get(key, {}).get("value")
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

    def claim(text, keys, kind="interpretation"):
        return {"text": text, "evidence_ids": [k for k in keys if k in facts], "kind": kind}

    state = pack["state"]
    breadth = number("market.breadth")
    month = number("SPY.return.21")
    if state == "defensive_stress":
        headline = "Technology leads the decline; sector participation holds up" if breadth is not None and breadth >= .6 else "Equity weakness extends beyond technology"
    elif state == "broad_risk_on":
        headline = "Stocks advance with broad sector support" if month is not None and month > 0 else "Long-term trends hold through the pullback"
    elif state == "fragile_transition":
        headline = "Index gains have narrow support" if month is not None and month > 0 and breadth is not None and breadth < .5 else "Equity recovery remains incomplete"
    else:
        headline = "Equity trends and participation disagree" if breadth is not None else "Market coverage is incomplete"
    assessment = []
    dd, trend = number("QQQ.drawdown.63"), number("SPY.trend.200")
    if month is not None and dd is not None:
        price = f"SPY {'lost' if month < 0 else 'gained' if month > 0 else 'returned'} {abs(month):.1%} over the past month. QQQ is {abs(dd):.1%} below its three-month high."
        assessment.append(claim(price, ["SPY.return.21", "QQQ.drawdown.63"], "observation"))
    if trend is not None and breadth is not None:
        denominator = number("market.breadth.coverage")
        participation = f"{round(breadth * denominator)} of {int(denominator)} sectors" if denominator else f"{breadth:.0%} of covered sectors"
        text = f"SPY is {abs(trend):.1%} {'below' if trend < 0 else 'above' if trend > 0 else 'from'} its 200-session average; {participation} are above theirs. "
        text += "That gap leaves room for sector rotation even as the headline indices weaken." if trend < 0 and breadth >= .6 else "Weak participation reinforces the index decline." if trend < 0 and breadth < .5 else "Participation is supporting the longer-term trend." if trend > 0 and breadth >= 2/3 else "The index and sector readings have yet to align."
        assessment.append(claim(text, ["SPY.trend.200", "market.breadth", "market.breadth.coverage"]))
    sections = [{"heading": "Equities and participation", "claims": assessment}] if assessment else []
    changes = []
    daily, weekly = number("QQQ.return.1"), number("QQQ.return.5")
    if daily is not None and weekly is not None:
        changes.append(claim(f"QQQ {'fell' if daily < 0 else 'rose' if daily > 0 else 'was unchanged at'} {abs(daily):.1%} at this close and is {weekly:+.1%} over five sessions.", ["QQQ.return.1", "QQQ.return.5"], "observation"))
    equal_day, semi_day = number("RSP.return.1"), number("SMH.return.1")
    if equal_day is not None and semi_day is not None:
        changes.append(claim(f"Equal-weight US equities (RSP) returned {equal_day:+.1%} for the session; semiconductors (SMH) returned {semi_day:+.1%}.", ["RSP.return.1", "SMH.return.1"], "observation"))
    breadth_day, breadth_month = number("market.breadth.change.1"), number("market.breadth.change.21")
    if breadth_day is not None and breadth_month is not None:
        opening = "Sector participation was unchanged from the prior close" if abs(breadth_day) < .00001 else f"Sector participation {'improved' if breadth_day > 0 else 'fell'} {abs(breadth_day) * 100:.1f} percentage points from the prior close"
        text = f"{opening}; the change over a month is {breadth_month * 100:+.1f} points."
        if breadth_day > 0 and breadth_month < 0:
            text += " This session's improvement has not reversed the monthly deterioration."
        changes.append(claim(text, ["market.breadth.change.1", "market.breadth.change.21"]))
    if changes:
        sections.append({"heading": "Since the previous close", "claims": changes})
    leaders = []
    ranked = [r for r in pack.get("sector_leadership", []) if number(f"{r['ticker']}.return.21") is not None]
    if ranked:
        top = ranked[0]
        ticker = top["ticker"]
        absolute = number(f"{ticker}.return.21")
        text = f"{SECTOR_NAMES.get(ticker, ticker)} ({ticker}) leads relative to SPY over the month: {absolute:+.1%} in absolute terms and {top['relative_return_21'] * 100:+.1f} percentage points relative to the index. "
        text += "It has still lost money over this window." if absolute < 0 else ""
        leaders.append(claim(text.rstrip(), [f"{ticker}.return.21", f"{ticker}.relative.21", "SPY.return.21"]))
        bottom = ranked[-1]
        if bottom["ticker"] != ticker:
            t = bottom["ticker"]
            relation = "trailing" if bottom["relative_return_21"] < 0 else "ahead of"
            leaders.append(claim(f"{t} ranks last among the covered sectors, returning {number(f'{t}.return.21'):+.1%} and {relation} SPY by {abs(bottom['relative_return_21']) * 100:.1f} points.", [f"{t}.return.21", f"{t}.relative.21"], "observation"))
    bonds, gold, credit = number("IEF.return.21"), number("GLD.return.21"), number("HYG.relative_IEF.21")
    if bonds is not None and gold is not None:
        text = f"Intermediate Treasuries (IEF) returned {bonds:+.1%}; gold (GLD) returned {gold:+.1%} over the month. "
        text += "Treasuries have held up better than gold during this period." if bonds > gold else "Gold has held up better than Treasuries during this period."
        leaders.append(claim(text, ["IEF.return.21", "GLD.return.21"], "observation"))
    if credit is not None:
        leaders.append(claim(f"The HYG/IEF price ratio is {credit:+.1%} over the month, showing {'weaker' if credit < 0 else 'stronger' if credit > 0 else 'unchanged'} high-yield fund performance relative to Treasuries. Duration differences also affect this comparison.", ["HYG.relative_IEF.21"]))
    if leaders:
        sections.append({"heading": "Leadership and defensive assets", "claims": leaders})
    models = []
    for bot in pack["bots"]:
        if "cash" not in bot:
            continue
        name = BOT_NAMES[bot["system"]]
        if not bot["eligible_for_comparison"]:
            models.append(claim(f"{name} was last updated for {bot['as_of']}; it is excluded from the current-close comparison.", [f"{bot['system']}.cash"], "observation"))
            continue
        text = f"{name}: {bot['equity_risk_proxy']:.1%} in equity-risk instruments and {bot['cash']:.1%} unallocated cash. "
        if bot.get("defensive_proxy_exposure", 0) > .0001:
            text += f"Bond and gold instruments account for {bot['defensive_proxy_exposure']:.1%}. "
        text += RULES.get(bot.get("reason"), "The frozen native rule determines this target") + "."
        schedule = selection_description(bot)
        if schedule:
            text += " " + schedule
        if facts.get(f"{bot['system']}.scheduled", {}).get("value") is True:
            text += " A scheduled selection review also ran at this close."
        delta = number(f"{bot['system']}.cash.change.1")
        keys = [f"{bot['system']}.cash", f"{bot['system']}.equity"]
        keys += [k for k in (f"{bot['system']}.scheduled", f"{bot['system']}.vol_scale", f"{bot['system']}.drawdown_scale") if k in facts]
        if delta is not None:
            text += " Cash is unchanged from the previous close." if abs(delta) < .00005 else f" Cash {'increased' if delta > 0 else 'decreased'} {abs(delta) * 100:.1f} percentage points from the previous close."
            keys.append(f"{bot['system']}.cash.change.1")
        holdings = sorted(bot.get("target_holdings", {}).items(), key=lambda item: item[1], reverse=True)[:3]
        if holdings:
            text += " Largest targets: " + ", ".join(f"{t} {w:.1%}" for t, w in holdings) + "."
        models.append(claim(text, keys))
        weak = [(t, w, number(f"{t}.return.21")) for t, w in holdings if number(f"{t}.return.21") is not None and number(f"{t}.return.21") <= -.05]
        if weak and bot["system"] in {"swing-trader", "rotation-trader"}:
            ticker, weight, ret = min(weak, key=lambda item: item[2])
            text = f"{name} still targets {weight:.1%} in {ticker}, which lost {abs(ret):.1%} over the month. "
            text += "The held basket differs from the strongest recent sectors. " if ranked and ranked[0]["ticker"] not in bot.get("target_holdings", {}) else "The recent loss has not removed it from the target basket. "
            models.append(claim(text, [f"{ticker}.return.21", f"{bot['system']}.equity"]))
    comparable = [b for b in pack["bots"] if b.get("eligible_for_comparison") and "equity_risk_proxy" in b]
    if len(comparable) > 1:
        low, high = min(comparable, key=lambda b: b["equity_risk_proxy"]), max(comparable, key=lambda b: b["equity_risk_proxy"])
        if high["equity_risk_proxy"] - low["equity_risk_proxy"] >= .25:
            text = f"The model disagreement is material: {BOT_NAMES[low['system']]} targets {low['equity_risk_proxy']:.1%} equity-risk exposure versus {high['equity_risk_proxy']:.1%} for {BOT_NAMES[high['system']]}. "
            text += "These are different selection and risk rules, not independent votes that the market is safe. Target exposures alone do not establish which approach is working; that requires their realized return paths."
            models.append(claim(text, [f"{low['system']}.equity", f"{high['system']}.equity"]))
    if models:
        sections.append({"heading": "Model positioning", "claims": models})
    return {"headline": headline, "sections": sections, "editorial_version": STYLE_VERSION}
