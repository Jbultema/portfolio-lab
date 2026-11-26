"""Evidence-only interpretation. No strategy selection, orders, or allocation authority."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from portfolio_lab.contracts import Bundle, ContractError, digest, json_hash, load_bundle
from portfolio_lab.desk_research import MARKETS, research_lenses

BRIEF_VERSION = "market-desk-v2"
SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
SYSTEMS = ("trade-bot", "swing-trader", "rotation-trader")
DEFENSIVE_PROXIES = frozenset({"GLD", "IAU", "IEF", "TLT", "AGG", "BIL", "SHY", "SGOV"})
LIMITATIONS = [
    "Historical briefs are reconstructions using today's frozen specifications and revised adjusted prices, not captured forecasts.",
    "Shared price inputs and correlated momentum rules are not independent confirmations.",
    "Targets are not actual holdings, fills, or personalized trade instructions.",
    "No external news, point-in-time macro releases, options positioning, or calibrated crash probabilities are supplied.",
    "Cycle Tracker and the separate Swing stock shadow are not integrated in this evidence pack; neither casts a vote.",
    "Fundamental Event Trader has separate source-bound context and readiness gates; it is not a market-wide confirmation vote.",
]


@lru_cache(maxsize=1)
def calendar():
    return xcals.get_calendar("XNYS", start="1990-01-01", end="2040-12-31")


def completed_sessions(count: int, now: datetime | None = None) -> pd.DatetimeIndex:
    now = pd.Timestamp(now or datetime.now(UTC))
    if now.tzinfo is None or not 1 <= count <= 252:
        raise ContractError("Timezone-aware clock and 1..252 sessions required")
    cal = calendar()
    days = cal.sessions_in_range((now - pd.Timedelta(days=count * 3 + 20)).date(), now.date())
    # Fifteen minutes lets the closing auction settle. Half-days use actual closes.
    done = [d for d in days if cal.session_close(d) + pd.Timedelta(minutes=15) <= now]
    return pd.DatetimeIndex(done[-count:]).tz_localize(None)


def close_time(day) -> str:
    return (calendar().session_close(pd.Timestamp(day)) + pd.Timedelta(minutes=15)).isoformat()


@dataclass
class Specialist:
    bundle: Bundle
    signals: pd.DataFrame
    telemetry: dict
    identity: dict


def load_specialists(paths: list[Path], telemetry_root: Path) -> dict[str, Specialist]:
    output = {}
    for path in paths:
        bundle = load_bundle(path)
        name = bundle.manifest["system"]
        if name not in SYSTEMS or name in output:
            raise ContractError("Unexpected or duplicate specialist")
        root = telemetry_root / name
        meta = json.loads((root / "manifest.json").read_text())
        if meta.get("schema_version") != 1 or meta.get("system") != name or meta.get("bundle_sha256") != digest(path / "manifest.json"):
            raise ContractError(f"Telemetry bundle mismatch: {name}")
        if meta.get("signals_sha256") != digest(root / "signals.parquet"):
            raise ContractError(f"Telemetry integrity failed: {name}")
        signals = pd.read_parquet(root / "signals.parquet")
        if signals.index.has_duplicates or not signals.index.is_monotonic_increasing:
            raise ContractError("Invalid telemetry dates")
        if not signals.index.isin(bundle.prices.index).all():
            raise ContractError("Telemetry contains unpriced sessions")
        target_columns = [c for c in signals if c.startswith("target_") and c.removeprefix("target_") in bundle.prices]
        if not target_columns:
            raise ContractError("Telemetry must reconcile to frozen primary targets")
        reconstructed = signals[target_columns].rename(columns=lambda c: c.removeprefix("target_"))
        if set(reconstructed) != set(bundle.targets[bundle.manifest["primary_expert"]]):
            raise ContractError("Telemetry omits primary target instruments")
        primary = bundle.targets[bundle.manifest["primary_expert"]].reindex(index=signals.index, columns=reconstructed.columns)
        if not np.allclose(primary, reconstructed, atol=1e-10, rtol=1e-9):
            raise ContractError(f"Native diagnostic/target mismatch: {name}")
        output[name] = Specialist(bundle, signals, meta, {
            "bundle_sha256": digest(path / "manifest.json"),
            "telemetry_sha256": digest(root / "manifest.json"),
            "code_sha256": bundle.manifest["code_sha256"],
            "bundle_captured_at": bundle.manifest["created_at_utc"],
        })
    return output


def collect_telemetry(paths: list[Path], repos_root: Path, destination: Path) -> list[Path]:
    modules = {
        "trade-bot": "trade_bot.research.interpretation_export",
        "swing-trader": "swing_trader.interpretation_export",
        "rotation-trader": "rotation_trader.interpretation_export",
    }
    destination.mkdir(parents=True, exist_ok=False)
    usable, health = [], {}
    for path in paths:
        name = json.loads((path / "manifest.json").read_text())["system"]
        if name not in modules:
            raise ContractError("Unqualified telemetry provider")
        root = repos_root / name
        try:
            subprocess.run([
                str(root / ".venv/bin/python"), "-m", modules[name],
                "--bundle", str(path.resolve()), "--output", str((destination / name).resolve()),
            ], cwd=root, check=True, timeout=240, capture_output=True, text=True)
            usable.append(path)
            health[name] = {"status": "captured"}
        except (OSError, subprocess.SubprocessError) as exc:
            health[name] = {"status": "telemetry_unavailable", "error_type": type(exc).__name__}
    (destination / "telemetry_health.json").write_text(json.dumps(health, indent=2) + "\n")
    if not usable:
        raise ContractError("No usable native telemetry")
    fundamental = repos_root / "fundamental-event-trader"
    if (fundamental / ".venv/bin/python").is_file():
        try:
            from portfolio_lab.event_context import capture

            payload = capture(fundamental, destination=destination)
        except (OSError, ValueError, subprocess.SubprocessError):
            from portfolio_lab.event_context import unavailable

            payload = unavailable("qualification_check_failed")
        (destination / "fundamental_event.json").write_text(json.dumps(payload, indent=2) + "\n")
    return usable


def _number(value):
    if pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.number)):
        return round(float(value), 8)
    return str(value)


def market_panel(specialists: dict[str, Specialist], day) -> tuple[pd.DataFrame, str]:
    """One declared source per pack; never stitch prices across vendors."""
    day = pd.Timestamp(day)
    # Trade Bot carries the broadest cross-asset context; never blend its prices with another panel.
    for name in ("trade-bot", "rotation-trader", "swing-trader"):
        if name not in specialists:
            continue
        prices = specialists[name].bundle.prices.loc[:day]
        if not prices.empty and prices.index[-1] == day and {"SPY", "QQQ"} <= set(prices):
            return prices, name
    raise ContractError(f"No fresh benchmark source for {day.date()}")


def build_pack(specialists: dict[str, Specialist], day) -> dict:
    """Prefix-only pack. Forward outcomes and capture-clock identities stay outside."""
    day = pd.Timestamp(day)
    if not calendar().is_session(day):
        raise ContractError("A completed exchange session is required")
    prices, market_source = market_panel(specialists, day)
    expected = calendar().sessions_in_range(prices.index[0], day).tz_localize(None)
    if not expected.isin(prices.index).all():
        raise ContractError("Market panel has missing sessions")
    facts = []

    def fact(identifier, label, value, unit="number", source=market_source, role="monitor", observed=None):
        observed = pd.Timestamp(observed or day)
        facts.append({"id": identifier, "label": label, "value": _number(value), "unit": unit,
                      "source": source, "role": role, "observed_session": str(observed.date()),
                      "available_after_utc": close_time(observed)})

    for ticker in dict.fromkeys([*MARKETS, *SECTORS]):
        if ticker not in prices:
            continue
        series = prices[ticker]
        for n in (1, 5, 21, 63):
            value = series.pct_change(n, fill_method=None).iloc[-1]
            fact(f"{ticker}.return.{n}", f"{ticker} {n}-session return", value, "percent")
        fact(f"{ticker}.drawdown.63", f"{ticker} drawdown from 63-session high", series.div(series.rolling(63).max()).sub(1).iloc[-1], "percent")
        fact(f"{ticker}.trend.200", f"{ticker} distance from 200-session average", series.div(series.rolling(200).mean()).sub(1).iloc[-1], "percent")
        fact(f"{ticker}.vol.21", f"{ticker} annualized 21-session volatility", series.pct_change(fill_method=None).rolling(21).std().mul(np.sqrt(252)).iloc[-1], "percent")
        for n in (5, 21, 63):
            relative_return = series.pct_change(n, fill_method=None).iloc[-1] - prices.SPY.pct_change(n, fill_method=None).iloc[-1]
            fact(f"{ticker}.relative.{n}", f"{ticker} {n}-session return less SPY", relative_return, "percentage_points")
    if {"HYG", "IEF"} <= set(prices):
        ratio_return = prices.HYG.div(prices.IEF).pct_change(21, fill_method=None).iloc[-1]
        fact("HYG.relative_IEF.21", "HYG / IEF ratio 21-session return (not a spread)", ratio_return, "percent")
    sectors = prices.reindex(columns=list(SECTORS))
    observed = sectors.notna() & sectors.rolling(200).mean().notna()
    breadth = sectors.gt(sectors.rolling(200).mean()).sum(axis=1).div(observed.sum(axis=1).replace(0, np.nan))
    fact("market.breadth", "Stable-sector share above 200-session average", breadth.iloc[-1], "percent")
    fact("market.breadth.coverage", "Stable sectors with valid price and long-trend history", int(observed.iloc[-1].sum()), "sectors")
    defensive = sectors[["XLP", "XLU", "XLV"]].pct_change(21, fill_method=None).iloc[-1]
    cyclical = sectors[["XLY", "XLI", "XLF", "XLB"]].pct_change(21, fill_method=None).iloc[-1]
    spread = defensive.mean() - cyclical.mean() if defensive.notna().all() and cyclical.notna().all() else None
    fact("sector.defensive_minus_cyclical.21", "Equal-weight defensive less cyclical sector month return", spread, "percentage_points")
    for n in (1, 5, 21):
        value = breadth.diff(n).iloc[-1]
        fact(f"market.breadth.change.{n}", f"Sector breadth change over {n} sessions", value, "percentage_points")
    relative = sectors.pct_change(21, fill_method=None).iloc[-1].sub(prices.SPY.pct_change(21, fill_method=None).iloc[-1])
    leaders = [{"ticker": t, "relative_return_21": _number(v)} for t, v in relative.dropna().sort_values(ascending=False).items()]
    bots = []
    for name in SYSTEMS:
        if name not in specialists:
            bots.append({"system": name, "status": "missing", "eligible_for_comparison": False})
            continue
        specialist = specialists[name]
        targets = specialist.bundle.targets[specialist.bundle.manifest["primary_expert"]].loc[:day]
        signals = specialist.signals.loc[:day]
        if targets.empty or signals.empty:
            bots.append({"system": name, "status": "missing", "eligible_for_comparison": False})
            continue
        date = min(targets.index[-1], signals.index[-1])
        weights = targets.loc[date]
        if isinstance(weights, pd.DataFrame):
            raise ContractError("Duplicate target date")
        cash = max(0.0, 1 - float(weights.sum()))
        defensive = float(weights.reindex(list(DEFENSIVE_PROXIES), fill_value=0).sum())
        equity = max(0.0, 1 - cash - defensive)
        recent_expected = calendar().sessions_window(date, -63).tz_localize(None)
        complete_history = bool(recent_expected.isin(specialist.bundle.prices.index).all())
        fresh = date == day and complete_history
        gaps = calendar().sessions_in_range(date, day)
        lag = len(gaps) - 1
        cash_history = 1 - targets.loc[:date].sum(axis=1)
        bot = {"system": name, "status": "fresh" if fresh else "incomplete_history" if date == day else "stale", "as_of": str(date.date()),
               "lag_sessions": lag, "eligible_for_comparison": fresh,
               "cash": round(cash, 8), "target_exposure": round(1 - cash, 8),
               "defensive_proxy_exposure": round(defensive, 8), "equity_risk_proxy": round(equity, 8),
               "stance": "defensive" if equity <= .5 else "reduced" if equity <= .8 else "invested",
               "target_holdings": {t: round(float(w), 8) for t, w in weights.items() if w > 1e-6},
               "reason": str(signals.loc[date, "reason"]),
               "semantics": specialist.telemetry["semantics"],
               "rules": specialist.telemetry.get("rules", specialist.telemetry.get("specification", {})),
               "limitations": specialist.telemetry["limitations"]}
        equity_history = targets.loc[:date].drop(columns=list(DEFENSIVE_PROXIES), errors="ignore").sum(axis=1)
        flags = equity_history.le(.5)
        bot["defensive_streak_sessions"] = int(flags.iloc[::-1].cumprod().sum())
        delta = targets.loc[:date].diff().abs().sum(axis=1)
        changes = delta[delta > 1e-6]
        bot["last_target_change"] = str(changes.index[-1].date()) if not changes.empty else None
        for n in (1, 5, 21):
            bot[f"cash_change_{n}"] = _number(cash_history.diff(n).iloc[-1])
            fact(f"{name}.cash.change.{n}", f"{name} cash-target change over {n} sessions", bot[f"cash_change_{n}"], "percentage_points", name, "target", date)
        fact(f"{name}.cash", f"{name} unallocated cash target", cash, "percent", name, "target", date)
        fact(f"{name}.equity", f"{name} equity-risk instrument proxy", equity, "percent", name, "target", date)
        fact(f"{name}.defensive_streak", f"{name} consecutive low equity-risk target sessions", bot["defensive_streak_sessions"], "sessions", name, "target", date)
        for column in specialist.telemetry["driver_columns"] + specialist.telemetry["monitor_columns"]:
            if column in signals:
                role = "native_driver" if column in specialist.telemetry["driver_columns"] else "monitor"
                fact(f"{name}.{column}", f"{name}: {column.replace('_', ' ')}", signals.loc[date, column], source=name, role=role, observed=date)
        bots.append(bot)
    lookup = {f["id"]: f["value"] for f in facts}
    dd = lookup.get("QQQ.drawdown.63")
    trend = lookup.get("SPY.trend.200")
    breadth_now = lookup.get("market.breadth")
    # Frozen descriptive rules, not optimized against the replay outcomes.
    state = "insufficient_data"
    if dd is not None and trend is not None and breadth_now is not None:
        state = "defensive_stress" if dd <= -.10 and (trend < 0 or breadth_now < .4) else "fragile_transition" if dd <= -.05 or breadth_now < .5 else "broad_risk_on" if trend > 0 and breadth_now >= 2/3 else "mixed"
    fresh_bots = [b for b in bots if b["eligible_for_comparison"]]
    stances = {b["stance"] for b in fresh_bots}
    comparison = "partial_coverage" if len(fresh_bots) < 3 else "divergent" if len(stances) > 1 else "aligned_not_independent"
    pack = {"schema_version": 1, "version": BRIEF_VERSION, "as_of_session": str(day.date()),
            "information_cutoff_utc": close_time(day), "evidence_status": "retrospective_reconstruction",
            "market_source": market_source, "state": state, "comparison": comparison,
            "fresh_postures_diverge": len(stances) > 1,
            "fresh_specialists": len(fresh_bots), "facts": facts, "bots": bots,
            "sector_leadership": leaders, "scenarios": scenarios(lookup), "limitations": LIMITATIONS,
            "authority": "interpretation_only", "action_authorized": False}
    pack["research"] = research_lenses(pack)
    return pack


def scenarios(values: dict) -> list[dict]:
    rules = [
        ("Repair", "Next 1-4 weeks", "SPY above its long trend, QQQ within five percent of its recent high, and sector breadth at least two thirds.",
         [("SPY.trend.200", ">", 0), ("QQQ.drawdown.63", ">", -.05), ("market.breadth", ">=", 2/3)],
         "Would support a broader repair interpretation; it does not change a native bot's schedule."),
        ("Continued stress", "Next 1-4 weeks", "QQQ at least ten percent below its recent high while SPY is below its long trend.",
         [("QQQ.drawdown.63", "<=", -.10), ("SPY.trend.200", "<", 0)],
         "Would support continued defensive monitoring, not a dated crash prediction."),
        ("Narrow leadership", "Next 1-4 weeks", "SPY above its long trend while fewer than half of stable sectors are above theirs.",
         [("SPY.trend.200", ">", 0), ("market.breadth", "<", .5)],
         "Would make headline-index strength a weak proxy for broad participation."),
    ]
    operations = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
                  "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
    result = []
    for title, horizon, description, tests, implication in rules:
        known = all(values.get(key) is not None for key, _, _ in tests)
        result.append({"name": title, "horizon": horizon, "conditions": description,
                       "active": all(operations[op](values[key], threshold) for key, op, threshold in tests) if known else None,
                       "evidence_ids": [key for key, _, _ in tests], "implication": implication,
                       "probability": None})
    return result


def display_value(fact: dict) -> str:
    value = fact["value"]
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        if fact["unit"] == "percentage_points":
            return f"{value * 100:+.1f} pp"
        if fact["unit"] == "percent":
            directional = any(token in fact["id"] for token in (".return.", ".drawdown.", ".trend."))
            return f"{value:+.1%}" if directional else f"{value:.1%}"
        return f"{int(value)}" if fact["unit"] == "sessions" else f"{value:.3f}"
    return str(value).replace("_", " ")


def evidence_brief(pack: dict) -> dict:
    """Always available, exactly grounded baseline; never masquerades as an LLM."""
    from portfolio_lab.editorial import copy_issues, daily_note

    note = daily_note(pack)
    prose = " ".join([note["headline"], *(c["text"] for s in note["sections"] for c in s["claims"])])
    if copy_issues(prose):
        raise ContractError("Formulaic editorial language in computed note")
    return {**note,
            "mode": "evidence_only", "agent_status": "not_requested",
            "skeptical_review": {"status": "deterministic_grounding", "issues": ["Descriptive classification is not a calibrated prediction."]}}


def score_replay(packs: list[dict], specialists: dict[str, Specialist], sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Outcomes are evaluation-only; require every actual exchange session."""
    rows = []
    for pack in packs:
        day = pd.Timestamp(pack["as_of_session"])
        values = {f["id"]: f["value"] for f in pack["facts"]}
        flags = {"early_watch": pack["state"] in {"fragile_transition", "defensive_stress"},
                 "confirmed_stress": pack["state"] == "defensive_stress",
                 "qqq_drawdown_5pct": values.get("QQQ.drawdown.63") <= -.05 if values.get("QQQ.drawdown.63") is not None else None,
                 "spy_below_long_trend": values.get("SPY.trend.200") < 0 if values.get("SPY.trend.200") is not None else None,
                 "sector_breadth_below_half": values.get("market.breadth") < .5 if values.get("market.breadth") is not None else None}
        for bot in pack["bots"]:
            flags[f"{bot['system']}_low_equity"] = bot["stance"] == "defensive" if bot["eligible_for_comparison"] else None
        for horizon in (5, 21):
            cal = calendar()
            future = cal.sessions_window(day, horizon + 1).tz_localize(None)
            # sessions_window's count includes the origin, not just later sessions.
            for ticker in ("SPY", "QQQ"):
                prices, source = market_panel(specialists, day)
                full = specialists[source].bundle.prices[ticker]
                valid = future.isin(full.index).all() and future[-1] <= sessions[-1]
                path = full.reindex(future)
                valid = bool(valid and path.notna().all())
                ret = float(path.iloc[-1] / path.iloc[0] - 1) if valid else None
                trough = float(path.div(path.iloc[0]).sub(1).min()) if valid else None
                warning = pack["state"] == "defensive_stress"
                rows.append({"session": str(day.date()), "horizon": horizon, "ticker": ticker,
                             "state": pack["state"], "matured": valid, "forward_return": ret,
                             "forward_worst_from_origin": trough,
                             "stress_warning": warning,
                             **{f"flag_{key}": value for key, value in flags.items()},
                             "large_loss": bool(trough <= -.05) if valid else None,
                             "false_defense": bool(warning and ret > .02 and trough > -.03) if valid else None})
    return pd.DataFrame(rows)


