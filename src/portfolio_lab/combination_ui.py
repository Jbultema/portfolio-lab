"""Read-only cross-specialist evidence; no path from this view to allocation."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from portfolio_lab.combination_stress import KIND, verify
from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.research import PERIODS

LABELS = {
    "trade_primary": "Trade Bot / i111 primary",
    "swing_primary": "Swing Trader",
    "rotation_primary": "Rotation Trader",
    "portfolio_lab_frozen": "Portfolio Lab / frozen allocator",
    "threeway_80_10_10": "Trade 80 / Swing 10 / Rotation 10",
    "threeway_60_20_20": "Trade 60 / Swing 20 / Rotation 20",
    "threeway_equal": "Three bots / equal budgets",
    "buy_hold_SPY": "SPY buy & hold",
    "buy_hold_QQQ": "QQQ buy & hold",
    "allocator_conditional": "Regime-conditioned allocator",
    "allocator_inverse_vol": "Inverse-volatility allocator",
}
COLORS = ["#176bb5", "#00836d", "#bd4b36", "#8c5198", "#686e76", "#a67b13"]


def label(name):
    if name in LABELS:
        return LABELS[name]
    if name.startswith("risk_match__"):
        return "Risk-matched Trade / " + label(name.removeprefix("risk_match__"))
    if name.startswith("probe__"):
        _, parent, share, probe = name.split("__", 3)
        return f"{share}% {label(probe)} + {label(parent)}"
    if name.startswith("parent_cash__"):
        _, parent, share = name.split("__")
        return f"{label(parent)} / {share}% removed to cash"
    if name.startswith(("event__", "structural__")):
        text = name.split("__", 1)[1]
        for before, after in (("cash_conversion_improvement", "Cash conversion"),
                              ("executed_net_common_repurchase", "Net repurchases"),
                              ("working_capital_repair", "Working-capital repair"),
                              ("self_funded_repurchase", "Self-funded repurchases"),
                              ("liquidity_repair", "Liquidity repair"),
                              ("_price_confirmed", " / trend confirmed"),
                              ("_event_only", " / event only"),
                              ("_h126", " / 126 sessions"), ("_h63", " / 63 sessions"),
                              ("_h21", " / 21 sessions")):
            text = text.replace(before, after)
        return text
    return name.replace("_", " ")


def load_evidence(pointer):
    config = json.loads(Path(pointer).read_text())
    root = Path(config["report"])
    if digest(root / "manifest.json") != config["manifest_sha256"]:
        raise ContractError("Combination manifest pointer mismatch")
    summary = verify(root)
    if summary["kind"] != KIND or summary["event_admitted"] is not False:
        raise ContractError("Unexpected combination research authority")
    frames = {name: pd.read_csv(root / f"{name}.csv") for name in (
        "performance", "episodes", "uncertainty", "frozen_position_shocks",
        "development_risk_fits", "scenario_counts", "signal_outages")}
    frames["returns"] = pd.read_parquet(root / "returns.parquet")
    return root, summary, json.loads((root / "protocol.json").read_text()), frames


def comparison_table(rows, baseline="trade_primary"):
    table = rows.set_index("candidate").copy()
    if baseline not in table.index:
        raise ContractError("Comparison is missing its unchanged Trade Bot control")
    table["cagr_delta"] = table.cagr - table.loc[baseline, "cagr"]
    table["drawdown_delta"] = table.max_drawdown - table.loc[baseline, "max_drawdown"]
    columns = ["cagr", "max_drawdown", "cagr_delta", "drawdown_delta", "sharpe", "average_risky_exposure", "annual_turnover"]
    out = table[columns].rename(columns={
        "cagr": "CAGR", "max_drawdown": "Max drawdown", "cagr_delta": "CAGR vs Trade",
        "drawdown_delta": "DD improvement vs Trade", "sharpe": "Sharpe",
        "average_risky_exposure": "Invested", "annual_turnover": "Annual turnover"})
    out.index = out.index.map(label)
    return out


def appraisal(rows, *, blend=None, parent="trade_primary", cash=None):
    frame = rows.set_index("candidate")
    if blend is None:
        blend = "portfolio_lab_frozen"
    if blend not in frame.index or parent not in frame.index:
        return []
    change = (frame.loc[blend, "cagr"] - frame.loc[parent, "cagr"]) * 100
    protection = (frame.loc[blend, "max_drawdown"] - frame.loc[parent, "max_drawdown"]) * 100
    messages = [f"{label(blend)}: {change:+.2f} percentage points of CAGR and {protection:+.2f} points of drawdown improvement versus {label(parent)} in this window."]
    if cash and cash in frame.index:
        return_change = (frame.loc[blend, "cagr"] - frame.loc[cash, "cagr"]) * 100
        drawdown_change = (frame.loc[blend, "max_drawdown"] - frame.loc[cash, "max_drawdown"]) * 100
        messages.append(f"Versus leaving the same sleeve in cash: {return_change:+.2f} points of CAGR and {drawdown_change:+.2f} points of drawdown improvement. Negative drawdown improvement means a larger loss.")
    else:
        messages.append("A shallower drawdown is not by itself added skill. Development-fitted Trade Bot controls separate some of the benefit of lower risk from the benefit of combining models.")
    return messages


def show_table(frame):
    percentages = {c: "{:.2%}" for c in frame if c not in {"Sharpe", "Annual turnover"}}
    formats = {**percentages, "Sharpe": "{:.2f}", "Annual turnover": "{:.2f}x"}
    st.dataframe(frame.style.format({c: f for c, f in formats.items() if c in frame}), width="stretch")


def chart_label(name):
    if name.startswith("risk_match__"):
        return "Risk-matched Trade"
    if name.startswith("probe__"):
        _, parent, share, _ = name.split("__", 3)
        return f"{'Trade' if parent == 'trade_primary' else 'Lab'} + {share}% event"
    if name.startswith("parent_cash__"):
        _, parent, share = name.split("__")
        return f"{'Trade' if parent == 'trade_primary' else 'Lab'} / {share}% to cash"
    return label(name)


def curves(returns, scope, names, start, end, lag=1, cost=25):
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.64, .36], vertical_spacing=.08)
    for i, name in enumerate(names):
        key = f"{scope}|{name}|lag{lag}|cost{cost}"
        if key not in returns:
            continue
        series = returns[key].loc[start:end].dropna()
        if series.empty:
            continue
        wealth = series.add(1).cumprod()
        color = COLORS[i % len(COLORS)]
        figure.add_trace(go.Scatter(x=wealth.index, y=wealth * 100, name=chart_label(name), line=dict(color=color, width=2)), row=1, col=1)
        dd = wealth.div(wealth.cummax().clip(lower=1)).sub(1)
        figure.add_trace(go.Scatter(x=dd.index, y=dd, name=label(name), showlegend=False, line=dict(color=color, width=1.5)), row=2, col=1)
    figure.update_yaxes(title_text="Growth of 100", row=1, col=1)
    figure.update_yaxes(title_text="Drawdown", tickformat=".0%", row=2, col=1)
    figure.update_layout(height=520, margin=dict(l=5, r=5, t=45, b=8), hovermode="x unified",
                         legend=dict(orientation="h", y=1.14), font=dict(size=12),
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="#e5e9ed")
    st.plotly_chart(figure, width="stretch")


def event_capture():
    pointer = Path(os.getenv("PORTFOLIO_LAB_STRESS", "reports/combination-stress/latest.json"))
    if not pointer.exists():
        return
    try:
        _, summary, _, _ = load_evidence(pointer)
    except (OSError, ValueError, KeyError, TypeError, ContractError):
        st.warning("The newer conditional event study failed evidence verification; its results are withheld.")
        return
    st.subheader("Conditional accounting research")
    st.write(f"{summary['event_probes']} accounting-policy probes are integrated into the combination study through {summary['as_of_close']}. They remain outside the qualified-specialist count and cannot set the daily allocation.")
    st.caption("Cash conversion, executed repurchases, working-capital repair, self-funded repurchases and liquidity repair. This is a ten-survivor sample, not a broad historical or prospective validation of the ten-family research program.")
    st.link_button("Combination lab", "?workspace=combination", icon=":material/compare_arrows:")


def render(pointer=None):
    st.markdown("""<style>
    .block-container{max-width:1600px;padding-top:1.7rem;padding-bottom:3rem}
    h1{font-size:2rem!important;letter-spacing:0!important}
    h2{font-size:1.3rem!important;letter-spacing:0!important}
    h3{font-size:1.08rem!important;letter-spacing:0!important}
    [data-testid="stMetric"]{border-top:2px solid #d8e0e9;padding:10px 0;min-height:88px}
    [data-testid="stMetricValue"]{font-size:1.6rem!important}
    @media(max-width:640px){[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){flex-wrap:wrap!important}
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"])>[data-testid="stColumn"]{min-width:calc(50% - .5rem)!important;flex:1 1 calc(50% - .5rem)!important}}
    </style>""", unsafe_allow_html=True)
    st.title("Combination Lab")
    try:
        root, summary, protocol, data = load_evidence(pointer or os.getenv("PORTFOLIO_LAB_STRESS", "reports/combination-stress/latest.json"))
    except (OSError, ValueError, KeyError, TypeError, ContractError) as exc:
        st.error(f"Verified combination evidence unavailable: {type(exc).__name__}")
        return
    st.caption(f"CLOSE {summary['as_of_close']}  |  Fixed-slate research  |  No allocation changes authorized")
    st.warning("Event probes are conditional research, not an admitted fourth bot. Ten surviving stocks and short coverage cannot establish a durable event edge.")
    scope = st.radio("Evidence scope", ["Core history", "Conditional event probes"], horizontal=True)
    event = scope == "Conditional event probes"
    key = "conditional_events" if event else "core_history"
    rows = data["performance"].query("scope == @key")
    a, b, c = st.columns(3)
    a.metric("Core history", f"{summary['core_start'][:4]} - {summary['as_of_close'][:4]}")
    b.metric("Portfolio stress paths", f"{summary['portfolio_paths_including_controls_and_stresses']:,}")
    c.metric("Event policies / admitted", f"{summary['event_probes']} / 0")
    period = st.selectbox("Measurement window", list(protocol["event_periods"]) if event else ["full", "recent_diagnostic", "current_transition", "later_diagnostic", "validation", "development"],
                          index=2 if event else 0, key=f"window_{key}")
    scenarios = protocol["event_scenarios"] if event else protocol["core_scenarios"]
    scenario_pairs = [(s["lag"], s["cost_bps"]) for s in scenarios]
    scenario = st.selectbox("Execution case", scenario_pairs, index=scenario_pairs.index((1, 25)),
                            format_func=lambda s: f"{s[0]}-session close fill / {s[1]} bps per traded side", key=f"execution_{key}")
    lag, cost = scenario
    selected_rows = rows.query("period == @period and lag == @lag and cost_bps == @cost")
    if event:
        parent = st.selectbox("Parent portfolio", protocol["event_parents"], format_func=label)
        probe = st.selectbox("Event policy", protocol["event_probes"], format_func=label)
        share = st.select_slider("Event sleeve", options=[10, 25], value=10, format_func=lambda x: f"{x}%")
        blend = f"probe__{parent}__{share}__{probe}"
        control = f"parent_cash__{parent}__{share}"
        names = list(dict.fromkeys(["trade_primary", parent, blend, control, f"risk_match__{blend}"]))
        st.caption("2023-2024 development; 2025 onward previously inspected conditional evaluation. The cash control removes the same parent budget without adding event stocks.")
    else:
        options = [n for n in selected_rows.candidate if not n.startswith("risk_match__")]
        names = st.multiselect("Portfolios", options,
            default=["trade_primary", "portfolio_lab_frozen", "threeway_80_10_10", "threeway_equal", "buy_hold_SPY"], format_func=label)
        if "trade_primary" not in names:
            names = ["trade_primary", *names]
        st.caption("The i111-derived Trade Bot primary is unchanged. All bots share one captured price and cash history, consolidated holdings, and identical fill/cost assumptions. This close-fill replay is not the older native next-open backtest.")
    subset = selected_rows[selected_rows.candidate.isin(names)]
    if subset.empty or "trade_primary" not in set(subset.candidate):
        st.error("Selected comparison has no verified baseline.")
        return
    performance, crises, execution, evidence = st.tabs(["Performance", "Crisis & concentration", "Execution & outages", "Evidence"])
    with performance:
        st.subheader("What this comparison shows")
        for message in appraisal(subset, **({"blend": blend, "parent": parent, "cash": control} if event else {})):
            st.write(message)
        show_table(comparison_table(subset))
        start, end = (protocol["event_periods"] if event else PERIODS)[period]
        if (lag, cost) in {(1, 25), (5, 50)}:
            curves(data["returns"], key, names, start, end, lag, cost)
        else:
            st.caption("Daily paths are retained for the primary and joint execution-stress cases; all nine core execution cases retain audited summary metrics.")
        if not event:
            controls = selected_rows[selected_rows.candidate.isin([f"risk_match__{n}" for n in names] + ["trade_primary", "trade_cash_75", "trade_cash_90"])]
            st.subheader("Risk and cash controls")
            show_table(comparison_table(controls))
            st.caption("Risk scales are fitted through 2011 only, then frozen. Their performance is shown only for later windows, never as if the fitted scale were known during development.")
        st.subheader("Paired uncertainty")
        uncertainty = data["uncertainty"].query("scope == @key and period == @period and lag == @lag and cost_bps == @cost")
        uncertainty = uncertainty[uncertainty.candidate.isin(names)]
        if uncertainty.empty:
            st.caption("Intervals are reserved for the later/recent core windows and 2025-plus conditional evaluation, at primary and joint-stress execution.")
        else:
            display = uncertainty[["candidate", "reference", "annual_log_excess", "lower95", "upper95", "within_slate_max_abs_mean_p"]].copy()
            display["candidate"] = display.candidate.map(label)
            st.dataframe(display.style.format({"annual_log_excess": "{:.2%}", "lower95": "{:.2%}", "upper95": "{:.2%}", "within_slate_max_abs_mean_p": "{:.3f}"}), width="stretch", hide_index=True)
        st.caption("Paired 63-session blocks; 1,000 resamples. Annual log excess is not a CAGR difference. Adjusted tests cover this fixed slate, not the full history of strategy research. Shared price inputs and previously inspected history limit independence.")
    with crises:
        if not event:
            st.subheader("Shared return behavior")
            columns = [f"core_history|{n}|lag1|cost25" for n in ("trade_primary", "swing_primary", "rotation_primary")]
            correlation = data["returns"][columns].loc[start:end].corr()
            correlation.columns = [label(n) for n in ("trade_primary", "swing_primary", "rotation_primary")]
            correlation.index = correlation.columns
            st.dataframe(correlation.style.format("{:.2f}"), width="stretch")
            st.caption("Daily net-return correlations, primary execution case, selected window. Different repository names do not establish independent information.")
        st.subheader("Historical episode outcomes")
        episodes = data["episodes"].query("scope == @key and lag == @lag and cost_bps == @cost")
        episodes = episodes[episodes.candidate.isin(names)]
        if episodes.empty:
            st.info("No historical episode rows for this execution case and coverage. Conditional event data do not cover 2008, 2020 or 2022.")
        else:
            pivot = episodes.pivot(index="episode", columns="candidate", values="max_drawdown").rename(columns=label)
            st.dataframe(pivot.style.format("{:.2%}"), width="stretch")
            st.dataframe(episodes[["candidate", "episode", "total_return", "max_drawdown", "sessions"]], width="stretch", hide_index=True)
        st.subheader("Latest holdings / instantaneous shocks")
        st.caption("Hypothetical one-step holdings losses, not forecast probabilities or a model of reactive de-risking. Technology sleeves are shocked as correlated exposures; cash receives no shock.")
        shocks = data["frozen_position_shocks"].query("scope == @key")
        shocks = shocks[shocks.candidate.isin(names)]
        st.dataframe(shocks.pivot(index="shock", columns="candidate", values="frozen_position_return").rename(columns=label).style.format("{:.2%}"), width="stretch")
    with execution:
        st.subheader("Delay and cost sensitivity")
        stressed = rows[rows.candidate.isin(names) & rows.period.eq(period)]
        st.dataframe(stressed[["candidate", "lag", "cost_bps", "cagr", "max_drawdown", "annual_turnover"]].style.format({"cagr": "{:.2%}", "max_drawdown": "{:.2%}", "annual_turnover": "{:.2f}"}), width="stretch", hide_index=True)
        st.subheader("Signal-availability outages")
        st.caption("Core bots only: hold the last captured target for five sessions, then cash that sleeve through session 21. Deltas compare with the same unfaulted portfolio over the following 63-session window; no missing market prices are fabricated.")
        outages = data["signal_outages"]
        st.dataframe(outages[["parent", "missing_specialist", "outage_start", "total_return_change", "drawdown_change"]].style.format({"total_return_change": "{:.2%}", "drawdown_change": "{:.2%}"}), width="stretch", hide_index=True)
    with evidence:
        st.write("**No winning policy selected or promoted.** The full fixed slate includes standalone bots, buy-and-hold, cash controls, sleeve ablations, development-risk-matched controls, and conditional event combinations.")
        st.caption("Core history begins in 2006, so this study cannot establish dot-com-era protection. Event accounting uses a small surviving-stock sample with unverified original-release vintages, not a qualified point-in-time universe.")
        st.json(summary)
        st.dataframe(data["development_risk_fits"], width="stretch", hide_index=True)
        st.download_button("Download performance", (root / "performance.csv").read_bytes(), file_name="combination-performance.csv", icon=":material/download:")
        st.download_button("Download frozen protocol", (root / "protocol.json").read_text(), file_name="combination-protocol.json", icon=":material/download:")
    st.caption("Research-only comparison. Model weights are not account holdings. Human execution only; no derivatives, leverage, or trading authority added.")
