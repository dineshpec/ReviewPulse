"""ReviewPulse Streamlit dashboard. Run: streamlit run app.py"""
from __future__ import annotations

import html as _h
from pathlib import Path

import pandas as pd
import streamlit as st

import analysis
import ui
from schemas import NEEDS_REVIEW
from validation import ValidationError, load_reviews

DATA_DIR = Path(__file__).resolve().parent / "data"
SAMPLES = {"week40": DATA_DIR / "reviews_week40.csv", "week39": DATA_DIR / "reviews_week39.csv"}
MAX_DETAIL = 25  # expandable review cards shown at once

st.set_page_config(page_title="ReviewPulse", page_icon=":material/monitoring:", layout="wide", initial_sidebar_state="expanded")
ui.inject_css()


# ---------------------------------------------------------------- pipeline
def run_pipeline(data: bytes, label: str, model: str, conc: int) -> pd.DataFrame:
    from chains import analyze_reviews, build_review_chain, get_llm  # lazy: keeps the UI importable without LLM deps

    df, warns = load_reviews(data)
    for w in warns:
        st.warning(f"{label}: {w}")
    chain = build_review_chain(get_llm(model))  # raises RuntimeError if no API key
    bar = st.progress(0.0, text=f"Analysing {label.lower()} ({len(df)} reviews)...")
    out = analyze_reviews(
        df, chain, max_concurrency=conc,
        progress=lambda d, t: bar.progress(min(d / t, 1.0) if t else 1.0, text=f"Analysing {label.lower()}: {d}/{t}"),
    )
    bar.empty()
    return out


def run_all(cur_bytes: bytes, prev_bytes: bytes | None, model: str, conc: int) -> dict:
    from chains import generate_report, get_llm

    with st.status("Analysing reviews...", expanded=True) as status:
        cur = run_pipeline(cur_bytes, "This week", model, conc)
        prev = run_pipeline(prev_bytes, "Last week", model, conc) if prev_bytes else None
        stats = analysis.compute_stats(cur)
        st.write("Writing weekly report...")
        report = generate_report(cur, analysis.stats_to_text(stats), llm=get_llm(model), max_concurrency=conc)
        status.update(label="Analysis complete", state="complete", expanded=False)
    return dict(
        cur=cur, stats=stats, report=report,
        prev_stats=analysis.compute_stats(prev) if prev is not None else None,
    )


def friendly_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if isinstance(e, ValidationError):
        return (f"That CSV could not be used: {msg}. Expected columns: review_id, date, platform, rating, review_text. "
                "Save it as UTF-8 CSV and try again.")
    if isinstance(e, RuntimeError) and "OPENAI_API_KEY" in msg:
        return "OpenAI API key not found. Copy `.env.example` to `.env`, set `OPENAI_API_KEY`, then restart the app."
    if "api key" in low or "401" in low or "authentication" in low:
        return "OpenAI rejected the API key. Check `OPENAI_API_KEY` in your `.env` file."
    if "rate" in low and "limit" in low or "429" in low:
        return "OpenAI rate limit reached. Lower Max concurrency in the sidebar or retry in a minute."
    if "connection" in low or "timeout" in low or "timed out" in low:
        return "Could not reach OpenAI. Check your internet connection and try again."
    return f"Analysis failed: {msg}"


# ---------------------------------------------------------------- sidebar
ss = st.session_state
ss.setdefault("sample_cur", False)
ss.setdefault("sample_prev", False)

with st.sidebar:
    st.markdown("### Data")
    up = st.file_uploader("This week's reviews (CSV)", type="csv", help="Columns: review_id, date, platform, rating, review_text")
    prev_up = st.file_uploader("Last week's reviews (optional)", type="csv", help="Adds trend deltas and a week-over-week table")
    st.markdown("### Settings")
    model = st.text_input("OpenAI model", value="gpt-4o-mini", help="Any chat model your key can access.")
    conc = st.slider("Max concurrency", 1, 16, 5, help="Parallel LLM calls. Lower it if you hit rate limits.")
    cur_bytes = up.getvalue() if up else (SAMPLES["week40"].read_bytes() if ss["sample_cur"] else None)
    prev_bytes = prev_up.getvalue() if prev_up else (SAMPLES["week39"].read_bytes() if ss["sample_prev"] else None)
    run = st.button("Analyze reviews", type="primary", disabled=cur_bytes is None, width="stretch")
    if cur_bytes is None:
        st.caption("Upload a CSV or use a sample to enable analysis.")
    with st.expander("About ReviewPulse"):
        st.markdown(f"**{ui.TAGLINE}**\n\n{ui.DESCRIPTION}\n\nAll numbers are computed with pandas; "
                    "the LLM only tags reviews and writes the narrative. Your API key is read from `.env` only.")

