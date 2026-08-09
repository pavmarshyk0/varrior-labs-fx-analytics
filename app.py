"""Read-only local dashboard for precomputed alpha-research artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = REPO_ROOT / "data" / "research" / "alpha" / "latest"


@st.cache_data
def load(root: str) -> tuple[dict, pd.DataFrame]:
    base = Path(root).expanduser().resolve()
    families_path = base / "families.json"
    if not families_path.exists():
        raise FileNotFoundError(
            f"Missing {families_path}. Build local research artifacts first or select a valid artifact directory."
        )

    families = json.loads(families_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for family, summary in families.items():
        for key, metric in summary.get("metrics", {}).items():
            policy, scenario = key.split(":", 1)
            rows.append(
                {
                    "family": family,
                    "exit_policy": policy,
                    "scenario": scenario,
                    **metric,
                }
            )
    return families, pd.DataFrame(rows)


st.set_page_config(page_title="Varrior Labs — EUR/USD Alpha Research", layout="wide")
st.title("EUR/USD deterministic alpha research")
st.caption(
    "Observed OOS research only • no profitability claim • no live execution controls"
)

root = st.sidebar.text_input("Research artifact directory", str(DEFAULT_ROOT))
st.sidebar.caption(
    "Broker-derived datasets and generated research artifacts are local-only and are not committed to the public repository."
)

try:
    summaries, metrics = load(root)
except Exception as exc:
    st.warning(str(exc))
    st.info(
        "The public repository intentionally excludes broker data. Point this dashboard at a local research artifact directory after running the research pipeline."
    )
    st.stop()

required_columns = {
    "family",
    "scenario",
    "trades",
    "gross_expectancy_r",
    "cost_drag_r",
    "net_expectancy_r",
    "max_drawdown_r",
    "win_rate",
}
missing = required_columns.difference(metrics.columns)
if missing:
    st.error(f"Research artifact schema is missing required columns: {sorted(missing)}")
    st.stop()

baseline = metrics[metrics.scenario == "BASELINE_1X"].copy()
st.subheader("Overview")
st.dataframe(
    baseline[
        [
            "family",
            "trades",
            "gross_expectancy_r",
            "cost_drag_r",
            "net_expectancy_r",
            "max_drawdown_r",
            "win_rate",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

if not baseline.empty:
    cols = st.columns(4)
    best = baseline.sort_values("net_expectancy_r", ascending=False).iloc[0]
    cols[0].metric("Best observed family", best.family)
    cols[1].metric("Net expectancy", f"{best.net_expectancy_r:.3f} R")
    cols[2].metric("Final holdout", summaries[best.family]["final_holdout_status"])
    cols[3].metric("OOS trades", int(best.trades))

st.subheader("Cost hurdle: gross edge − execution costs = net edge")
fig = px.bar(
    baseline.melt(
        id_vars="family",
        value_vars=["gross_expectancy_r", "cost_drag_r", "net_expectancy_r"],
        var_name="metric",
        value_name="R",
    ),
    x="family",
    y="R",
    color="metric",
    barmode="group",
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Cost stress")
st.plotly_chart(
    px.line(metrics, x="scenario", y="net_expectancy_r", color="family", markers=True),
    use_container_width=True,
)

st.subheader("Data quality and reproducibility")
for family, summary in summaries.items():
    with st.expander(family):
        st.json(
            {
                "dataset": summary["dataset"],
                "walk_forward": summary["walk_forward"],
                "candidate_fingerprint": summary["candidate_universe_fingerprint"],
                "final_holdout_status": summary["final_holdout_status"],
            }
        )

st.info(
    "This dashboard only reads precomputed JSON/Parquet-derived research artifacts. It contains no broker integration, order controls, or automated execution path."
)

diagnostics_path = Path(root).resolve().parents[1] / "alpha_gen2" / "latest" / "failure_analysis.json"
if diagnostics_path.exists():
    st.subheader("Failure analysis & outcome geometry")
    diagnostic = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    for family, details in diagnostic.get("families", {}).items():
        with st.expander(family):
            st.write("Outcome geometry", details.get("outcome_geometry", {}))
            st.dataframe(
                pd.DataFrame(details.get("by_direction", {})).T,
                use_container_width=True,
            )
            st.dataframe(
                pd.DataFrame(details.get("by_session", {})).T,
                use_container_width=True,
            )
            st.write(
                "Pre-entry feature / gross-EV correlation",
                details.get("feature_gross_ev_correlation", {}),
            )
