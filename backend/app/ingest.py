"""PDF ingestion: page text plus a verified section label for every page.

AGO reports ship with PDF bookmarks (Part > Ministry > Agency > Observation), but
some bookmarks point at the wrong page. We check each bookmark title against the
page text and, if it isn't there, search the parent section's page range for it.
The verified bookmarks then give every page a label like
"PART I B > MINISTRY OF MANPOWER > Weaknesses in ..." so findings can be
attributed to the right agency and cited by page.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

import pymupdf
from pydantic import BaseModel

MIN_FINGERPRINT_CHARS = 200


class Bookmark(BaseModel):
    level: int
    title: str
    page: int  # 1-based PDF page after verification
    original_page: int
    verified: bool  # title text was found on `page`


class Page(BaseModel):
    number: int  # 1-based PDF page index
    printed: str | None  # page number printed on the page, used in citations
    context: list[str]  # section path in effect at the top of the page
    headings: list[str]  # bookmark titles that start on this page
    in_scope: bool  # between OVERVIEW and the annexes
    text: str

    def fingerprint(self) -> str | None:
        """Hash of the page's letters and digits, so a re-saved or re-exported copy
        of the same report (different file bytes, same text) can be recognised.
        Near-empty pages (covers, Part dividers) are skipped: they repeat across
        different reports and would cause false matches."""
        key = re.sub(r"[^a-z0-9]", "", self.text.lower())
        return hashlib.sha256(key.encode()).hexdigest()[:32] if len(key) >= MIN_FINGERPRINT_CHARS else None

    def labelled_text(self) -> str:
        header = f"[PDF page {self.number} | printed page {self.printed or '-'}"
        if self.context:
            header += f" | section: {' > '.join(self.context)}"
        if self.headings:
            header += f" | new headings on this page: {' ; '.join(self.headings)}"
        return f"{header}]\n{self.text.strip()}\n"


class Report(BaseModel):
    report_id: str  # e.g. "fy2023_24"
    fiscal_year: str  # e.g. "FY2023/24"
    file_name: str
    sha256: str
    page_count: int
    bookmarks: list[Bookmark]
    pages: list[Page]

    def scoped_text(self) -> str:
        return "\n".join(p.labelled_text() for p in self.pages if p.in_scope)


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def _key(text: str, case_sensitive: bool) -> str:
    # Compare on letters/digits only: titles wrap across lines and use odd spacing.
    text = text if case_sensitive else text.lower()
    return re.sub(r"[^A-Za-z0-9]", "", text)


def _title_on_page(title: str, page_text: str) -> bool:
    # ALL-CAPS bookmarks (ministries, agencies) are printed as caps headings; matching
    # case-sensitively avoids hitting ordinary mentions in body text.
    caps = title.upper() == title
    needle = _key(title, caps)
    return bool(needle) and needle in _key(page_text, caps)


def _verify_bookmarks(toc: list[list], texts: list[str], skip: set[int]) -> list[Bookmark]:
    n_pages = len(texts)
    marks = [
        Bookmark(level=lvl, title=_clean_title(t), page=p, original_page=p, verified=False)
        for lvl, t, p in toc
    ]
    parent: list[int | None] = []
    stack: list[int] = []
    for i, m in enumerate(marks):
        while stack and marks[stack[-1]].level >= m.level:
            stack.pop()
        parent.append(stack[-1] if stack else None)
        stack.append(i)

    def parent_range(i: int) -> tuple[int, int]:
        par = parent[i]
        if par is None:
            return 1, n_pages
        end = n_pages
        for j in range(par + 1, len(marks)):
            if marks[j].level <= marks[par].level:
                end = marks[j].page
                break
        return marks[par].page, end

    # Shallow levels first, so a child's search window uses its parent's corrected page.
    for level in sorted({m.level for m in marks}):
        for i, m in enumerate(marks):
            if m.level != level:
                continue
            lo, hi = parent_range(i)
            # Titles repeat across agencies (e.g. "Improve Management of Payments"), so
            # the page must also fall inside the parent's range to count as verified.
            if lo <= m.page <= hi and _title_on_page(m.title, texts[m.page - 1]):
                m.verified = True
                continue
            hits = [
                p for p in range(lo, hi + 1)
                if p not in skip and _title_on_page(m.title, texts[p - 1])
            ]
            if hits:
                m.page = min(hits, key=lambda p: abs(p - m.original_page))
                m.verified = True
    return marks


def _printed_number(text: str) -> str | None:
    for line in text.splitlines()[:3]:
        if re.fullmatch(r"\d{1,3}", line.strip()):
            return line.strip()
    return None


def _fiscal_year(file_name: str, texts: list[str]) -> str:
    # The report's own wording ("audits carried out ... for the financial year 2023/24")
    # is more trustworthy than a file name, which users can get wrong.
    found = Counter(
        y for t in texts[:20] for y in re.findall(r"financial year (\d{4}/\d{2})", t)
    )
    if found:
        return f"FY{found.most_common(1)[0][0]}"
    m = re.search(r"fy\s*(\d{4})[_/-](\d{2})", file_name.lower())
    return f"FY{m.group(1)}/{m.group(2)}" if m else "unknown"


def load_report(path: Path) -> Report:
    return parse_pdf(path.read_bytes(), path.name)


def parse_pdf(data: bytes, file_name: str) -> Report:
    doc = pymupdf.open(stream=data, filetype="pdf")
    texts = [page.get_text() for page in doc]
    toc = doc.get_toc(simple=True)

    # Don't let bookmark search land on the contents pages, which list every title.
    first = {_clean_title(t).upper(): p for lvl, t, p in toc if lvl == 1}
    contents, overview = first.get("CONTENTS"), first.get("OVERVIEW")
    skip = set(range(contents, overview)) if contents and overview else set()

    bookmarks = _verify_bookmarks(toc, texts, skip)

    annex = next((b.page for b in bookmarks if b.level == 1 and b.title.upper().startswith("ANNEX")), None)
    scope_start = next((b.page for b in bookmarks if b.level == 1 and b.title.upper() == "OVERVIEW"), 1)
    scope_end = (annex - 1) if annex else len(texts)

    ordered = sorted(enumerate(bookmarks), key=lambda ib: (ib[1].page, ib[0]))
    pages: list[Page] = []
    path_stack: list[str] = []
    k = 0
    for number, text in enumerate(texts, start=1):
        context = list(path_stack)
        headings = []
        while k < len(ordered) and ordered[k][1].page == number:
            b = ordered[k][1]
            path_stack = path_stack[: b.level - 1] + [b.title]
            headings.append(b.title)
            k += 1
        pages.append(
            Page(
                number=number,
                printed=_printed_number(text),
                context=context,
                headings=headings,
                in_scope=scope_start <= number <= scope_end,
                text=text,
            )
        )

    return Report(
        report_id=Path(file_name).stem.removeprefix("ar_"),
        fiscal_year=_fiscal_year(file_name, texts),
        file_name=file_name,
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=len(texts),
        bookmarks=bookmarks,
        pages=pages,
    )
