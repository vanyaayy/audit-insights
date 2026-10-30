"""Duplicate detection on upload: identical bytes, re-saved copies, and different reports."""

import sqlite3
from pathlib import Path

import pymupdf
import pytest

from app import db, service

REPORTS = Path(__file__).resolve().parents[2] / "data" / "reports"
FY2425 = (REPORTS / "ar_fy2024_25.pdf").read_bytes()
FY2324 = (REPORTS / "ar_fy2023_24.pdf").read_bytes()


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(service, "PDF_DIR", tmp_path / "reports")
    db.init()


def _edited(data: bytes, delete_pages: range | None = None) -> bytes:
    """Re-save a PDF the way a re-download or re-export would: same text, different bytes."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    doc.set_metadata({**doc.metadata, "title": "Re-exported copy", "producer": "another tool"})
    if delete_pages:
        doc.delete_pages(from_page=delete_pages.start, to_page=delete_pages.stop - 1)
    return doc.tobytes(garbage=3, deflate=True)


def test_identical_file_is_a_duplicate():
    first = service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    again = service.add_pdf(FY2425, "renamed.pdf")
    assert first.is_new and not again.is_new
    assert again.report_id == first.report_id
    assert again.reason == "identical file already uploaded"


def test_resaved_copy_with_different_bytes_is_caught_by_content():
    first = service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    copy = _edited(FY2425)
    assert copy != FY2425
    again = service.add_pdf(copy, "AGO report 2025 (1).pdf")
    assert not again.is_new and again.report_id == first.report_id
    assert "same text" in again.reason


def test_corrected_edition_is_accepted_with_an_overlap_warning():
    # One page differs (a correction): must not be rejected, but the user is told
    # which report it overlaps so they can remove the older version.
    service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    doc = pymupdf.open(stream=FY2425, filetype="pdf")
    doc.delete_page(40)
    doc.insert_pdf(pymupdf.open(stream=FY2324, filetype="pdf"), from_page=40, to_page=40, start_at=40)
    corrected = service.add_pdf(doc.tobytes(), "ar_fy2024_25_corrected.pdf")
    assert corrected.is_new
    assert corrected.overlaps[0][0] == "fy2024_25" and corrected.overlaps[0][1] >= 0.95
    assert corrected.same_year == ["fy2024_25"]


def test_copy_with_pages_removed_is_accepted_with_an_overlap_warning():
    service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    trimmed = service.add_pdf(_edited(FY2425, delete_pages=range(0, 2)), "without-cover.pdf")
    assert trimmed.is_new
    assert trimmed.overlaps == [("fy2024_25", 1.0)]


def test_different_report_is_not_a_duplicate():
    # Different years share boilerplate pages (annexes, audit authority), but far below 90%.
    service.add_pdf(FY2324, "ar_fy2023_24.pdf")
    other = service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    assert other.is_new and other.report_id == "fy2024_25"
    assert other.same_year == [] and other.overlaps == []


def test_extract_of_an_existing_report_is_accepted_with_a_warning():
    service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    extract = service.add_pdf(_edited(FY2425, delete_pages=range(40, 98)), "extract.pdf")
    assert extract.is_new and extract.overlaps[0][0] == "fy2024_25"


def test_different_content_for_the_same_year_is_added_with_a_warning():
    # e.g. a revised edition: same year (from the overview text), mostly new pages.
    service.add_pdf(FY2425, "ar_fy2024_25.pdf")
    doc = pymupdf.open(stream=FY2425, filetype="pdf")
    doc.delete_pages(from_page=25, to_page=97)
    doc.insert_pdf(pymupdf.open(stream=FY2324, filetype="pdf"), from_page=25, to_page=110)
    revised = service.add_pdf(doc.tobytes(), "revised.pdf")
    assert revised.is_new
    assert revised.report_id.startswith("fy2024_25_")  # id taken, so suffixed
    assert revised.same_year == ["fy2024_25"]
    assert revised.overlaps == []  # well under half its pages are shared


def test_year_comes_from_report_text_not_a_misleading_file_name():
    added = service.add_pdf(FY2324, "ar_fy2024_25.pdf")
    assert added.report_id == "fy2023_24"


def test_old_database_gets_fingerprints_backfilled(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as c:
        c.execute("CREATE TABLE pages (report_id TEXT, number INTEGER, printed TEXT, context TEXT,"
                  " headings TEXT, in_scope INTEGER, text TEXT NOT NULL, PRIMARY KEY (report_id, number))")
        c.execute("INSERT INTO pages VALUES ('r', 1, NULL, '[]', '[]', 1, ?)", ("Access rights review. " * 20,))
        c.execute("INSERT INTO pages VALUES ('r', 2, NULL, '[]', '[]', 1, 'PART II')")
    monkeypatch.setattr(db, "DB_PATH", old)
    db.init()
    with sqlite3.connect(old) as c:
        rows = dict(c.execute("SELECT number, fingerprint FROM pages").fetchall())
    assert rows[1] and len(rows[1]) == 32
    assert rows[2] is None  # near-empty divider pages are not fingerprinted
