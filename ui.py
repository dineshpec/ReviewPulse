"""ReviewPulse UI kit: design tokens, CSS, header, KPI cards and Plotly charts (presentation only)."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from schemas import NEEDS_REVIEW

APP_NAME = "ReviewPulse"
TAGLINE = "Understand every customer signal."
DESCRIPTION = "Highlights customer sentiment, review trends, ratings, and recurring complaints."

# ---- design tokens ----
TOKENS = {
    "brand": "#3730A3", "brand_soft": "#EEF0FF", "ink": "#111827", "muted": "#4B5563",
    "line": "#E5E7EB", "bg": "#F7F8FC", "card": "#FFFFFF",
    "radius": "14px", "gap": "1rem",
}
# Sentiment semantics green / amber / red. Labels and +/~/- marks always accompany colour.
SENTIMENT_COLORS = {"positive": "#15803D", "neutral": "#D97706", "negative": "#B91C1C", NEEDS_REVIEW: "#6B7280"}
SENTIMENT_ORDER = ["positive", "neutral", "negative"]
SEQ_COLOR = TOKENS["brand"]

CSS = """
<style>
:root {
  --brand:%(brand)s; --brand-soft:%(brand_soft)s; --ink:%(ink)s; --muted:%(muted)s;
  --line:%(line)s; --card:%(card)s; --radius:%(radius)s; --gap:%(gap)s;
}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] { visibility:hidden; }
header[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:2.2rem; padding-bottom:3rem; max-width:1280px; }
.rp-header { display:flex; align-items:center; gap:14px; padding:18px 22px; margin-bottom:var(--gap);
  background:linear-gradient(135deg,#312E81 0%%,#3730A3 55%%,#4F46E5 100%%); border-radius:var(--radius); color:#fff; }
.rp-header svg { flex:0 0 auto; }
.rp-name { font-size:1.6rem; font-weight:750; letter-spacing:-0.02em; line-height:1.1; margin:0; color:#fff; }
.rp-tag { font-size:1rem; margin:2px 0 0; color:#E0E7FF; }
.rp-desc { font-size:.85rem; margin:2px 0 0; color:#C7D2FE; }
.rp-card { background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:16px 18px;
  box-shadow:0 1px 2px rgba(17,24,39,.04); height:100%%; margin-bottom:.5rem; }
.rp-kpi-label { font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; }
.rp-kpi-value { font-size:1.9rem; font-weight:750; line-height:1.2; margin-top:4px; color:var(--ink); }
.rp-delta { display:inline-block; font-size:.8rem; font-weight:600; margin-top:4px; padding:2px 8px; border-radius:999px; }
.rp-delta.good { color:#14532D; background:#DCFCE7; } .rp-delta.bad { color:#7F1D1D; background:#FEE2E2; }
.rp-delta.flat { color:#374151; background:#F3F4F6; }
.rp-step { display:flex; gap:12px; align-items:flex-start; }
.rp-step-n { flex:0 0 32px; height:32px; border-radius:50%%; background:var(--brand); color:#fff; font-weight:700;
  display:flex; align-items:center; justify-content:center; }
.rp-step h4 { margin:0 0 2px; font-size:1.02rem; color:var(--ink); } .rp-step p { margin:0; color:var(--muted); font-size:.9rem; }
.rp-chip { display:inline-block; font-size:.78rem; padding:3px 10px; border-radius:999px; background:var(--brand-soft);
  color:var(--brand); font-weight:600; margin-right:6px; }
.rp-badge { display:inline-block; padding:1px 8px; border-radius:999px; font-size:.75rem; font-weight:700; color:#fff; }
.rp-example { border-left:3px solid #B91C1C; padding:4px 10px; margin:6px 0; color:var(--ink); font-size:.92rem; }
.stTabs [data-baseweb="tab-list"] { gap:6px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight:600; padding:8px 14px; }
button:focus-visible, [role="tab"]:focus-visible { outline:3px solid #A5B4FC !important; outline-offset:2px; }
@media (max-width: 640px) {
  .rp-header { padding:14px; } .rp-name { font-size:1.25rem; } .rp-kpi-value { font-size:1.5rem; }
}
</style>
""" % TOKENS

LOGO_SVG = (
    '<svg width="46" height="46" viewBox="0 0 48 48" role="img" aria-label="ReviewPulse logo" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="48" height="48" rx="12" fill="#FFFFFF" fill-opacity=".16"/>'
    '<polyline points="6,26 15,26 20,13 27,37 33,22 37,26 42,26" fill="none" stroke="#FFFFFF" stroke-width="3.2" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header() -> None:
    st.markdown(
        f'<div class="rp-header">{LOGO_SVG}<div><p class="rp-name">{APP_NAME}</p>'
        f'<p class="rp-tag">{TAGLINE}</p><p class="rp-desc">{DESCRIPTION}</p></div></div>',
        unsafe_allow_html=True,
    )


def steps() -> None:
    items = [
        ("1", "Upload", "Add this week's reviews as CSV (review_id, date, platform, rating, review_text). Add last week's for trends."),
        ("2", "Analyze", "Every review is tagged for sentiment, category, urgency and language, then summarised into a report."),
        ("3", "Act", "Reply to urgent reviews, fix recurring complaints and share the weekly report."),
    ]
    for col, (n, t, d) in zip(st.columns(3), items):
        col.markdown(
            f'<div class="rp-card"><div class="rp-step"><div class="rp-step-n">{n}</div>'
            f"<div><h4>{t}</h4><p>{html.escape(d)}</p></div></div></div>",
            unsafe_allow_html=True,
        )


def _delta_html(delta, higher_is_good: bool | None, unit: str = "", decimals: int = 1) -> str:
    if delta is None:
        return ""
    if abs(delta) < 10 ** -(decimals + 1):
        return '<span class="rp-delta flat">→ no change vs last week</span>'
    arrow = "↑" if delta > 0 else "↓"
    cls = "flat" if higher_is_good is None else ("good" if (delta > 0) == higher_is_good else "bad")
    return f'<span class="rp-delta {cls}">{arrow} {abs(delta):.{decimals}f}{unit} vs last week</span>'


def kpi_cards(stats: dict, prev: dict | None) -> None:
    def diff(getter):
        if not prev:
            return None
        a, b = getter(stats), getter(prev)
        return None if a is None or b is None else a - b

    cards = [
        ("Total reviews", f"{stats['total']:,}", _delta_html(diff(lambda s: s["total"]), None, "", 0)),
        ("Average rating", "n/a" if stats["avg_rating"] is None else f"{stats['avg_rating']:.2f} / 5",
         _delta_html(diff(lambda s: s["avg_rating"]), True, "", 2)),
        ("Positive", f"{stats['sentiment_pct']['positive']}%",
         _delta_html(diff(lambda s: s["sentiment_pct"]["positive"]), True, " pts")),
        ("Negative", f"{stats['sentiment_pct']['negative']}%",
         _delta_html(diff(lambda s: s["sentiment_pct"]["negative"]), False, " pts")),
        ("Urgent (HIGH)", f"{stats['urgent']}", _delta_html(diff(lambda s: s["urgent"]), False, "", 0)),
    ]
    for col, (label, value, delta) in zip(st.columns(5), cards):
        col.markdown(
            f'<div class="rp-card"><div class="rp-kpi-label">{label}</div>'
            f'<div class="rp-kpi-value">{value}</div>{delta}</div>',
            unsafe_allow_html=True,
        )


# ---- charts ----
def _style(fig: go.Figure, height: int = 340, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color=TOKENS["ink"]), showlegend=legend,
        legend=dict(orientation="h", y=-0.2, x=0), hoverlabel=dict(bgcolor="white", font_size=13),
    )
    fig.update_xaxes(showgrid=False, linecolor=TOKENS["line"])
    fig.update_yaxes(gridcolor=TOKENS["line"], zeroline=False)
    return fig


def donut(split: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=split["sentiment"].str.title(), values=split["count"], hole=0.58, sort=False,
        marker=dict(colors=[SENTIMENT_COLORS[s] for s in split["sentiment"]], line=dict(color="white", width=2)),
        textinfo="percent", hovertemplate="%{label}: %{value} reviews (%{percent})<extra></extra>",
    ))
    return _style(fig)


def bar(df: pd.DataFrame, x: str, y: str, horizontal: bool = False, x_title: str = "", y_title: str = "Reviews") -> go.Figure:
    if horizontal:
        fig = go.Figure(go.Bar(x=df[y], y=df[x], orientation="h", text=df[y], textposition="outside", cliponaxis=False,
                               marker_color=SEQ_COLOR, hovertemplate="%{y}: %{x} reviews<extra></extra>"))
        _style(fig, legend=False)
        fig.update_yaxes(autorange="reversed", title=x_title)
        fig.update_xaxes(title=y_title)
    else:
        fig = go.Figure(go.Bar(x=df[x], y=df[y], text=df[y], textposition="outside", cliponaxis=False,
                               marker_color=SEQ_COLOR, hovertemplate="%{x}: %{y} reviews<extra></extra>"))
        _style(fig, legend=False)
        fig.update_xaxes(title=x_title, type="category")
        fig.update_yaxes(title=y_title)
    return fig


def sentiment_over_time(long: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for s in SENTIMENT_ORDER:
        g = long[long["sentiment"] == s]
        fig.add_trace(go.Bar(x=g["date"], y=g["count"], name=s.title(), marker_color=SENTIMENT_COLORS[s],
                             hovertemplate="%{x|%d %b}: %{y} " + s + "<extra></extra>"))
    fig.update_layout(barmode="stack")
    _style(fig)
    fig.update_yaxes(title="Reviews")
    return fig


def platform_stacked(pb: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for s in SENTIMENT_ORDER:
        fig.add_trace(go.Bar(y=pb["platform"], x=pb[s], name=s.title(), orientation="h", marker_color=SENTIMENT_COLORS[s],
                             hovertemplate="%{y}: %{x} " + s + "<extra></extra>"))
    fig.update_layout(barmode="stack")
    _style(fig)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Reviews")
    return fig


def sentiment_badge(s: str) -> str:
    mark = {"positive": "+", "neutral": "~", "negative": "-"}.get(s, "?")
    return f'<span class="rp-badge" style="background:{SENTIMENT_COLORS.get(s, "#6B7280")}">{mark} {html.escape(str(s).title())}</span>'
