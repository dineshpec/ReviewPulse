"""All counts, percentages, trends and exports are computed here with pandas (never by the LLM)."""
from __future__ import annotations

import pandas as pd

from schemas import CATEGORIES, NEEDS_REVIEW, SENTIMENTS


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["sentiment"] != NEEDS_REVIEW]


def sentiment_split(df: pd.DataFrame) -> pd.DataFrame:
    """Count + percent per sentiment (percent of successfully analysed reviews)."""
    counts = _valid(df)["sentiment"].value_counts().reindex(SENTIMENTS, fill_value=0)
    total = int(counts.sum())
    pct = (counts / total * 100).round(1) if total else counts.astype(float)
    return pd.DataFrame({"sentiment": counts.index, "count": counts.values, "percent": pct.values})


def category_counts(df: pd.DataFrame, negative_only: bool = False) -> pd.DataFrame:
    v = _valid(df)
    if negative_only:
        v = v[v["sentiment"] == "negative"]
    counts = v["category"].value_counts().reindex(CATEGORIES, fill_value=0)
    return pd.DataFrame({"category": counts.index, "count": counts.values})


def urgent_reviews(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["urgency"] == "high"].reset_index(drop=True)


def needs_review_count(df: pd.DataFrame) -> int:
    return int((df["sentiment"] == NEEDS_REVIEW).sum())


def compute_stats(df: pd.DataFrame) -> dict:
    v = _valid(df)
    split = sentiment_split(df)
    dates = df["date"].dropna()
    neg_cat = category_counts(df, negative_only=True)
    neg_cat = neg_cat[neg_cat["count"] > 0].sort_values("count", ascending=False)
    cat = category_counts(df)
    ratings = df["rating"].dropna().astype(float)
    return {
        "total": int(len(df)),
        "analysed": int(len(v)),
        "needs_review": needs_review_count(df),
        "sentiment_counts": {r.sentiment: int(r.count) for r in split.itertuples()},
        "sentiment_pct": {r.sentiment: float(r.percent) for r in split.itertuples()},
        "category_counts": {r.category: int(r.count) for r in cat.itertuples()},
        "negative_by_category": {r.category: int(r.count) for r in neg_cat.itertuples()},
        "urgent": int((df["urgency"] == "high").sum()),
        "avg_rating": None if ratings.empty else round(float(ratings.mean()), 2),
        "date_from": None if dates.empty else dates.min().strftime("%Y-%m-%d"),
        "date_to": None if dates.empty else dates.max().strftime("%Y-%m-%d"),
        "reviews_by_platform": {k: int(x) for k, x in df.groupby("platform").size().items()},
        "negative_by_platform": {
            k: int(x) for k, x in v[v["sentiment"] == "negative"].groupby("platform").size().items()
        },
    }


def stats_to_text(stats: dict) -> str:
    """Render pandas stats as text for the report chain prompt."""
    sc, sp = stats["sentiment_counts"], stats["sentiment_pct"]
    return "\n".join(
        [
            f"Period: {stats['date_from']} to {stats['date_to']}",
            f"Total reviews: {stats['total']} (analysed {stats['analysed']}, needs manual review {stats['needs_review']})",
            "Sentiment: " + ", ".join(f"{k} {sc[k]} ({sp[k]}%)" for k in sc),
            "Negative reviews by category: "
            + (", ".join(f"{k}={v}" for k, v in stats["negative_by_category"].items()) or "none"),
            "Reviews by category: " + ", ".join(f"{k}={v}" for k, v in stats["category_counts"].items()),
            "Negative reviews by platform: "
            + (", ".join(f"{k}={v}" for k, v in stats["negative_by_platform"].items()) or "none"),
            f"Average rating: {stats['avg_rating']}",
            f"Urgent (HIGH) reviews: {stats['urgent']}",
        ]
    )


def trend_arrow(delta: float, higher_is_good: bool | None, eps: float = 0.0) -> str:
    """Arrow for a change. higher_is_good=None means neutral (arrow only, no verdict)."""
    if abs(delta) <= eps:
        return "→"
    up = delta > 0
    arrow = "↑" if up else "↓"
    if higher_is_good is None:
        return arrow
    return f"{arrow} ({'good' if up == higher_is_good else 'bad'})"


def trend_table(current: dict, previous: dict) -> pd.DataFrame:
    """Week-over-week comparison built from two compute_stats() dicts."""
    rows = []
    good = {"positive": True, "neutral": None, "negative": False}
    for s in SENTIMENTS:
        a, b = previous["sentiment_pct"].get(s, 0.0), current["sentiment_pct"].get(s, 0.0)
        d = round(b - a, 1)
        rows.append((f"{s.title()} %", a, b, d, trend_arrow(d, good[s])))
    for label, key, hig in (("Urgent reviews", "urgent", False), ("Total reviews", "total", None)):
        d = current[key] - previous[key]
        rows.append((label, previous[key], current[key], d, trend_arrow(d, hig)))
    if current["avg_rating"] is not None and previous["avg_rating"] is not None:
        d = round(current["avg_rating"] - previous["avg_rating"], 2)
        rows.append(("Avg rating", previous["avg_rating"], current["avg_rating"], d, trend_arrow(d, True)))
    for c in CATEGORIES:
        a = previous["negative_by_category"].get(c, 0)
        b = current["negative_by_category"].get(c, 0)
        rows.append((f"Negative: {c}", a, b, b - a, trend_arrow(b - a, False)))
    return pd.DataFrame(rows, columns=["metric", "last_week", "this_week", "change", "trend"])


