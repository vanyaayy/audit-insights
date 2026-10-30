"""Command-line entry point (same operations as the API, run in the foreground).

    uv run python -m app.pipeline                 # ingest data/reports, extract, synthesise, export
    uv run python -m app.pipeline --ingest-only   # no API key needed
    uv run python -m app.pipeline --reprocess     # re-extract reports already done
    uv run python -m app.pipeline --list-models
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import db, service
from .llm import make_client


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", type=Path, default=service.PDF_DIR)
    ap.add_argument("--ingest-only", action="store_true")
    ap.add_argument("--reprocess", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--model")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.list_models:
        print("\n".join(make_client(model=args.model).list_models()))
        return

    db.init()
    for path in sorted(args.reports.glob("*.pdf")):
        try:
            added = service.add_pdf(path.read_bytes(), path.name)
        except service.InvalidReport as e:
            print(f"skipped {path.name}: {e}")
            continue
        row = db.get_report_row(added.report_id)
        print(f"{'ingested' if added.is_new else 'known   '} {path.name} -> {added.report_id} "
              f"({row['fiscal_year']}, {row['page_count']} pages, {row['bookmarks_corrected']} bookmarks corrected)")
    if args.ingest_only:
        return

    llm = make_client(model=args.model)
    failed: list[str] = []
    for row in db.list_reports():
        if row["status"] == "done" and not args.reprocess:
            continue
        print(f"extracting {row['id']} with {llm.model} ...", flush=True)
        try:
            service.process_report(row["id"], llm)
        except Exception as e:  # one report failing shouldn't stop the others
            failed.append(row["id"])
            print(f"  FAILED: {e}\n  (completed sections are cached; re-run to resume)", flush=True)
            continue
        found = db.list_findings([row["id"]])
        status = {s: sum(f.verification == s for f in found) for s in ("verified", "partial", "unverified")}
        print(f"  {len(found)} IT findings {status}")

    if failed:
        # A briefing built without these reports would be incomplete; keep the previous one.
        print(f"\nNot all reports finished ({', '.join(failed)}). Re-run the same command; "
              "cached sections are reused. The briefing is generated once every report is done.")
        raise SystemExit(1)

    run_id = db.create_insights_run([])
    try:
        service.run_insights(run_id, llm)
    except Exception as e:
        print(f"Briefing FAILED: {e}\nRe-run the same command (extraction results are cached).")
        raise SystemExit(1)
    data = db.get_insights(run_id)["data"]
    print(f"insights: {len(data['themes'])} themes, {len(data['recurring_issues'])} recurring issues")
    service.export_json()
    print(f"exported to {service.EXPORT_DIR}")


if __name__ == "__main__":
    main()
