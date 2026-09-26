"""Duplicate detection and removal: exact matches plus fuzzy near-duplicates."""

from difflib import SequenceMatcher

import pandas as pd


def exact_dedup(df, key_columns, keep="first"):
    """Drop rows that are exact duplicates on the given key columns.

    Args:
        df: pandas DataFrame.
        key_columns: str or list of str — columns that define a duplicate.
        keep: which duplicate to keep ('first', 'last', False).

    Returns:
        (cleaned DataFrame, number of rows removed).
    """
    if isinstance(key_columns, str):
        key_columns = [key_columns]
    before = len(df)
    cleaned = df.drop_duplicates(subset=key_columns, keep=keep).reset_index(drop=True)
    return cleaned, before - len(cleaned)


def _row_key(row):
    """Build a normalized comparison string for a row."""
    parts = []
    for value in row:
        text = "" if pd.isna(value) else str(value)
        parts.append(" ".join(text.lower().split()))  # collapse whitespace, lower
    return " | ".join(parts)


def fuzzy_dedup(df, key_columns, threshold=0.85):
    """Drop near-duplicate rows whose key columns are textually similar.

    Rows are compared pairwise on a normalized key built from
    ``key_columns``; when two rows score above ``threshold``
    (difflib.SequenceMatcher ratio), the later row is dropped.

    Args:
        df: pandas DataFrame.
        key_columns: str or list of str — columns that define a duplicate.
        threshold: similarity ratio in (0, 1]; higher is stricter.

    Returns:
        (cleaned DataFrame, number of rows removed).
    """
    if isinstance(key_columns, str):
        key_columns = [key_columns]
    keys = [_row_key(row) for row in df[key_columns].itertuples(index=False)]
    keep_idx = []
    for i, key in enumerate(keys):
        is_dupe = False
        for j in keep_idx:
            if SequenceMatcher(None, key, keys[j]).ratio() >= threshold:
                is_dupe = True
                break
        if not is_dupe:
            keep_idx.append(i)
    cleaned = df.iloc[keep_idx].reset_index(drop=True)
    return cleaned, len(df) - len(cleaned)
