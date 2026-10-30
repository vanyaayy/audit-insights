"""SQLite store. One file, no server; JSON columns hold the nested records and the
columns we filter on are pulled out alongside them."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .ingest import Bookmark, Page, Report
from .schemas import FindingRecord

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
# Overridable so tests, demos and containers can point at their own database.
DB_PATH = Path(os.getenv("APP_DB_PATH", DATA_DIR / "app.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    fiscal_year TEXT NOT NULL,
    sha256 TEXT UNIQUE NOT NULL,
    page_count INTEGER NOT NULL,
    bookmarks TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | processing | done | failed
    progress TEXT,
    error TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    printed TEXT,
    context TEXT NOT NULL,
    headings TEXT NOT NULL,
    in_scope INTEGER NOT NULL,
    text TEXT NOT NULL,
    fingerprint TEXT,              -- hash of the page text; NULL for near-empty pages
    PRIMARY KEY (report_id, number)
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    fiscal_year TEXT NOT NULL,
    entity TEXT NOT NULL,
    ministry TEXT NOT NULL,
    control_domain TEXT NOT NULL,
    severity TEXT NOT NULL,
    verification TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS findings_report ON findings(report_id);
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_ids TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | processing | done | failed
    error TEXT,
    data TEXT,
    created_at TEXT NOT NULL
);
"""

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    # The API threads and the worker thread share one file; serialise writes.
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)
        # Databases created before page fingerprints existed: add and backfill.
        columns = {row["name"] for row in c.execute("PRAGMA table_info(pages)")}
        if "fingerprint" not in columns:
            c.execute("ALTER TABLE pages ADD COLUMN fingerprint TEXT")
            rows = c.execute("SELECT report_id, number, text FROM pages").fetchall()
            c.executemany(
                "UPDATE pages SET fingerprint = ? WHERE report_id = ? AND number = ?",
                [(_fingerprint(r["text"]), r["report_id"], r["number"]) for r in rows],
            )
        c.execute("CREATE INDEX IF NOT EXISTS pages_fingerprint ON pages(fingerprint)")


def _fingerprint(text: str) -> str | None:
    return Page(number=0, printed=None, context=[], headings=[], in_scope=False, text=text).fingerprint()


# --- reports -----------------------------------------------------------------

def insert_report(r: Report, status: str = "queued") -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO reports (id, file_name, fiscal_year, sha256, page_count, bookmarks, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (r.report_id, r.file_name, r.fiscal_year, r.sha256, r.page_count,
             json.dumps([b.model_dump() for b in r.bookmarks]), status, now()),
        )
        c.executemany(
            "INSERT INTO pages (report_id, number, printed, context, headings, in_scope, text, fingerprint)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(r.report_id, p.number, p.printed, json.dumps(p.context), json.dumps(p.headings),
              int(p.in_scope), p.text, p.fingerprint()) for p in r.pages],
        )


def page_matches(fingerprints: set[str]) -> list[tuple[str, int]]:
    """Existing reports sharing page fingerprints with a new upload, most shared first."""
    if not fingerprints:
        return []
    with connect() as c:
        rows = c.execute(
            f"SELECT report_id, COUNT(DISTINCT fingerprint) AS shared FROM pages"
            f" WHERE fingerprint IN ({','.join('?' * len(fingerprints))})"
            f" GROUP BY report_id ORDER BY shared DESC",
            list(fingerprints),
        ).fetchall()
    return [(r["report_id"], r["shared"]) for r in rows]


def fingerprint_count(report_id: str) -> int:
    with connect() as c:
        return c.execute(
            "SELECT COUNT(DISTINCT fingerprint) FROM pages WHERE report_id = ? AND fingerprint IS NOT NULL",
            (report_id,),
        ).fetchone()[0]


def reports_in_year(fiscal_year: str) -> list[str]:
    with connect() as c:
        return [r["id"] for r in c.execute("SELECT id FROM reports WHERE fiscal_year = ?", (fiscal_year,))]


