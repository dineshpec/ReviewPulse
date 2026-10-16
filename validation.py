"""CSV validation: check columns, drop empty rows, normalise types. No LLM needed."""
from __future__ import annotations

import io

import pandas as pd

from schemas import REQUIRED_COLUMNS


class ValidationError(ValueError):
    """Raised when an uploaded file cannot be used."""


def validate_reviews(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return (clean_df, warnings). Raises ValidationError on fatal problems."""
    warnings: list[str] = []
    df = df.copy()
    df.columns = [str(c).strip().lower().lstrip("﻿") for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValidationError(f"Missing required column(s): {', '.join(missing)}")
    df = df[REQUIRED_COLUMNS].copy()

    # Whitespace-only cells count as empty.
    for col in REQUIRED_COLUMNS:
        df[col] = df[col].astype(object).where(df[col].notna(), None)
        df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)
        df[col] = df[col].map(lambda x: None if x == "" else x)

    n0 = len(df)
    df = df.dropna(how="all")
    df = df[df["review_text"].notna()]
    dropped = n0 - len(df)
    if dropped:
        warnings.append(f"Dropped {dropped} empty row(s) / rows without review text.")

    df = df.reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        warnings.append(f"{int(df['date'].isna().sum())} row(s) have an unreadable date.")

    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    bad_rating = ~df["rating"].between(1, 5)  # NaN is also "bad"
    if bad_rating.any():
        warnings.append(f"{int(bad_rating.sum())} row(s) have a missing/invalid rating (set to blank).")
        df.loc[bad_rating, "rating"] = float("nan")

    no_id = df["review_id"].isna()
    if no_id.any():
        for i in df.index[no_id]:
            df.loc[i, "review_id"] = f"ROW-{i + 1}"
        warnings.append(f"{int(no_id.sum())} row(s) had no review_id; generated ids.")
    dup = df["review_id"].duplicated()
    if dup.any():
        warnings.append(f"Dropped {int(dup.sum())} duplicate review_id row(s).")
        df = df[~dup]

    df = df.reset_index(drop=True)
    if df.empty:
        raise ValidationError("No usable reviews found after cleaning.")
    df["review_id"] = df["review_id"].astype(str)
    df["platform"] = df["platform"].fillna("Unknown").astype(str)
    df["review_text"] = df["review_text"].astype(str)
    return df, warnings


def load_reviews(source) -> tuple[pd.DataFrame, list[str]]:
    """Read a CSV path / file-like / bytes and validate it."""
    try:
        if isinstance(source, (bytes, bytearray)):
            source = io.BytesIO(source)
        raw = pd.read_csv(source, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        raise ValidationError(f"Could not read CSV: {e}") from e
    return validate_reviews(raw)