ui.header()

if run and cur_bytes is not None:
    try:
        ss["result"] = run_all(cur_bytes, prev_bytes, model, conc)
    except Exception as e:  # noqa: BLE001 - surfaced as a friendly message
        st.error(friendly_error(e))

res = ss.get("result")

# ---------------------------------------------------------------- empty state
if not res:
    ui.steps()
    st.markdown("")
    st.markdown("#### Try it instantly")
    b1, b2, _ = st.columns([1, 1.3, 2])
    if b1.button("Use sample week 40", width="stretch"):
        ss["sample_cur"] = True
        st.rerun()
    if b2.button("Use sample week 39 as last week", width="stretch"):
        ss["sample_prev"] = True
        st.rerun()
    chips = []
    if up or ss["sample_cur"]:
        chips.append("This week: " + (up.name if up else "sample week 40"))
    if prev_up or ss["sample_prev"]:
        chips.append("Last week: " + (prev_up.name if prev_up else "sample week 39"))
    if chips:
        st.markdown("".join(f'<span class="rp-chip">{c}</span>' for c in chips), unsafe_allow_html=True)
        st.caption("Ready. Click **Analyze reviews** in the sidebar.")
    else:
        st.caption("Or upload your own CSV from the sidebar. Sample data is in the `data/` folder.")
    st.stop()

# ---------------------------------------------------------------- results
cur, stats, report, prev_stats = res["cur"], res["stats"], res["report"], res.get("prev_stats")
trends = analysis.trend_table(stats, prev_stats) if prev_stats else None

st.caption(f"Period {stats['date_from']} to {stats['date_to']}"
           + (f" | {stats['needs_review']} review(s) could not be analysed and are excluded from percentages" if stats["needs_review"] else ""))
ui.kpi_cards(stats, prev_stats)
st.markdown("")

t_over, t_trend, t_comp, t_rep, t_rev = st.tabs(["Overview", "Trends", "Recurring complaints", "Weekly report", "Reviews"])

with t_over:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Sentiment split")
        st.plotly_chart(ui.donut(analysis.sentiment_split(cur)), width="stretch")
    with c2:
        st.subheader("Reviews by category")
        cc = analysis.category_counts(cur).sort_values("count", ascending=False)
        st.plotly_chart(ui.bar(cc, "category", "count", horizontal=True), width="stretch")
    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Rating distribution")
        rd = analysis.rating_distribution(cur)
        rd["rating"] = rd["rating"].astype(str) + " star"
        st.plotly_chart(ui.bar(rd, "rating", "count"), width="stretch")
    with c4:
        st.subheader("Sentiment over time")
        sbd = analysis.sentiment_by_date(cur)
        if sbd.empty:
            st.info("No valid dates to chart.")
        else:
            st.plotly_chart(ui.sentiment_over_time(sbd), width="stretch")
    st.subheader("By platform")
    pb = analysis.platform_breakdown(cur)
    p1, p2 = st.columns([3, 2])
    p1.plotly_chart(ui.platform_stacked(pb), width="stretch")
    p2.dataframe(
        pb[["platform", "total", "negative_pct", "avg_rating"]], hide_index=True, width="stretch",
        column_config={"platform": "Platform", "total": "Reviews", "negative_pct": st.column_config.NumberColumn("Negative %", format="%.1f%%"),
                       "avg_rating": st.column_config.NumberColumn("Avg rating", format="%.2f")},
    )

with t_trend:
    st.subheader("Week-over-week")
    if trends is None:
        st.info("Add last week's CSV (or use the sample week 39) and re-run the analysis to see trends.")
    else:
        st.caption("Arrows show change vs last week. 'good' / 'bad' reflect whether the direction helps the business.")
        st.dataframe(
            trends, hide_index=True, width="stretch",
            column_config={"metric": "Metric", "last_week": "Last week", "this_week": "This week", "change": "Change", "trend": "Trend"},
        )