def replay_summary(packs: list[dict], outcomes: pd.DataFrame) -> dict:
    mature = outcomes[outcomes.matured]
    rows = []
    for (ticker, horizon), data in mature.groupby(["ticker", "horizon"]):
        warning = data.stress_warning
        loss = data.large_loss.astype(bool)
        tp = int((warning & loss).sum())
        rows.append({"ticker": ticker, "horizon": int(horizon), "matured": len(data),
                     "warnings": int(warning.sum()), "large_losses": int(loss.sum()),
                     "precision": tp / int(warning.sum()) if warning.sum() else None,
                     "recall": tp / int(loss.sum()) if loss.sum() else None,
                     "base_rate": float(loss.mean()),
                     "false_defense_count": int(data.false_defense.sum()),
                     "mean_forward_return": float(data.forward_return.mean())})
    signal_rows = []
    for column in [c for c in outcomes if c.startswith("flag_")]:
        for (ticker, horizon), data in mature.groupby(["ticker", "horizon"]):
            data = data[data[column].notna()]
            warning = data[column].astype(bool)
            loss = data.large_loss.astype(bool)
            true_positive = int((warning & loss).sum())
            signal_rows.append({"signal": column.removeprefix("flag_"), "ticker": ticker,
                                "horizon": int(horizon), "matured": len(data), "warnings": int(warning.sum()),
                                "precision": true_positive / int(warning.sum()) if warning.sum() else None,
                                "recall": true_positive / int(loss.sum()) if loss.sum() else None,
                                "base_rate": float(loss.mean()) if len(data) else None,
                                "mean_return_when_active": float(data.loc[warning, "forward_return"].mean()) if warning.any() else None,
                                "mean_return_when_inactive": float(data.loc[~warning, "forward_return"].mean()) if (~warning).any() else None})
    onsets = []
    daily = outcomes[outcomes.ticker.eq("QQQ") & outcomes.horizon.eq(5)]
    for column in [c for c in daily if c.startswith("flag_")]:
        active = daily[daily[column].eq(True)]
        first = daily[column].iloc[0]
        onsets.append({"signal": column.removeprefix("flag_"), "active_sessions": len(active),
                       "first_active_in_window": active.session.iloc[0] if len(active) else None,
                       "last_active_in_window": active.session.iloc[-1] if len(active) else None,
                       "left_censored": bool(pd.notna(first) and first)})
    return {"sessions": len(packs), "start": packs[0]["as_of_session"], "end": packs[-1]["as_of_session"],
            "fully_fresh_days": sum(p["fresh_specialists"] == 3 for p in packs),
            "state_counts": pd.Series([p["state"] for p in packs]).value_counts().to_dict(),
            "scorecards": rows, "signal_scorecards": signal_rows, "signal_onsets": onsets,
            "authority": "interpretation_only", "promotion_eligible": False,
            "evaluation_caveats": ["Overlapping horizons are dependent; this small sample is not validation of predictive alpha.",
                                   "Precision/recall refer to a frozen descriptive stress flag, not an LLM prediction.",
                                   "No strategy CAGR is attributed to a commentary layer.",
                                   "Rules were implemented after these dates were observed; this is not preregistered blind validation.",
                                   "Latest horizons without complete future sessions are excluded, never treated as zero returns."]}


