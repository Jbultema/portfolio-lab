"""Read-only market desk. Presentation cannot change policy identity or allocations."""

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from portfolio_lab.briefing import completed_sessions, display_value, verify_replay
from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.desk_research import (
    MACRO_GROUPS,
    MARKETS,
    macro_insights,
    macro_rows,
    macro_synthesis,
)
from portfolio_lab.editorial import render_fact_tokens, warning_assessment

COLORS = {"SPY": "#1876c9", "QQQ": "#a447b5", "RSP": "#0b8a70", "SMH": "#d15b36", "GLD": "#a07c13", "IEF": "#65758b"}
BOT_COLORS = {"trade-bot": "#1876c9", "swing-trader": "#0b8a70", "rotation-trader": "#a447b5"}
STATE_LABELS = {"defensive_stress": "Defensive stress", "fragile_transition": "Fragile transition", "broad_risk_on": "Broad participation", "mixed": "Mixed conditions", "insufficient_data": "Insufficient evidence"}


def plot_style(fig, height=350):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=15, b=8),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Arial", size=12, color="#334155"),
                      legend=dict(orientation="h", y=1.1), hovermode="x unified")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e8edf2", zerolinecolor="#cbd5e1")
    return fig


@st.cache_data(show_spinner=False)
def read_archive(report: str, identity: str):
    root = Path(report)
    if digest(root / "manifest.json") != identity:
        raise ContractError("Manifest pointer mismatch")
    manifest = verify_replay(root)
    return manifest, pd.read_parquet(root / "timeline.parquet"), pd.read_parquet(root / "market_prices.parquet"), json.loads((root / "summary.json").read_text())


