"""Pydantic models and allowed values shared by the whole app."""
from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "neutral", "negative"]
Category = Literal["food_quality", "delivery", "price", "staff", "packaging", "app"]
Urgency = Literal["low", "medium", "high"]

SENTIMENTS = ["positive", "neutral", "negative"]
CATEGORIES = ["food_quality", "delivery", "price", "staff", "packaging", "app"]
URGENCIES = ["low", "medium", "high"]
REQUIRED_COLUMNS = ["review_id", "date", "platform", "rating", "review_text"]
NEEDS_REVIEW = "needs review"


class ReviewAnalysis(BaseModel):
    """Structured result the LLM must return for one review."""

    review_id: str = Field(description="Copy the review_id exactly as given.")
    sentiment: Sentiment = Field(description="Overall customer mood.")
    category: Category = Field(description="Main topic of the review.")
    urgency: Urgency = Field(
        description="high = needs a reply today (food poisoning/health, wrong order, "
        "refund, abuse, rude staff); medium = clear complaint; low = otherwise."
    )
    language: str = Field(description="Language of the review: English, Tamil, Tanglish, or Mixed.")
    summary: str = Field(description="One English sentence summarising the review.")
    suggested_reply: str = Field(
        description="Polite ready-to-post reply, written in the SAME language/style as the review."
    )


class ThemeList(BaseModel):
    """Map-step output: themes found in one chunk of reviews."""

    complaints: list[str] = Field(description="Short complaint themes seen in this chunk.")
    praises: list[str] = Field(description="Short praise themes seen in this chunk.")


class WeeklyReport(BaseModel):
    """Reduce-step output: the narrative part of the weekly report."""

    top_complaints: list[str] = Field(description="Top 3 complaints, most frequent first.")
    top_praise: list[str] = Field(description="Top praise points.")
    action_items: list[str] = Field(description="Exactly 3 concrete action items.")
    urgent_note: str = Field(description="One sentence about the urgent reviews.")
