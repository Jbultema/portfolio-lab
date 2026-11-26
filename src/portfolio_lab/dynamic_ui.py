"""Read-only dynamic router research; no automatic specialist admission."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from portfolio_lab.adaptive_cash_audit import verify_audit
from portfolio_lab.adaptive_research import KIND as ADAPTIVE_KIND
from portfolio_lab.adaptive_research import verify as verify_adaptive
from portfolio_lab.combination_ui import COLORS
from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.dynamic_context_followup import verify as verify_followup
from portfolio_lab.dynamic_research import EVENT_PERIODS, PERIODS, verify

ROLES = {"raw": "Dynamic router", "capped": "Router / Trade exposure cap", "matched_trade": "Trade / matched target exposure",
         "cash_ablation": "Trade budget only / alternatives in cash", "no_event_ablation": "Event-free price ablation",
         "matched_spy": "Trade + SPY / matched invested target"}


def load_evidence(pointer):
    config = json.loads(Path(pointer).read_text())
    root = Path(config["report"])
    if digest(root / "manifest.json") != config["manifest_sha256"]:
        raise ContractError("Dynamic research pointer mismatch")
    kind = json.loads((root / "manifest.json").read_text()).get("kind")
    summary = verify_adaptive(root) if kind == ADAPTIVE_KIND else verify(root)
    registry = json.loads((root / "registry.json").read_text())
    event_registry = json.loads((root / "event_registry.json").read_text())
    frames = {n: pd.read_csv(root / f"{n}.csv") for n in ("performance", "episodes", "uncertainty", "switching", "exposure_audit", "frozen_shocks")}
    frames["returns"] = pd.read_parquet(root / "returns.parquet")
    if config.get("cash_audit_report"):
        cash_audit = Path(config["cash_audit_report"])
        if digest(cash_audit / "manifest.json") != config["cash_audit_manifest_sha256"]:
            raise ContractError("Cash audit pointer mismatch")
        cash_summary = verify_audit(cash_audit)
        if cash_summary["source_manifest_sha256"] != config["manifest_sha256"]:
            raise ContractError("Cash audit belongs to a different study")
        frames["cash_uncertainty"] = pd.read_csv(cash_audit / "uncertainty.csv")
        frames["cash_rolling"] = pd.read_csv(cash_audit / "rolling_consistency.csv")
    if config.get("followup_report"):
        followup = Path(config["followup_report"])
        if digest(followup / "manifest.json") != config["followup_manifest_sha256"]:
            raise ContractError("Follow-up pointer mismatch")
        verify_followup(followup)
        if json.loads((followup / "protocol.json").read_text())["source_manifest_sha256"] != config["manifest_sha256"]:
            raise ContractError("Follow-up belongs to a different primary study")
        frames["context_followup"] = pd.read_csv(followup / "performance.csv")
    return root, summary, registry["core"], event_registry, frames


def comparison(rows, candidate):
    baseline = rows[rows.candidate.eq("trade_primary") & rows.role.eq("raw")]
    if len(baseline) != 1:
        raise ContractError("Exactly one unchanged Trade comparison is required")
    baseline = baseline.iloc[0]
    selected = rows[rows.candidate.eq(candidate)].copy()
    selected["Portfolio"] = selected.role.map(ROLES)
    reference = rows[rows.candidate.eq("trade_primary") & rows.role.eq("raw")].copy()
    reference["Portfolio"] = "Unchanged Trade Bot"
    selected = pd.concat([reference, selected], ignore_index=True)
    selected["CAGR vs Trade"] = selected.cagr - baseline.cagr
    selected["DD improvement"] = selected.max_drawdown - baseline.max_drawdown
    return selected[["Portfolio", "cagr", "max_drawdown", "CAGR vs Trade", "DD improvement", "sharpe", "average_risky_exposure", "annual_turnover"]].rename(columns={"cagr": "CAGR", "max_drawdown": "Max drawdown", "sharpe": "Sharpe", "average_risky_exposure": "Invested", "annual_turnover": "Annual turnover"})


def performance_chart(returns, scope, candidate, roles, start, end, lag, cost):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.65, .35], vertical_spacing=.08)
    labels = {"raw": "Router", "capped": "Router capped", "matched_trade": "Trade matched", "matched_spy": "Trade + SPY", "cash_ablation": "Cash control"}
    paths = [("trade_primary", "raw", "Trade Bot")] + [(candidate, role, labels.get(role, ROLES[role])) for role in roles]
    for i, (name, role, label) in enumerate(paths):
        r = returns[f"{scope}|{name}|{role}|lag{lag}|cost{cost}"].loc[start:end].dropna()
        equity = r.add(1).cumprod()
        color = COLORS[i % len(COLORS)]
        fig.add_trace(go.Scatter(x=r.index, y=equity * 100, name=label, line=dict(color=color, width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=r.index, y=equity.div(equity.cummax().clip(lower=1)).sub(1), name=label, showlegend=False, line=dict(color=color, width=1.5)), row=2, col=1)
    fig.update_layout(height=540, margin=dict(l=5, r=5, t=85, b=8), hovermode="x unified", legend=dict(orientation="h", y=1.23),
                      font=dict(size=12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(title_text="Growth of 100", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown", tickformat=".0%", row=2, col=1)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e5e9ed")
    st.plotly_chart(fig, width="stretch")


def render(pointer=None):
    st.markdown("""<style>
    .block-container{max-width:1600px;padding-top:1.7rem;padding-bottom:3rem}
    h1{font-size:2rem!important;letter-spacing:0!important}h2{font-size:1.3rem!important;letter-spacing:0!important}h3{font-size:1.08rem!important;letter-spacing:0!important}
    [data-testid="stMetric"]{border-top:2px solid #d8e0e9;padding:10px 0;min-height:88px}
    [data-testid="stMetricValue"]{font-size:1.6rem!important}
    @media(max-width:640px){[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){flex-wrap:wrap!important}
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"])>[data-testid="stColumn"]{min-width:calc(50% - .5rem)!important;flex:1 1 calc(50% - .5rem)!important}}
    </style>""", unsafe_allow_html=True)
    try:
        root, summary, registry, events, data = load_evidence(pointer or os.getenv("PORTFOLIO_LAB_DYNAMIC", "reports/dynamic-allocation/latest.json"))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Verified dynamic research unavailable: {type(exc).__name__}")
        return
    adaptive = summary.get("kind") == ADAPTIVE_KIND
    st.title("Adaptive Allocation Research" if adaptive else "Dynamic Allocation Research")
    st.caption(f"CLOSE {summary['as_of_close']}  |  Three research rounds  |  No allocation changes authorized")
    st.warning("Retrospective research, not an untouched holdout or an approved portfolio. " + (
        "Cash top-ups can increase market risk; compare both matched-exposure controls. Online models use only matured labels."
        if adaptive else "Conditional event rules retain the small-sample and original-release-vintage limitations."))
    a, b, c = st.columns(3)
    a.metric("Core policies", summary["core_candidates"])
    b.metric("Mechanism families" if adaptive else "Conditional event policies", 8 if adaptive else summary["conditional_candidates"])
    c.metric("Execution paths", f"{summary['portfolio_paths_including_controls_and_stresses']:,}")
    event = bool(events) and st.radio("Study", ["Core dynamic routers", "Conditional event allocation"], horizontal=True) == "Conditional event allocation"
    scope = "conditional_events" if event else "core"
    specs = events if event else registry
    candidate = st.selectbox("Research policy", [s["name"] for s in specs], key=f"policy_{scope}")
    selected_spec = next(s for s in specs if s["name"] == candidate)
    periods = EVENT_PERIODS if event else PERIODS
    options = [n for n, (start, _) in periods.items() if (pd.Timestamp(start) if start else pd.Timestamp(summary["core_start"])) >= pd.Timestamp(selected_spec["available_from"])]
    preferred = "evaluation_2025_plus" if event else "post_selection_2019_plus"
    period = st.selectbox("Measurement window", options, index=options.index(preferred), key=f"window_{candidate}")
    lag, cost = st.selectbox("Execution case", [tuple(pair) for pair in summary.get("scenarios", [(1, 25), (1, 10), (5, 50)])], format_func=lambda pair: f"{pair[0]}-session close fill / {pair[1]} bps per traded side")
    rows = data["performance"].query("scope == @scope and period == @period and lag == @lag and cost_bps == @cost")
    table = comparison(rows, candidate)
    raw = table[table.Portfolio.eq("Dynamic router")].iloc[0]
    st.write(f"Selected router versus unchanged Trade Bot: **{raw['CAGR vs Trade'] * 100:+.2f} points of CAGR**, **{raw['DD improvement'] * 100:+.2f} points of drawdown improvement**. Positive drawdown improvement means a smaller loss.")
    st.caption(f"Simulated availability starts {selected_spec['available_from']}. Follow-ups selected only on earlier windows; later outcomes do not select the families. These dates are research chronology, not evidence that these rules were deployed live then.")
    if adaptive:
        st.caption(f"Pre-2019 gated research choice: {summary['gated_pre2019_research_candidate']}. This is not the best later-period row selected with hindsight.")
    performance, allocations, stresses, evidence = st.tabs(["Performance", "Budgets & exposure", "Crises & execution", "Selection & evidence"])
    with performance:
        formats = {n: "{:.2%}" for n in table if n not in {"Portfolio", "Sharpe", "Annual turnover"}}
        st.dataframe(table.style.format(formats | {"Sharpe": "{:.2f}", "Annual turnover": "{:.2f}x"}), hide_index=True, width="stretch")
        left, right = periods[period]
        roles = ["raw", "capped", "matched_trade"]
        if adaptive:
            roles.extend(["matched_spy", "cash_ablation"])
        performance_chart(data["returns"], scope, candidate, roles, left, right, lag, cost)
        st.caption("The capped router cannot exceed Trade Bot's close-known invested target. Its Trade control matches that target exposure; holdings may drift differently between trades. The cash ablation leaves every alternative budget uninvested.")
        if adaptive:
            st.caption("The SPY control retains Trade positions and adds the same surplus investment to SPY when the router invests more cash. This matches gross target exposure, not beta or exact realized exposure.")
        st.subheader("Paired excess uncertainty")
        intervals = data["uncertainty"].query("scope == @scope and candidate == @candidate and period == @period and lag == @lag and cost_bps == @cost")
        if intervals.empty:
            st.caption("Paired block intervals are evaluated for 2019 onward core results and 2025 onward conditional results, at primary and joint-stress execution.")
        else:
            st.dataframe(intervals[["reference", "block_sessions", "annual_log_excess", "lower95", "upper95", "within_slate_max_abs_mean_p"]].style.format({"annual_log_excess": "{:.2%}", "lower95": "{:.2%}", "upper95": "{:.2%}", "within_slate_max_abs_mean_p": "{:.3f}"}), hide_index=True, width="stretch")
        st.caption("1,000 paired resamples per 21/63/126-session block. Adjustments cover this slate, not the entire historical research program or adaptive selection history.")
        if "cash_uncertainty" in data:
            st.subheader("Does the cash control add value?")
            st.caption("Post-hoc analysis of already-replayed controls, not a newly qualified strategy. Compare full history as well as later results.")
            cash_intervals = data["cash_uncertainty"].query("candidate == @candidate and period == @period and lag == @lag and cost_bps == @cost")
            if not cash_intervals.empty:
                st.dataframe(cash_intervals[["block_sessions", "annual_log_excess", "lower95", "upper95", "within_slate_max_abs_mean_p"]].style.format({"annual_log_excess": "{:.2%}", "lower95": "{:.2%}", "upper95": "{:.2%}", "within_slate_max_abs_mean_p": "{:.3f}"}), hide_index=True, width="stretch")
            else:
                st.caption("Cash-control block intervals cover full history and 2019 onward at primary and joint-stress execution.")
            st.dataframe(data["cash_rolling"].query("candidate == @candidate"), hide_index=True, width="stretch")
        st.subheader("Complete policy slate")
        st.dataframe(rows[rows.role.eq("raw")][["candidate", "round", "cagr", "max_drawdown", "sharpe", "average_risky_exposure", "annual_turnover"]].style.format({"cagr": "{:.2%}", "max_drawdown": "{:.2%}", "sharpe": "{:.2f}", "average_risky_exposure": "{:.1%}", "annual_turnover": "{:.2f}"}), hide_index=True, width="stretch")
    with allocations:
        budget = pd.read_parquet(root / ("event_budgets.parquet" if event else "budgets.parquet"))[candidate].loc[left:right]
        plotted = budget.copy()
        plotted["cash" if adaptive else "unassigned_cash"] = 1 - budget.sum(axis=1)
        figure = go.Figure()
        for i, name in enumerate(plotted):
            figure.add_trace(go.Scatter(x=plotted.index, y=plotted[name], name=name.replace("_", " "), stackgroup="budget", line=dict(width=.5, color=COLORS[i % len(COLORS)])))
        figure.update_layout(height=350, margin=dict(l=5, r=5, t=50, b=10), legend=dict(orientation="h", y=1.15), hovermode="x unified")
        figure.update_yaxes(range=[0, 1], tickformat=".0%")
        st.plotly_chart(figure, width="stretch")
        st.caption("Risky-asset target contributions from each bot, after internal cash; the remainder is portfolio cash. These are not strategy-notional budgets. Daily projection keeps the combined portfolio long-only and unlevered."
                   if adaptive else "Strategy budgets before each bot's internal cash position. A 100% Trade Bot budget is not necessarily 100% equities. No minimum budget is reserved for alternatives.")
        if not event:
            st.dataframe(data["switching"].query("candidate == @candidate"), hide_index=True, width="stretch")
            st.dataframe(data["exposure_audit"].query("candidate == @candidate"), hide_index=True, width="stretch")
    with stresses:
        episode_rows = data["episodes"].query("scope == @scope and candidate == @candidate and lag == @lag and cost_bps == @cost")
        st.subheader("Historical episodes")
        st.dataframe(episode_rows, hide_index=True, width="stretch")
        st.subheader("Execution sensitivity")
        st.dataframe(data["performance"].query("scope == @scope and period == @period and candidate == @candidate"), hide_index=True, width="stretch")
        st.subheader("Latest holdings / hypothetical gaps")
        st.caption("Fixed instantaneous shocks, not probabilities, forecasts or a simulation of reactive de-risking.")
        st.dataframe(data["frozen_shocks"].query("scope == @scope and candidate == @candidate"), hide_index=True, width="stretch")
    with evidence:
        if "context_followup" in data:
            st.subheader("Additional price-context follow-up")
            st.caption("Six additional rules, prompted by a short-sample stress ablation. Post-hoc long-history falsification, not an untouched confirmation. Table: 2019 onward, next-close fills, 25 bps.")
            extra = data["context_followup"].query("period == 'post_selection_2019_plus' and role == 'raw' and lag == 1 and cost_bps == 25")
            st.dataframe(extra[["candidate", "cagr", "max_drawdown", "sharpe"]].style.format({"cagr": "{:.2%}", "max_drawdown": "{:.2%}", "sharpe": "{:.2f}"}), hide_index=True, width="stretch")
            st.download_button("Download context follow-up", data["context_followup"].to_csv(index=False), file_name="price-context-followup.csv", icon=":material/download:")
        st.json(selected_spec)
        for filename in ("selection_a.json", "selection_b.json"):
            st.json(json.loads((root / filename).read_text()))
        st.json(summary)
        st.download_button("Download performance", (root / "performance.csv").read_bytes(), file_name="dynamic-allocation-performance.csv", icon=":material/download:")
        st.download_button("Download protocol", (root / "protocol.json").read_text(), file_name="dynamic-allocation-protocol.json", icon=":material/download:")
        readout = Path("docs/adaptive_allocation_findings_20261126.md" if adaptive else "docs/dynamic_allocation_findings_20261126.md")
        if readout.is_file():
            st.download_button("Download research readout", readout.read_text(), file_name=readout.name, icon=":material/download:")
    st.caption("No automatic promotion. Model targets are not personal account holdings. Native bot strategies remain unchanged.")