def render(research_view):
    st.markdown("""<style>
    .block-container{padding-top:1.7rem;padding-bottom:3rem;max-width:1600px}
    h1{font-size:2rem!important;letter-spacing:0!important} h2{font-size:1.3rem!important;letter-spacing:0!important}
    h3{font-size:1.08rem!important;letter-spacing:0!important}
    [data-testid="stMetric"]{border-top:2px solid #d8e0e9;padding:12px 0;min-height:96px}
    [data-testid="stMetricLabel"]{font-size:.8rem} [data-testid="stMetricValue"]{font-size:1.65rem}
    [data-testid="stSidebar"]{background:#f3f6f8} .stCaption{color:#64748b}
    button{letter-spacing:0!important}
    @media(max-width:640px){
      [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [data-testid="stMetric"]){flex-wrap:wrap!important}
      [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [data-testid="stMetric"])>[data-testid="stColumn"]{min-width:calc(50% - .5rem)!important;flex:1 1 calc(50% - .5rem)!important}
    }
    </style>""", unsafe_allow_html=True)
    try:
        pointer = Path("reports/market-desk/latest.json")
        config = json.loads(pointer.read_text()) if pointer.exists() else {}
        root = Path(os.getenv("PORTFOLIO_LAB_DESK", config.get("report", "")))
        identity = config.get("manifest_sha256") if not os.getenv("PORTFOLIO_LAB_DESK") else digest(root / "manifest.json")
        manifest, timeline, prices, summary = read_archive(str(root), identity)
        verify_replay(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Market Desk evidence unavailable: {type(exc).__name__}")
        return
    with st.sidebar:
        st.subheader("Portfolio Lab")
        st.caption("MARKET INTERPRETATION DESK")
        view = st.radio("Workspace", ["Current read", "Macro & cross-asset", "News & events", "Signals & bots", "Event research", "System scorecard", "Combination lab", "Dynamic allocation", "Adaptive allocation", "Replay scorecard", "Evidence", "Portfolio research"], label_visibility="collapsed")
        selected = manifest["sessions"][-1]
        if view not in {"Portfolio research", "System scorecard", "Combination lab", "Dynamic allocation", "Adaptive allocation"}:
            selected = st.selectbox("Session close", list(reversed(manifest["sessions"])), format_func=lambda x: pd.Timestamp(x).strftime("%a, %b %d, %Y"))
        st.divider()
        st.caption(f"{summary['sessions']} completed sessions")
        st.caption(f"{summary['start']} to {summary['end']}")
        st.caption("Interpretation only. Human execution only.")
    if view == "Portfolio research":
        research_view()
        return
    if view == "System scorecard":
        from portfolio_lab.system_scorecard_ui import render as render_system

        render_system()
        return
    if view == "Adaptive allocation":
        from portfolio_lab.dynamic_ui import render as render_adaptive

        render_adaptive(os.getenv("PORTFOLIO_LAB_ADAPTIVE", "reports/adaptive-allocation/latest.json"))
        return
    if view == "Dynamic allocation":
        from portfolio_lab.dynamic_ui import render as render_dynamic

        render_dynamic()
        return
    if view == "Combination lab":
        from portfolio_lab.combination_ui import render as render_combinations

        render_combinations()
        return
    # Verify selected files on every rerun, not only when cached archive data is loaded.
    folder = root / "sessions" / selected
    for name in ("pack", "brief", "agent"):
        file = folder / f"{name}.json"
        if digest(file) != manifest["artifacts"][str(file.relative_to(root))]:
            st.error("Selected brief failed its evidence integrity check.")
            return
    pack = json.loads((folder / "pack.json").read_text())
    brief = json.loads((folder / "brief.json").read_text())
    facts = {f["id"]: f for f in pack["facts"]}
    day = pd.Timestamp(selected)
    st.title("Market Interpretation Desk")
    st.caption(f"CLOSE {selected}  |  {brief['mode'].replace('_', ' ').upper()}  |  No action authorized")
    latest_expected = str(completed_sessions(1)[-1].date())
    if manifest["sessions"][-1] < latest_expected:
        st.warning(f"Archive is behind the latest completed session ({latest_expected}). Last brief: {manifest['sessions'][-1]}.")
    missing = [b["system"] for b in pack["bots"] if not b["eligible_for_comparison"]]
    if missing:
        st.warning("Partial coverage: " + ", ".join(missing) + ". Excluded from same-session comparison.")
    if view == "Current read":
        current_read(pack, brief, facts, timeline.loc[:day], prices.loc[:day], day, root, is_current=selected == manifest["sessions"][-1])
        if selected == manifest["sessions"][-1]:
            from portfolio_lab.position_context import render as render_position

            render_position(root)
            context_path = root / "context/trade-bot/macro_context.json"
            if context_path.exists():
                context = json.loads(context_path.read_text())
                st.subheader("Growth, credit and liquidity")
                st.caption(f"Latest revised macro observations, captured {context['captured_at_utc']}. Separate from the historical price replay.")
                for message in macro_synthesis(context):
                    st.write(f"**{message['cycle']}:** {message['text']}")
    elif view == "Macro & cross-asset":
        research_view_readout(root, pack, facts, selected == manifest["sessions"][-1])
    elif view == "News & events":
        news_view(root, selected == manifest["sessions"][-1])
    elif view == "Signals & bots":
        bot_view(pack, facts, timeline.loc[:day], day)
        operating_context(root, day)
    elif view == "Event research":
        event_view(root, selected, manifest["sessions"][-1])
    elif view == "Replay scorecard":
        scorecard(summary, root, timeline)
    else:
        evidence_view(pack, facts, manifest, root, brief)
    st.divider()
    st.caption("Historical reconstruction, not a captured forecast. Model targets are not actual holdings. Shared price-driven models are not independent votes.")


def current_read(pack, brief, facts, timeline, prices, day, root, *, is_current=False):
    sections = {section["heading"]: section["claims"] for section in brief["sections"]}
    st.subheader(brief["headline"])
    for claim in sections.get("Equities and participation", []):
        st.write(claim["text"])
    a, b, c, d = st.columns(4)
    a.metric("QQQ / 63-session high", display_value(facts["QQQ.drawdown.63"]))
    b.metric("SPY / past month", display_value(facts["SPY.return.21"]))
    c.metric("Sectors above trend", display_value(facts["market.breadth"]))
    d.metric("Fresh specialist models", f"{pack['fresh_specialists']} / 3")
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        st.subheader("Market path")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.70, .30], vertical_spacing=.06)
        for ticker in ("SPY", "QQQ", "RSP", "SMH"):
            if ticker in prices:
                series = prices[ticker].dropna()
                if not series.empty:
                    fig.add_trace(go.Scatter(x=series.index, y=series / series.iloc[0] * 100, name=ticker, line=dict(color=COLORS[ticker], width=2)), row=1, col=1)
        for ticker in ("SPY", "QQQ"):
            key = f"{ticker}.drawdown.63"
            fig.add_trace(go.Scatter(x=timeline.index, y=timeline[key], name=f"{ticker} drawdown", line=dict(color=COLORS[ticker], width=1.5), showlegend=False), row=2, col=1)
        fig.update_yaxes(title_text="Rebased to 100", row=1, col=1)
        fig.update_yaxes(title_text="63-session DD", tickformat=".0%", row=2, col=1)
        st.plotly_chart(plot_style(fig, 440), width="stretch")
    with right:
        st.subheader("Since the previous close")
        for claim in sections.get("Since the previous close", []):
            st.write(claim["text"])
        st.caption("Month and quarter comparisons use 21 and 63 trading sessions.")
    st.subheader("Model posture")
    bot_table(pack)
    for claim in sections.get("Model positioning", []):
        st.write(claim["text"])
    operating_summary(root, str(day.date()))
    if is_current:
        news_view(root, True, compact=True)
    st.subheader("Leadership and defensive assets")
    for claim in sections.get("Leadership and defensive assets", []):
        st.write(claim["text"])
    st.subheader("Sector leadership / past month")
    leadership = pd.DataFrame(pack["sector_leadership"]).sort_values("relative_return_21")
    if not leadership.empty:
        chart = go.Figure(go.Bar(x=leadership.relative_return_21, y=leadership.ticker, orientation="h",
                                marker_color=["#0b8a70" if v >= 0 else "#cb5347" for v in leadership.relative_return_21]))
        chart.update_xaxes(title="Return relative to SPY", tickformat=".0%")
        st.plotly_chart(plot_style(chart, 300), width="stretch")
    st.subheader("Conditions that would change the view")
    for scenario in pack["scenarios"]:
        status = "ACTIVE" if scenario["active"] else "NOT ACTIVE" if scenario["active"] is False else "UNKNOWN"
        with st.expander(f"{scenario['name']} / {status} / {scenario['horizon']}", expanded=scenario["active"] is True):
            st.write(scenario["conditions"])
            st.write(scenario["implication"])
            st.caption(" | ".join(f"{facts[k]['label']}: {display_value(facts[k])}" for k in scenario["evidence_ids"]))
    summary = json.loads((root / "summary.json").read_text())
    if str(day.date()) == summary["end"]:
        appraisal = warning_assessment(summary)
        if appraisal:
            st.subheader("What the warnings have actually shown")
            for paragraph in appraisal:
                st.write(paragraph)
    if brief["mode"] != "evidence_only":
        st.subheader("Reviewed interpretation")
        for section in brief["sections"]:
            st.markdown(f"**{section['heading']}**")
            for claim in section["claims"]:
                st.write(render_fact_tokens(claim["text"], facts))
                st.caption(" | ".join(f"{facts[k]['label']}: {display_value(facts[k])}" for k in claim["evidence_ids"]))


