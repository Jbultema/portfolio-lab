"""Local control room and native deep-dive links."""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from portfolio_lab.operations import SYSTEMS, active, job_file, read_job, start, store

DASHBOARDS = {"trade-bot": ("Trade Bot deep dive", "http://localhost:8502"),
              "swing-trader": ("Swing Trader", "http://localhost:8501"),
              "rotation-trader": ("Rotation Trader", "http://localhost:8503"),
              "fundamental-event-trader": ("Event Trader", "?workspace=event"),
              "position-bot": ("Position Bot", "http://[::1]:8516")}


def controls():
    root = Path.cwd()
    with st.sidebar:
        st.link_button("Daily operations", "?workspace=operations", icon=":material/tune:", width="stretch")
        st.link_button("Positioning research", "?workspace=position", icon=":material/groups:", width="stretch")
        try:
            current = active(root)
        except (OSError, ValueError, KeyError):
            current = {"status": "unknown"}
        if st.button("Update all & publish", icon=":material/sync:", disabled=current is not None, width="stretch", key="global_daily_update"):
            result = start(root)
            st.session_state["daily_job_id"] = result["job_id"]
            st.rerun()
        if st.button("Rebuild verified local data", icon=":material/replay:", disabled=current is not None, width="stretch", key="cached_daily_update"):
            result = start(root, refresh=False)
            st.session_state["daily_job_id"] = result["job_id"]
            st.rerun()
        if current:
            st.caption("Daily update: " + current["status"])
        st.divider()
        config_file = root / "data/operations_config.json"
        config = json.loads(config_file.read_text()) if config_file.exists() else {}
        links = config.get("dashboards", {})
        for name, (label, url) in DASHBOARDS.items():
            destination = links.get(name, url)
            if name == "fundamental-event-trader":
                st.link_button(label, destination, icon=":material/open_in_new:", width="stretch")
                continue
            left, right = st.columns([5, 1])
            left.link_button(label, destination, icon=":material/open_in_new:", width="stretch")
            if right.button("", icon=":material/play_arrow:", help=f"Start {label}", key=f"launch_{name}"):
                from portfolio_lab.dashboard_services import launch

                try:
                    launch(root, name, destination)
                    st.rerun()
                except (OSError, ValueError) as exc:
                    st.error(str(exc))


@st.fragment(run_every="5s")
def progress():
    root = Path.cwd()
    pointer = store(root) / "latest.json"
    if not pointer.exists():
        st.info("No coordinated daily run has been recorded.")
        return
    try:
        active(root)
        job = json.loads(pointer.read_text())["job_id"]
        payload = read_job(root, job)
    except (OSError, ValueError, KeyError):
        st.error("Daily job receipt unavailable.")
        return
    a, b, c = st.columns(3)
    a.metric("Daily Run", payload["status"].replace("_", " ").title())
    b.metric("Requested Session", payload["expected_session"])
    complete = store(root) / "last_complete.json"
    c.metric("Fully Synchronized", json.loads(complete.read_text())["session"] if complete.exists() else "Not Yet")
    stages = pd.DataFrame(payload.get("stages", []))
    if not stages.empty:
        shown = stages.reindex(columns=["system", "status", "readiness", "finished_at_utc", "error"]).fillna("")
        shown.columns = ["System", "Update", "Readiness", "Finished (Denver)", "Error"]
        shown["Readiness"] = shown.Readiness.replace({"blocked_no_allocation_authority": "Blocked: data gates"})
        times = pd.to_datetime(shown["Finished (Denver)"], utc=True, errors="coerce")
        shown["Finished (Denver)"] = times.dt.tz_convert("America/Denver").dt.strftime("%b %d, %I:%M %p").fillna("")
        st.dataframe(shown, hide_index=True, width="stretch")
    if payload.get("error"):
        st.error(payload["error"])
    if payload["status"] in {"queued", "running"}:
        if st.button("Cancel update", icon=":material/stop:", key="cancel_daily"):
            job_file(root, job).with_name("cancel.request").touch(exist_ok=True)
            st.info("Cancellation requested.")
    if payload.get("report"):
        st.link_button("Open daily analysis", "?workspace=desk", icon=":material/description:")
    for stage in payload.get("stages", []):
        file = Path(stage["log"])
        if file.exists():
            with st.expander(stage["system"] + " log"):
                from portfolio_lab.system_inventory import redact_credentials

                st.code(redact_credentials(file.read_text(errors="replace")[-8000:]), language="text")


def render():
    st.title("Daily Operations")
    st.caption("Completed-session evidence | Research only | No orders authorized")
    progress()
    st.subheader("Connected Systems")
    st.dataframe(pd.DataFrame([{"system": name, "daily_mode": "Public news and qualified event context" if name == "fundamental-event-trader"
                              else "Frozen-rule data refresh", "allocation_authority": "None"} for name in SYSTEMS]),
                 hide_index=True, width="stretch")
    st.subheader("Schedule")
    import subprocess

    result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/com.jbultema.portfolio-lab.daily"],
                            capture_output=True, text=True, check=False) if os.uname().sysname == "Darwin" else None
    if result and result.returncode == 0:
        st.success("Coordinated daily scheduler is loaded. Completed-session checks run every 15 minutes while this Mac is awake.")
    else:
        st.warning("Coordinated daily scheduler is not loaded. The legacy report-only scheduler is a separate service.")


def position_view():
    from portfolio_lab.position_context import render as render_position

    st.title("Positioning Research")
    # Prefer the latest synchronized archive, not a review-only environment override.
    pointer = Path("reports/market-desk/latest.json")
    if not pointer.exists():
        st.info("No daily archive.")
        return
    from portfolio_lab.briefing import verify_replay

    root = Path(json.loads(pointer.read_text())["report"])
    verify_replay(root)
    render_position(root)
    file = Path("reports/position-integration/latest.json")
    if file.exists():
        pointer = json.loads(file.read_text())
        report = Path(pointer["report"])
        from portfolio_lab.position_stress import verify

        verify(report, pointer["manifest_sha256"])
        st.subheader("Does Positioning Improve The Portfolio?")
        performance = pd.read_csv(report / "performance.csv")
        period = st.selectbox("Evaluation period", list(performance.period.unique()))
        st.dataframe(performance[performance.period.eq(period)], hide_index=True, width="stretch")
        returns = pd.read_parquet(report / "returns.parquet")
        names = st.multiselect("Portfolios", list(returns), default=["trade_primary", "trade90_position10", "position_only"])
        st.line_chart(returns[names].add(1).cumprod())
        st.download_button("Positioning integration readout", (report / "readout.md").read_text(), "position-integration.md", icon=":material/download:")