with t_comp:
    st.subheader("Recurring complaints")
    rc = analysis.recurring_complaints(cur)
    if rc.empty:
        st.success("No negative reviews in this period.")
    else:
        st.caption("Negative reviews grouped by category, most frequent first. Examples are AI summaries, urgent first.")
        for r in rc.itertuples():
            label = f"{r.category.replace('_', ' ').title()}: {r.count} review(s), {r.share_pct}% of complaints"
            with st.expander(label, expanded=r.Index == 0):
                m1, m2, m3 = st.columns(3)
                m1.metric("Complaints", r.count)
                m2.metric("Urgent", r.urgent)
                m3.metric("Avg rating", "n/a" if r.avg_rating is None else f"{r.avg_rating:.2f}")
                st.markdown("".join(f'<div class="rp-example">{_h.escape(e)}</div>' for e in r.examples), unsafe_allow_html=True)
    if report.top_complaints:
        st.markdown("**Themes called out by the report**")
        st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(report.top_complaints, 1)))

with t_rep:
    md = analysis.report_to_markdown(report, stats, trends)
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Download .md", md, file_name="reviewpulse_weekly_report.md", mime="text/markdown", width="stretch")
    with d2.popover("Copy report", width="stretch"):
        st.caption("Use the copy icon at the top right of the block.")
        st.code(md, language="markdown")
    with st.container(border=True):
        st.markdown(md)

with t_rev:
    f1, f2, f3 = st.columns(3)
    sent = f1.multiselect("Sentiment", ["positive", "neutral", "negative", NEEDS_REVIEW])
    cats = f2.multiselect("Category", sorted(cur["category"].dropna().unique()))
    plats = f3.multiselect("Platform", sorted(cur["platform"].dropna().unique()))
    f4, f5, f6 = st.columns(3)
    urg = f4.multiselect("Urgency", ["high", "medium", "low", NEEDS_REVIEW])
    langs = f5.multiselect("Language", sorted(x for x in cur["language"].dropna().unique() if x))
    q = f6.text_input("Search text", placeholder="e.g. cold, refund, delivery")
    only_high = st.toggle("Show only HIGH urgency", value=False)

    view = cur
    for col, vals in (("sentiment", sent), ("category", cats), ("platform", plats), ("urgency", urg), ("language", langs)):
        if vals:
            view = view[view[col].isin(vals)]
    if only_high:
        view = view[view["urgency"] == "high"]
    if q.strip():
        mask = view["review_text"].str.contains(q.strip(), case=False, regex=False) | view["summary"].fillna("").str.contains(q.strip(), case=False, regex=False)
        view = view[mask]

    st.caption(f"{len(view)} of {len(cur)} review(s) shown. Rows marked '{NEEDS_REVIEW}' failed validation after retries.")
    st.dataframe(
        view[["review_id", "date", "platform", "rating", "sentiment", "category", "urgency", "language", "review_text"]],
        hide_index=True, width="stretch",
        column_config={"date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                       "review_text": st.column_config.TextColumn("Review", width="large")},
    )
    st.download_button("Download enriched CSV (Excel-ready)", data=analysis.to_excel_csv(cur),
                       file_name="reviews_enriched.csv", mime="text/csv")

    st.markdown("#### Review details")
    if view.empty:
        st.info("No reviews match the filters.")
    for r in view.head(MAX_DETAIL).itertuples():
        flag = " [URGENT]" if r.urgency == "high" else ""
        with st.expander(f"{r.review_id} | {r.platform} | {r.sentiment} | {r.category}{flag}"):
            st.markdown(ui.sentiment_badge(r.sentiment), unsafe_allow_html=True)
            st.markdown(f"**Review:** {r.review_text}")
            st.markdown(f"**Summary:** {r.summary or 'n/a'}")
            st.markdown("**Suggested reply**")
            st.code(r.suggested_reply or "n/a", language=None, wrap_lines=True)
    if len(view) > MAX_DETAIL:
        st.caption(f"Showing details for the first {MAX_DETAIL}. Narrow the filters to see others.")
