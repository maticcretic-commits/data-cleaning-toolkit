"""Field normalization: phones, emails, dates, currency, whitespace, casing."""

import re
from datetime import datetime

import pandas as pd
from dateutil import parser as dateutil_parser


def trim_whitespace(df, columns=None):
    """Strip leading/trailing whitespace (and collapse internal runs) in text columns."""
    df = df.copy()
    cols = columns or df.select_dtypes(include="object").columns.tolist()
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v
            )
    return df


def title_case(df, columns):
    """Title-case the given columns after trimming."""
    df = df.copy()
    if isinstance(columns, str):
        columns = [columns]
    for col in columns:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: v.strip().title() if isinstance(v, str) else v
            )
    return df


def normalize_email(value):
    """Lowercase and trim an email address; returns None for blanks."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    return text or None


def normalize_phone(value, default_country="91"):
    """Normalize a phone number to ``+CC-XXXXXXXXXX`` form.

    Handles Indian-style inputs: ``98765 43210``, ``09876543210``,
    ``+91-9876543210``, ``919876543210`` all become ``+91-9876543210``.
    Non-matching values are returned with digits preserved (``+`` kept).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if len(digits) == 10:
        return f"+{default_country}-{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+{default_country}-{digits[1:]}"
    if len(digits) == 12 and digits.startswith(default_country):
        return f"+{default_country}-{digits[2:]}"
    return ("+" if text.startswith("+") else "") + digits


def normalize_date(series, dayfirst=True):
    """Parse mixed-format date strings into datetimes.

    Handles ``12/05/2024``, ``2024-06-01``, ``12-May-2024``,
    ``May 12, 2024`` etc. Each value is parsed individually so mixed
    formats in one column all resolve. Unparseable values become ``NaT``.
    """

    def _parse_one(value):
        if value is None:
            return pd.NaT
        if isinstance(value, float) and pd.isna(value):
            return pd.NaT
        if isinstance(value, (pd.Timestamp, datetime)):
            return pd.Timestamp(value)
        text = str(value).strip()
        if not text:
            return pd.NaT
        try:
            return pd.Timestamp(dateutil_parser.parse(text, dayfirst=dayfirst))
        except (ValueError, OverflowError, TypeError):
            return pd.NaT

    return pd.to_datetime(pd.Series(series).apply(_parse_one))


def normalize_currency(value):
    """Clean a currency string to a float.

    ``"₹1,25,000"`` → ``125000.0``; ``"$1,299.50"`` → ``1299.5``.
    Returns ``None`` for blanks/unparseable values.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[₹$€£\s]", "", text)          # currency symbols, spaces
    text = re.sub(r"(?i)\brs\.?", "", text)        # 'Rs' / 'Rs.' prefix
    text = text.replace(",", "")                   # thousand separators
    # allow a single decimal point and an optional leading minus
    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    return float(text)


# Registry mapping CLI normalize tokens -> (column-agnostic function, kind).
# 'series' functions operate on a whole pandas Series; 'scalar' on each value.
NORMALIZERS = {
    "phone": (normalize_phone, "scalar"),
    "email": (normalize_email, "scalar"),
    "date": (normalize_date, "series"),
    "currency": (normalize_currency, "scalar"),
    "trim": (lambda v: v.strip() if isinstance(v, str) else v, "scalar"),
    "case": (lambda v: v.strip().title() if isinstance(v, str) else v, "scalar"),
}


def apply_normalizer(df, kind, column):
    """Apply a named normalizer (see NORMALIZERS) to one column."""
    df = df.copy()
    if column not in df.columns:
        raise KeyError(f"Column not found: {column!r}")
    func, func_kind = NORMALIZERS[kind]
    if func_kind == "series":
        df[column] = func(df[column])
    else:
        df[column] = df[column].apply(func)
    return df