def report_by_sha(sha: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id FROM reports WHERE sha256 = ?", (sha,)).fetchone()
    return dict(row) if row else None


def report_id_taken(report_id: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM reports WHERE id = ?", (report_id,)).fetchone() is not None


def list_reports() -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT r.id, r.file_name, r.fiscal_year, r.page_count, r.status, r.progress, r.error, r.model,"
            " r.created_at, r.processed_at, r.bookmarks,"
            " (SELECT COUNT(*) FROM findings f WHERE f.report_id = r.id) AS finding_count"
            " FROM reports r ORDER BY r.fiscal_year, r.id"
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        marks = json.loads(d.pop("bookmarks"))
        d["bookmarks_corrected"] = sum(m["page"] != m["original_page"] for m in marks)
        out.append(d)
    return out


def get_report_row(report_id: str) -> dict | None:
    return next((r for r in list_reports() if r["id"] == report_id), None)


def get_report(report_id: str) -> Report | None:
    with connect() as c:
        row = c.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        pages = c.execute(
            "SELECT * FROM pages WHERE report_id = ? ORDER BY number", (report_id,)
        ).fetchall()
    return Report(
        report_id=row["id"], fiscal_year=row["fiscal_year"], file_name=row["file_name"],
        sha256=row["sha256"], page_count=row["page_count"],
        bookmarks=[Bookmark(**b) for b in json.loads(row["bookmarks"])],
        pages=[
            Page(number=p["number"], printed=p["printed"], context=json.loads(p["context"]),
                 headings=json.loads(p["headings"]), in_scope=bool(p["in_scope"]), text=p["text"])
            for p in pages
        ],
    )


def set_report_status(report_id: str, status: str, progress: str | None = None,
                      error: str | None = None, model: str | None = None) -> None:
    with connect() as c:
        c.execute(
            "UPDATE reports SET status = ?, progress = ?, error = ?, model = COALESCE(?, model),"
            " processed_at = CASE WHEN ? = 'done' THEN ? ELSE processed_at END WHERE id = ?",
            (status, progress, error, model, status, now(), report_id),
        )


def delete_report(report_id: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM reports WHERE id = ?", (report_id,))


def reports_with_status(*statuses: str) -> list[str]:
    with connect() as c:
        q = f"SELECT id FROM reports WHERE status IN ({','.join('?' * len(statuses))})"
        return [r["id"] for r in c.execute(q, statuses).fetchall()]


# --- findings ----------------------------------------------------------------

def replace_findings(report_id: str, findings: list[FindingRecord]) -> None:
    with connect() as c:
        c.execute("DELETE FROM findings WHERE report_id = ?", (report_id,))
        c.executemany(
            "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(f.id, f.report_id, f.fiscal_year, f.entity, f.ministry, f.control_domain.value,
              f.severity.value, f.verification, f.model_dump_json()) for f in findings],
        )


def list_findings(report_ids: list[str] | None = None) -> list[FindingRecord]:
    with connect() as c:
        if report_ids:
            q = f"SELECT data FROM findings WHERE report_id IN ({','.join('?' * len(report_ids))}) ORDER BY id"
            rows = c.execute(q, report_ids).fetchall()
        else:
            rows = c.execute("SELECT data FROM findings ORDER BY id").fetchall()
    return [FindingRecord.model_validate_json(r["data"]) for r in rows]


def get_finding(finding_id: str) -> FindingRecord | None:
    with connect() as c:
        row = c.execute("SELECT data FROM findings WHERE id = ?", (finding_id,)).fetchone()
    return FindingRecord.model_validate_json(row["data"]) if row else None


# --- insights ----------------------------------------------------------------

def create_insights_run(report_ids: list[str]) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO insights (report_ids, status, created_at) VALUES (?, 'queued', ?)",
            (json.dumps(report_ids), now()),
        )
        return cur.lastrowid


def set_insights(run_id: int, status: str, data: dict | None = None, error: str | None = None) -> None:
    with connect() as c:
        c.execute(
            "UPDATE insights SET status = ?, data = COALESCE(?, data), error = ? WHERE id = ?",
            (status, json.dumps(data, default=str) if data is not None else None, error, run_id),
        )


def get_insights(run_id: int | None = None) -> dict | None:
    with connect() as c:
        if run_id is None:
            row = c.execute("SELECT * FROM insights ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = c.execute("SELECT * FROM insights WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["report_ids"] = json.loads(d["report_ids"])
    d["data"] = json.loads(d["data"]) if d["data"] else None
    return d


def latest_done_insights() -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id FROM insights WHERE status = 'done' ORDER BY id DESC LIMIT 1").fetchone()
    return get_insights(row["id"]) if row else None


def insights_with_status(*statuses: str) -> list[int]:
    with connect() as c:
        q = f"SELECT id FROM insights WHERE status IN ({','.join('?' * len(statuses))})"
        return [r["id"] for r in c.execute(q, statuses).fetchall()]

