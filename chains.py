"""LangChain LCEL chains: per-review classifier (map) and weekly report (reduce)."""
from __future__ import annotations

import os
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate

from schemas import NEEDS_REVIEW, ReviewAnalysis, ThemeList, WeeklyReport

REVIEW_SYSTEM = """You analyse customer reviews for a restaurant / online food business.
Reviews may be English, Tamil (Tamil script) or Tanglish (Tamil in English letters).
Return the requested structured fields.
- category must be one of: food_quality, delivery, price, staff, packaging, app.
- urgency=high ONLY for health issues (food poisoning, illness, hair/insect in food),
  wrong order, refund demands, abuse or rude staff. medium = a clear complaint. low = otherwise.
- summary: ONE English sentence, even if the review is Tamil or Tanglish.
- language: English, Tamil, Tanglish or Mixed.
- suggested_reply: polite, short, ready to post, written in the SAME language and script
  as the review (Tamil review -> Tamil reply, Tanglish -> Tanglish, English -> English).
  For urgent issues, apologise and invite them to share the order ID by DM."""

REVIEW_HUMAN = "review_id: {review_id}\nplatform: {platform}\nrating: {rating}\nreview_text: {review_text}"

MAP_SYSTEM = """You read a batch of short English summaries of customer reviews.
List the recurring complaint themes and praise themes (3-6 words each, no numbers)."""

REDUCE_SYSTEM = """You write the weekly feedback report for a business owner.
You get exact statistics computed by software plus theme lists from review chunks.
Do NOT invent or recompute any numbers; only reference the numbers given.
Produce top complaints (max 3), top praise, exactly 3 concrete action items, and one
sentence about the urgent reviews."""


def get_llm(model: str | None = None, temperature: float = 0.0):
    """Create the OpenAI chat model. The key comes from .env / environment only."""
    from langchain_openai import ChatOpenAI

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set. Copy .env.example to .env and add your key.")
    return ChatOpenAI(model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=temperature)


def build_review_chain(llm):
    prompt = ChatPromptTemplate.from_messages([("system", REVIEW_SYSTEM), ("human", REVIEW_HUMAN)])
    return prompt | llm.with_structured_output(ReviewAnalysis)


def build_map_chain(llm):
    prompt = ChatPromptTemplate.from_messages([("system", MAP_SYSTEM), ("human", "{summaries}")])
    return prompt | llm.with_structured_output(ThemeList)


def build_reduce_chain(llm):
    prompt = ChatPromptTemplate.from_messages(
        [("system", REDUCE_SYSTEM), ("human", "STATISTICS:\n{stats}\n\nTHEMES FROM CHUNKS:\n{themes}")]
    )
    return prompt | llm.with_structured_output(WeeklyReport)


def _inputs(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "review_id": r.review_id,
            "platform": r.platform,
            "rating": "" if pd.isna(r.rating) else int(r.rating),
            "review_text": r.review_text,
        }
        for r in df.itertuples()
    ]


def _fallback(inp: dict) -> dict:
    return {
        "review_id": inp["review_id"],
        "sentiment": NEEDS_REVIEW,
        "category": NEEDS_REVIEW,
        "urgency": NEEDS_REVIEW,
        "language": "",
        "summary": "",
        "suggested_reply": "",
    }


def analyze_reviews(
    df: pd.DataFrame,
    chain,
    max_concurrency: int = 5,
    max_retries: int = 2,
    progress: Callable[[int, int], None] | None = None,
    batch_size: int = 25,
) -> pd.DataFrame:
    """Classify every review with chain.batch. Failed/invalid items (exceptions such as
    Pydantic validation errors) are retried up to `max_retries` times, then marked
    'needs review'. Works with any chain returning ReviewAnalysis-like objects."""
    inputs = _inputs(df)
    results: dict[int, dict] = {}
    pending = list(range(len(inputs)))
    for _ in range(max_retries + 1):
        if not pending:
            break
        still_failed: list[int] = []
        for s in range(0, len(pending), batch_size):
            chunk = pending[s : s + batch_size]
            outs = chain.batch(
                [inputs[i] for i in chunk],
                config={"max_concurrency": max_concurrency},
                return_exceptions=True,
            )
            for i, out in zip(chunk, outs):
                if isinstance(out, Exception) or out is None:
                    still_failed.append(i)
                else:
                    d = out.model_dump() if hasattr(out, "model_dump") else dict(out)
                    d["review_id"] = inputs[i]["review_id"]  # never trust the LLM for the key
                    results[i] = d
            if progress:
                progress(len(results), len(inputs))
        pending = still_failed
    for i in pending:
        results[i] = _fallback(inputs[i])
    if progress:
        progress(len(inputs), len(inputs))
    out_df = pd.DataFrame([results[i] for i in range(len(inputs))])
    return df.merge(out_df, on="review_id", how="left")


def _chunks(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def generate_report(
    analyzed: pd.DataFrame,
    stats_text: str,
    llm=None,
    map_chain=None,
    reduce_chain=None,
    chunk_size: int = 40,
    max_concurrency: int = 5,
) -> WeeklyReport:
    """Map-reduce: themes per chunk of summaries (map), then one final report (reduce).
    `stats_text` is produced by pandas (analysis.stats_to_text)."""
    map_chain = map_chain or build_map_chain(llm)
    reduce_chain = reduce_chain or build_reduce_chain(llm)
    summaries = [f"[{r.sentiment}/{r.category}] {r.summary}" for r in analyzed.itertuples() if r.summary]
    chunk_inputs = [{"summaries": "\n".join(c)} for c in _chunks(summaries, chunk_size)]
    themes = map_chain.batch(chunk_inputs, config={"max_concurrency": max_concurrency}) if chunk_inputs else []
    themes_text = "\n".join(
        f"Chunk {i + 1}: complaints={t.complaints}; praises={t.praises}" for i, t in enumerate(themes)
    )
    return reduce_chain.invoke({"stats": stats_text, "themes": themes_text or "(none)"})
