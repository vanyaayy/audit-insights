"""Checks that every quote the model returns really appears on the page it cites.

This is the guard against hallucinated evidence: a finding is only marked
"verified" if all its quotes are found in the source PDF text.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .ingest import Report
from .schemas import FindingRecord

MATCH_THRESHOLD = 90.0
_REPLACEMENTS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_REPLACEMENTS)).strip().lower()


def _score(quote: str, page_text: str) -> float:
    if quote in page_text:
        return 100.0
    return fuzz.partial_ratio(quote, page_text)


def verify_finding(record: FindingRecord, report: Report) -> FindingRecord:
    pages = {p.number: p for p in report.pages}
    for ev in record.evidence:
        quote = normalise(ev.quote)
        # Try the cited page first, then neighbours (a quote can be cited one page
        # off or run across a page break).
        best_page, best = ev.pdf_page, 0.0
        for n in (ev.pdf_page, ev.pdf_page - 1, ev.pdf_page + 1):
            if n in pages and (s := _score(quote, normalise(pages[n].text))) > best:
                best_page, best = n, s
        if best < MATCH_THRESHOLD:
            for n in (ev.pdf_page - 1, ev.pdf_page):
                if n in pages and n + 1 in pages:
                    s = _score(quote, normalise(pages[n].text + " " + pages[n + 1].text))
                    if s > best:
                        best_page, best = n, s
        ev.pdf_page = best_page
        ev.printed_page = pages[best_page].printed if best_page in pages else None
        ev.match_score = round(best, 1)
        ev.verified = best >= MATCH_THRESHOLD

    ok = sum(ev.verified for ev in record.evidence)
    record.verification = (
        "verified" if record.evidence and ok == len(record.evidence)
        else "partial" if ok else "unverified"
    )
    return record

