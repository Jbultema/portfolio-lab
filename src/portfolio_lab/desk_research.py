"""Transparent research lenses. Descriptive evidence, not allocation rules or probabilities."""

import math

import pandas as pd

MARKETS = {
    "SPY": "US large cap", "QQQ": "Nasdaq 100", "RSP": "Equal-weight US", "SMH": "Semiconductors",
    "IWM": "US small cap", "EFA": "Developed ex-US", "VEA": "Developed ex-US", "EEM": "Emerging markets",
    "VWO": "Emerging markets", "HYG": "High-yield bonds", "LQD": "Investment-grade bonds",
    "IEF": "Intermediate Treasuries", "TLT": "Long Treasuries", "SHY": "Short Treasuries",
    "GLD": "Gold", "DBC": "Broad commodities", "USO": "Oil fund", "UUP": "US dollar fund",
    "VNQ": "Real estate", "MTUM": "Momentum", "QUAL": "Quality", "VLUE": "Value",
}


def research_lenses(pack):
    values = {f["id"]: f["value"] for f in pack["facts"]}

    def v(key):
        value = values.get(key)
        return value if isinstance(value, (float, int)) and math.isfinite(value) else None

    clusters = []

    def cluster(name, keys, test, meaning, caveat):
        known = all(v(k) is not None for k in keys)
        clusters.append({"name": name, "status": test(*[v(k) for k in keys]) if known else "unavailable",
                         "evidence_ids": keys, "meaning": meaning, "caveat": caveat})

    cluster("Equity structure", ["QQQ.drawdown.63", "SPY.trend.200"],
            lambda dd, trend: "adverse" if dd <= -.10 and trend < 0 else "supportive" if dd > -.05 and trend > 0 else "mixed",
            "Distinguishes a technology drawdown from deterioration in broader index structure.",
            "Damage confirmation, not an independent prediction of a crash date.")
    cluster("Participation", ["market.breadth", "RSP.relative.21"],
            lambda b, r: "supportive" if b >= 2/3 and r > 0 else "adverse" if b < .5 and r < 0 else "mixed",
            "Tests whether equal-weight performance and sector participation confirm headline indices.",
            "Equal-weight outperformance during a falling market can be relative shelter, not an absolute uptrend.")
    cluster("Leadership migration", ["SMH.relative.21", "sector.defensive_minus_cyclical.21"],
            lambda smh, defensive: "adverse" if smh < 0 and defensive > 0 else "supportive" if smh > 0 and defensive < 0 else "mixed",
            "Technology weakness alongside defensive leadership is consistent with rotation away from growth risk.",
            "Defensive and cyclical baskets are fixed sector proxies, not economic causal attribution.")
    cluster("Credit-market proxy", ["HYG.relative_IEF.21"],
            lambda r: "adverse" if r < -.02 else "supportive" if r > .02 else "mixed",
            "Compares high-yield fund total return with intermediate Treasuries over a month.",
            "Not a credit spread: duration, coupons and rates differ. Check observed OAS in the current macro panel.")
    cluster("Dollar / duration", ["UUP.return.21", "IEF.return.21"],
            lambda dollar, bonds: "adverse" if dollar > .02 and bonds < -.02 else "supportive" if dollar < -.02 and bonds > .02 else "mixed",
            "A rising dollar and falling Treasury fund can coincide with tighter market financing conditions.",
            "This is not a measured global liquidity cycle or an estimate of policy intent.")
    theses = [
        {"name": "Technology-led unwind", "horizon": "Days to weeks", "cluster": "Equity structure",
         "support": ["QQQ.drawdown.63", "SMH.relative.21", "SPY.trend.200"],
         "counter": ["market.breadth", "RSP.relative.21"],
         "interpretation": "The main question is whether weakness spreads from technology into the rest of the equity market. Sector participation and equal-weight returns provide the cross-check.",
         "invalidation": "Broad repair requires SPY above its long trend, QQQ within five percent of its recent high and at least two thirds of stable sectors above trend.",
         "bot_implication": "Trade Bot controls technology exposure. Rotation Trader can retain other sectors. Their holdings and rebalance dates explain more than a shared risk label."},
        {"name": "Rotation or broad liquidation?", "horizon": "Weeks to months", "cluster": "Leadership migration",
         "support": ["sector.defensive_minus_cyclical.21", "RSP.relative.21"],
         "counter": ["market.breadth", "SPY.return.21", "HYG.relative_IEF.21"],
         "interpretation": "Check absolute sector returns alongside the rankings. Defensive sectors gaining while technology falls supports a rotation view; defensive sectors also falling offers less protection.",
         "invalidation": "The rotation interpretation weakens if participation collapses and credit deteriorates together; it also changes if technology regains broad relative leadership.",
         "bot_implication": "Monthly sector holdings can lag a fast transition. A native timing warning waiting for rebalance is a schedule mismatch to review, not an applied defensive trade."},
        {"name": "Macro confirmation still matters", "horizon": "Months to quarters", "cluster": "Dollar / duration",
         "support": ["UUP.return.21", "IEF.return.21"], "counter": ["GLD.return.21", "HYG.relative_IEF.21"],
         "interpretation": "A longer-term macro view needs economic releases and financing data. The price panel can show where investors are moving, while the current-vintage macro panel tests whether credit and growth tell the same story.",
         "invalidation": "Reassess when measured credit conditions, inflation momentum or growth change. Direct positioning data are still missing.",
         "bot_implication": "Longer-horizon views remain conditional. No macro narrative overrides a bot's frozen specification or a failed data gate."},
    ]
    for thesis in theses:
        thesis["status"] = next(c["status"] for c in clusters if c["name"] == thesis["cluster"])
        thesis["support"] = [k for k in thesis["support"] if v(k) is not None]
        thesis["counter"] = [k for k in thesis["counter"] if v(k) is not None]
    headlines = {
        "defensive_stress": "Technology losses coincide with broad-index trend damage; broad repair is not confirmed.",
        "fragile_transition": "Fragile participation or technology weakness persists; headline-index strength needs confirmation.",
        "broad_risk_on": "Broad index structure and sector participation align; this is observed strength, not a crash-risk estimate.",
        "mixed": "Markets are sending a mixed message; distinguish relative leadership from absolute protection.",
    }
    return {"version": "research-lenses-1", "clusters": clusters, "theses": theses,
            "headline": headlines.get(pack.get("state"), "Market evidence is incomplete."),
            "confidence": "Descriptive only; forecast probabilities and predictive edge are uncalibrated.",
            "independence": "Clusters organize related evidence; they are not independent votes or an additive crash score."}