def operating_summary(root, selected):
    external_path = root / "context/trade-bot/external_research_context.json"
    if external_path.exists():
        records = json.loads(external_path.read_text()).get("rows", [])
        native = [r for r in records if r.get("matched_market_date") == selected and r.get("matched_source") == "saved_snapshot_retrospective_comparison"]
        if native and native[-1].get("trade_bot_final_defensive_weight") is not None:
            st.caption(f"Saved Trade Bot baseline / {selected}: {native[-1]['trade_bot_final_defensive_weight']:.1%} defensive allocation. This baseline and the research control above are different models; neither represents your account holdings.")
    stock_path = root / "context/swing-trader/stock_context.json"
    if stock_path.exists():
        stock = json.loads(stock_path.read_text())
        headline = stock.get("headline", {})
        if stock.get("as_of_session", "9999") <= selected:
            st.info(f"Swing stock shadow / {stock.get('as_of_session', 'unknown')}: {headline.get('label', 'unavailable')}. {headline.get('headline', 'No qualified stock-state evidence')}.")
    fundamental_path = root / "context/fundamental_event.json"
    if fundamental_path.exists():
        fundamental = json.loads(fundamental_path.read_text())
        st.caption(f"Historical event strategies: {fundamental.get('status', 'unavailable')}. News monitor: {fundamental.get('news', {}).get('status', 'not collected')}. News does not change model allocations.")


def news_view(root, current, *, compact=False):
    from portfolio_lab.event_context import read

    st.subheader("Financial News and Events")
    if not current:
        st.info("Current news is withheld from historical sessions. Publication dates alone do not establish what this system knew at that close.")
        return
    context = read(root) or {}
    news = context.get("news", {})
    if not news or news.get("status") in {"not_collected", "unavailable"}:
        st.info("No usable news capture. Missing coverage is not a neutral or bearish market signal.")
        return
    st.caption(f"NEWS CAPTURE {news.get('captured_at_utc', 'unknown')}. Separate from the close-based model readings. No news-based allocation authorized.")
    if news["status"] == "stale":
        st.warning("Stale news evidence. The capture time above is not a current market update.")
    sources = news.get("sources", [])
    if not compact:
        a, b, c, d = st.columns(4)
        a.metric("Source feeds", f"{sum(s['status'] != 'unavailable' for s in sources)} / {len(sources)}")
        b.metric("Recent items", news.get("item_count", len(news.get("items", []))))
        c.metric("Bodies read", news["article_bodies_read"])
        d.metric("Coverage", news["status"].capitalize())
    else:
        st.caption(f"{news.get('item_count', 0)} recent items; {news['article_bodies_read']} article bodies read. Coverage: {news['status']}.")
    items = list(news.get("items", []))
    if not compact:
        left, middle, right = st.columns(3)
        topic = left.selectbox("News topic", ["All topics", *sorted({topic for row in items for topic in row["topics"]})])
        publisher = middle.selectbox("News publisher", ["All publishers", *sorted({row["source"] for row in items})])
        search = right.text_input("Search news")
        a, b = st.columns(2)
        bodies_only = a.toggle("Article bodies read only", value=False)
        include_legal = b.toggle("Include legal solicitations", value=False)
        items = [row for row in items if (topic == "All topics" or topic in row["topics"])
                 and (publisher == "All publishers" or row["source"] == publisher)
                 and (not bodies_only or row["coverage"] == "article_read")
                 and (include_legal or row.get("content_kind") != "legal_solicitation_or_announcement")
                 and (not search or search.casefold() in (row["title"] + " " + " ".join(row["entities"])).casefold())]
    else:
        items = [row for row in items if row.get("content_kind") != "legal_solicitation_or_announcement"]
    seen = set()
    for row in items[:5 if compact else 30]:
        group = row.get("coverage_group", row["id"])
        if group in seen:
            continue
        seen.add(group)
        title = row["display_title"].replace("[", "(").replace("]", ")")
        st.markdown(f"**[{title}]({row['url']})**")
        coverage = "Article body read" if row["coverage"] == "article_read" else "Headline / feed summary only"
        publication = pd.Timestamp(row["published_at_utc"]).tz_convert("America/New_York").strftime("%b %d, %I:%M %p ET")
        st.caption(f"{row['source']} | {publication} | {coverage}")
        if row["source_kind"] in {"issuer_newsroom", "issuer_release_wire"}:
            st.caption("Issuer or interested-party statement; not independent reporting.")
        if row["display_excerpt"]:
            st.write(row["display_excerpt"])
        if row["topics"]:
            st.caption(" / ".join(row["topics"]))
        if not compact:
            with st.expander("Source timing and topic evidence"):
                st.write(f"First observed: {row['first_seen_at_utc']}. This version available: {row['available_at_utc']}.")
                st.json({"matched_topic_terms": row["topics"], "entity_tags_not_security_identity": row["entities"],
                         "content_sha256": row["content_sha256"]})
    if not items:
        st.info("No stories match these filters.")
    if not compact:
        st.subheader("News source health")
        st.dataframe(pd.DataFrame([{"Source": s["source"], "Kind": s["kind"].replace("_", " "),
                                    "Status": s["status"], "Items": s["items"], "Access issue": s.get("error", "")}
                                   for s in sources]), hide_index=True, width="stretch")
        with st.expander("News evidence limits"):
            for limit in news.get("limits", []):
                st.write(limit)


