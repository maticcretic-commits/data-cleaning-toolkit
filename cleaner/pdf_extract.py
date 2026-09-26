"""PDF extraction: per-page text and embedded images, persisted to CSV/SQLite."""

import csv
import os
import sqlite3
from datetime import datetime, timezone

from PIL import Image
from pypdf import PdfReader

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    extracted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    page_no INTEGER NOT NULL,
    text TEXT,
    UNIQUE (document_id, page_no)
);
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    page_no INTEGER NOT NULL,
    image_index INTEGER NOT NULL,
    filename TEXT NOT NULL,
    format TEXT,
    width INTEGER,
    height INTEGER
);
"""


def extract_text_pages(pdf_path):
    """Return [(page_no, text), ...] — page_no is 1-based."""
    reader = PdfReader(pdf_path)
    return [(i + 1, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]


def extract_images(pdf_path, out_dir):
    """Save every embedded image to ``out_dir`` with Pillow.

    Returns a list of dicts: page_no, image_index, filename, format,
    width, height.
    """
    os.makedirs(out_dir, exist_ok=True)
    reader = PdfReader(pdf_path)
    saved = []
    for page_no, page in enumerate(reader.pages, start=1):
        for image_index, image in enumerate(page.images):
            ext = image.name.rsplit(".", 1)[-1].lower() if "." in image.name else "png"
            filename = f"page{page_no}_img{image_index}.{ext}"
            path = os.path.join(out_dir, filename)
            with open(path, "wb") as fh:
                fh.write(image.data)
            width = height = None
            fmt = ext.upper()
            try:
                with Image.open(path) as im:
                    width, height = im.size
                    fmt = im.format or fmt
            except Exception:
                pass  # keep the raw bytes even if Pillow can't decode them
            saved.append(
                {
                    "page_no": page_no,
                    "image_index": image_index,
                    "filename": filename,
                    "format": fmt,
                    "width": width,
                    "height": height,
                }
            )
    return saved


def pages_to_csv(pdf_path, csv_path):
    """Write per-page text to a CSV (columns: page_no, text)."""
    rows = extract_text_pages(pdf_path)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["page_no", "text"])
        writer.writerows(rows)
    return csv_path


def extract_to_db(pdf_path, db_path, image_dir=None):
    """Extract a PDF into SQLite: documents, pages and images tables.

    Embedded images are saved under ``image_dir`` (defaults to
    ``<db stem>_images/`` next to the database).

    Returns a summary dict: document_id, page_count, text_pages, image_count.
    """
    if image_dir is None:
        image_dir = os.path.splitext(db_path)[0] + "_images"
    pages = extract_text_pages(pdf_path)
    images = extract_images(pdf_path, image_dir)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        cur = conn.execute(
            "INSERT INTO documents (source_path, page_count, extracted_at) VALUES (?, ?, ?)",
            (
                os.path.abspath(pdf_path),
                len(pages),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        doc_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO pages (document_id, page_no, text) VALUES (?, ?, ?)",
            [(doc_id, page_no, text) for page_no, text in pages],
        )
        conn.executemany(
            """INSERT INTO images
               (document_id, page_no, image_index, filename, format, width, height)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    doc_id,
                    img["page_no"],
                    img["image_index"],
                    img["filename"],
                    img["format"],
                    img["width"],
                    img["height"],
                )
                for img in images
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "document_id": doc_id,
        "page_count": len(pages),
        "text_pages": sum(1 for _, t in pages if t),
        "image_count": len(images),
        "image_dir": image_dir,
        "db_path": db_path,
    }