# Per-series age limits are disclosure gates, not release-date estimates.
MACRO_GROUPS = {
    "Growth & labor": [("INDPRO", 65), ("PAYEMS", 65), ("UNRATE", 65), ("ICSA", 21), ("CFNAI", 65)],
    "Inflation": [("CPIAUCSL", 65), ("CPILFESL", 65), ("PCEPILFE", 75), ("T5YIE", 10)],
    "Monetary & credit": [("DFF", 10), ("DFII10", 10), ("T10Y2Y", 10), ("BAMLH0A0HYM2", 10), ("NFCI", 21)],
    "Liquidity": [("WALCL", 21), ("WDTGAL", 21), ("RRPONTSYD", 10), ("RESBALNS", 21), ("M2SL", 75)],
    "Fiscal": [("FYFSD", 450), ("GFDEGDQ188S", 150)],
    "Positioning": [],
}


def macro_observations(series, cutoff):
    observations = series.get("observations", [])
    usable = [o for o in observations if pd.Timestamp(o["observation_date"]) <= cutoff and math.isfinite(o["value"])]
    usable.sort(key=lambda o: o["observation_date"])
    if len({o["observation_date"] for o in usable}) != len(usable):
        raise ValueError("Duplicate macro observation date")
    return usable


def macro_rows(context):
    """No inferred release timing, invented positions, or retroactive point-in-time claims."""
    today = pd.Timestamp(context["captured_at_utc"]).tz_convert("UTC").tz_localize(None).normalize()
    catalog = {s["id"]: s for s in context.get("series", [])}
    rows = []
    for group, specs in MACRO_GROUPS.items():
        for identifier, limit in specs:
            series = catalog.get(identifier, {})
            usable = macro_observations(series, today)
            last = usable[-1] if usable else None
            age = (today - pd.Timestamp(last["observation_date"])).days if last else None
            rows.append({"Cycle": group, "Series": identifier, "Indicator": series.get("name", identifier),
                         "Latest": last["value"] if last else None, "Observation": last["observation_date"] if last else None,
                         "Age / days": age, "Coverage": "missing" if last is None else "stale" if age > limit else "within_age_limit",
                         "Change / observation": last["value"] - usable[-2]["value"] if len(usable) > 1 else None,
                         "Change / 3 observations": last["value"] - usable[-4]["value"] if len(usable) > 3 else None,
                         "Source": series.get("source_url", f"https://fred.stlouisfed.org/series/{identifier}")})
    return rows


