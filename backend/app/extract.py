"""Per-report extraction: split a report by Part and ask the LLM for IT findings."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .ingest import Page, Report
from .llm import LLMClient
from .schemas import ExtractionOutput, FindingRecord
from .verify import verify_finding

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "extract_system.md").read_text()
FALLBACK_CHUNK_PAGES = 30
MIN_CHUNK_CHARS = 10_000


def chunk_report(report: Report) -> list[tuple[str, list[Page]]]:
    """One chunk per top-level Part, so each call reads ~10-40 pages closely.

    The Overview only summarises the detailed Parts, so it is skipped here. PDFs
    without bookmarks fall back to fixed-size page windows.
    """
    pages = [p for p in report.pages if p.in_scope]
    parts = [b for b in report.bookmarks if b.level == 1 and b.page in {p.number for p in pages}]
    if not parts:
        return [
            (f"pages {pages[i].number}-{pages[min(i + FALLBACK_CHUNK_PAGES, len(pages)) - 1].number}",
             pages[i : i + FALLBACK_CHUNK_PAGES])
            for i in range(0, len(pages), FALLBACK_CHUNK_PAGES)
        ]

    chunks: list[tuple[str, list[Page]]] = []
    for i, part in enumerate(parts):
        end = parts[i + 1].page if i + 1 < len(parts) else pages[-1].number + 1
        if part.title.upper() == "OVERVIEW":
            continue
        chunk = [p for p in pages if part.page <= p.number < end]
        if not chunk:
            continue
        # Tiny Parts (e.g. the 2-page financial statements opinion) ride along with a
        # neighbour so they don't each cost a rate-limited call.
        if chunks and _size(chunks[-1][1]) < MIN_CHUNK_CHARS:
            prev_title, prev_pages = chunks.pop()
            chunk, part_title = prev_pages + chunk, f"{prev_title} + {part.title}"
        else:
            part_title = part.title
        chunks.append((part_title, chunk))
    if len(chunks) > 1 and _size(chunks[-1][1]) < MIN_CHUNK_CHARS:
        last_title, last_pages = chunks.pop()
        prev_title, prev_pages = chunks.pop()
        chunks.append((f"{prev_title} + {last_title}", prev_pages + last_pages))
    return chunks


def _size(pages: list[Page]) -> int:
    return sum(len(p.text) for p in pages)


def extract_report(
    report: Report, llm: LLMClient, on_progress: Callable[[int, int], None] | None = None
) -> list[FindingRecord]:
    records: list[FindingRecord] = []
    chunks = chunk_report(report)
    for i, (title, pages) in enumerate(chunks):
        if on_progress:
            on_progress(i + 1, len(chunks))
        prompt = (
            f"Report: Report of the Auditor-General for {report.fiscal_year}\n"
            f"Section: {title}\n\n"
            + "\n".join(p.labelled_text() for p in pages)
        )
        out = llm.generate(
            system=SYSTEM_PROMPT,
            prompt=prompt,
            schema=ExtractionOutput,
            tag=f"extract-{report.report_id}-{i}",
        )
        for f in out.findings:
            record = FindingRecord(
                **f.model_dump(exclude={"evidence"}),
                evidence=[e.model_dump() for e in f.evidence],
                id=f"{report.report_id}-{len(records) + 1:02d}",
                report_id=report.report_id,
                fiscal_year=report.fiscal_year,
            )
            records.append(verify_finding(record, report))
    return records
