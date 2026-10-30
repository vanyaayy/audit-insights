"""Downloadable outputs for auditors: a findings register (CSV, opens in Excel)
and a briefing note (PDF) built from an insights run."""

from __future__ import annotations

import csv
import io
from datetime import date
from html import escape

import pymupdf

from .schemas import FindingRecord


def findings_csv(findings: list[FindingRecord]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "ID", "Report year", "Ministry", "Entity", "System", "Observation (AGO heading)", "Control domain",
        "Audit type", "Severity", "Severity rationale", "Issue", "Key facts", "Root cause", "Risk / impact",
        "CIA impact", "Criteria breached", "Management response",
        "Evidence (printed page: quote)", "Evidence verified",
    ])
    for f in findings:
        w.writerow([
            f.id, f.fiscal_year, f.ministry, f.entity, f.system or "", f.observation_title,
            f.control_domain.value, f.audit_type.value, f.severity.value, f.severity_rationale,
            f.issue_summary, "; ".join(f.key_facts), f.root_cause or "", f.risk_impact,
            ", ".join(c.value for c in f.cia_impact), "; ".join(f.criteria_breached),
            f.management_response or "",
            "\n".join(f"p.{e.printed_page or e.pdf_page}: \"{e.quote}\"" for e in f.evidence),
            f.verification,
        ])
    return "﻿" + buf.getvalue()  # BOM so Excel reads UTF-8 correctly


# --- briefing PDF ---------------------------------------------------------------
# Laid out from HTML with PyMuPDF (already used for reading the reports), so no
# extra PDF library or system dependency is needed.

_CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #0f1b2d; line-height: 1.45; }
h1 { font-size: 20pt; margin: 0 0 4pt 0; color: #12456b; }
h2 { font-size: 13pt; margin: 18pt 0 6pt 0; padding-bottom: 3pt; border-bottom: 1px solid #e3e8ef; color: #12456b; }
h3 { font-size: 11pt; margin: 12pt 0 4pt 0; }
p { margin: 0 0 6pt 0; }
ul { margin: 2pt 0 6pt 0; }
li { margin-bottom: 2pt; }
.meta { color: #6b7a8f; font-size: 9pt; margin-bottom: 10pt; }
.note { color: #b54708; border: 1px solid #f5c98a; padding: 6pt; font-size: 9pt; }
.label { font-weight: bold; }
.sources { color: #6b7a8f; font-size: 8.5pt; }
.High { color: #b42318; font-weight: bold; }
.Medium { color: #b54708; font-weight: bold; }
.Low { color: #475467; font-weight: bold; }
"""

_PAGE = pymupdf.paper_rect("a4")
_BODY = _PAGE + (54, 60, -54, -60)  # margins: left, top, right, bottom (points)


def _briefing_html(insights: dict, findings: dict[str, FindingRecord]) -> str:
    e = lambda t: escape(str(t))  # noqa: E731

    def sources(ids: list[str]) -> str:
        parts = []
        for i in ids:
            f = findings.get(i)
            if f:
                page = f.evidence[0].printed_page if f.evidence else None
                parts.append(f"{e(f.entity)}, {e(f.fiscal_year)}{f', p.{e(page)}' if page else ''}")
        parts = list(dict.fromkeys(parts))  # two findings on the same page cite it once
        return f'<p class="sources">Sources: {"; ".join(parts)}</p>' if parts else ""

    def bullets(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul>" if items else ""

    stats = insights.get("stats", {})
    sev = stats.get("by_severity", {})
    out = [
        "<h1>IT Controls Briefing</h1>",
        f'<p class="meta">AGO annual reports {e(", ".join(stats.get("reports", [])))} &#183; '
        f'{stats.get("total_findings", 0)} IT findings (High {sev.get("High", 0)}, Medium {sev.get("Medium", 0)}, '
        f'Low {sev.get("Low", 0)}) &#183; generated {date.today():%d %b %Y}</p>',
    ]
    if insights.get("placeholder"):
        out.append('<p class="note">Sample briefing written for development. Regenerate insights in the app to replace it.</p>')

    out += ["<h2>Executive summary</h2>", f"<p>{e(insights['executive_summary'])}</p>"]

    out.append("<h2>Focus areas for the next audit cycle</h2>")
    for a in insights["focus_areas"]:
        out += [f'<h3><span class="{e(a["priority"])}">[{e(a["priority"])}]</span> {e(a["area"])}</h3>',
                f"<p>{e(a['rationale'])}</p>", sources(a["finding_ids"])]

    out.append("<h2>Themes</h2>")
    for n, t in enumerate(insights["themes"], 1):
        out += [
            f"<h3>{n}. {e(t['name'])}</h3>",
            f"<p>{e(t['summary'])}</p>",
            f'<p><span class="label">Why it matters:</span> {e(t["why_it_matters"])}</p>',
            f'<p><span class="label">Seen at:</span> {e(", ".join(t["entities"]))} ({e(", ".join(t["years"]))})</p>',
        ]
        if t["recommendations"]:
            out += ['<p class="label">Recommendations for agencies</p>', bullets(t["recommendations"])]
        if t["audit_procedures"]:
            out += ['<p class="label">Suggested audit procedures</p>', bullets(t["audit_procedures"])]
        out.append(sources(t["finding_ids"]))

    out.append("<h2>Recurring issues</h2>")
    for r in insights["recurring_issues"]:
        out += [f"<h3>{e(r['issue'])}</h3>", f"<p>{e(r['pattern'])}</p>", sources(r["finding_ids"])]

    out.append("<h2>Key insights</h2>")
    for k in insights["key_insights"]:
        out += [f"<p>{e(k['insight'])}</p>", sources(k["finding_ids"])]

    out.append('<p class="sources">Every source above is a finding whose quoted evidence was checked against the report PDF.</p>')
    return "<body>" + "".join(out) + "</body>"


def briefing_pdf(insights: dict, findings: dict[str, FindingRecord]) -> bytes:
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    story = pymupdf.Story(html=_briefing_html(insights, findings), user_css=_CSS)
    more = True
    while more:
        device = writer.begin_page(_PAGE)
        more, _ = story.place(_BODY)
        story.draw(device)
        writer.end_page()
    writer.close()

    # Running footer with page numbers, added once the page count is known.
    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    for i, page in enumerate(doc, 1):
        footer = pymupdf.Rect(54, _PAGE.height - 40, _PAGE.width - 54, _PAGE.height - 24)
        page.insert_textbox(footer, "IT Controls Briefing  |  AGO annual reports", fontsize=8, color=(0.42, 0.48, 0.56))
        page.insert_textbox(footer, f"Page {i} of {doc.page_count}", fontsize=8, color=(0.42, 0.48, 0.56), align=pymupdf.TEXT_ALIGN_RIGHT)
    doc.set_metadata({"title": "IT Controls Briefing", "subject": "IT control findings across AGO annual reports"})
    return doc.tobytes(garbage=3, deflate=True)
