"""Ingestion and quote verification against the real AGO PDFs (no API calls)."""

from pathlib import Path

import pytest

from app.extract import chunk_report
from app.ingest import load_report
from app.schemas import FindingRecord
from app.verify import verify_finding

REPORTS = Path(__file__).resolve().parents[2] / "data" / "reports"


@pytest.fixture(scope="module")
def fy2122():
    return load_report(REPORTS / "ar_fy2021_22.pdf")


@pytest.fixture(scope="module")
def fy2425():
    return load_report(REPORTS / "ar_fy2024_25.pdf")


def test_wrong_bookmarks_are_corrected(fy2122):
    moved = {b.title: (b.original_page, b.page) for b in fy2122.bookmarks if b.page != b.original_page}
    assert moved["Improve Contracting and Contract Management Process"] == (91, 79)
    assert moved["Improve Management of Payments"] == (93, 82)
    assert moved["MINISTRY OF SUSTAINABILITY AND THE ENVIRONMENT"] == (56, 43)


def test_pages_carry_section_labels_and_printed_numbers(fy2425):
    page = fy2425.pages[33]  # PDF page 34
    assert page.printed == "24"
    assert "MINISTRY OF MANPOWER" in page.context
    assert page.in_scope


def test_scope_excludes_front_matter_and_annexes(fy2425):
    scoped = [p.number for p in fy2425.pages if p.in_scope]
    assert scoped[0] == 10 and scoped[-1] == 89


def test_small_parts_are_merged_into_neighbouring_chunks(fy2425):
    titles = [t for t, _ in chunk_report(fy2425)]
    assert len(titles) == 3
    assert not any(t.upper() == "OVERVIEW" for t in titles)


def _record(report, page: int, quote: str) -> FindingRecord:
    return FindingRecord(
        observation_title="x", ministry="x", entity="x", system=None, audit_type="IT general controls",
        control_domain="Privileged access management", secondary_domains=[], issue_summary="x", key_facts=[],
        root_cause=None, risk_impact="x", cia_impact=[], severity="High", severity_rationale="x",
        criteria_breached=[], management_response=None, remediation_target=None,
        id="t", report_id=report.report_id, fiscal_year=report.fiscal_year,
        evidence=[{"pdf_page": page, "quote": quote}],
    )


QUOTE = ("This command could be used by 24 MOM IT staff and IT vendor staff to change the "
         "password of any account including the “root” account.")


def test_exact_quote_is_verified(fy2425):
    r = verify_finding(_record(fy2425, 34, QUOTE), fy2425)
    assert r.verification == "verified" and r.evidence[0].printed_page == "24"


def test_quote_cited_one_page_off_is_moved_to_the_right_page(fy2425):
    r = verify_finding(_record(fy2425, 35, QUOTE.replace("“root”", "root")), fy2425)
    assert r.verification == "verified" and r.evidence[0].pdf_page == 34


def test_fabricated_quote_is_rejected(fy2425):
    r = verify_finding(_record(fy2425, 34, "MOM failed to encrypt its backup tapes for the WINS-EP system for three years."), fy2425)
    assert r.verification == "unverified"
