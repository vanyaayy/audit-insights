"""Single background worker. One thread processes jobs in order, which keeps us
inside the LLM's per-minute rate limit no matter how many reports are uploaded."""

from __future__ import annotations

import logging
import queue
import threading

from . import db, service
from .llm import LLMError, make_client

log = logging.getLogger("worker")
INTERRUPTED = "Interrupted before finishing. Reprocess to resume; completed sections are cached."


class AlreadyQueued(RuntimeError):
    pass


class Worker:
    def __init__(self) -> None:
        self.jobs: queue.Queue[tuple[str, str | int]] = queue.Queue()
        self._llm = None
        # Reports queued or running; guards against the same report being queued twice
        # (e.g. a double-click on "Re-run"), which would spend the model calls twice.
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        # Jobs cut off by a restart are flagged rather than resumed automatically, so
        # starting the server never spends API quota on its own. Re-running reuses
        # the cached sections.
        for rid in db.reports_with_status("queued", "processing"):
            db.set_report_status(rid, "failed", error=INTERRUPTED)
        for run_id in db.insights_with_status("queued", "processing"):
            db.set_insights(run_id, "failed", error=INTERRUPTED)
        self._thread.start()

    def submit_report(self, report_id: str) -> None:
        with self._lock:
            if report_id in self._pending:
                raise AlreadyQueued(f"{report_id} is already queued or processing")
            self._pending.add(report_id)
        db.set_report_status(report_id, "queued")
        self.jobs.put(("report", report_id))

    def submit_insights(self, report_ids: list[str]) -> int:
        run_id = db.create_insights_run(report_ids)
        self.jobs.put(("insights", run_id))
        return run_id

    def _client(self):
        if self._llm is None:
            self._llm = make_client()
        return self._llm

    def _run(self) -> None:
        while True:
            kind, ref = self.jobs.get()
            try:
                llm = self._client()
                if kind == "report":
                    service.process_report(str(ref), llm)
                else:
                    service.run_insights(int(ref), llm)
            except LLMError as e:
                log.error("%s %s failed: %s", kind, ref, e)
                if kind == "report":
                    db.set_report_status(str(ref), "failed", error=str(e))
                else:
                    db.set_insights(int(ref), "failed", error=str(e))
            except Exception:
                log.exception("%s %s failed", kind, ref)
            finally:
                if kind == "report":
                    with self._lock:
                        self._pending.discard(str(ref))
                self.jobs.task_done()