def to_excel_csv(df: pd.DataFrame) -> bytes:
    """CSV bytes with a UTF-8 BOM so Excel renders Tamil correctly."""
    out = df.copy()
    if pd.api.types.is_datetime64_any_dtype(out["date"]):
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.to_csv(index=False).encode("utf-8-sig")


# ---------- aggregates used by the dashboard (pandas only) ----------
def rating_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Count of reviews per star rating 1..5 (blank ratings ignored)."""
    r = df["rating"].dropna().round().astype(int)
    counts = r.value_counts().reindex(range(1, 6), fill_value=0)
    return pd.DataFrame({"rating": counts.index, "count": counts.values})


def sentiment_by_date(df: pd.DataFrame) -> pd.DataFrame:
    """Long format (date, sentiment, count) for analysed reviews with a valid date; zero-filled."""
    v = _valid(df).dropna(subset=["date"]).copy()
    if v.empty:
        return pd.DataFrame(columns=["date", "sentiment", "count"])
    v["date"] = pd.to_datetime(v["date"]).dt.normalize()
    wide = v.groupby(["date", "sentiment"]).size().unstack(fill_value=0).reindex(columns=SENTIMENTS, fill_value=0)
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"), fill_value=0)
    long = wide.rename_axis("date").reset_index().melt(id_vars="date", var_name="sentiment", value_name="count")
    return long.sort_values(["date", "sentiment"]).reset_index(drop=True)


def platform_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Per platform: total, sentiment counts, negative %, avg rating."""
    rows = []
    for plat, g in df.groupby("platform"):
        v = _valid(g)
        n = len(v)
        neg = int((v["sentiment"] == "negative").sum())
        rows.append(
            {
                "platform": plat,
                "total": int(len(g)),
                "positive": int((v["sentiment"] == "positive").sum()),
                "neutral": int((v["sentiment"] == "neutral").sum()),
                "negative": neg,
                "negative_pct": round(neg / n * 100, 1) if n else 0.0,
                "avg_rating": round(float(g["rating"].mean()), 2) if g["rating"].notna().any() else None,
            }
        )
    cols = ["platform", "total", "positive", "neutral", "negative", "negative_pct", "avg_rating"]
    return pd.DataFrame(rows, columns=cols).sort_values("total", ascending=False).reset_index(drop=True)


def recurring_complaints(df: pd.DataFrame, n_examples: int = 3) -> pd.DataFrame:
    """Negative reviews grouped by category: count, share, urgent count, avg rating and example reviews.
    Examples prefer high-urgency, then low-rating reviews. Sorted by count descending."""
    neg = _valid(df)
    neg = neg[neg["sentiment"] == "negative"]
    cols = ["category", "count", "share_pct", "urgent", "avg_rating", "examples"]
    if neg.empty:
        return pd.DataFrame(columns=cols)
    rank = {"high": 0, "medium": 1, "low": 2}
    rows = []
    for cat, g in neg.groupby("category"):
        g = g.assign(_u=g["urgency"].map(rank).fillna(3)).sort_values(["_u", "rating"], na_position="last")
        ex = [t if isinstance(t, str) and t else r for t, r in zip(g["summary"], g["review_text"])][:n_examples]
        rows.append(
            {
                "category": cat,
                "count": int(len(g)),
                "share_pct": round(len(g) / len(neg) * 100, 1),
                "urgent": int((g["urgency"] == "high").sum()),
                "avg_rating": round(float(g["rating"].mean()), 2) if g["rating"].notna().any() else None,
                "examples": ex,
            }
        )
    return pd.DataFrame(rows, columns=cols).sort_values("count", ascending=False).reset_index(drop=True)


def report_to_markdown(report, stats: dict, trends: pd.DataFrame | None = None) -> str:
    """Weekly report as Markdown. `report` is a WeeklyReport (or any object with the same attributes)."""
    pct = stats["sentiment_pct"]
    lines = [
        "# ReviewPulse weekly report",
        "",
        f"**Period:** {stats['date_from']} to {stats['date_to']}  ",
        f"**Total reviews:** {stats['total']} | "
        + " | ".join(f"{k.title()} {pct[k]}%" for k in pct)
        + f" | Avg rating {stats['avg_rating']}",
        "",
        "## Top complaints",
        *[f"{i}. {x}" for i, x in enumerate(report.top_complaints, 1)],
        "",
        "## Top praise",
        *[f"- {x}" for x in report.top_praise],
        "",
        f"## Urgent\n{stats['urgent']} review(s) need a reply within 24 hours. {report.urgent_note}",
        "",
        "## Action items",
        *[f"{i}. {x}" for i, x in enumerate(report.action_items, 1)],
    ]
    if trends is not None and not trends.empty:
        lines += ["", "## Week-over-week trends", "", "| Metric | Last week | This week | Change | Trend |", "|---|---|---|---|---|"]
        lines += [f"| {r.metric} | {r.last_week} | {r.this_week} | {r.change} | {r.trend} |" for r in trends.itertuples()]
    return "\n".join(lines) + "\n"
