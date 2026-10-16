"""Offline tests: pandas, validation and retry logic. No API key or network needed."""
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analysis  # noqa: E402
from chains import analyze_reviews, generate_report  # noqa: E402
from schemas import NEEDS_REVIEW, ReviewAnalysis, ThemeList, WeeklyReport  # noqa: E402
from validation import ValidationError, load_reviews, validate_reviews  # noqa: E402

HEADER = "review_id,date,platform,rating,review_text\n"


def make_df(rows):
    return pd.DataFrame(rows, columns=["review_id", "date", "platform", "rating", "review_text"])


# ---------- validation ----------
def test_missing_columns_raises():
    with pytest.raises(ValidationError, match="review_text"):
        validate_reviews(pd.DataFrame({"review_id": ["1"], "date": ["2026-10-01"], "platform": ["x"], "rating": ["5"]}))


def test_drops_empty_rows_and_dupes():
    csv = HEADER + 'R1,2026-10-01,Zomato,5,"Great"\n,,,,\nR2,2026-10-02,Swiggy,2,   \nR1,2026-10-03,Google,4,"dup"\n'
    df, warns = load_reviews(csv.encode())
    assert list(df["review_id"]) == ["R1"]
    assert any("Dropped" in w for w in warns)
    assert any("duplicate" in w for w in warns)


def test_bad_rating_and_date_warn_not_crash():
    df, warns = load_reviews((HEADER + "R1,notadate,Zomato,9,ok\n").encode())
    assert pd.isna(df.loc[0, "rating"]) and pd.isna(df.loc[0, "date"])
    assert len(warns) == 2


def test_all_empty_raises():
    with pytest.raises(ValidationError):
        load_reviews((HEADER + ",,,,\n").encode())


def test_bom_and_tamil_roundtrip():
    text = "பிரியாணி சூப்பர்"
    raw = ("﻿" + HEADER + f"R1,2026-10-01,Google,5,{text}\n").encode("utf-8")
    df, _ = load_reviews(raw)
    assert df.loc[0, "review_text"] == text


def test_shipped_sample_files_valid():
    root = Path(__file__).resolve().parent.parent / "data"
    cur, _ = load_reviews(root / "reviews_week40.csv")
    prev, _ = load_reviews(root / "reviews_week39.csv")
    assert len(cur) >= 200 and 0 < len(prev) < len(cur)