def macro_insights(context):
    """Simple, inspectable transformations of current-vintage observations only."""
    coverage = {r["Series"]: r for r in macro_rows(context)}
    series = {s["id"]: s for s in context.get("series", [])}
    output = []
    specs = [
        ("Growth", "INDPRO", 12, "yoy", "Industrial production year-on-year", "Growth in industrial output, not a GDP forecast."),
        ("Labor", "PAYEMS", 3, "difference", "Payroll change over three months / thousands", "Net change in current-revised payroll levels; not a first-release jobs surprise."),
        ("Labor", "UNRATE", 3, "difference", "Unemployment change over three months / pp", "Rising unemployment can confirm labor cooling; direction alone does not date a recession."),
        ("Inflation", "CPILFESL", 12, "yoy", "Core CPI year-on-year", "Current revised index change, not a consensus surprise."),
        ("Inflation", "CPILFESL", 3, "annualized", "Core CPI three-month annualized pace", "A short annualized rate can be noisy; compare with the year-on-year pace."),
        ("Inflation", "PCEPILFE", 12, "yoy", "Core PCE year-on-year", "Different coverage from CPI; not an independent market vote."),
        ("Credit", "BAMLH0A0HYM2", 20, "difference", "High-yield OAS change over twenty observations / pp", "Observed credit spread, unlike the HYG/IEF fund-return proxy."),
        ("Monetary", "DFII10", 20, "difference", "Ten-year real yield change over twenty observations / pp", "Higher real yields can pressure long-duration valuations; not an equity timing model."),
        ("Liquidity", "WALCL", 4, "pct", "Fed assets change over four weekly observations", "Balance-sheet stock only. Not global liquidity, reserve creation, or a complete net-liquidity formula."),
        ("Fiscal", "GFDEGDQ188S", 1, "difference", "Federal debt/GDP change over one quarterly observation / pp", "A fiscal stock ratio, not a measured fiscal impulse or a forecast of issuance."),
    ]
    for group, identifier, periods, mode, label, caveat in specs:
        cutoff = pd.Timestamp(context["captured_at_utc"]).tz_convert("UTC").tz_localize(None).normalize()
        records = macro_observations(series.get(identifier, {}), cutoff)
        row = coverage.get(identifier, {})
        usable = row.get("Coverage") == "within_age_limit" and len(records) > periods
        reason = "stale_or_missing_series" if row.get("Coverage") != "within_age_limit" else "insufficient_observations"
        old = records[-periods-1]["value"] if len(records) > periods else None
        if records and (mode in {"yoy", "annualized"} or identifier in {"PAYEMS", "UNRATE"}):
            months = pd.PeriodIndex([r["observation_date"] for r in records], freq="M")
            anchor = months[-1] - periods
            usable = row.get("Coverage") == "within_age_limit" and not months.has_duplicates and anchor in months
            old = records[months.get_loc(anchor)]["value"] if usable else None
            if row.get("Coverage") == "within_age_limit":
                reason = "missing_calendar_comparison_or_duplicate_month"
        value = None
        if usable:
            last = records[-1]["value"]
            if mode == "difference":
                value = last - old
            elif old > 0 and last > 0:
                value = (last / old) ** (12 / periods if mode == "annualized" else 1) - 1
        output.append({"group": group, "series": identifier, "label": label, "value": value,
                       "unit": "percent" if mode != "difference" else "native_difference",
                       "observation": row.get("Observation"), "coverage": row.get("Coverage", "missing"),
                       "unavailable_reason": None if value is not None else reason,
                       "caveat": caveat, "source": row.get("Source")})
    return output


def macro_synthesis(context):
    insights = macro_insights(context)

    def value(identifier, text=None):
        return next((i["value"] for i in insights if i["series"] == identifier and (text is None or text in i["label"])), None)

    messages = []
    production, payroll, unemployment = value("INDPRO"), value("PAYEMS"), value("UNRATE")
    if production is not None and payroll is not None and unemployment is not None:
        messages.append({"cycle": "Growth & labor", "text":
                         f"Industrial production is {production:+.2%} year on year. Payrolls changed by {payroll * 1000:+,.0f} over three months; unemployment changed {unemployment:+.1f} percentage points. "
                         + ("Both output and payroll growth remain positive." if production > 0 and payroll > 0 else "Output and payrolls both weakened." if production < 0 and payroll < 0 else "Output and job growth point in different directions."),
                         "series": ["INDPRO", "PAYEMS", "UNRATE"]})
    yoy, pace = value("CPILFESL", "year-on-year"), value("CPILFESL", "annualized")
    if yoy is not None and pace is not None:
        messages.append({"cycle": "Inflation", "text":
                         f"Core CPI rose at a {pace:.2%} annualized pace over three months, compared with {yoy:.2%} year-on-year. "
                         + ("Recent inflation is running faster than the year-on-year rate." if pace > yoy else "The recent pace is slower than the year-on-year rate." if pace < yoy else "The two rates are equal."),
                         "series": ["CPILFESL"]})
    spread = value("BAMLH0A0HYM2")
    if spread is not None:
        messages.append({"cycle": "Credit", "text":
                         f"High-yield credit spreads {'widened' if spread > 0 else 'narrowed' if spread < 0 else 'were unchanged at'} {abs(spread) * 100:.1f} basis points over twenty observations. "
                         + ("Credit is signaling greater financing pressure on this measure." if spread > 0 else "Credit is providing less support for a broad financial-stress interpretation." if spread < 0 else "There is no net change on this measure."),
                         "series": ["BAMLH0A0HYM2"]})
    liquidity = value("WALCL")
    if liquidity is not None:
        messages.append({"cycle": "Liquidity", "text":
                         f"Fed assets changed {liquidity:+.2%} over four weekly observations. Reserve balances, Treasury cash and reverse repo need to be checked separately before calling this a change in overall liquidity.", "series": ["WALCL"]})
    return messages