def render_readout(packs: list[dict], summary: dict, context=None) -> str:
    from portfolio_lab.desk_research import macro_synthesis
    from portfolio_lab.editorial import warning_assessment

    latest = packs[-1]
    context = context or {}
    note = evidence_brief(latest)
    lines = [f"# {note['headline']}", "", f"Market close: {latest['as_of_session']}. Portfolio Lab daily research note.", ""]
    for section in note["sections"]:
        if section["heading"] == "Model positioning" and context.get("macro"):
            macro = context["macro"]
            lines += ["## Growth, Credit and Liquidity", "",
                      f"Current revised observations, captured {macro['captured_at_utc']}. These observations are excluded from historical signals and scores.", ""]
            for message in macro_synthesis(macro):
                lines.extend([f"**{message['cycle']}:** {message['text']}",
                              "Sources: " + ", ".join(message["series"]) + ".", ""])
        lines.extend([f"## {section['heading']}", ""])
        for claim in section["claims"]:
            lines.extend([claim["text"], ""])
    stock = context.get("stock", {})
    if stock:
        headline = stock.get("headline", {})
        lines += [f"Swing stock shadow, latest captured close {stock.get('as_of_session', 'unknown')}: {headline.get('label', 'unavailable')}. {headline.get('headline', 'No qualified stock-state evidence')}.", ""]
    event = context.get("event", {})
    news = event.get("news", {})
    if news:
        lines += ["## Current Financial News", "",
                  f"News capture: {news.get('captured_at_utc', 'not collected')}. Coverage: {news['status']}. Article bodies read: {news['article_bodies_read']}.",
                  "These are current observations, separate from the historical close-based readings and from event-strategy validation. No news-based allocation is authorized.", ""]
        shown = 0
        for row in news.get("items", []):
            if row.get("content_kind") == "legal_solicitation_or_announcement":
                continue
            title = row["display_title"].replace("[", "(").replace("]", ")")
            lines += [f"- [{title}]({row['url']}) / {row['source']} / {row['coverage']} / published {row['published_at_utc']}."]
            shown += 1
            if shown >= 12:
                break
        unavailable = [s["source"] for s in news.get("sources", []) if s["status"] == "unavailable"]
        if unavailable:
            lines += ["", "Unavailable sources: " + ", ".join(unavailable) + "."]
        lines += ["", "Topic tags are not sentiment or predictive scores. Issuer publicity is not independent reporting; syndicated coverage is not independent confirmation.", ""]
    if event:
        lines += ["## Fundamental Event Research", "",
                  f"Latest operational capture: {event.get('captured_at_utc', 'unknown')}. Status: {event.get('status', 'unavailable')}; stage: {event.get('stage', 'unknown')}.",
                  f"Registered hypotheses: {event.get('registered_hypotheses', 0)}; tested on real data: {event.get('tested_on_real_data', 0)}.", ""]
        if event.get("status") == "blocked":
            lines += ["This specialist contributes no positioning signal. Its missing data is not evidence of a neutral or bearish market view.", ""]
        for error in event.get("errors", []):
            lines += [f"Unresolved gate: {error}.", ""]
        for request in event.get("source_access", {}).get("requests", []):
            lines += [f"Official-source response: HTTP {request.get('http_status', 'unknown')} / {request.get('url', 'unknown')}.", ""]
        coverage = event.get("hypothesis_coverage", [])
        if coverage:
            lines += ["| Content family | Registered variants | Variants with features | Tested variants |", "|---|---:|---:|---:|"]
            for row in coverage:
                lines.append(f"| {row['family'].replace('_', ' ')} | {row['registered_variants']} | {row['variants_with_features']} | {row['tested_variants']} |")
            lines += ["", "Registered parameter variants are not independent discoveries. Ownership and 8-K content parsers remain unimplemented; filing counts cannot substitute for verified content.", ""]
        shadow = event.get("prospective_shadow", {})
        if shadow:
            lines += [f"Prospective evidence: {shadow['status'].replace('_', ' ')}; {shadow['recorded_sessions']} on-time sessions, {shadow['consecutive_sessions']} consecutive. Minimum observation window for review: {shadow['minimum_sessions_for_review']} sessions, not an alpha or allocation approval.", ""]
        outcomes = event.get("prospective_outcomes", {})
        if outcomes.get("status") == "recorded_decisions_marked":
            lines += ["Modeled forward performance of pre-recorded decisions; not account returns.", "",
                      "| Model | Completed execution sessions | Total return | Maximum drawdown |", "|---|---:|---:|---:|"]
            for row in outcomes["performance"]:
                lines.append(f"| {row['name']} | {row['sessions']} | {row['total_return']:.2%} | {row['max_drawdown']:.2%} |")
            lines += ["", outcomes["limits"], ""]
    lines += ["## Conditions to Watch", ""]
    for scenario in latest["scenarios"]:
        if scenario["active"] is not None:
            lines += [f"**{scenario['name']} ({scenario['horizon']}):** {scenario['conditions']}", ""]
    appraisal = warning_assessment(summary)
    if appraisal:
        lines += ["## What the Warnings Have Actually Shown", ""]
        for paragraph in appraisal:
            lines += [paragraph, ""]
    lines += ["## Scope and Sources", "",
              f"Price source: {latest['market_source']}; {latest['fresh_specialists']} current specialists. Month and quarter returns use 21 and 63 sessions.",
              f"Reconstruction: {summary['start']} to {summary['end']} ({summary['sessions']} NYSE sessions); all specialists fresh on {summary['fully_fresh_days']} days.",
              "The note describes research targets, not account holdings or execution instructions. Historical notes use current fixed specifications and revised prices.", "",
              "## Model Details", "", "| Model | Close | Status | Equity-risk proxy | Cash | Low-equity streak | Recorded native rule |",
              "|---|---|---|---:|---:|---:|---|"]
    for bot in latest["bots"]:
        if "cash" in bot:
            lines.append(f"| {bot['system']} | {bot['as_of']} | {bot['status']} | {bot['equity_risk_proxy']:.1%} | {bot['cash']:.1%} | {bot['defensive_streak_sessions']} | {bot['reason']} |")
        else:
            lines.append(f"| {bot['system']} | unavailable | missing | n/a | n/a | n/a | none |")
    lines += ["", "Research-control targets are not actual holdings. Stored operating summaries and Cycle Tracker context are in separate artifacts; their multipliers and phases do not replace final target exposure.",
              "", "## Timing Within This Window", "", "| Flag | Active sessions | First observed | Last observed | Active at left boundary |",
              "|---|---:|---|---|---|"]
    for row in summary["signal_onsets"]:
        lines.append(f"| {row['signal']} | {row['active_sessions']} | {row['first_active_in_window'] or 'none'} | {row['last_active_in_window'] or 'none'} | {row['left_censored']} |")
    lines += ["", "An active left boundary censors the true onset; it is not evidence that the flag began on that date.",
              "", "## Five-Session QQQ Loss Discrimination", "",
              "Loss label: at least a 5% drop from the origin during the next five exchange sessions.", "",
              "| Flag | Mature origins | Warnings | Precision | Recall | Unconditional loss rate |",
              "|---|---:|---:|---:|---:|---:|"]
    for row in summary["signal_scorecards"]:
        if row["ticker"] != "QQQ" or row["horizon"] != 5:
            continue
        numbers = [f"{row[k]:.1%}" if row[k] is not None else "undefined" for k in ("precision", "recall", "base_rate")]
        lines.append(f"| {row['signal']} | {row['matured']} | {row['warnings']} | {' | '.join(numbers)} |")
    lines += ["", "## Interpretation and Limits", "",
              "A broad watch flag can have high recall without much discrimination. Compare precision with the unconditional loss rate, not with zero.",
              "Hard stress is a confirmation of observed damage. No matured warning origins means its forward predictive value is unknown, not successful.",
              "Small, overlapping warning samples can look strong by chance. Low-equity strategies can also protect from one sleeve's decline while missing stronger sectors; this scorecard is not strategy P&L.", ""]
    lines.extend(f"- {text}" for text in summary["evaluation_caveats"])
    return "\n".join(lines) + "\n"


