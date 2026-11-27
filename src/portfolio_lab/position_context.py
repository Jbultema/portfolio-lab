"""Positioning is separate conditional evidence, never a fourth independent market vote."""

import json
import math
import os
import re
import subprocess
from datetime import UTC, datetime

import pandas as pd

from portfolio_lab.contracts import ContractError


def validate(payload):
    if (not isinstance(payload, dict) or payload.get("schema_version") != 1
            or payload.get("system") != "position-bot" or payload.get("authority") != "research_only"
            or any(payload.get(k) is not False for k in ("action_authorized", "portfolio_allocation_allowed", "automatic_promotion_allowed"))
            or payload.get("status") not in {"research_shadow", "stale_research", "unavailable"}):
        raise ContractError("Invalid positioning context authority")
    captured = pd.Timestamp(payload.get("captured_at_utc"))
    if pd.isna(captured) or captured.tzinfo is None:
        raise ContractError("Ambiguous positioning capture")
    observations = payload.get("observations", [])
    if not isinstance(observations, list) or any(not isinstance(r, dict) for r in observations):
        raise ContractError("Malformed positioning observations")
    tickers = [r.get("ticker") for r in observations]
    if any(not isinstance(t, str) or not t for t in tickers) or len(tickers) != len(set(tickers)):
        raise ContractError("Invalid or duplicate positioning market")
    for row in observations:
        for field in ("asset_net_fraction_open_interest", "fast_net_fraction_open_interest"):
            number = row.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ContractError("Nonfinite positioning observation")
        if (not re.fullmatch(r"[0-9a-f]{64}", row.get("source_sha256", ""))
                or pd.Timestamp(row["report_date"]).date() > captured.date()
                or pd.Timestamp(row["scheduled_release_at"]) > captured):
            raise ContractError("Future or unbound positioning observation")
    weights = payload.get("target_holdings", {})
    if (not isinstance(weights, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                          or not math.isfinite(v) or v < 0 for v in weights.values())
            or sum(weights.values()) > 1 + 1e-10 or payload["status"] == "unavailable" and weights):
        raise ContractError("Invalid or unavailable positioning target")
    return payload


def capture(root):
    try:
        result = subprocess.run([str(root / ".venv/bin/python"), "-m", "position_bot.cli", "status"],
            cwd=root, env=os.environ | {"PYTHONPATH": str(root / "src")}, timeout=120,
            capture_output=True, text=True, check=True)
        return validate(json.loads(result.stdout))
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"schema_version": 1, "system": "position-bot", "authority": "research_only",
                "status": "unavailable", "action_authorized": False, "portfolio_allocation_allowed": False,
                "automatic_promotion_allowed": False, "captured_at_utc": datetime.now(UTC).isoformat(),
                "observations": [], "remaining_gates": ["Restore verified Position Bot daily capture"]}


def section(context):
    validate(context)
    lines = ["", "## Public Positioning", "", f"Status: {context['status']}. Research only; not an allocation vote."]
    if context.get("observations"):
        lines += [f"Price session: {context['as_of_session']}. Frozen research rule: {context['selected_rule']}.",
                  "", "| Market | Report date | Asset / managed-money net / OI | Leveraged / managed-money net / OI |", "|---|---|---:|---:|"]
        lines += [f"| {r['ticker']} | {r['report_date']} | {r['asset_net_fraction_open_interest']:.1%} | {r['fast_net_fraction_open_interest']:.1%} |"
                  for r in context["observations"]]
    lines += ["", "Remaining gates: " + "; ".join(context.get("remaining_gates", [])) + ".",
              "Historical release timing/original vintages remain conditional. Crowding alone is not a sell signal."]
    return "\n".join(lines)


def render(root):
    import streamlit as st

    st.subheader("Public Positioning")
    file = root / "context/position_bot.json"
    if not file.exists():
        st.info("No Position Bot capture in this archive.")
        return
    value = validate(json.loads(file.read_text()))
    st.caption(f"{value['status'].replace('_', ' ').title()} | No allocation authority")
    if value.get("observations"):
        frame = pd.DataFrame(value["observations"])
        import plotly.graph_objects as go

        chart = go.Figure()
        for field, label, color in (("asset_net_fraction_open_interest", "Asset / managed", "#12816a"),
                                     ("fast_net_fraction_open_interest", "Leveraged / managed", "#c76038")):
            chart.add_bar(x=frame.ticker, y=frame[field], name=label, marker_color=color,
                          hovertemplate="%{x}: %{y:.1%}<extra>" + label + "</extra>")
        chart.update_layout(height=350, barmode="group", margin=dict(l=8, r=8, t=55, b=8),
                            legend=dict(orientation="h", y=1.2, font=dict(size=11)),
                            font=dict(size=12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        chart.update_yaxes(title="Net / open interest", tickformat=".0%", gridcolor="#e8edf2")
        st.plotly_chart(chart, width="stretch")
        shown = frame[["ticker", "report_date", "asset_net_fraction_open_interest", "fast_net_fraction_open_interest", "fresh"]].copy()
        shown.columns = ["Market", "Report Date", "Asset / Managed Net", "Leveraged / Managed Net", "Fresh"]
        for column in ("Asset / Managed Net", "Leveraged / Managed Net"):
            shown[column] *= 100
        st.dataframe(shown, hide_index=True, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="%.1f%%")
            for column in ("Asset / Managed Net", "Leveraged / Managed Net")})
        st.caption("Financial futures: asset managers and leveraged funds. Gold: managed money in both series; not two independent groups.")
    st.warning("Historical timing and original-vintage qualification are incomplete. This is context, not an independent confirmation vote.")
