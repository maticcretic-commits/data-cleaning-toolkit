"""Tests for data-cleaning-toolkit. The PDF fixture is generated in-test with pypdf."""

import os
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from cleaner import (
    apply_schema,
    exact_dedup,
    extract_to_db,
    fuzzy_dedup,
    merge_columns,
    normalize_currency,
    normalize_date,
    normalize_email,
    normalize_phone,
    pages_to_csv,
    split_column,
)


@pytest.fixture
def messy_df():
    return pd.DataFrame(
        {
            "email": [
                "  ALICE@Example.com ",
                "alice@example.com",
                "bob@example.com",
                "bobby@example.com",
            ],
            "phone": ["98765 43210", "09876543210", "+91-9876543211", "919876543212"],
            "signup_date": ["12/05/2024", "2024-06-01", "15-Jun-2024", "May 2, 2024"],
            "amount": ["₹1,25,000", "$1,299.50", " 750 ", "Rs. 2,000"],
        }
    )


# --- dedup ---------------------------------------------------------------

def test_exact_dedup_removes_exact_dupes():
    df = pd.DataFrame({"email": ["a@x.com", "a@x.com", "b@x.com"], "v": [1, 1, 2]})
    cleaned, removed = exact_dedup(df, "email")
    assert removed == 1
    assert len(cleaned) == 2
    assert cleaned["email"].tolist() == ["a@x.com", "b@x.com"]


def test_exact_dedup_multi_key():
    df = pd.DataFrame(
        {"email": ["a@x.com", "a@x.com", "a@x.com"], "city": ["Patna", "Patna", "Delhi"]}
    )
    cleaned, removed = exact_dedup(df, ["email", "city"])
    assert removed == 1
    assert len(cleaned) == 2


def test_fuzzy_dedup_catches_near_dupes():
    df = pd.DataFrame(
        {
            "name": ["Jon Doe", "John Doe", "Jane Smith", "Jon  Doe"],
            "email": ["j@x.com", "j@x.com", "jane@x.com", "j@x.com"],
        }
    )
    cleaned, removed = fuzzy_dedup(df, ["name", "email"], threshold=0.85)
    assert removed == 2
    assert len(cleaned) == 2
    assert "Jane Smith" in cleaned["name"].tolist()


def test_fuzzy_dedup_keeps_distinct_rows():
    df = pd.DataFrame({"name": ["Alice Kumar", "Ravi Sharma", "Priya Singh"]})
    cleaned, removed = fuzzy_dedup(df, "name", threshold=0.9)
    assert removed == 0
    assert len(cleaned) == 3


# --- normalize ------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("98765 43210", "+91-9876543210"),
        ("09876543210", "+91-9876543210"),
        ("+91-9876543210", "+91-9876543210"),
        ("919876543210", "+91-9876543210"),
        ("  +91 98765 43210 ", "+91-9876543210"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_phone_indian_formats(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_email():
    assert normalize_email("  ALICE@Example.COM ") == "alice@example.com"
    assert normalize_email(None) is None


def test_normalize_date_mixed_formats():
    result = normalize_date(["12/05/2024", "2024-06-01", "15-Jun-2024", "May 2, 2024"])
    assert pd.api.types.is_datetime64_any_dtype(result)
    assert result.notna().all()
    assert result.iloc[0] == pd.Timestamp("2024-05-12")
    assert result.iloc[2] == pd.Timestamp("2024-06-15")


def test_normalize_date_bad_values_become_nat():
    result = normalize_date(["not a date", "2024-01-01"])
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == pd.Timestamp("2024-01-01")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("₹1,25,000", 125000.0),
        ("$1,299.50", 1299.5),
        (" 750 ", 750.0),
        ("Rs. 2,000", 2000.0),
        ("n/a", None),
        (None, None),
    ],
)
def test_normalize_currency(raw, expected):
    assert normalize_currency(raw) == expected


def test_messy_df_end_to_end(messy_df):
    df = messy_df.copy()
    df["email"] = df["email"].apply(normalize_email)
    df["phone"] = df["phone"].apply(normalize_phone)
    df["signup_date"] = normalize_date(df["signup_date"])
    df["amount"] = df["amount"].apply(normalize_currency)
    cleaned, removed = exact_dedup(df, "email")
    assert removed == 1  # the two alice rows collapse after email normalization
    assert cleaned["phone"].tolist() == [
        "+91-9876543210",
        "+91-9876543211",
        "+91-9876543212",
    ]
    assert cleaned["amount"].tolist()[0] == 125000.0


# --- reformat -------------------------------------------------------------

def test_apply_schema_column_mapping():
    df = pd.DataFrame({"Full Name": ["A B"], "Phone Number": ["123"]})
    out = apply_schema(df, {"Full Name": "full_name", "Phone Number": "phone"})
    assert out.columns.tolist() == ["full_name", "phone"]