# ---------- analysis ----------
def analysed():
    df = make_df(
        [
            ["1", "2026-10-01", "Zomato", 5, "a"],
            ["2", "2026-10-02", "Swiggy", 1, "b"],
            ["3", "2026-10-03", "Swiggy", 1, "c"],
            ["4", "2026-10-04", "Google", 3, "d"],
            ["5", "2026-10-04", "Google", 2, "e"],
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df["sentiment"] = ["positive", "negative", "negative", "neutral", NEEDS_REVIEW]
    df["category"] = ["food_quality", "delivery", "delivery", "app", NEEDS_REVIEW]
    df["urgency"] = ["low", "high", "medium", "low", NEEDS_REVIEW]
    return df


def test_sentiment_split_excludes_needs_review():
    s = analysis.sentiment_split(analysed()).set_index("sentiment")
    assert s.loc["negative", "count"] == 2 and s.loc["negative", "percent"] == 50.0
    assert s["count"].sum() == 4 and s["percent"].sum() == 100.0


def test_category_and_urgent():
    df = analysed()
    cc = analysis.category_counts(df).set_index("category")["count"]
    assert cc["delivery"] == 2 and cc["price"] == 0 and cc.sum() == 4
    assert list(analysis.urgent_reviews(df)["review_id"]) == ["2"]
    assert analysis.needs_review_count(df) == 1


def test_compute_stats():
    st_ = analysis.compute_stats(analysed())
    assert st_["total"] == 5 and st_["analysed"] == 4 and st_["urgent"] == 1
    assert st_["negative_by_category"] == {"delivery": 2}
    assert st_["negative_by_platform"] == {"Swiggy": 2}
    assert st_["avg_rating"] == 2.4
    assert (st_["date_from"], st_["date_to"]) == ("2026-10-01", "2026-10-04")
    assert "Urgent (HIGH) reviews: 1" in analysis.stats_to_text(st_)


def test_trend_arrows():
    cur = analysis.compute_stats(analysed())
    prev = dict(cur, urgent=3, sentiment_pct={"positive": 10.0, "neutral": 25.0, "negative": 65.0}, total=3)
    t = analysis.trend_table(cur, prev).set_index("metric")
    assert t.loc["Urgent reviews", "trend"] == "↓ (good)"
    assert t.loc["Negative %", "trend"] == "↓ (good)"
    assert t.loc["Positive %", "trend"] == "↑ (good)"
    assert t.loc["Total reviews", "trend"] == "↑"
    assert analysis.trend_arrow(0, True) == "→"


def test_excel_csv_has_bom_and_tamil():
    df = analysed()
    df.loc[0, "review_text"] = "சுவை அருமை"
    b = analysis.to_excel_csv(df)
    assert b.startswith(b"\xef\xbb\xbf")
    assert "சுவை அருமை" in b.decode("utf-8-sig")
    assert pd.read_csv(io.BytesIO(b), encoding="utf-8-sig").loc[0, "review_text"] == "சுவை அருமை"


# ---------- chains with fake LLM ----------
class FakeChain:
    """Mimics chain.batch(); fails the first `fail_times` calls per review_id (or forever)."""

    def __init__(self, fail_times=0, always_fail=()):
        self.calls = {}
        self.fail_times, self.always_fail = fail_times, set(always_fail)

    def batch(self, inputs, config=None, return_exceptions=False):
        assert config and config["max_concurrency"] >= 1 and return_exceptions
        outs = []
        for inp in inputs:
            rid = inp["review_id"]
            self.calls[rid] = self.calls.get(rid, 0) + 1
            if rid in self.always_fail or self.calls[rid] <= self.fail_times:
                try:  # a genuinely invalid category, as the LLM might return
                    ReviewAnalysis(review_id=rid, sentiment="negative", category="parking",
                                   urgency="low", language="English", summary="s", suggested_reply="r")
                except Exception as e:
                    outs.append(e)
            else:
                outs.append(ReviewAnalysis(review_id="WRONG", sentiment="positive", category="food_quality",
                                           urgency="low", language="English", summary="ok", suggested_reply="thanks"))
        return outs


def test_invalid_category_rejected_by_schema():
    with pytest.raises(Exception):
        ReviewAnalysis(review_id="1", sentiment="positive", category="parking", urgency="low",
                       language="English", summary="s", suggested_reply="r")


def test_retry_then_success():
    df, _ = load_reviews((HEADER + "R1,2026-10-01,Zomato,5,good\nR2,2026-10-01,Zomato,4,nice\n").encode())
    chain = FakeChain(fail_times=1)
    out = analyze_reviews(df, chain, max_retries=2)
    assert (out["sentiment"] == "positive").all()
    assert list(out["review_id"]) == ["R1", "R2"]  # ids restored, not "WRONG"
    assert chain.calls == {"R1": 2, "R2": 2}


def test_marks_needs_review_after_retries():
    df, _ = load_reviews((HEADER + "R1,2026-10-01,Zomato,5,good\nR2,2026-10-01,Zomato,1,bad\n").encode())
    chain = FakeChain(always_fail={"R2"})
    out = analyze_reviews(df, chain, max_retries=2).set_index("review_id")
    assert out.loc["R2", "category"] == NEEDS_REVIEW and out.loc["R2", "urgency"] == NEEDS_REVIEW
    assert out.loc["R1", "sentiment"] == "positive"
    assert chain.calls["R2"] == 3  # 1 try + 2 retries


class FakeMap:
    def __init__(self):
        self.n = 0

    def batch(self, inputs, config=None):
        self.n = len(inputs)
        return [ThemeList(complaints=["late delivery"], praises=["tasty biryani"]) for _ in inputs]


class FakeReduce:
    def invoke(self, d):
        self.got = d
        return WeeklyReport(top_complaints=["a"], top_praise=["b"], action_items=["1", "2", "3"], urgent_note="n")


def test_report_map_reduce_chunks_and_passes_stats():
    df = analysed()
    df["summary"] = "something happened"
    m, r = FakeMap(), FakeReduce()
    rep = generate_report(df, "STATS-HERE", map_chain=m, reduce_chain=r, chunk_size=2)
    assert m.n == 3  # 5 summaries / chunk of 2
    assert r.got["stats"] == "STATS-HERE" and "late delivery" in r.got["themes"]
    assert len(rep.action_items) == 3


# ---------- dashboard aggregates ----------
def enriched():
    df = analysed()
    df["rating"] = df["rating"].astype(float)
    df["summary"] = ["good", "cold food", "late rider", "ok app", ""]
    return df


def test_rating_distribution_all_stars():
    d = analysis.rating_distribution(enriched()).set_index("rating")["count"]
    assert list(d.index) == [1, 2, 3, 4, 5] and d[1] == 2 and d[4] == 0 and d.sum() == 5


def test_sentiment_by_date_zero_fills_days():
    df = enriched()
    df.loc[3, "date"] = pd.Timestamp("2026-10-06")
    d = analysis.sentiment_by_date(df)
    assert d["date"].nunique() == 6  # Oct 1..6, gaps filled
    assert d["count"].sum() == 4  # needs-review row excluded
    assert set(d["sentiment"]) == {"positive", "neutral", "negative"}
    assert analysis.sentiment_by_date(df.iloc[0:0]).empty


def test_platform_breakdown():
    p = analysis.platform_breakdown(enriched()).set_index("platform")
    assert p.loc["Swiggy", "negative"] == 2 and p.loc["Swiggy", "negative_pct"] == 100.0
    assert p.loc["Google", "total"] == 2 and p.loc["Google", "neutral"] == 1
    assert p.loc["Zomato", "avg_rating"] == 5.0


def test_recurring_complaints_ranks_and_examples():
    r = analysis.recurring_complaints(enriched())
    assert list(r["category"]) == ["delivery"]
    row = r.iloc[0]
    assert row["count"] == 2 and row["share_pct"] == 100.0 and row["urgent"] == 1
    assert row["examples"][0] == "cold food"  # high urgency first
    assert analysis.recurring_complaints(enriched().assign(sentiment="positive")).empty


def test_report_to_markdown():
    stats = analysis.compute_stats(enriched())
    rep = WeeklyReport(top_complaints=["late"], top_praise=["tasty"], action_items=["a", "b", "c"], urgent_note="Reply fast.")
    md = analysis.report_to_markdown(rep, stats, analysis.trend_table(stats, stats))
    assert md.startswith("# ReviewPulse") and "## Action items" in md and "Week-over-week" in md and "Reply fast." in md
