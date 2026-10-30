"""API and worker integration tests: real FastAPI app, real SQLite and PDFs in a
temporary folder, with a stand-in LLM so no model is called."""

import threading
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import api, db, service
from app import worker as worker_module
from app.schemas import ExtractionOutput

REPORTS = Path(__file__).resolve().parents[2] / "data" / "reports"
FY2425 = (REPORTS / "ar_fy2024_25.pdf").read_bytes()
QUOTE = ("This command could be used by 24 MOM IT staff and IT vendor staff to change the "
         "password of any account including the “root” account.")
FINDING = {
    "observation_title": "Weaknesses in Management of Most Privileged Operating System Account",
    "ministry": "Ministry of Manpower", "entity": "Ministry of Manpower", "system": "WINS-EP",
    "audit_type": "IT general controls", "control_domain": "Privileged access management", "secondary_domains": [],
    "issue_summary": "A sudo command let 24 staff change the root password.", "key_facts": [], "root_cause": None,
    "risk_impact": "x", "cia_impact": ["Availability"], "severity": "High", "severity_rationale": "x",
    "criteria_breached": [], "management_response": None,
    "evidence": [{"pdf_page": 34, "quote": QUOTE}],
}


class FakeLLM:
    """Returns one MOM finding for the section that contains it; can be paused."""

    def __init__(self, provider: str, gate: threading.Event | None = None):
        self.provider = provider
        self.model = f"fake/{provider}"
        self.models_used: set[str] = set()
        self.gate = gate

    def generate(self, *, system, prompt, schema, tag):
        if self.gate:
            self.gate.wait(10)
        self.models_used.add(self.model)
        if schema is ExtractionOutput:
            return ExtractionOutput.model_validate({"findings": [FINDING] if "WINS-EP" in prompt else []})
        raise AssertionError("insights not expected in these tests")


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(service, "PDF_DIR", tmp_path / "reports")
    monkeypatch.setattr(service, "EXPORT_DIR", tmp_path / "output")  # nothing to seed
    monkeypatch.setattr(api, "worker", worker_module.Worker())  # fresh worker thread per test
    made: list[str] = []
    gate = {"event": None}

    def fake_client(provider=None, model=None):
        made.append(provider or "gemini")
        return FakeLLM(provider or "gemini", gate["event"])

    monkeypatch.setattr(worker_module, "make_client", fake_client)
    with TestClient(api.app) as client:
        yield client, made, gate, tmp_path


def _wait_for(client, report_id, statuses=("done", "failed"), timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = next((r for r in client.get("/api/reports").json() if r["id"] == report_id), None)
        if row and row["status"] in statuses:
            return row
        time.sleep(0.1)
    raise AssertionError(f"{report_id} did not reach {statuses}")


def _upload(client, *files):
    return client.post("/api/reports", files=[("files", f) for f in files])


def test_upload_process_and_view_evidence(env):
    client, made, _, _ = env
    res = _upload(client, ("ar_fy2024_25.pdf", FY2425, "application/pdf")).json()
    assert res[0]["report_id"] == "fy2024_25" and res[0]["duplicate"] is False
    row = _wait_for(client, "fy2024_25")
    assert row["status"] == "done" and row["finding_count"] == 1
    assert made == ["gemini"]  # default engine

    finding = client.get("/api/findings").json()[0]
    assert finding["verification"] == "verified"
    png = client.get(f"/api/findings/{finding['id']}/evidence/0.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert client.get("/api/reports/fy2024_25/pdf").status_code == 200


def test_rejects_non_pdf_too_many_files_and_oversized_requests(env, monkeypatch):
    client, *_ = env
    assert "not a PDF" in _upload(client, ("notes.txt", b"hello", "text/plain")).json()[0]["error"]
    assert _upload(client, *[(f"{i}.pdf", b"%PDF", "application/pdf") for i in range(11)]).status_code == 413
    huge = client.post("/api/reports", content=b"x", headers={"content-length": str(600 * 1024 * 1024),
                                                             "content-type": "multipart/form-data; boundary=x"})
    assert huge.status_code == 413
    monkeypatch.setattr(api, "MAX_UPLOAD_MB", 1)  # the real report is ~3.7 MB
    assert "larger than 1 MB" in _upload(client, ("big.pdf", FY2425, "application/pdf")).json()[0]["error"]


def test_reprocess_while_queued_is_refused(env):
    client, _, gate, _ = env
    gate["event"] = threading.Event()  # hold the first job inside the model call
    _upload(client, ("ar_fy2024_25.pdf", FY2425, "application/pdf"))
    assert client.post("/api/reports/fy2024_25/reprocess").status_code == 409
    gate["event"].set()
    _wait_for(client, "fy2024_25")
    assert client.post("/api/reports/fy2024_25/reprocess").status_code == 200
    _wait_for(client, "fy2024_25")


def test_delete_removes_findings_and_the_stored_pdf(env):
    client, _, _, tmp = env
    _upload(client, ("my upload.pdf", FY2425, "application/pdf"))
    _wait_for(client, "fy2024_25")
    stored = tmp / "reports" / "fy2024_25.pdf"
    assert stored.exists()
    assert client.delete("/api/reports/fy2024_25").status_code == 200
    assert not stored.exists()
    assert client.get("/api/findings").json() == []
    assert client.delete("/api/reports/fy2024_25").status_code == 404



def test_jobs_interrupted_by_a_restart_are_flagged_not_resumed(env):
    client, made, _, _ = env
    report = service.parse_pdf(FY2425, "ar_fy2024_25.pdf")
    db.insert_report(report, status="processing")
    run_id = db.create_insights_run([])
    worker_module.Worker().start()  # what server startup does
    assert db.get_report_row("fy2024_25")["status"] == "failed"
    assert "Interrupted" in db.get_insights(run_id)["error"]
    assert made == []  # no model was called


def test_text_pdf_with_only_short_pages_is_accepted(env):
    # Enough text overall, but no page long enough to fingerprint: must not crash.
    doc = pymupdf.open()
    for i in range(20):
        doc.new_page().insert_text((72, 72), f"Short page {i} " * 12)
    added = service.add_pdf(doc.tobytes(), "short-pages.pdf")
    assert added.is_new and added.overlaps == []


def test_status_reports_whether_a_key_is_configured(env, monkeypatch):
    client, *_ = env
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert client.get("/api/status").json()["llm_configured"] is True
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert client.get("/api/status").json()["llm_configured"] is False
