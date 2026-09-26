"""Reshape tables: rename columns via a schema, wide<->long, split/merge columns."""

import pandas as pd


def apply_schema(df, mapping):
    """Rename columns according to a schema mapping.

    ``mapping`` may be a flat dict ``{"Old Name": "new_name"}`` or a dict
    containing a ``"columns"`` key with that dict inside.
    Unknown columns are left untouched.
    """
    if isinstance(mapping, dict) and "columns" in mapping:
        mapping = mapping["columns"]
    df = df.copy()
    return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})


def melt_wide_to_long(df, id_vars, value_vars=None, var_name="metric", value_name="value"):
    """Convert a wide table (one column per month/metric) to long format.

    Example: columns ``Jan, Feb, Mar`` become rows with
    ``metric`` in {Jan, Feb, Mar} and the amount in ``value``.
    """
    return pd.melt(
        df, id_vars=id_vars, value_vars=value_vars,
        var_name=var_name, value_name=value_name,
    )


def split_column(df, column, into, sep=r"\s+", regex=True):
    """Split one column into several (e.g. 'Full Name' -> 'First', 'Last').

    Args:
        column: source column name.
        into: list of new column names.
        sep: separator passed to ``Series.str.split``.
    """
    df = df.copy()
    if column not in df.columns:
        raise KeyError(f"Column not found: {column!r}")
    parts = (
        df[column].astype("string").str.strip().str.split(
            sep, n=len(into) - 1, expand=True, regex=regex
        )
    )
    for i, name in enumerate(into):
        df[name] = parts[i] if i in parts.columns else pd.NA
    return df


def merge_columns(df, columns, new_column, sep=" "):
    """Merge several columns into one, skipping missing values.

    Example: ``['First', 'Last']`` -> ``'Full Name'``.
    """
    df = df.copy()
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(f"Columns not found: {missing}")
    df[new_column] = (
        df[columns]
        .astype("string")
        .apply(lambda row: sep.join(v for v in row if pd.notna(v)), axis=1)
    )
    return df