def event_view(root, selected, latest):
    from portfolio_lab.event_context import read

    st.subheader("Fundamental Event Trader")
    payload = read(root)
    if not payload or payload.get("schema_version") != 2:
        st.warning("This archive has no detailed event-specialist capture. No event opinion or allocation is available.")
        return
    st.caption(f"Operational capture {payload['captured_at_utc']}. Company filings and fundamentals, separate from macro-news interpretation.")
    if payload.get("news", {}).get("items"):
        st.caption(f"Financial-news monitor: {payload['news']['status']}; {payload['news']['article_bodies_read']} article bodies read. Strategy qualification below is a separate assessment.")
    a, b, c = st.columns(3)
    a.metric("Research stage", {"data_acquisition": "Data needed", "portfolio_validation": "Validation", "prospective_shadow": "Shadow"}.get(payload["stage"], "Review"))
    b.metric("Registered hypotheses", payload["registered_hypotheses"])
    c.metric("Tested on real data", payload["tested_on_real_data"])
    if payload["status"] in {"blocked", "unavailable"}:
        st.warning("Event signals are inactive. This is an unresolved data or validation gate, not a neutral or bearish market signal.")
    elif payload["status"] == "stale_research":
        st.warning("The event dataset is behind the latest completed session. These are stale research targets, not a current positioning recommendation.")
    else:
        st.info("Research shadow only. No automatic promotion or account-level execution is authorized.")
    errors = payload.get("errors", [])
    if errors:
        labels = {"no_qualified_historical_dataset": "No qualified historical dataset, including delisted securities and original filing evidence.",
                  "no_validated_portfolio_research": "No verified portfolio research report is configured.",
                  "dataset_behind_latest_completed_session": "The captured dataset does not include the latest completed market session."}
        for error in errors:
            st.write(labels.get(error, error))
    access = payload.get("source_access", {})
    st.subheader("Official-source access")
    if access.get("requests"):
        st.caption(f"Latest acquisition attempt: {access.get('captured_at_utc', 'unknown')}.")
        st.dataframe(pd.DataFrame([{"Official endpoint": row.get("url"), "HTTP status": row.get("http_status"), "Passed": row.get("passed")}
                                   for row in access["requests"]]), hide_index=True, width="stretch",
                     column_config={"Official endpoint": st.column_config.LinkColumn()})
    else:
        st.write("No direct-request evidence in the latest capture; a verified official bulk import can supply the archive instead.")
    st.subheader("Historical-data qualification")
    criteria = [{"Requirement": row["criterion"].replace("_", " ").capitalize(),
                 "Evidence": "Passed" if row["passed"] else "Not qualified"} for row in payload.get("criteria", [])]
    if criteria:
        st.dataframe(pd.DataFrame(criteria), hide_index=True, width="stretch")
    coverage = payload.get("coverage")
    if coverage:
        st.caption(f"Captured coverage: {coverage['sessions']} sessions, {coverage['securities']} historical identities, {coverage['delisted']} delisted identities, {coverage['events']} source-bound events.")
    if selected != latest:
        st.info("Current event research targets and completed research outcomes are withheld for this historical selection. This operational capture is not evidence available at that past close.")
        return
    from portfolio_lab.combination_ui import event_capture

    event_capture()
    st.subheader("What has actually been tested")
    family_rows = [{"Content family": row["family"].replace("_", " "),
                    "Registered": row["registered_variants"], "Features available": row["variants_with_features"],
                    "Tested": row["tested_variants"], "Content required": row["content"]}
                   for row in payload.get("hypothesis_coverage", [])]
    if family_rows:
        st.dataframe(pd.DataFrame(family_rows), hide_index=True, width="stretch")
    shadow = payload.get("prospective_shadow", {})
    if shadow:
        st.subheader("Prospective evidence")
        left, right = st.columns(2)
        left.metric("On-time observations", shadow["recorded_sessions"])
        right.metric("Consecutive sessions", shadow["consecutive_sessions"])
        st.write(f"{shadow['status'].replace('_', ' ').capitalize()}. Minimum observation window for review: {shadow['minimum_sessions_for_review']} sessions. No profitability or allocation approval is implied.")
        if shadow.get("missing_sessions"):
            st.warning("Missing pre-execution observations: " + ", ".join(shadow["missing_sessions"]))
        outcomes = payload.get("prospective_outcomes", {})
        if outcomes.get("status") == "recorded_decisions_marked":
            st.dataframe(pd.DataFrame(outcomes["performance"]), hide_index=True, width="stretch",
                         column_config={k: st.column_config.NumberColumn(format="percent") for k in ("total_return", "max_drawdown", "cagr")})
            st.caption(outcomes["limits"])
    if payload["status"] not in {"blocked", "unavailable"}:
        st.subheader("Frozen-policy research targets")
        st.caption(f"Data through {payload.get('as_of_session', 'unknown')}. Research targets are not account holdings.")
        if payload.get("target_holdings"):
            st.dataframe(pd.Series(payload["target_holdings"], name="Target weight").to_frame(), width="stretch",
                         column_config={"Target weight": st.column_config.NumberColumn(format="percent")})
        else:
            st.write("No qualifying active event positions; the frozen policy remains in cash.")
        st.subheader("Development, validation and lockbox performance")
        if payload.get("performance"):
            st.dataframe(pd.DataFrame(payload["performance"]), hide_index=True, width="stretch",
                         column_config={k: st.column_config.NumberColumn(format="percent") for k in ("cagr", "max_drawdown", "total_return", "volatility", "average_equity_exposure")})
        st.subheader("Source-bound events")
        if payload.get("recent_events"):
            st.dataframe(pd.DataFrame(payload["recent_events"]), hide_index=True, width="stretch")
    st.subheader("Remaining admission gates")
    for gate in payload.get("remaining_gates", []):
        st.write(gate)
    with st.expander("Recorded policy and evidence identities"):
        st.json({key: payload.get(key) for key in ("policy", "dataset_manifest_sha256", "research_manifest_sha256", "code_sha256", "portfolio_allocation_allowed")})