def publish_replay(paths: list[Path], telemetry_root: Path, output: Path, *, count=40, now=None, agent=False) -> Path:
    from portfolio_lab.brief_agent import narrate

    initial_code = interpretation_hash()
    specialists = load_specialists(paths, telemetry_root)
    sessions = completed_sessions(count, now)
    output.mkdir(parents=True, exist_ok=False)
    context_files = []
    for name, specialist in specialists.items():
        for filename, expected in specialist.telemetry.get("context_artifacts", {}).items():
            source = (telemetry_root / name / filename).resolve()
            if not source.is_relative_to((telemetry_root / name).resolve()) or digest(source) != expected:
                raise ContractError("Context artifact integrity failure")
            target = output / "context" / name / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            context_files.append(str(target.relative_to(output)))
    for name in ("fundamental_event.json", "source_health.json", "telemetry_health.json"):
        if (telemetry_root / name).exists():
            target = output / "context" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(telemetry_root / name, target)
            context_files.append(str(target.relative_to(output)))
    event_path = telemetry_root / "fundamental_event.json"
    if event_path.exists():
        event_context = json.loads(event_path.read_text())
        for name, expected in event_context.get("news_context_artifacts", {}).items():
            source = (telemetry_root / name).resolve()
            if not source.is_relative_to((telemetry_root / "fundamental-news").resolve()) or digest(source) != expected:
                raise ContractError("News telemetry evidence mismatch")
            target = output / "context" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            context_files.append(str(target.relative_to(output)))
    identities = {name: s.identity for name, s in specialists.items()}
    packs = []
    timeline = []
    for day in sessions:
        pack = build_pack(specialists, day)
        brief, transcript = narrate(pack, enabled=agent)
        folder = output / "sessions" / str(day.date())
        folder.mkdir(parents=True)
        for name, payload in (("pack.json", pack), ("brief.json", brief), ("agent.json", transcript)):
            (folder / name).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
        packs.append(pack)
        fresh = {b["system"] for b in pack["bots"] if b["eligible_for_comparison"]}
        values = {f["id"]: f["value"] if not f["id"].startswith(tuple(f"{s}." for s in SYSTEMS)) or f["source"] in fresh else None for f in pack["facts"]}
        timeline.append({"session": day, "state": pack["state"], "fresh_specialists": pack["fresh_specialists"], **values})
    outcomes = score_replay(packs, specialists, sessions)
    outcomes.to_csv(output / "outcomes.csv", index=False)
    pd.DataFrame(timeline).set_index("session").to_parquet(output / "timeline.parquet")
    prices, _ = market_panel(specialists, sessions[-1])
    prices.loc[sessions[0]:, [c for c in dict.fromkeys([*MARKETS, *SECTORS]) if c in prices]].to_parquet(output / "market_prices.parquet")
    summary = replay_summary(packs, outcomes)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    note_context = {}
    for key, name in (("macro", "trade-bot/macro_context.json"), ("stock", "swing-trader/stock_context.json"), ("event", "fundamental_event.json")):
        file = output / "context" / name
        if file.exists():
            note_context[key] = json.loads(file.read_text())
    (output / "readout.md").write_text(render_readout(packs, summary, note_context))
    if interpretation_hash() != initial_code:
        raise ContractError("Interpretation code changed during replay; archive not published")
    manifest = {"schema_version": 1, "version": BRIEF_VERSION, "created_at_utc": datetime.now(UTC).isoformat(),
                "authority": "interpretation_only", "action_authorized": False,
                "evidence_status": "retrospective_reconstruction", "source_identities": identities,
                "context_artifacts": context_files,
                "environment": {name: version(name) for name in ("numpy", "pandas", "pyarrow", "exchange-calendars")},
                "brief_code_sha256": initial_code, "sessions": [str(d.date()) for d in sessions],
                "artifacts": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify_replay(output)
    return output


def interpretation_hash():
    root = Path(__file__).parent
    return json_hash({name: digest(root / name) for name in ("briefing.py", "brief_agent.py", "brief_runner.py", "desk_research.py", "editorial.py", "event_context.py")})


def verify_replay(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("authority") != "interpretation_only" or manifest.get("action_authorized") is not False:
        raise ContractError("Invalid brief authority")
    required = {"summary.json", "timeline.parquet", "outcomes.csv", "market_prices.parquet"}
    for day in manifest["sessions"]:
        required |= {f"sessions/{day}/{name}.json" for name in ("pack", "brief", "agent")}
    if not required <= manifest["artifacts"].keys():
        raise ContractError("Incomplete brief archive")
    for name, expected in manifest["artifacts"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != expected:
            raise ContractError(f"Brief artifact mismatch: {name}")
    days = pd.DatetimeIndex(pd.to_datetime(manifest["sessions"]))
    if days.empty or days.has_duplicates or not days.is_monotonic_increasing:
        raise ContractError("Invalid archive session sequence")
    if not days.equals(calendar().sessions_in_range(days[0], days[-1]).tz_localize(None)):
        raise ContractError("Archive must cover contiguous trading sessions")
    for day in manifest["sessions"]:
        pack = json.loads((root / "sessions" / day / "pack.json").read_text())
        validate_pack(pack, day)
    event_file = root / "context/fundamental_event.json"
    if event_file.exists():
        from portfolio_lab.event_context import read

        event = read(root)
        if ("context/fundamental_event.json" not in manifest["artifacts"]
                or (event.get("schema_version") == 2
                    and pd.Timestamp(event["captured_at_utc"]) > pd.Timestamp(manifest["created_at_utc"]))):
            raise ContractError("Unbound or future event-specialist capture")
        news = event.get("news", {})
        if news.get("items"):
            relative = "fundamental-news/manifest.json"
            expected = event.get("news_context_artifacts", {}).get(relative)
            if not expected or expected != news["manifest_sha256"]:
                raise ContractError("News context lacks its source archive")
            news_meta = json.loads((root / "context" / relative).read_text())
            for name, digest_value in {"manifest.json": expected, **news_meta["artifacts"]}.items():
                key = str(Path("context/fundamental-news") / name)
                if manifest["artifacts"].get(key) != digest_value:
                    raise ContractError("Incomplete bound news evidence archive")
    return manifest


def validate_pack(pack: dict, session: str) -> None:
    if pack.get("as_of_session") != session or pack.get("authority") != "interpretation_only" or pack.get("action_authorized") is not False:
        raise ContractError("Invalid fact-pack identity or authority")
    if pack.get("information_cutoff_utc") != close_time(session):
        raise ContractError("Invalid information cutoff")
    identifiers = [f["id"] for f in pack["facts"]]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("Duplicate fact identity")
    cutoff = pd.Timestamp(pack["information_cutoff_utc"])
    for fact in pack["facts"]:
        if fact["observed_session"] > session or pd.Timestamp(fact["available_after_utc"]) > cutoff:
            raise ContractError("Future information in fact pack")
        if fact["role"] not in {"monitor", "native_driver", "target"}:
            raise ContractError("Unrecognized evidence role")
    fresh = [b for b in pack["bots"] if b["eligible_for_comparison"]]
    if len(fresh) != pack["fresh_specialists"] or any(b["as_of"] != session for b in fresh):
        raise ContractError("Stale bot counted as fresh")
    if any(b.get("cash", 0) < 0 or b.get("cash", 0) > 1 for b in pack["bots"]):
        raise ContractError("Invalid cash target")
