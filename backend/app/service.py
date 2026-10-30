"""Application operations shared by the API and the CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .extract import extract_report
from .ingest import parse_pdf
from .insights import synthesise
from .llm import LLMClient

PDF_DIR = db.DATA_DIR / "reports"
EXPORT_DIR = db.DATA_DIR / "output"
MIN_TEXT_CHARS = 2_000
# Share of pages in common above which an upload is flagged as overlapping an
# existing report. Different AGO years share ~1% (boilerplate annex pages).
OVERLAP_NOTICE = 0.5


class InvalidReport(ValueError):
    pass


def _report_id(fiscal_year: str, file_name: str, sha: str) -> str:
    m = re.fullmatch(r"FY(\d{4})/(\d{2})", fiscal_year)
    base = f"fy{m.group(1)}_{m.group(2)}" if m else re.sub(r"[^a-z0-9]+", "_", Path(file_name).stem.lower()).strip("_")[:40]
    return base if not db.report_id_taken(base) else f"{base}_{sha[:6]}"


@dataclass
class AddResult:
    report_id: str
    is_new: bool
    reason: str | None = None  # why an upload was treated as a duplicate
    same_year: list[str] = field(default_factory=list)  # other reports for the same fiscal year
    overlaps: list[tuple[str, float]] = field(default_factory=list)  # (report_id, share of pages matching)


def add_pdf(data: bytes, file_name: str) -> AddResult:
    """Store and ingest a PDF.

    Only exact duplicates are skipped: identical file bytes (SHA-256 of the file), or
    a different file with exactly the same page text (a re-saved or re-downloaded
    copy). Those add nothing and would double-count findings.

    Anything with changes, e.g. a corrected edition, is accepted. If it largely
    overlaps an existing report, or shares its fiscal year, the result says so and
    the user decides whether to delete the older one.
    """
    if not data.startswith(b"%PDF"):
        raise InvalidReport(f"{file_name} is not a PDF")
    try:
        report = parse_pdf(data, file_name)
    except Exception as e:  # corrupt or encrypted files
        raise InvalidReport(f"Could not read {file_name}: {e}") from e

    if existing := db.report_by_sha(report.sha256):
        return AddResult(existing["id"], False, "identical file already uploaded")
    if sum(len(p.text) for p in report.pages) < MIN_TEXT_CHARS:
        raise InvalidReport(f"{file_name} has no text layer (scanned PDF); OCR is not supported yet")

    prints = {fp for p in report.pages if (fp := p.fingerprint())}
    # A text PDF whose pages are all too short to fingerprint has nothing to compare.
    matches = db.page_matches(prints) if prints else []
    for other_id, shared in matches[:1]:
        if shared == len(prints) == db.fingerprint_count(other_id):
            return AddResult(other_id, False, "same text as an existing report (re-saved copy)")

    # Informational only: never blocks the upload.
    overlaps = [(rid, round(shared / len(prints), 2)) for rid, shared in matches if shared / len(prints) >= OVERLAP_NOTICE]
    same_year = db.reports_in_year(report.fiscal_year) if report.fiscal_year != "unknown" else []
    report.report_id = _report_id(report.fiscal_year, file_name, report.sha256)
    existing_file = PDF_DIR / Path(file_name).name
    if existing_file.exists() and existing_file.read_bytes() == data:
        report.file_name = existing_file.name  # already in the reports folder (CLI)
    else:
        report.file_name = f"{report.report_id}.pdf"
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        (PDF_DIR / report.file_name).write_bytes(data)
    db.insert_report(report)
    return AddResult(report.report_id, True, same_year=same_year, overlaps=overlaps)


def delete_report(report_id: str) -> None:
    """Remove a report, its findings, and its stored PDF (unless another report row
    still points at the same file)."""
    row = db.get_report_row(report_id)
    db.delete_report(report_id)
    if row and not any(r["file_name"] == row["file_name"] for r in db.list_reports()):
        (PDF_DIR / row["file_name"]).unlink(missing_ok=True)


def pdf_path(report_id: str) -> Path | None:
    row = db.get_report_row(report_id)
    return PDF_DIR / row["file_name"] if row else None


def process_report(report_id: str, llm: LLMClient) -> None:
    report = db.get_report(report_id)
    if report is None:
        return
    db.set_report_status(report_id, "processing", "starting")
    llm.models_used = set()
    try:
        findings = extract_report(
            report, llm,
            on_progress=lambda i, n: db.set_report_status(report_id, "processing", f"section {i} of {n}"),
        )
        db.replace_findings(report_id, findings)
        # Fallbacks may have stepped in; record what actually produced the findings.
        db.set_report_status(report_id, "done", model=", ".join(sorted(llm.models_used)) or None)
    except Exception as e:
        db.set_report_status(report_id, "failed", error=str(e))
        raise


def run_insights(run_id: int, llm: LLMClient) -> None:
    run = db.get_insights(run_id)
    db.set_insights(run_id, "processing")
    try:
        findings = db.list_findings(run["report_ids"] or None)
        if not findings:
            raise ValueError("No findings to analyse yet; process some reports first")
        db.set_insights(run_id, "done", data=synthesise(findings, llm))
    except Exception as e:
        db.set_insights(run_id, "failed", error=str(e))
        raise


# --- JSON export / seed ------------------------------------------------------
# The exported JSON is committed so the app shows results without an API key.

def export_json(out_dir: Path | None = None) -> None:
    out_dir = out_dir or EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = [r for r in db.list_reports() if r["status"] == "done"]
    (out_dir / "reports.json").write_text(json.dumps(reports, indent=2))
    findings = db.list_findings([r["id"] for r in reports]) if reports else []
    (out_dir / "findings.json").write_text(
        json.dumps([f.model_dump(mode="json") for f in findings], indent=2, ensure_ascii=False)
    )
    if insights := db.latest_done_insights():
        (out_dir / "insights.json").write_text(json.dumps(insights, indent=2, ensure_ascii=False))


def seed_from_export(out_dir: Path | None = None) -> int:
    """On an empty database, load committed results so the demo works offline."""
    from .schemas import FindingRecord

    out_dir = out_dir or EXPORT_DIR
    if db.list_reports() or not (out_dir / "reports.json").exists():
        return 0
    loaded = 0
    for r in json.loads((out_dir / "reports.json").read_text()):
        path = PDF_DIR / r["file_name"]
        if not path.exists():
            continue
        report = parse_pdf(path.read_bytes(), r["file_name"])
        report.report_id = r["id"]
        db.insert_report(report, status="done")
        db.set_report_status(r["id"], "done", model=r.get("model"))
        loaded += 1
    findings = [FindingRecord.model_validate(f) for f in json.loads((out_dir / "findings.json").read_text())]
    for rid in {f.report_id for f in findings}:
        db.replace_findings(rid, [f for f in findings if f.report_id == rid])
    if (out_dir / "insights.json").exists():
        ins = json.loads((out_dir / "insights.json").read_text())
        run_id = db.create_insights_run(ins["report_ids"])
        db.set_insights(run_id, "done", data=ins["data"])
    return loaded