def research_theses(pack, facts):
    research = pack.get("research")
    if not research:
        return
    st.subheader("Research theses / evidence and rebuttal")
    st.caption(research["confidence"] + " " + research["independence"])
    for thesis in research["theses"]:
        with st.expander(f"{thesis['name']} / {thesis['horizon']} / {thesis['status'].upper()}", expanded=thesis["status"] == "adverse"):
            st.write(thesis["interpretation"])
            left, right = st.columns(2)
            for column, keys, title in ((left, thesis["support"], "Primary evidence"), (right, thesis["counter"], "Cross-checks / counterevidence")):
                column.markdown(f"**{title}**")
                for key in keys:
                    column.write(f"{facts[key]['label']}: **{display_value(facts[key])}**")
                if not keys:
                    column.caption("No usable evidence in this source panel.")
            st.markdown("**What would change the thesis**")
            st.write(thesis["invalidation"])
            st.markdown("**Implication for the bots**")
            st.write(thesis["bot_implication"])


def return_heatmap(facts, tickers, title):
    available = [t for t in tickers if f"{t}.return.21" in facts]
    if not available:
        st.info("No instruments available for this panel.")
        return
    horizons = (1, 5, 21, 63)
    z = [[facts.get(f"{t}.return.{n}", {}).get("value") for n in horizons] for t in available]
    chart = go.Figure(go.Heatmap(z=z, x=["1 day", "1 week", "1 month", "3 months"], y=available,
                               colorscale=[[0, "#b64148"], [.5, "#f7f9fb"], [1, "#16856b"]],
                               zmid=0, zmin=-.20, zmax=.20, xgap=3, ygap=3,
                               text=[["n/a" if v is None else f"{v:+.1%}" for v in row] for row in z],
                               texttemplate="%{text}", hovertemplate="%{y} / %{x}: %{z:.2%}<extra></extra>",
                               colorbar=dict(tickformat=".0%", thickness=10)))
    chart.update_yaxes(autorange="reversed")
    st.subheader(title)
    st.plotly_chart(plot_style(chart, max(280, len(available) * 32 + 75)), width="stretch")