def test_apply_schema_nested_form():
    df = pd.DataFrame({"A": [1]})
    out = apply_schema(df, {"columns": {"A": "b"}})
    assert out.columns.tolist() == ["b"]


def test_split_and_merge_columns():
    df = pd.DataFrame({"full_name": ["Nitesh Kumar", "Asha Devi"]})
    split = split_column(df, "full_name", ["first_name", "last_name"])
    assert split["first_name"].tolist() == ["Nitesh", "Asha"]
    assert split["last_name"].tolist() == ["Kumar", "Devi"]
    merged = merge_columns(split, ["first_name", "last_name"], "rejoined")
    assert merged["rejoined"].tolist() == ["Nitesh Kumar", "Asha Devi"]


# --- PDF extraction (PDF generated in-test) -------------------------------

def make_test_pdf(path):
    """Build a 2-page PDF: page 1 has text + an embedded image, page 2 text only."""
    writer = PdfWriter()
    for page_no in (1, 2):
        page = writer.add_blank_page(595, 842)
        content = DecodedStreamObject()
        stream = (
            f"BT /F1 24 Tf 72 760 Td (Test invoice page {page_no}) Tj ET "
            f"BT /F1 12 Tf 72 720 Td (Total: 999) Tj ET"
        )
        if page_no == 1:
            stream += " q 50 0 0 50 72 600 cm /Im1 Do Q"
        content.set_data(stream.encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(content)

        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = writer._add_object(font)
        resources = DictionaryObject()
        resources[NameObject("/Font")] = fonts

        if page_no == 1:
            img = Image.new("RGB", (4, 4), color=(200, 30, 30))
            img_obj = DecodedStreamObject()
            img_obj.set_data(img.tobytes())
            img_obj[NameObject("/Type")] = NameObject("/XObject")
            img_obj[NameObject("/Subtype")] = NameObject("/Image")
            img_obj[NameObject("/Width")] = NumberObject(4)
            img_obj[NameObject("/Height")] = NumberObject(4)
            img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
            img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
            xobjects = DictionaryObject()
            xobjects[NameObject("/Im1")] = writer._add_object(img_obj)
            resources[NameObject("/XObject")] = xobjects
        page[NameObject("/Resources")] = resources

    with open(path, "wb") as fh:
        writer.write(fh)


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = str(tmp_path / "sample.pdf")
    make_test_pdf(pdf_path)
    return pdf_path


def test_pdf_text_extraction(sample_pdf):
    from cleaner import extract_text_pages

    pages = extract_text_pages(sample_pdf)
    assert len(pages) == 2
    assert "Test invoice page 1" in pages[0][1]
    assert "Total: 999" in pages[1][1]


def test_pdf_to_db(sample_pdf, tmp_path):
    db_path = str(tmp_path / "out.sqlite")
    img_dir = str(tmp_path / "imgs")
    summary = extract_to_db(sample_pdf, db_path, image_dir=img_dir)
    assert summary["page_count"] == 2
    assert summary["text_pages"] == 2
    assert summary["image_count"] == 1

    conn = sqlite3.connect(db_path)
    try:
        docs = conn.execute("SELECT source_path, page_count FROM documents").fetchall()
        assert len(docs) == 1 and docs[0][1] == 2
        pages = conn.execute("SELECT page_no, text FROM pages ORDER BY page_no").fetchall()
        assert len(pages) == 2
        assert "invoice page 2" in pages[1][1]
        imgs = conn.execute(
            "SELECT page_no, filename, width, height FROM images"
        ).fetchall()
        assert len(imgs) == 1
        assert imgs[0][0] == 1 and imgs[0][2] == 4 and imgs[0][3] == 4
    finally:
        conn.close()
    assert os.path.isfile(os.path.join(img_dir, imgs[0][1]))


def test_pages_to_csv(sample_pdf, tmp_path):
    csv_path = str(tmp_path / "pages.csv")
    pages_to_csv(sample_pdf, csv_path)
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ["page_no", "text"]
    assert len(df) == 2


# --- CLI smoke test --------------------------------------------------------

def test_cli_end_to_end(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = tmp_path / "leads.csv"
    src.write_text(
        "Full Name,Email,Mobile\n"
        " Alice Smith ,ALICE@x.com,98765 43210\n"
        "Alice Smith,alice@x.com,09876543210\n"
        "Bob Rao,bob@x.com,9123456780\n"
    )
    out = tmp_path / "clean.csv"
    cmd = [
        sys.executable, os.path.join(root, "clean.py"), str(src),
        "--dedup", "email",
        "--normalize", "email,phone:mobile",
        "--split", "Full Name:first,last",
        "-o", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    assert proc.returncode == 0, proc.stderr
    df = pd.read_csv(str(out))
    assert len(df) == 2  # alice dupes collapsed after email normalization
    assert df["Email"].tolist() == ["alice@x.com", "bob@x.com"]
    assert df["Mobile"].tolist() == ["+91-9876543210", "+91-9123456780"]
    assert df["first"].tolist() == ["Alice", "Bob"]
