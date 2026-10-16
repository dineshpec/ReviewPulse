"""UI smoke tests with Streamlit AppTest. No API calls: results are precomputed with fake labels."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest  # noqa: E402

import analysis  # noqa: E402
from schemas import CATEGORIES, NEEDS_REVIEW, WeeklyReport  # noqa: E402
from validation import load_reviews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")


def fake_analysed(name):
    df, _ = load_reviews(ROOT / "data" / name)
    rng = np.random.default_rng(0)
    df["sentiment"] = np.where(df["rating"] >= 4, "positive", np.where(df["rating"] <= 2, "negative", "neutral"))
    df["category"] = rng.choice(CATEGORIES, len(df))
    df["urgency"] = rng.choice(["low", "medium", "high"], len(df), p=[0.6, 0.3, 0.1])
    df["language"] = rng.choice(["English", "Tamil", "Tanglish"], len(df))
    df["summary"] = "Customer says something."
    df["suggested_reply"] = "Thank you for your feedback."
    df.loc[0, ["sentiment", "category", "urgency"]] = NEEDS_REVIEW
    return df


def loaded_result(with_prev=True):
    cur = fake_analysed("reviews_week40.csv")
    prev = fake_analysed("reviews_week39.csv")
    rep = WeeklyReport(top_complaints=["Late delivery"], top_praise=["Tasty biryani"],
                       action_items=["a", "b", "c"], urgent_note="Reply today.")
    return dict(cur=cur, stats=analysis.compute_stats(cur), report=rep,
                prev_stats=analysis.compute_stats(prev) if with_prev else None)


def test_empty_state_renders():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert [b.label for b in at.button if "sample" in b.label.lower()] == ["Use sample week 40", "Use sample week 39 as last week"]


def test_sample_buttons_enable_analyze():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.button[0].click().run()
    assert not at.exception and at.session_state["sample_cur"]
    assert [b for b in at.button if b.label == "Analyze reviews"][0].disabled is False


@pytest.mark.parametrize("with_prev", [True, False])
def test_loaded_state_renders(with_prev):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["result"] = loaded_result(with_prev)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 5


def test_filters_do_not_crash():
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["result"] = loaded_result()
    at.run()
    at.toggle[0].set_value(True).run()
    assert not at.exception
    at.text_input[-1].set_value("zzzz-no-match").run()
    assert not at.exception
