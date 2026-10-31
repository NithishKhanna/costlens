"""CostLens web app.  Run:  streamlit run app.py"""

from __future__ import annotations

import io
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from costlens import __version__
from costlens.data import DataValidationError, generate_demo_data, load_csv, prepare
from costlens.detectors import KIND_LABELS, Thresholds
from costlens.narrator import answer, executive_summary, llm_available, money
from costlens.pipeline import analyse
from costlens.report import to_markdown

st.set_page_config(page_title="CostLens", page_icon="🔎", layout="wide")

# ---------------------------------------------------------------------------
# Look and feel
# ---------------------------------------------------------------------------
INK, MUTED, TEAL, CORAL, AMBER, GRID = "#0F172A", "#64748B", "#0E9F8E", "#E4572E", "#F2A541", "#E2E8F0"
SEV_COLOR = {"high": CORAL, "medium": AMBER, "low": "#94A3B8"}

st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1280px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.cl-hero {display:flex; align-items:baseline; gap:.75rem; margin-bottom:.25rem;}
.cl-hero h1 {margin:0; font-size:2.1rem;}
.cl-tag {color:#64748B; font-size:1rem;}
.cl-kpi {border:1px solid #E2E8F0; border-radius:12px; padding:14px 16px; background:#FFFFFF; height:100%;}
.cl-kpi .l {color:#64748B; font-size:.8rem; text-transform:uppercase; letter-spacing:.04em;}
.cl-kpi .v {font-size:1.6rem; font-weight:700; color:#0F172A; line-height:1.3;}
.cl-kpi .s {font-size:.85rem; color:#64748B;}
.cl-kpi.accent {border-color:#0E9F8E; background:#F0FBF9;}
.cl-kpi.warn {border-color:#E4572E; background:#FFF5F2;}
.cl-card {border:1px solid #E2E8F0; border-left:5px solid var(--c); border-radius:10px;
          padding:12px 16px; margin-bottom:10px; background:#FFFFFF;}
.cl-card .t {font-weight:600; color:#0F172A;}
.cl-card .m {color:#64748B; font-size:.85rem; margin:2px 0 6px 0;}
.cl-pill {display:inline-block; padding:1px 8px; border-radius:999px; font-size:.75rem;
          font-weight:600; color:white; background:var(--c); margin-right:6px;}
.cl-save {float:right; font-weight:700; color:#0E9F8E;}
</style>
""",
    unsafe_allow_html=True,
)


def md(text: str) -> str:
    """Escape $ so Streamlit does not render dollar amounts as LaTeX."""
    return text.replace("\\$", "$").replace("$", "\\$")


def kpi(col, label, value, sub="", kind=""):
    col.markdown(f'<div class="cl-kpi {kind}"><div class="l">{label}</div><div class="v">{value}</div>'
                 f'<div class="s">{sub}</div></div>', unsafe_allow_html=True)


def style_fig(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="white",
                      paper_bgcolor="white", font=dict(color=INK, size=13),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), hovermode="x unified")
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


# ---------------------------------------------------------------------------
# Data + analysis (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_demo() -> tuple[pd.DataFrame, list[str]]:
    r = prepare(generate_demo_data())
    return r.df, r.warnings


@st.cache_data(show_spinner=False)
def load_upload(content: bytes) -> tuple[pd.DataFrame, list[str]]:
    r = load_csv(io.BytesIO(content))
    return r.df, r.warnings


@st.cache_data(show_spinner=False)
def run_analysis(df: pd.DataFrame, th: dict):
    return analyse(df, Thresholds(**th))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🔎 CostLens")
    st.caption("Why is platform cost growing faster than usage?")
    source = st.radio("Data", ["Demo data platform", "Upload my CSV"], label_visibility="collapsed")
    uploaded = None
    if source == "Upload my CSV":
        uploaded = st.file_uploader("Daily cost + usage per resource (CSV)", type=["csv"])
        sample_path = os.path.join(os.path.dirname(__file__), "data", "demo_cost_usage.csv")
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as fh:
                st.download_button("Download a sample CSV", fh.read(), "costlens_sample.csv", "text/csv")

    st.divider()
    st.markdown("**AI narrative**")
    key_input = st.text_input("Anthropic API key (optional)", type="password",
                              help="Used only for this session. Without a key CostLens uses its offline engine.")
    api_key = key_input or os.getenv("ANTHROPIC_API_KEY") or None
    use_llm = st.toggle("Use Claude for summaries and chat", value=True)
    ai_on = use_llm and llm_available(api_key)
    st.caption("🟢 Claude connected" if ai_on else "⚪ Offline mode: rule-based summaries and answers")

    with st.expander("Detection settings"):
        th = dict(
            idle_days=st.slider("Idle if no usage for (days)", 7, 30, 14),
            underutil_pct=st.slider("Over-provisioned below utilisation (%)", 10, 50, 25),
            unit_cost_increase_pct=st.slider("Flag cost-per-unit increase above (%)", 20, 200, 50, step=10),
            min_monthly_cost=st.slider("Ignore resources under ($/month)", 0, 1000, 100, step=50),
        )
    st.caption(f"v{__version__} · MIT licence")

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
try:
    if source == "Upload my CSV":
        if uploaded is None:
            st.markdown('<div class="cl-hero"><h1>CostLens</h1><span class="cl-tag">platform cost intelligence</span></div>',
                        unsafe_allow_html=True)
            st.info("Upload a CSV with one row per resource per day. Required columns: "
                    "`date, resource_id, service, cost_usd`. Optional: `resource_name, category, team, "
                    "environment, usage_units, usage_unit_name, utilization_pct`. See the Data tab of the "
                    "demo or the README for details.")
            st.stop()
        df, warnings = load_upload(uploaded.getvalue())
    else:
        df, warnings = load_demo()
except DataValidationError as exc:
    st.error(f"That file can't be analysed: {exc}")
    st.stop()

with st.spinner("Analysing cost and usage..."):
    a = run_analysis(df, th)
k = a.kpis

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------
st.markdown('<div class="cl-hero"><h1>CostLens</h1><span class="cl-tag">platform cost intelligence</span></div>',
            unsafe_allow_html=True)
st.caption(f"{k.start.date():%d %b %Y} – {k.end.date():%d %b %Y} · {k.n_resources} resources · "
           f"{k.n_teams} teams · {'demo data' if source.startswith('Demo') else uploaded.name}")
for w in warnings:
    st.warning(w)

c1, c2, c3, c4, c5 = st.columns(5)
kpi(c1, "Spend, last 30 days", money(k.cost_30d), f"{k.cost_growth_pct:+.1f}% vs previous 30 days")
gap_cost = k.cost_index_now - 100 if not np.isnan(k.cost_index_now) else np.nan
gap_use = k.usage_index_now - 100 if not np.isnan(k.usage_index_now) else np.nan
kpi(c2, "Cost vs usage",
    f"{gap_cost:+.0f}% / {gap_use:+.0f}%" if not np.isnan(gap_cost) else "n/a",
    "growth since start", "warn" if (gap_cost - gap_use) > 10 else "")
pct = a.monthly_savings / k.cost_30d * 100 if k.cost_30d else 0
kpi(c3, "Savings found", f"{money(a.monthly_savings)}/mo", f"{pct:.0f}% of spend · {money(round(a.monthly_savings) * 12)}/yr",
    "accent")
kpi(c4, "Annual run-rate", money(k.annual_run_rate), "at last-30-day pace")
kpi(c5, "No owner tag", f"{k.untagged_share_pct:.1f}%", f"{money(k.untagged_cost_30d)} in 30 days")
st.write("")

tabs = st.tabs(["Overview", "Findings", "Teams", "Spikes", "Forecast", "Ask CostLens", "Data"])

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
with tabs[0]:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Cost vs usage")
        idx = a.index.dropna(subset=["usage_index"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=idx["period"], y=idx["usage_index"], name="Usage index",
                                 line=dict(color=TEAL, width=3)))
        fig.add_trace(go.Scatter(x=idx["period"], y=idx["cost_index"], name="Cost index",
                                 line=dict(color=CORAL, width=3), fill="tonexty",
                                 fillcolor="rgba(228,87,46,0.12)"))
        fig.add_hline(y=100, line=dict(color=MUTED, dash="dot", width=1))
        fig.update_yaxes(title="Index (first 4 weeks = 100)")
        st.plotly_chart(style_fig(fig), width="stretch")
        st.caption("Usage index blends each resource's own usage (queries, task runs, reads, users) weighted "
                   "by its share of cost. The shaded area is spend that usage does not explain.")
    with right:
        st.subheader("Executive summary")
        cache_key = ("summary", hash(str(a.context)), ai_on)
        if cache_key not in st.session_state:
            if ai_on:
                with st.spinner("Claude is writing the summary..."):
                    st.session_state[cache_key] = executive_summary(a.context, True, api_key)
            else:
                st.session_state[cache_key] = executive_summary(a.context, False)
        text, src = st.session_state[cache_key]
        st.markdown(md(text))
        st.caption("Written by Claude from the computed numbers" if src == "claude" else "Offline summary")

    st.subheader("Where the money is")
    fx = a.findings[a.findings["est_monthly_savings"] > 0]
    if len(fx):
        by_kind = fx.groupby("label")["est_monthly_savings"].sum().sort_values()
        fig = go.Figure(go.Bar(x=by_kind.values, y=by_kind.index, orientation="h", marker_color=TEAL,
                               text=[money(v) for v in by_kind.values], textposition="outside"))
        fig.update_xaxes(title="Estimated savings ($/month)")
        fig.update_layout(hovermode="closest")
        st.plotly_chart(style_fig(fig, 60 + 45 * len(by_kind)), width="stretch")
    else:
        st.success("No savings opportunities found with the current settings.")

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
def resource_chart(rid: str):
    g = a.df[a.df["resource_id"] == rid].set_index("date").sort_index()
    w = g[["cost_usd", "usage_units"]].resample("W").sum(min_count=1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=w.index, y=w["cost_usd"], name="Cost ($/week)", marker_color="rgba(228,87,46,0.75)"))
    if w["usage_units"].notna().any():
        fig.add_trace(go.Scatter(x=w.index, y=w["usage_units"], name=f"{g['usage_unit_name'].iloc[-1]}/week",
                                 line=dict(color=TEAL, width=3), yaxis="y2"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, rangemode="tozero"))
    return style_fig(fig, 260)


with tabs[1]:
    f = a.findings
    st.subheader(f"{len(f)} findings · {money(a.monthly_savings)}/month to save")
    if not len(f):
        st.success("Nothing to fix. Cost is in line with usage.")
    else:
        fc1, fc2, fc3 = st.columns(3)
        sev = fc1.multiselect("Severity", ["high", "medium", "low"], default=["high", "medium", "low"])
        teams_sel = fc2.multiselect("Team", sorted(f["team"].unique()), default=sorted(f["team"].unique()))
        kinds = fc3.multiselect("Type", sorted(f["label"].unique()), default=sorted(f["label"].unique()))
        view = f[f["severity"].isin(sev) & f["team"].isin(teams_sel) & f["label"].isin(kinds)]
        for i, row in view.iterrows():
            c = SEV_COLOR[row["severity"]]
            save = (f'<span class="cl-save">save {money(row["est_monthly_savings"])}/mo</span>'
                    if row["est_monthly_savings"] > 0 else "")
            st.markdown(
                f'<div class="cl-card" style="--c:{c}">{save}<div class="t">{row["title"]}</div>'
                f'<div class="m"><span class="cl-pill" style="--c:{c}">{row["severity"]}</span>'
                f'{row["label"]} · {row["team"]} · {row["service"]} · {row["environment"]} · '
                f'{money(row["monthly_cost"])}/mo · {row["confidence"]} confidence</div>'
                f'<div><b>Why:</b> {row["evidence"]}</div><div><b>Do this:</b> {row["recommendation"]}</div></div>',
                unsafe_allow_html=True)
            with st.expander("Show the data behind this"):
                st.plotly_chart(resource_chart(row["resource_id"]), width="stretch",
                                key=f"rc-{i}")
        d1, d2 = st.columns(2)
        d1.download_button("Download findings (CSV)", view.to_csv(index=False), "costlens_findings.csv", "text/csv")
        summary_text = st.session_state.get(("summary", hash(str(a.context)), ai_on), (None,))[0]
        d2.download_button("Download full report (Markdown)", to_markdown(a, summary_text),
                           "costlens_report.md", "text/markdown")

# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Showback by team")
    t = a.teams.copy()
    show = pd.DataFrame({
        "Team": t["team"],
        "Spend, 30 days": t["cost_30d"].map(money),
        "Share": t["share_pct"].map(lambda v: f"{v:.0f}%"),
        "Cost change": t["cost_growth_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.0f}%"),
        "Usage change": t["usage_growth_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.0f}%"),
        "Savings available": t["savings_available"].map(lambda v: f"{money(v)}/mo"),
    })
    st.dataframe(show, hide_index=True, width="stretch")

    wk = a.df.copy()
    wk["week"] = wk["date"].dt.to_period("W").dt.start_time
    pv = wk.groupby(["week", "team"])["cost_usd"].sum().unstack(fill_value=0)
    pv = pv.iloc[1:-1] if len(pv) > 3 else pv
    palette = [TEAL, "#3B82F6", AMBER, "#8B5CF6", "#14B8A6", CORAL, "#94A3B8"]
    fig = go.Figure()
    for j, team in enumerate(pv.sum().sort_values(ascending=False).index):
        fig.add_trace(go.Bar(x=pv.index, y=pv[team], name=team, marker_color=palette[j % len(palette)]))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="$ per week")
    st.plotly_chart(style_fig(fig, 380), width="stretch")

    st.subheader("Top resources")
    r = a.resources.head(15)
    st.dataframe(pd.DataFrame({
        "Resource": r["resource_name"], "Team": r["team"], "Service": r["service"],
        "Spend, 30 days": r["cost_30d"].map(money),
        "Cost change": r["cost_growth_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.0f}%"),
        "Usage change": r["usage_growth_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.0f}%"),
    }), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Spikes
# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Daily spend and cost spikes")
    daily = a.df.groupby("date")["cost_usd"].sum()
    fig = go.Figure(go.Scatter(x=daily.index, y=daily.values, name="Daily spend", line=dict(color=INK, width=2)))
    if len(a.anomalies):
        an = a.anomalies
        fig.add_trace(go.Scatter(x=an["date"], y=daily.reindex(an["date"]).values, mode="markers",
                                 name="Spike", marker=dict(color=CORAL, size=13, symbol="diamond"),
                                 text=an["resource_name"], hovertemplate="%{text}<extra></extra>"))
    fig.update_yaxes(title="$ per day")
    st.plotly_chart(style_fig(fig, 360), width="stretch")
    if len(a.anomalies):
        an = a.anomalies
        st.dataframe(pd.DataFrame({
            "Date": an["date"].dt.date, "Resource": an["resource_name"], "Team": an["team"],
            "Actual": an["cost_usd"].map(money), "Normal": an["expected_usd"].map(money),
            "Excess": an["excess_usd"].map(money)}), hide_index=True, width="stretch")
        st.caption("A spike is a day far above the resource's own recent normal (robust z-score on a rolling "
                   "median, weekdays and weekends compared separately). Lasting step-changes are reported as "
                   "cost-per-unit findings instead.")
    else:
        st.success("No cost spikes detected.")

# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Next 90 days")
    fc = a.forecast
    hist, fut = fc[fc["actual"].notna()].tail(120), fc[fc["forecast"].notna()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist["date"], y=hist["actual"], name="Actual", line=dict(color=INK, width=1.5)))
    fig.add_trace(go.Scatter(x=fut["date"], y=fut["high"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fut["date"], y=fut["low"], fill="tonexty", fillcolor="rgba(228,87,46,0.12)",
                             line=dict(width=0), name="90% range", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fut["date"], y=fut["forecast"], name="If nothing changes",
                             line=dict(color=CORAL, width=3)))
    fig.add_trace(go.Scatter(x=fut["date"], y=fut["with_fixes"], name="With CostLens fixes",
                             line=dict(color=TEAL, width=3, dash="dash")))
    fig.update_yaxes(title="$ per day")
    st.plotly_chart(style_fig(fig, 380), width="stretch")
    f1, f2, f3 = st.columns(3)
    kpi(f1, "Next 90 days, no action", money(fut["forecast"].sum()))
    kpi(f2, "Next 90 days, with fixes", money(fut["with_fixes"].sum()), "fixes phased in over 30 days", "accent")
    kpi(f3, "Avoided spend", money(fut["forecast"].sum() - fut["with_fixes"].sum()), "in the next quarter")
    st.caption("Linear trend on the last 60 days with a weekday/weekend profile. Deliberately simple so "
               "finance can check it.")

# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Ask CostLens")
    st.caption("Answers come only from the numbers above. " +
               ("Claude is answering." if ai_on else "Offline mode: try the suggested questions."))
    if "chat" not in st.session_state:
        st.session_state.chat = []
    suggestions = ["Where can we save the most?", "Why is cost growing faster than usage?",
                   "What about the ML team?", "Were there any cost spikes?", "What has no owner?"]
    cols = st.columns(len(suggestions))
    clicked = None
    for c, s in zip(cols, suggestions):
        if c.button(s, width="stretch"):
            clicked = s
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(md(m["content"]))
    q = st.chat_input("Ask about cost, teams, resources, spikes...") or clicked
    if q:
        st.session_state.chat.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply, src = answer(q, a.context, ai_on, api_key, st.session_state.chat[:-1])
            st.markdown(md(reply))
        st.session_state.chat.append({"role": "assistant", "content": reply})

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Input data")
    st.dataframe(a.df.sort_values(["date", "resource_id"], ascending=[False, True]).head(500),
                 hide_index=True, width="stretch")
    st.markdown("""
**Expected format: one row per resource per day.**

| Column | Required | Example |
|---|---|---|
| `date` | yes | 2026-10-01 |
| `resource_id` | yes | wh-analytics |
| `service` | yes | Snowflake |
| `cost_usd` | yes | 482.10 |
| `resource_name` | no | ANALYTICS_WH |
| `category` | no | compute, warehouse, storage, database, saas, other |
| `team` | no | Analytics (blank = untagged) |
| `environment` | no | prod, staging, dev |
| `usage_units` | no | 9120 |
| `usage_unit_name` | no | queries |
| `utilization_pct` | no | 63.5 |

Common billing-export names such as `BilledCost`, `ServiceName`, `ResourceId` and `ChargePeriodStart`
(FOCUS format) are mapped automatically.
""")