def research_view_readout(root, pack, facts, latest):
    st.subheader("Cross-asset risk map")
    st.caption(f"Price evidence through {pack['as_of_session']}. Same source panel: {pack['market_source']}. Returns use 1 / 5 / 21 / 63 exchange sessions; not forecasts.")
    a, b = st.columns(2, gap="large")
    with a:
        return_heatmap(facts, MARKETS, "Markets / absolute returns")
    with b:
        return_heatmap(facts, ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"), "Sectors / absolute returns")
    st.subheader("Signal clusters")
    st.caption("Related signals are grouped, not counted as independent confirmations. Missing evidence is not a neutral reading.")
    for cluster in pack.get("research", {}).get("clusters", []):
        with st.expander(f"{cluster['name']} / {cluster['status'].upper()}", expanded=True):
            st.write(cluster["meaning"])
            st.caption(" | ".join(f"{facts[k]['label']}: {display_value(facts[k])}" for k in cluster["evidence_ids"] if k in facts))
    with st.expander("Definitions and limitations"):
        for cluster in pack.get("research", {}).get("clusters", []):
            st.caption(f"{cluster['name']}: {cluster['caveat']}")
    st.subheader("Macro cycles / current-vintage context")
    if not latest:
        st.info("Current-vintage macro is withheld for historical session selections. It is not release-timed evidence available at that past close.")
        return
    path = root / "context/trade-bot/macro_context.json"
    if not path.exists():
        st.warning("No verified macro capture in this archive. Rebuild the desk after refreshing Trade Bot.")
        return
    context = json.loads(path.read_text())
    st.warning("CURRENT VINTAGE ONLY. Observation dates are not release dates. This macro panel is excluded from replay signals, historical scores, and trading rules.")
    st.caption(f"Captured {context['captured_at_utc']}. Source: Trade Bot's public FRED cache. Publication timestamps unverified.")
    rows = macro_rows(context)
    frame = pd.DataFrame(rows)
    coverage = [{"Cycle": group, "Available within age limit": int((frame.Cycle.eq(group) & frame.Coverage.eq('within_age_limit')).sum()),
                 "Selected indicators": len(specs), "Boundary": "No direct positioning data" if not specs else "Fiscal stocks, not fiscal impulse" if group == "Fiscal" else "Current revised observations; no release surprise"}
                for group, specs in MACRO_GROUPS.items()]
    st.dataframe(pd.DataFrame(coverage), hide_index=True, width="stretch")
    st.subheader("Economic read-through")
    for message in macro_synthesis(context):
        st.write(f"**{message['cycle']}:** {message['text']}")
        st.caption("Sources: " + ", ".join(message["series"]))
    insights = macro_insights(context)
    for group in dict.fromkeys(i["group"] for i in insights):
        with st.expander(group, expanded=group in {"Growth", "Inflation", "Credit"}):
            for insight in [i for i in insights if i["group"] == group]:
                value = insight["value"]
                label = "unavailable" if value is None else f"{value:+.2%}" if insight["unit"] == "percent" else f"{value:+.3f}"
                st.write(f"**{insight['label']}: {label}**")
                st.caption(f"Observation {insight['observation']} / {insight['coverage']}. {insight['caveat']}")
                if insight.get("unavailable_reason"):
                    st.caption("Calculation unavailable: " + insight["unavailable_reason"].replace("_", " "))
    st.subheader("Macro indicator trends")
    catalog = {s["id"]: s for s in context.get("series", []) if s.get("observations")}
    if catalog:
        selected = st.selectbox("Macro indicator", list(catalog), format_func=lambda k: f"{k} / {catalog[k]['name']}")
        indicator = catalog[selected]
        series = pd.DataFrame(indicator["observations"])
        chart = go.Figure(go.Scatter(x=series.observation_date, y=series.value, mode="lines+markers", line=dict(color="#1876c9", width=2)))
        chart.update_yaxes(title_text="Native FRED units")
        st.plotly_chart(plot_style(chart, 300), width="stretch")
        st.link_button("Source and units / FRED", indicator["source_url"])
    with st.expander("Source freshness and raw macro observations"):
        st.dataframe(frame, hide_index=True, width="stretch", column_config={"Source": st.column_config.LinkColumn()})
        st.caption("Observation-age limits are display gates, not verified publication lags. Native differences retain the series' units.")
    st.subheader("Research coverage / remaining gaps")
    st.write("Macro stocks and economic trends now complement price-based monitoring. Direct positioning, release surprises, a verified forward event calendar, global economic breadth, and validated probabilistic forecasting remain unavailable. No parity with a proprietary research service is claimed.")
    external_path = root / "context/trade-bot/external_research_context.json"
    if external_path.exists():
        import re

        external = json.loads(external_path.read_text())
        st.subheader("42 Macro / public commentary cross-check")
        st.caption(f"Captured {external['captured_at_utc']}. Public videos only; no private subscriber content.")
        for row in reversed(external["rows"]):
            with st.expander(f"{row['published_date']} / {row['title']}"):
                st.write(f"Mechanical language proxy: {row.get('macro_posture_label', 'unknown')}. Evidence: {row.get('classification_text_source', 'unknown')}.")
                st.write(f"Trade Bot matched close: {row.get('matched_market_date', 'unknown')} / gap {row.get('days_from_tradebot', 'unknown')} calendar days. Source: {row.get('matched_source', 'unknown')}.")
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", str(row["video_id"])):
                    st.link_button("Public video", f"https://www.youtube.com/watch?v={row['video_id']}")
        for limitation in external["limitations"]:
            st.caption(limitation)


def bot_table(pack):
    rows = []
    for bot in pack["bots"]:
        rows.append({"Specialist": bot["system"], "Coverage": bot["status"], "Signal close": bot.get("as_of", "Unavailable"),
                     "Posture": bot.get("stance", "Unknown"), "Cash target": bot.get("cash"),
                     "Defensive assets": bot.get("defensive_proxy_exposure"), "Equity-risk proxy": bot.get("equity_risk_proxy"),
                     "Low-risk streak": bot.get("defensive_streak_sessions"),
                     "Cash change / week": bot.get("cash_change_5"),
                     "Rule": bot.get("reason", "Unavailable").replace("_", " ")})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_order=["Specialist", "Posture", "Equity-risk proxy", "Cash target", "Signal close", "Coverage"], column_config={
        k: st.column_config.NumberColumn(format="percent") for k in ("Cash target", "Defensive assets", "Equity-risk proxy", "Cash change / week")})
    for bot in pack["bots"]:
        if "reason" in bot:
            st.caption(f"{bot['system']}: {bot['reason'].replace('_', ' ')}. Low-equity streak: {bot['defensive_streak_sessions']} sessions.")
    st.caption("Equity-risk proxy excludes listed Treasury, bond and gold instruments; it is not a beta estimate or constituent look-through. Low-risk means at most half the target in other instruments.")


