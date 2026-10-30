"""HTTP API.  Run: uv run uvicorn app.api:app --reload"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import pymupdf
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db, export, service
from .insights import compute_stats
from .llm import DEFAULT_MODEL, llm_configured
from .worker import AlreadyQueued, Worker

logging.basicConfig(level=logging.INFO)
worker = Worker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    service.seed_from_export()
    worker.start()
    yield


app = FastAPI(title="AGO IT Audit Insights", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MAX_UPLOAD_MB = 50  # per file
MAX_FILES_PER_UPLOAD = 10
MAX_REQUEST_MB = MAX_UPLOAD_MB * MAX_FILES_PER_UPLOAD
CHUNK = 1024 * 1024


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Refuse oversized uploads from the Content-Length header, before the body is read."""
    if request.method == "POST" and request.url.path == "/api/reports":
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_REQUEST_MB * 1024 * 1024:
            return JSONResponse({"detail": f"Upload larger than {MAX_REQUEST_MB} MB"}, status_code=413)
    return await call_next(request)


async def _read_limited(f: UploadFile, limit: int) -> bytes | None:
    """Read an upload in chunks, stopping as soon as it passes the limit, so one
    oversized file never ends up fully in memory. None means "too large"."""
    buf = bytearray()
    while chunk := await f.read(CHUNK):
        buf.extend(chunk)
        if len(buf) > limit:
            return None
    return bytes(buf)


# --- reports -----------------------------------------------------------------

@app.get("/api/reports")
def list_reports():
    return db.list_reports()


@app.post("/api/reports")
async def upload_reports(files: list[UploadFile] = File(...)):
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(413, f"Upload at most {MAX_FILES_PER_UPLOAD} files at a time")
    results = []
    for f in files:  # one file in memory at a time
        data = await _read_limited(f, MAX_UPLOAD_MB * 1024 * 1024)
        await f.close()
        if data is None:
            results.append({"file": f.filename, "error": f"larger than {MAX_UPLOAD_MB} MB"})
            continue
        try:
            added = service.add_pdf(data, f.filename or "upload.pdf")
        except service.InvalidReport as e:
            results.append({"file": f.filename, "error": str(e)})
            continue
        if added.is_new:
            worker.submit_report(added.report_id)
        results.append({
            "file": f.filename,
            "report_id": added.report_id,
            "duplicate": not added.is_new,
            "reason": added.reason,
            "same_year": added.same_year,
            "overlaps": [{"report_id": rid, "share": share} for rid, share in added.overlaps],
        })
    return results


@app.post("/api/reports/{report_id}/reprocess")
def reprocess(report_id: str):
    if not db.get_report_row(report_id):
        raise HTTPException(404, "report not found")
    try:
        worker.submit_report(report_id)
    except AlreadyQueued as e:
        raise HTTPException(409, str(e)) from e
    return {"status": "queued"}


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str):
    if not db.get_report_row(report_id):
        raise HTTPException(404, "report not found")
    service.delete_report(report_id)
    return {"deleted": report_id}


@app.get("/api/reports/{report_id}/pdf")
def report_pdf(report_id: str):
    path = service.pdf_path(report_id)
    if not path or not path.exists():
        raise HTTPException(404, "report not found")
    return FileResponse(path, media_type="application/pdf")


# --- status ------------------------------------------------------------------

@app.get("/api/status")
def status():
    """Whether AI processing is available. Without a key the app still shows the
    committed results; the UI just turns off upload, re-run and regenerate."""
    return {"llm_configured": llm_configured(), "model": os.getenv("GEMINI_MODEL", DEFAULT_MODEL)}


# --- findings ----------------------------------------------------------------

def _filtered(report_ids, years, entities, domains, severities, verification, q):
    findings = db.list_findings(report_ids or None)
    if "review" in verification:  # the UI's "Needs review" = anything not fully verified
        verification = [v for v in verification if v != "review"] + ["partial", "unverified"]
    q = (q or "").lower()
    return [
        f for f in findings
        if (not years or f.fiscal_year in years)
        and (not entities or f.entity in entities)
        and (not domains or f.control_domain.value in domains)
        and (not severities or f.severity.value in severities)
        and (not verification or f.verification in verification)
        and (not q or q in f.model_dump_json().lower())
    ]


@app.get("/api/findings")
def list_findings(
    report_id: list[str] = Query(default=[]),
    year: list[str] = Query(default=[]),
    entity: list[str] = Query(default=[]),
    domain: list[str] = Query(default=[]),
    severity: list[str] = Query(default=[]),
    verification: list[str] = Query(default=[]),
    q: str | None = None,
):
    return _filtered(report_id, year, entity, domain, severity, verification, q)


@app.get("/api/findings/{finding_id}")
def get_finding(finding_id: str):
    f = db.get_finding(finding_id)
    if not f:
        raise HTTPException(404, "finding not found")
    return f


@app.get("/api/findings/{finding_id}/evidence/{index}.png")
def evidence_image(finding_id: str, index: int, dpi: int = 110):
    """The cited PDF page rendered with the quote highlighted."""
    f = db.get_finding(finding_id)
    if not f or not 0 <= index < len(f.evidence):
        raise HTTPException(404, "evidence not found")
    path = service.pdf_path(f.report_id)
    ev = f.evidence[index]
    doc = pymupdf.open(path)
    page = doc[ev.pdf_page - 1]
    quads = page.search_for(ev.quote, quads=True)
    if not quads:  # quote wraps oddly; fall back to its opening words
        quads = page.search_for(" ".join(ev.quote.split()[:8]), quads=True)
    if quads:
        page.add_highlight_annot(quads)
    png = page.get_pixmap(dpi=min(max(dpi, 60), 200)).tobytes("png")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/stats")
def stats(report_id: list[str] = Query(default=[])):
    findings = [f for f in db.list_findings(report_id or None) if f.verification != "unverified"]
    return compute_stats(findings)


# --- insights ----------------------------------------------------------------

class InsightsRequest(BaseModel):
    report_ids: list[str] = []


@app.post("/api/insights")
def generate_insights(req: InsightsRequest):
    return {"run_id": worker.submit_insights(req.report_ids)}


@app.get("/api/insights/latest")
def latest_insights():
    return {"latest": db.get_insights(), "latest_done": db.latest_done_insights()}


@app.get("/api/insights/{run_id}")
def get_insights(run_id: int):
    run = db.get_insights(run_id)
    if not run:
        raise HTTPException(404, "insights run not found")
    return run


# --- exports -----------------------------------------------------------------

@app.get("/api/export/findings.csv")
def export_findings(
    report_id: list[str] = Query(default=[]),
    year: list[str] = Query(default=[]),
    entity: list[str] = Query(default=[]),
    domain: list[str] = Query(default=[]),
    severity: list[str] = Query(default=[]),
    verification: list[str] = Query(default=[]),
    q: str | None = None,
):
    findings = _filtered(report_id, year, entity, domain, severity, verification, q)
    return Response(
        export.findings_csv(findings),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="it-findings-register.csv"'},
    )


@app.get("/api/export/briefing.pdf")
def export_briefing():
    run = db.latest_done_insights()
    if not run:
        raise HTTPException(404, "no insights generated yet")
    findings = {f.id: f for f in db.list_findings()}
    return Response(
        export.briefing_pdf(run["data"], findings),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="it-controls-briefing.pdf"'},
    )
