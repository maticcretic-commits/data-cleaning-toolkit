"""data-cleaning-toolkit: dedup, normalize, reformat tabular data and extract PDF content."""

from .dedup import exact_dedup, fuzzy_dedup
from .normalize import (
    apply_normalizer,
    normalize_phone,
    normalize_email,
    normalize_date,
    normalize_currency,
    trim_whitespace,
    title_case,
    NORMALIZERS,
)
from .reformat import apply_schema, melt_wide_to_long, split_column, merge_columns
from .pdf_extract import (
    extract_text_pages,
    extract_images,
    extract_to_db,
    pages_to_csv,
)

__all__ = [
    "exact_dedup",
    "fuzzy_dedup",
    "apply_normalizer",
    "NORMALIZERS",
    "normalize_phone",
    "normalize_email",
    "normalize_date",
    "normalize_currency",
    "trim_whitespace",
    "title_case",
    "apply_schema",
    "melt_wide_to_long",
    "split_column",
    "merge_columns",
    "extract_text_pages",
    "extract_images",
    "extract_to_db",
    "pages_to_csv",
]

__version__ = "1.0.0"
