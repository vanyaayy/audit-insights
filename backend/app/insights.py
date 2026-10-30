"""Cross-report consolidation.

Counts and groupings are computed in code (LLMs miscount). Gemini then writes the
narrative from the extracted findings and must cite finding ids; ids it invents
are dropped, and years/entities for each theme are derived from the cited ids.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from .llm import LLMClient
from .schemas import FindingRecord, Severity

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "synthesis_system.md").read_text()


class ThemeOutput(BaseModel):
    name: str
    summary: str = Field(description="What keeps going wrong, with agencies, systems and years.")
    why_it_matters: str
    finding_ids: list[str]
    recommendations: list[str]
    audit_procedures: list[str]


class RecurringIssueOutput(BaseModel):
    issue: str
    pattern: str = Field(description="How it recurs across years/agencies and any shared root cause.")
    finding_ids: list[str]


class InsightOutput(BaseModel):
    insight: str
    finding_ids: list[str]


class FocusAreaOutput(BaseModel):
    area: str
    priority: Severity
    rationale: str
    finding_ids: list[str]


class InsightsOutput(BaseModel):
    executive_summary: str
    themes: list[ThemeOutput]
    recurring_issues: list[RecurringIssueOutput]
    key_insights: list[InsightOutput]
    focus_areas: list[FocusAreaOutput]


def compute_stats(findings: list[FindingRecord]) -> dict:
    years = sorted({f.fiscal_year for f in findings})
    by_domain_year: dict[str, Counter] = defaultdict(Counter)
    by_entity: dict[str, dict] = {}
    for f in findings:
        by_domain_year[f.control_domain.value][f.fiscal_year] += 1
        e = by_entity.setdefault(
            f.entity, {"entity": f.entity, "ministry": f.ministry, "years": set(), "count": 0, "domains": Counter()}
        )
        e["years"].add(f.fiscal_year)
        e["count"] += 1
        e["domains"][f.control_domain.value] += 1

    domains = {
        d: {
            "total": sum(c.values()),
            "by_year": {y: c.get(y, 0) for y in years},
            "years_present": sum(1 for y in years if c.get(y)),
            "entities": sorted({f.entity for f in findings if f.control_domain.value == d}),
        }
        for d, c in sorted(by_domain_year.items(), key=lambda kv: -sum(kv[1].values()))
    }
    return {
        "reports": years,
        "total_findings": len(findings),
        "by_year": dict(Counter(f.fiscal_year for f in findings)),
        "by_severity": dict(Counter(f.severity.value for f in findings)),
        "by_verification": dict(Counter(f.verification for f in findings)),
        "domains": domains,
        "recurring_domains": [d for d, v in domains.items() if v["years_present"] >= 2 or len(v["entities"]) >= 2],
        "entities": sorted(
            (
                {**e, "years": sorted(e["years"]), "domains": dict(e["domains"])}
                for e in by_entity.values()
            ),
            key=lambda e: -e["count"],
        ),
        "criteria_breached": Counter(c for f in findings for c in f.criteria_breached).most_common(),
        "systems": sorted({f"{f.system} ({f.entity})" for f in findings if f.system}),
    }


def _compact(f: FindingRecord) -> dict:
    return {
        "id": f.id,
        "year": f.fiscal_year,
        "entity": f.entity,
        "ministry": f.ministry,
        "system": f.system,
        "domain": f.control_domain.value,
        "other_domains": [d.value for d in f.secondary_domains],
        "severity": f.severity.value,
        "issue": f.issue_summary,
        "facts": f.key_facts,
        "root_cause": f.root_cause,
        "criteria_breached": f.criteria_breached,
        "response": f.management_response,
    }


def synthesise(findings: list[FindingRecord], llm: LLMClient) -> dict:
    # Findings whose evidence could not be found in the PDF are kept out of the briefing.
    usable = [f for f in findings if f.verification != "unverified"]
    stats = compute_stats(usable)
    prompt = (
        "## Statistics (computed, authoritative)\n"
        + json.dumps(stats, indent=1, default=str)
        + "\n\n## Findings\n"
        + "\n".join(json.dumps(_compact(f), ensure_ascii=False) for f in usable)
    )
    out = llm.generate(system=SYSTEM_PROMPT, prompt=prompt, schema=InsightsOutput, tag="synthesis")

    by_id = {f.id: f for f in usable}

    def ground(item: BaseModel) -> dict:
        d = item.model_dump(mode="json")
        ids = [i for i in d["finding_ids"] if i in by_id]
        d["finding_ids"] = ids
        d["years"] = sorted({by_id[i].fiscal_year for i in ids})
        d["entities"] = sorted({by_id[i].entity for i in ids})
        return d

    sections = {
        name: [g for g in (ground(x) for x in getattr(out, name)) if g["finding_ids"]]
        for name in ("themes", "recurring_issues", "key_insights", "focus_areas")
    }
    return {
        "executive_summary": out.executive_summary,
        **sections,
        "stats": stats,
        "excluded_unverified": [f.id for f in findings if f.verification == "unverified"],
    }
