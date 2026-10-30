"""Briefing PDF and findings CSV exports."""

import pymupdf

from app.export import briefing_pdf, findings_csv
from app.schemas import FindingRecord

FINDING = FindingRecord(
    observation_title="Weak Controls over the Most Privileged Accounts", ministry="Prime Minister's Office",
    entity="Public Service Division", system="HRP", audit_type="IT general controls",
    control_domain="Privileged access management", secondary_domains=[], issue_summary="Root misconfigured.",
    key_facts=["17 administrators"], root_cause=None, risk_impact="x", cia_impact=["Integrity"], severity="High",
    severity_rationale="x", criteria_breached=["GovTech advisory dated 1 June 2020"], management_response=None,
    id="fy2022_23-02", report_id="fy2022_23", fiscal_year="FY2022/23",
    evidence=[{"pdf_page": 32, "quote": "q", "printed_page": "22", "verified": True}], verification="verified",
)
GROUNDED = {"finding_ids": ["fy2022_23-02", "fy2022_23-02"], "years": ["FY2022/23"], "entities": ["Public Service Division"]}
INSIGHTS = {
    "executive_summary": "Privileged access is the most persistent weakness – see “root” findings.",
    "themes": [{**GROUNDED, "name": "Uncontrolled root access", "summary": "s", "why_it_matters": "w",
                "recommendations": ["Restrict sudo"], "audit_procedures": ["Review sudoers files"]}],
    "recurring_issues": [{**GROUNDED, "issue": "Root misconfigured", "pattern": "p"}],
    "key_insights": [{**GROUNDED, "insight": "Vendors hold most privileged accounts <and> it shows."}],
    "focus_areas": [{**GROUNDED, "area": "Privileged access", "priority": "High", "rationale": "r"}],
    "stats": {"reports": ["FY2022/23"], "total_findings": 1, "by_severity": {"High": 1}},
}


def test_briefing_pdf_contains_the_sections_and_sources():
    doc = pymupdf.open(stream=briefing_pdf(INSIGHTS, {FINDING.id: FINDING}), filetype="pdf")
    # The font typesets "fi" as one ligature glyph; expand it when reading the text back.
    flags = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES
    text = " ".join(page.get_text(flags=flags) for page in doc)
    for expected in ("IT Controls Briefing", "Executive summary", "Focus areas", "Themes", "Recurring issues",
                     "Key insights", "Review sudoers files", "<and>", "Page 1 of"):
        assert expected in text
    # The same finding cited twice appears once in the sources line.
    assert text.count("Public Service Division, FY2022/23, p.22") == 4  # once per section


def test_findings_csv_opens_in_excel_with_one_row_per_finding():
    csv_text = findings_csv([FINDING])
    assert csv_text.startswith("﻿")  # BOM so Excel detects UTF-8
    assert len(csv_text.strip().splitlines()) == 2
