"""Source-bound performance, specialist and prospective-evidence review surface."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio_lab.combination_stress import bound
from portfolio_lab.contracts import ContractError, digest


def load_scorecard(pointer):
    config = json.loads(Path(pointer).read_text())
    if config.get("schema_version") != 1 or config.get("action_authorized") is not False:
        raise ContractError("Research-only system scorecard required")
    folders, manifests = {}, {}
    for name in ("validation", "native", "specialists"):
        entry = config["archives"][name]
        root = Path(entry["path"])
        if digest(root / "manifest.json") != entry["manifest_sha256"]:
            raise ContractError("System evidence pointer integrity failure")
        manifest = json.loads((root / "manifest.json").read_text())
        for file, identity in manifest["artifacts"].items():
            bound(root, file, identity)
        folders[name], manifests[name] = root, manifest
    summary = json.loads((folders["validation"] / "summary.json").read_text())
    if summary.get("action_authorized") is not False or summary.get("portfolio_allocation_allowed") is not False:
        raise ContractError("Validation has unexpected allocation authority")
    if summary["native_manifest_sha256"] != digest(folders["native"] / "manifest.json"):
        raise ContractError("Native and common-clock study mismatch")
    checkpoints = []
    for item in config.get("checkpoints", []):
        path = Path(item["path"])
        if digest(path) != item["sha256"]:
            raise ContractError("Release receipt changed")
        checkpoints.append(json.loads(path.read_text()))
    return {"config": config, "summary": summary, "folders": folders, "manifests": manifests,
        "performance": pd.read_csv(folders["validation"] / "performance.csv"),
        "returns": pd.read_parquet(folders["validation"] / "returns.parquet"),
        "overlap": pd.read_csv(folders["specialists"] / "overlap.csv"), "checkpoints": checkpoints}


def candidate_label(spec):
    if spec["kind"] == "unchanged":
        return "Unchanged parent"
    if spec["kind"] == "static":
        return f"Static {spec['scale']:.0%} risk control"
    return f"{spec['mode'].title()} / {spec['lookback']} sessions / guard {spec['incumbent_drawdown_guard']}"


def remote_pr_state(item):
    read = item.get("public_pr_read", {})
    if read.get("verified") is not True:
        return "Unverified"
    return "Open" if read.get("data") else "None open"


def performance_view(data):
    specs = data["manifests"]["native"]["candidates"]
    parents = list(dict.fromkeys(spec["parent"] for spec in specs))
    parent = st.selectbox("Parent strategy", parents, format_func=lambda s: "Current i111 primary" if "reentry_vol" in s else "Native risk-repair challenger")
    options = [spec for spec in specs if spec["parent"] == parent]
    chosen = st.selectbox("Risk rule", options, format_func=candidate_label, index=1)
    a, b, c = st.columns(3)
    cost = a.selectbox("Trading cost per side", [25, 50, 10], format_func=lambda x: f"{x} bp")
    lag = b.selectbox("Fill delay", [1, 3], format_func=lambda x: f"{x} session" + ("s" if x != 1 else ""))
    period = c.selectbox("Historical window", ["full", "later", "pre2019", "recent"],
        format_func=lambda x: {"full": "Full shared history", "later": "2019 onward", "pre2019": "Before 2019", "recent": "2024 onward"}[x])
    sample = data["performance"].query("cost_bps == @cost and lag == @lag and period == @period").set_index("candidate")
    baseline = parent + "__unchanged"
    candidate = chosen["name"]
    left, right = sample.loc[baseline], sample.loc[candidate]
    a, b, c, d = st.columns(4)
    a.metric("Parent CAGR", f"{left.cagr:.2%}")
    b.metric("Candidate CAGR", f"{right.cagr:.2%}", f"{100*(right.cagr-left.cagr):+.2f} pp")
    c.metric("Parent maximum drawdown", f"{left.max_drawdown:.2%}")
    d.metric("Candidate maximum drawdown", f"{right.max_drawdown:.2%}")
    names = {"Parent": baseline, "Candidate": candidate, "Static 85%": parent + "__static85", "SPY": "buy_hold_SPY", "QQQ": "buy_hold_QQQ"}
    bounds = {"full": (None, None), "later": ("2019-01-01", None), "pre2019": (None, "2018-12-31"), "recent": ("2024-01-01", None)}
    first, last = bounds[period]
    fig = go.Figure()
    dd = go.Figure()
    for (label, name), color in zip(names.items(), ("#2476ba", "#d04b44", "#12806b", "#7d8790", "#9c55a8"), strict=True):
        equity = data["returns"][f"{name}|lag{lag}|cost{cost}"].loc[first:last].add(1).cumprod()
        fig.add_trace(go.Scatter(x=equity.index, y=equity, name=label, line={"color": color, "width": 2}))
        dd.add_trace(go.Scatter(x=equity.index, y=equity/equity.cummax().clip(lower=1)-1, name=label, line={"color": color, "width": 1.5}))
    for chart in (fig, dd):
        chart.update_layout(height=330, margin={"l": 8, "r": 8, "t": 16, "b": 12},
            legend={"orientation": "h"}, hovermode="x unified", paper_bgcolor="white", plot_bgcolor="white")
        chart.update_xaxes(showgrid=False)
        chart.update_yaxes(gridcolor="#e7ecef")
    st.subheader("Funded growth")
    fig.update_yaxes(title_text="Growth of $1")
    st.plotly_chart(fig, width="stretch")
    st.subheader("Drawdown path")
    dd.update_yaxes(tickformat=".0%")
    st.plotly_chart(dd, width="stretch")
    table = pd.DataFrame([{ "Model": label, "CAGR %": sample.loc[name].cagr*100,
        "Max DD %": sample.loc[name].max_drawdown*100, "Annual turnover": sample.loc[name].annual_turnover}
        for label, name in names.items()])
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Performance data", data["performance"].to_csv(index=False), "native-risk-performance.csv", "text/csv")
    st.caption("Selected modern-stock universe. Previously examined history, not a new holdout. Native and funded common-clock results are separate experiments.")


def specialists_view(data):
    st.subheader("Different decisions, shared information")
    st.dataframe(pd.DataFrame([
        {"System": "Trade Bot", "Decision": "Selected technology momentum and cash risk", "Evidence": "Conditional selected-stock history"},
        {"System": "Swing Trader", "Decision": "Monthly cross-asset momentum", "Evidence": "Not a validated fast panic system"},
        {"System": "Rotation Trader", "Decision": "Sector leadership and allocation timing", "Evidence": "Funded ledger corrected; no new promotion"},
        {"System": "Event Trader", "Decision": "Company filings and news", "Evidence": "Context only; broad historical gate unmet"},
    ]), hide_index=True, width="stretch")
    st.subheader("Same-clock overlap")
    st.dataframe(data["overlap"].round(3), hide_index=True, width="stretch")
    st.warning("Three price-driven bots are not three independent confirmations. Zero ticker overlap can still hide shared economic exposure.")
    st.caption("Full-sample correlations are descriptive. They do not establish a future diversification benefit or allocation rule.")


def forecasts_view(data):
    from portfolio_lab.forecast_accountability import score, summarize

    st.subheader("Captured forecasts")
    root = Path(os.getenv("PORTFOLIO_LAB_FORECASTS", "data/forecasts"))
    prices = pd.read_parquet(data["folders"]["native"] / "prices.parquet")
    rows = score(root, prices)
    if not rows:
        st.info("No prospective forecasts have been captured. Historical desk replays are reconstructions, not forecast evidence.")
        return
    frame = pd.DataFrame(rows)
    mature = frame[frame.status.eq("matured_uncalibrated") & frame.performance_eligible]
    a, b, c = st.columns(3)
    a.metric("Captured claims", len(frame))
    b.metric("Matured claims", len(mature))
    c.metric("Mean Brier score", f"{mature.brier.mean():.3f}" if len(mature) else "Pending")
    st.dataframe(frame, hide_index=True, width="stretch")
    st.subheader("Nonoverlapping evidence by forecast series")
    st.dataframe(pd.DataFrame(summarize(rows)), hide_index=True, width="stretch")
    st.caption("Lower Brier is better. Overlapping outcomes are not independent observations. No probability calibration or trading authority is implied.")
    st.download_button("Forecast records", json.dumps(rows, indent=2), "forecast-records.json", "application/json")


def releases_view(data):
    rows = []
    for checkpoint in data["checkpoints"]:
        for name, item in checkpoint["repositories"].items():
            checks = item.get("public_ci_read", {}).get("data", {}).get("check_runs", [])
            rows.append({"Cycle": checkpoint["cycle"], "Repository": name,
                "Tests passed": item["tests"]["passed"], "Clean release tree": item["worktree_clean"],
                "Personal push verified": item["pushed_and_read_back"], "PR state": remote_pr_state(item),
                "Reported CI checks": str(len(checks)) if item.get("public_ci_read", {}).get("verified") else "Unverified",
                "Commit": item["head"][:10]})
    st.subheader("Recorded release checkpoints")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.warning("Personal SSH pushes and local QA do not establish PR or remote-CI acceptance. Original worktrees retain protected data and pre-existing changes.")


def render():
    st.markdown("""<style>.block-container{max-width:1480px;padding-top:1.7rem}h1{font-size:2rem!important;letter-spacing:0!important}h2{font-size:1.3rem!important;letter-spacing:0!important}[data-testid=stMetricValue]{font-size:1.5rem}button{letter-spacing:0!important}</style>""", unsafe_allow_html=True)
    st.title("System Scorecard")
    st.markdown("[Market Desk](/)")
    try:
        data = load_scorecard(os.getenv("PORTFOLIO_LAB_SYSTEM", "reports/system-scorecard/latest.json"))
        summary = data["summary"]
        st.caption(f"RESEARCH ONLY | {summary['start']} to {summary['end']} | {summary['paths']} funded execution paths")
        st.warning("No new staged-risk candidate qualified for promotion. The operating primary is unchanged.")
        for tab, function in zip(st.tabs(["Performance", "Specialists", "Forecast Record", "Release Health"]),
            (performance_view, specialists_view, forecasts_view, releases_view), strict=True):
            with tab:
                function(data)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"System evidence unavailable: {type(exc).__name__}")
