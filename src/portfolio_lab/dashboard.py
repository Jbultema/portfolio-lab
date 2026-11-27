from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from portfolio_lab.audit import audit


def research_view():
    st.title("Portfolio Lab")
    pointer = Path("reports/latest.json")
    default = os.environ.get("PORTFOLIO_LAB_REPORT")
    if default is None and pointer.exists():
        default = json.loads(pointer.read_text())["report"]
    if not default:
        st.warning("No evaluated portfolio")
        return
    report = Path(default)
    checked = audit(report)
    if checked["errors"]:
        st.error("Evidence unavailable: " + ", ".join(checked["errors"]))
        return
    current = json.loads((report / "current_state.json").read_text())
    st.caption(f"Close {current['as_of_close']} | Research only | No action authorized")
    a, b, c = st.columns(3)
    a.metric("Market State", current["market_state"]["state"].title())
    b.metric("Candidate Cash", f"{current['cash']:.1%}")
    c.metric("Selected Research Policy", current["selected_research_policy"])
    performance, allocation, overlap, stress, research = st.tabs(
        ["Performance", "Allocation", "Overlap", "Execution", "Evidence"]
    )
    with performance:
        returns = pd.read_parquet(report / "returns.parquet")
        names = st.multiselect(
            "Portfolios",
            list(returns),
            default=[
                "trade_primary",
                "equal_blend",
                current["selected_research_policy"],
                "buy_hold_SPY",
            ],
        )
        period = st.selectbox(
            "Period",
            [
                "full",
                "later_diagnostic",
                "recent_diagnostic",
                "current_transition",
                "development",
                "validation",
            ],
        )
        starts = {
            "later_diagnostic": "2019-01-01",
            "recent_diagnostic": "2024-01-01",
            "current_transition": "2026-06-01",
            "validation": "2012-01-01",
        }
        ends = {
            "development": "2011-12-31",
            "validation": "2018-12-31",
            "later_diagnostic": "2023-12-31",
        }
        r = returns.loc[starts.get(period) : ends.get(period), names]
        figure = make_subplots(
            rows=2, cols=1, shared_xaxes=True, row_heights=[0.67, 0.33], vertical_spacing=0.06
        )
        for name in names:
            equity = r[name].add(1).cumprod()
            figure.add_trace(go.Scatter(x=equity.index, y=equity * 100, name=name), row=1, col=1)
            figure.add_trace(
                go.Scatter(
                    x=equity.index,
                    y=equity.div(equity.cummax().clip(lower=1)).sub(1),
                    name=name,
                    showlegend=False,
                ),
                row=2,
                col=1,
            )
        figure.update_yaxes(title_text="Growth of 100", row=1, col=1)
        figure.update_yaxes(title_text="Drawdown", tickformat=".0%", row=2, col=1)
        figure.update_layout(
            height=600, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h")
        )
        st.plotly_chart(figure, width="stretch")
        m = pd.read_csv(report / "metrics.csv")
        st.dataframe(
            m[m.period.eq(period) & m.candidate.isin(names)]
            .set_index("candidate")
            .drop(columns=["family", "period"]),
            width="stretch",
        )
    with allocation:
        left, right = st.columns(2)
        left.dataframe(pd.Series(current["budgets"], name="Budget").to_frame(), width="stretch")
        right.dataframe(
            pd.Series(current["target_holdings"], name="Target")
            .sort_values(ascending=False)
            .to_frame(),
            width="stretch",
        )
        st.line_chart(pd.read_parquet(report / "selected_budgets.parquet"))
    with overlap:
        st.dataframe(pd.read_csv(report / "orthogonality.csv"), width="stretch")
        st.dataframe(pd.read_csv(report / "price_sources.csv"), width="stretch")
    with stress:
        st.dataframe(pd.read_csv(report / "execution_stress.csv"), width="stretch")
        st.dataframe(pd.read_csv(report / "episodes.csv"), width="stretch")
    with research:
        st.dataframe(pd.read_csv(report / "bootstrap.csv"), width="stretch")
        st.dataframe(pd.read_csv(report / "trial_registry.csv"), width="stretch")
        st.download_button(
            "Research Report", (report / "report.md").read_text(), file_name="portfolio-research.md"
        )


def main():
    st.set_page_config(page_title="Market Desk | Portfolio Lab", layout="wide", page_icon=":material/monitoring:")
    st.markdown("""<style>
    h1{font-size:2rem!important;letter-spacing:0!important}
    h2{font-size:1.3rem!important;letter-spacing:0!important}
    h3{font-size:1.08rem!important;letter-spacing:0!important}
    [data-testid="stMetricValue"]{font-size:1.65rem}
    </style>""", unsafe_allow_html=True)
    from portfolio_lab.operations_ui import controls

    controls()
    if st.query_params.get("workspace") == "operations":
        from portfolio_lab.operations_ui import render

        render()
        return
    if st.query_params.get("workspace") == "position":
        from portfolio_lab.operations_ui import position_view

        position_view()
        return
    if st.query_params.get("workspace") == "event":
        from portfolio_lab.briefing import verify_replay
        from portfolio_lab.desk_ui import event_view

        pointer = json.loads(Path("reports/market-desk/latest.json").read_text())
        root = Path(pointer["report"])
        manifest = verify_replay(root)
        selected = manifest["sessions"][-1]
        event_view(root, selected, selected)
        return
    if st.query_params.get("workspace") == "system":
        from portfolio_lab.system_scorecard_ui import render

        render()
        return
    if st.query_params.get("workspace") == "adaptive" or os.environ.get("PORTFOLIO_LAB_ADAPTIVE"):
        from portfolio_lab.dynamic_ui import render

        render(os.getenv("PORTFOLIO_LAB_ADAPTIVE", "reports/adaptive-allocation/latest.json"))
        return
    if st.query_params.get("workspace") == "dynamic" or os.environ.get("PORTFOLIO_LAB_DYNAMIC"):
        from portfolio_lab.dynamic_ui import render

        render()
        return
    if st.query_params.get("workspace") == "combination" or os.environ.get("PORTFOLIO_LAB_STRESS"):
        from portfolio_lab.combination_ui import render

        render()
        return
    pointer = Path("reports/market-desk/latest.json")
    if os.environ.get("PORTFOLIO_LAB_DESK") or (pointer.exists() and not os.environ.get("PORTFOLIO_LAB_REPORT")):
        from portfolio_lab.desk_ui import render

        render(research_view)
    else:
        research_view()


if __name__ == "__main__":
    main()
