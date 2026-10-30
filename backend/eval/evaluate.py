"""Measures extraction recall against a hand-labelled set of IT findings.

    uv run python -m eval.evaluate

Each (gold item, extracted finding) pair from the same report is scored: it must
cite a page in the gold page range (+/- 1) and mention at least one gold keyword.
Pairs are then assigned best-score-first, so when several findings sit on the same
pages (e.g. four root-account issues at MOM) each gold item gets the finding that
fits it best, and each finding is used once. Extracted findings that match no gold
item are listed for manual review: the gold set is not exhaustive, so these are
either extra valid findings or false positives.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app import db
from app.schemas import FindingRecord
from app.verify import normalise

GOLD = json.loads((Path(__file__).parent / "gold.json").read_text())


def _text(f: FindingRecord) -> str:
    return normalise(" ".join(
        [f.observation_title, f.issue_summary, f.system or "", *f.key_facts, *(e.quote for e in f.evidence)]
    ))


def score(g: dict, f: FindingRecord) -> float:
    if f.report_id != g["report_id"]:
        return 0
    lo, hi = g["pages"]
    pages = [e.pdf_page for e in f.evidence]
    if any(lo <= p <= hi for p in pages):
        page_score = 2
    elif any(lo - 1 <= p <= hi + 1 for p in pages):
        page_score = 1
    else:
        return 0
    text = _text(f)
    hits = sum(normalise(k) in text for k in g["keywords"])
    return page_score + hits if hits else 0


def assign(gold: list[dict], findings: list[FindingRecord]) -> dict[str, str]:
    pairs = sorted(
        ((score(g, f), g["id"], f.id) for g in gold for f in findings),
        key=lambda t: -t[0],
    )
    matched: dict[str, str] = {}
    used: set[str] = set()
    for s, gid, fid in pairs:
        if s and gid not in matched and fid not in used:
            matched[gid] = fid
            used.add(fid)
    return matched


def main() -> None:
    reports = {r["id"] for r in db.list_reports() if r["status"] == "done"}
    gold = [g for g in GOLD if g["report_id"] in reports]
    findings = db.list_findings(sorted(reports))
    matched = assign(gold, findings)

    print(f"{'gold':5} {'match':14} issue")
    for g in gold:
        print(f"{g['id']:5} {matched.get(g['id'], 'MISSED'):14} {g['entity']}: {g['issue']}")

    extra = [f for f in findings if f.id not in matched.values()]
    n = len(gold)
    print(f"\nReports evaluated: {', '.join(sorted(reports))}")
    print(f"Recall: {len(matched)}/{n} = {len(matched) / max(n, 1):.0%}")
    print(f"Extracted: {len(findings)} findings, "
          f"{sum(f.verification == 'verified' for f in findings)} with all quotes verified")
    sev = Counter(f.severity.value for f in findings)
    print("Severity: " + ", ".join(f"{k} {sev.get(k, 0)}" for k in ("High", "Medium", "Low")))

    print(f"\nNot in gold set ({len(extra)}), review manually:")
    for f in extra:
        print(f"  {f.id:14} [{f.severity.value:6}] {f.entity}: {f.issue_summary[:100]}")


if __name__ == "__main__":
    main()