def bot_view(pack, facts, timeline, day):
    bot_table(pack)
    st.subheader("Target-risk timeline")
    fig = go.Figure()
    for name in BOT_COLORS:
        key = f"{name}.equity"
        if key in timeline:
            fig.add_trace(go.Scatter(x=timeline.index, y=timeline[key], name=name, line=dict(color=BOT_COLORS[name], width=2, shape="hv"), connectgaps=False))
    fig.update_yaxes(title="Equity-risk instrument proxy", tickformat=".0%", range=[0, 1.05])
    st.plotly_chart(plot_style(fig), width="stretch")
    selected = st.selectbox("Specialist detail", [b["system"] for b in pack["bots"]])
    bot = next(b for b in pack["bots"] if b["system"] == selected)
    if "cash" not in bot:
        st.info("No usable target or native telemetry for this session.")
        return
    a, b = st.columns(2)
    a.subheader("Target basket")
    a.dataframe(pd.Series(bot["target_holdings"], name="Target weight").sort_values(ascending=False).to_frame(), width="stretch")
    b.subheader("Native rule and boundaries")
    b.write(bot["reason"].replace("_", " ").capitalize())
    b.caption(bot["semantics"].replace("_", " "))
    b.write(f"Last material target change: {bot['last_target_change'] or 'Not observed'}")
    for text in bot["limitations"]:
        b.caption(text)
    with b.expander("Frozen native rule specification"):
        st.json(bot["rules"])
    st.subheader("Drivers versus monitors")
    rows = [{"Signal": f["label"], "Value": display_value(f), "Role": f["role"], "Observed": f["observed_session"], "Fact ID": f["id"]} for f in facts.values() if f["source"] == selected]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def scorecard(summary, root, timeline):
    a, b, c = st.columns(3)
    a.metric("Sessions replayed", summary["sessions"])
    b.metric("Full fresh coverage", f"{summary['fully_fresh_days']} / {summary['sessions']}")
    c.metric("Prospective forecasts", "0")
    st.info("This is a retrospective signal-and-explanation replay, not a trading-performance or blind forecast backtest.")
    st.subheader("Did the stress flag distinguish subsequent damage?")
    st.caption("Frozen stress rule: QQQ drawdown at least 10%, plus SPY below its 200-session average or sector breadth below 40%. Outcome: at least 5% loss from the origin within the horizon. False defense: return above 2% with worst loss better than -3%.")
    score = pd.DataFrame(summary["scorecards"])
    st.dataframe(score, hide_index=True, width="stretch", column_config={
        k: st.column_config.NumberColumn(format="percent") for k in ("precision", "recall", "base_rate", "mean_forward_return")})
    st.subheader("Which signals carried information?")
    signals = pd.DataFrame(summary["signal_scorecards"])
    if signals.empty:
        st.info("Forward outcomes have not matured. Predictive performance is not yet evaluable.")
    else:
        a, b = st.columns(2)
        ticker = a.selectbox("Outcome benchmark", ["QQQ", "SPY"])
        horizon = b.selectbox("Forward sessions", [5, 21])
        st.dataframe(signals[signals.ticker.eq(ticker) & signals.horizon.eq(horizon)], hide_index=True, width="stretch", column_config={
            k: st.column_config.NumberColumn(format="percent") for k in ("precision", "recall", "base_rate", "mean_return_when_active", "mean_return_when_inactive")})
    st.caption("Precision must be compared with the base rate. High accuracy in a uniformly falling market is not evidence of a durable edge. Undefined values mean there were no eligible warnings or loss events.")
    st.subheader("Session history")
    st.dataframe(pd.DataFrame(summary["signal_onsets"]), hide_index=True, width="stretch")
    st.dataframe(timeline[["state", "fresh_specialists", "QQQ.drawdown.63", "SPY.return.21", "market.breadth"]].sort_index(ascending=False), width="stretch")
    st.subheader("Forward outcomes")
    st.dataframe(pd.read_csv(root / "outcomes.csv"), hide_index=True, width="stretch")
    for caveat in summary["evaluation_caveats"]:
        st.caption(caveat)
    st.download_button("Download outcome scorecard", (root / "outcomes.csv").read_bytes(), "market-desk-outcomes.csv", icon=":material/download:")
    if (root / "readout.md").exists():
        st.download_button("Download research readout", (root / "readout.md").read_text(), "market-desk-readout.md", icon=":material/download:")


