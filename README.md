# data-cleaning-toolkit

A Python toolkit for turning messy client data into clean, analysis-ready tables —
deduplicate and normalize CSV/Excel files, reshape columns, and pull text and
images out of PDFs into a queryable database.

## The problem it solves

Client data rarely arrives clean. Typical real-world messes this toolkit handles:

- **Duplicates** — the same customer listed 3 times with slightly different
  spellings (`Jon Doe` vs `John Doe`, `ALICE@x.com` vs `alice@x.com`).
- **Inconsistent formats** — phone numbers as `98765 43210`, `09876543210`,
  `+91-9876543210`; dates as `12/05/2024`, `15-Jun-2024`, `May 2, 2024`;
  amounts as `₹1,25,000` vs `$1,299.50`.
- **Data trapped in PDFs** — invoices and reports whose text and scanned images
  need to land in a database, not stay locked in a document.

## Features

- **Dedup** — exact duplicates on key columns, plus fuzzy dedup that catches
  near-duplicates via similarity scoring (configurable threshold).
- **Normalize** — trim whitespace, case rules, email lowercasing, Indian phone
  normalization (`+91-XXXXXXXXXX`), mixed-format date parsing, currency cleanup
  (`₹1,25,000` → `125000.0`).
- **Reformat** — rename columns via a JSON schema, melt wide tables to long
  format, split one column into many (`Full Name` → `First` + `Last`), merge
  columns back together.
- **PDF extraction** — per-page text extraction (pypdf), embedded image
  extraction (pypdf + Pillow), persisted to SQLite (`documents`, `pages`,
  `images` tables) and optionally to CSV.
- **CLI** — one command to clean a file end to end; column names resolve
  case-insensitively.

## Quickstart

```bash
pip install -r requirements.txt

# Clean a messy CSV: dedup on email, normalize phone + dates, rename columns, save
python clean.py leads.csv --dedup email --normalize phone:mobile,date:signup_date \
    --schema mapping.json -o leads_clean.csv

# Fuzzy dedup to catch near-duplicate names
python clean.py leads.csv --dedup name,email --fuzzy --fuzzy-threshold 0.9 -o clean.csv

# Split a name column while cleaning
python clean.py leads.csv --dedup email --split "Full Name:first_name,last_name" -o clean.csv

# Extract a PDF's text + images into SQLite
python clean.py invoice.pdf --pdf-out invoice.sqlite
python clean.py invoice.pdf --pdf-out invoice.sqlite --pdf-images ./imgs --pdf-csv pages.csv
```

`mapping.json` example:

```json
{"Full Name": "full_name", "Phone Number": "phone", "E-mail": "email"}
```

Python API:

```python
from cleaner import exact_dedup, fuzzy_dedup, normalize_phone, extract_to_db

df, removed = exact_dedup(df, "email")
df, removed = fuzzy_dedup(df, ["name", "email"], threshold=0.9)
normalize_phone("09876543210")          # -> '+91-9876543210'
summary = extract_to_db("invoice.pdf", "invoice.sqlite")
```

## Before / after

| email (raw)         | phone (raw)     | signup (raw) | amount (raw) | → | email | phone            | signup     | amount   |
|---------------------|-----------------|--------------|--------------|---|-------|------------------|------------|----------|
| `  ALICE@Example.com ` | `98765 43210` | `12/05/2024` | `₹1,25,000`  | → | `alice@example.com` | `+91-9876543210` | `2024-05-12` | `125000.0` |
| `alice@example.com` | `09876543210`   | `2024-06-01` | `$1,299.50`  | → | *(dupe removed)* | | | |
| `bob@example.com`   | `+91-9876543211`| `15-Jun-2024`| `Rs. 2,000`  | → | `bob@example.com` | `+91-9876543211` | `2024-06-15` | `2000.0` |

## Tech stack

- **pandas** — table loading, transformation, dedup
- **openpyxl** — Excel (`.xlsx`) input/output
- **pypdf** — PDF text and embedded-image extraction
- **Pillow** — image decoding and metadata
- **sqlite3** (stdlib) — PDF content database
- **pytest** — test suite (28 tests)

## Project layout

```
clean.py                 CLI entry point
cleaner/
  __init__.py            public API
  dedup.py               exact_dedup, fuzzy_dedup
  normalize.py           phone/email/date/currency/whitespace/case
  reformat.py            apply_schema, melt, split/merge columns
  pdf_extract.py         PDF text + images -> CSV / SQLite
tests/test_cleaner.py    pytest suite (PDF fixture generated in-test)
requirements.txt
```

Run the tests:

```bash
python -m pytest tests/ -q
```

## License

MIT
