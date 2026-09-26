#!/usr/bin/env python3
"""CLI for data-cleaning-toolkit.

Tabular cleaning:
    python clean.py input.csv --dedup email --normalize phone,date --schema mapping.json -o out.csv
    python clean.py input.xlsx --dedup email --fuzzy --normalize phone:mobile,email --split "full_name:first_name,last_name" -o out.csv

PDF extraction:
    python clean.py doc.pdf --pdf-out db.sqlite
    python clean.py doc.pdf --pdf-out db.sqlite --pdf-images ./imgs --pdf-csv pages.csv
"""

import argparse
import json
import os
import sys

import pandas as pd

from cleaner import (
    apply_schema,
    apply_normalizer,
    exact_dedup,
    extract_images,
    extract_text_pages,
    extract_to_db,
    fuzzy_dedup,
    merge_columns,
    pages_to_csv,
    split_column,
    NORMALIZERS,
)

TABULAR_EXTS = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Clean messy CSV/Excel data or extract PDF content to a database."
    )
    p.add_argument("input", help="Input file: .csv/.xlsx for cleaning, .pdf for extraction")
    p.add_argument("-o", "--output", help="Output file for cleaned data (.csv/.xlsx)")
    p.add_argument("--dedup", help="Comma-separated key column(s) for exact dedup, e.g. 'email'")
    p.add_argument("--fuzzy", action="store_true",
                   help="Use fuzzy dedup instead of exact (catches near-duplicates)")
    p.add_argument("--fuzzy-threshold", type=float, default=0.85,
                   help="Similarity threshold for fuzzy dedup (default 0.85)")
    p.add_argument("--normalize",
                   help="Comma-separated normalize specs, e.g. 'phone,date' or 'phone:mobile,email'")
    p.add_argument("--schema", help="JSON file with column mapping, e.g. {'Old':'new'}")
    p.add_argument("--split",
                   help="Split a column: 'source:new1,new2' or 'source:new1,new2:sep'")
    p.add_argument("--merge",
                   help="Merge columns: 'a,b:new' or 'a,b:new:sep'")
    p.add_argument("--pdf-out", help="SQLite db path: extract PDF text/images into it")
    p.add_argument("--pdf-images", help="Directory for extracted PDF images")
    p.add_argument("--pdf-csv", help="Also write per-page PDF text to this CSV")
    return p.parse_args(argv)


def parse_normalize_specs(spec):
    """'phone:mobile,email' -> [('phone', 'mobile'), ('email', 'email')].

    A bare token that is a known normalizer type applies to the column
    with the same name; otherwise it is treated as a column name to trim.
    """
    out = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            kind, column = token.split(":", 1)
            kind, column = kind.strip(), column.strip()
        elif token in NORMALIZERS:
            kind, column = token, token
        else:
            kind, column = "trim", token
        if kind not in NORMALIZERS:
            raise ValueError(f"Unknown normalizer: {kind!r}")
        out.append((kind, column))
    return out


def resolve_column(df, name):
    """Return the actual column name matching ``name`` case-insensitively."""
    for col in df.columns:
        if str(col).lower() == str(name).lower():
            return col
    raise KeyError(f"Column not found: {name!r}")


def read_table(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext in (".tsv", ".txt"):
        return pd.read_csv(path, sep="\t")
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise ValueError(f"Unsupported input format: {ext}")


def write_table(df, path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df.to_csv(path, index=False)
    elif ext in (".xlsx", ".xls"):
        df.to_excel(path, index=False)
    else:
        raise ValueError(f"Unsupported output format: {ext}")


def clean_table(args):
    df = read_table(args.input)
    print(f"Loaded {len(df)} rows x {len(df.columns)} cols from {args.input}")

    if args.schema:
        with open(args.schema, encoding="utf-8") as fh:
            mapping = json.load(fh)
        df = apply_schema(df, mapping)
        print(f"Schema applied: {len(mapping.get('columns', mapping))} column mapping(s)")

    if args.normalize:
        for kind, column in parse_normalize_specs(args.normalize):
            column = resolve_column(df, column)
            df = apply_normalizer(df, kind, column)
            print(f"Normalized {column!r} as {kind}")

    if args.split:
        # 'source:new1,new2' or 'source:new1,new2:sep'
        src, rest = args.split.split(":", 1)
        if ":" in rest:
            cols, sep = rest.rsplit(":", 1)
        else:
            cols, sep = rest, r"\s+"
        into = [c.strip() for c in cols.split(",")]
        src = resolve_column(df, src.strip())
        df = split_column(df, src, into, sep=sep)
        print(f"Split {src!r} into {into}")

    if args.merge:
        # 'a,b:new' or 'a,b:new:sep'
        cols, rest = args.merge.split(":", 1)
        if ":" in rest:
            new_col, sep = rest.rsplit(":", 1)
        else:
            new_col, sep = rest, " "
        columns = [resolve_column(df, c.strip()) for c in cols.split(",")]
        new_col = new_col.strip()
        df = merge_columns(df, columns, new_col, sep=sep)
        print(f"Merged {columns} into {new_col!r}")

    if args.dedup:
        keys = [resolve_column(df, k.strip()) for k in args.dedup.split(",")]
        if args.fuzzy:
            df, removed = fuzzy_dedup(df, keys, threshold=args.fuzzy_threshold)
            print(f"Fuzzy dedup on {keys}: removed {removed} row(s)")
        else:
            df, removed = exact_dedup(df, keys)
            print(f"Exact dedup on {keys}: removed {removed} row(s)")

    if not args.output:
        raise SystemExit("Nothing to do: pass -o/--output for cleaned data.")
    write_table(df, args.output)
    print(f"Wrote {len(df)} rows to {args.output}")


def extract_pdf(args):
    summary = extract_to_db(args.input, args.pdf_out, image_dir=args.pdf_images)
    print(
        f"Extracted {args.input}: {summary['page_count']} page(s), "
        f"{summary['text_pages']} with text, {summary['image_count']} image(s) "
        f"-> {summary['db_path']} (images in {summary['image_dir']})"
    )
    if args.pdf_csv:
        pages_to_csv(args.input, args.pdf_csv)
        print(f"Per-page text CSV: {args.pdf_csv}")


def main(argv=None):
    args = parse_args(argv)
    ext = os.path.splitext(args.input)[1].lower()
    if ext == ".pdf":
        if not args.pdf_out:
            raise SystemExit("PDF input requires --pdf-out <db.sqlite>")
        extract_pdf(args)
    elif ext in TABULAR_EXTS:
        clean_table(args)
    else:
        raise SystemExit(f"Unsupported input: {args.input} (need .csv/.xlsx or .pdf)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