def evidence_view(pack, facts, manifest, root, brief):
    st.subheader("Evidence ledger")
    st.caption(f"Archive captured {manifest['created_at_utc']} | Observations through {pack['information_cutoff_utc']}")
    st.dataframe(pd.DataFrame(pack["facts"]), hide_index=True, width="stretch")
    st.subheader("Coverage and limitations")
    for text in pack["limitations"]:
        st.write(text)
    st.write(f"Narration: **{brief['mode'].replace('_', ' ')}**")
    st.caption(f"Agent status: {brief['agent_status']}")
    st.json(manifest["source_identities"], expanded=False)
    st.download_button("Download fact pack", json.dumps(pack, indent=2), "market-fact-pack.json", icon=":material/download:")
    st.download_button("Download archive manifest", (root / "manifest.json").read_text(), "market-desk-manifest.json", icon=":material/download:")
    operating_context(root, pd.Timestamp(pack["as_of_session"]))


def operating_context(root, day):
    st.subheader("Captured operating records")
    st.caption("Separate from the frozen research-control replay above. Storage time is retained; these records do not create backdated forecasts or independent votes.")
    history = root / "context/trade-bot/operating_history.parquet"
    if history.exists():
        frame = pd.read_parquet(history)
        frame = frame[pd.to_datetime(frame.market_date) <= day].drop_duplicates("market_date", keep="first")
        frame = frame[pd.to_datetime(frame.market_date) >= day - pd.Timedelta(days=65)]
        frame["capture_timing"] = "historical_or_after_close_capture"
        if "stored_at_utc" in frame:
            frame["stored_at_utc"] = frame.stored_at_utc.fillna("")
        st.markdown("**Trade Bot operating summary**")
        st.dataframe(frame.drop(columns=["combined_config_hash"], errors="ignore"), hide_index=True, width="stretch")
        st.caption("The operating risk-budget multiplier is one stage of that pipeline, not total equity exposure. It is not interchangeable with the reconstructed control's final target weight.")
    cycle = root / "context/trade-bot/cycle_context.json"
    if cycle.exists():
        rows = json.loads(cycle.read_text())
        rows = [r for r in rows if r.get("market_date", "9999") <= str(day.date())]
        st.markdown("**Cycle Tracker / context only**")
        if rows:
            latest = rows[0]
            st.write(f"Structured phase: {latest['dominant_phase'].replace('_', ' ')}. Observation: {latest['market_date']}. Captured: {latest['created_at_utc']}.")
            st.warning("Raw phase and smoothed narrative may disagree. The transition model has known structural restrictions; neither is an allocation override.")
            with st.expander("Stored Cycle Tracker readout"):
                st.text(latest.get("readout", "Unavailable"))
        else:
            st.caption("No Cycle Tracker context at or before this observation date.")
    stock = root / "context/swing-trader/stock_context.json"
    if stock.exists():
        payload = json.loads(stock.read_text())
        st.markdown("**Swing stock shadow / separate from the monthly ETF control**")
        st.json(payload, expanded=False)
        st.caption("This is the latest captured operational audit, not a historical vote for the selected session.")
    fundamental = root / "context/fundamental_event.json"
    if fundamental.exists():
        gate = json.loads(fundamental.read_text())
        st.markdown("**Fundamental Event Trader**")
        st.write(f"Data qualification: {gate['status']}. Portfolio allocation allowed: {gate['portfolio_allocation_allowed']}.")
        st.caption(", ".join(gate["errors"]))
