import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, ExternalLink, Quote } from "lucide-react";
import { api, urls, type Finding } from "../api";
import { useFindingParam } from "../lib/useFindingParam";
import { SeverityBadge, Tag, VerificationMark } from "./ui";

export function FindingDrawer() {
  const { findingId, close } = useFindingParam();
  const { data: finding, isLoading } = useQuery({
    queryKey: ["finding", findingId],
    queryFn: () => api.finding(findingId!),
    enabled: !!findingId,
  });

  useEffect(() => {
    if (!findingId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [findingId, close]);

  if (!findingId) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Finding detail">
      <button type="button" className="absolute inset-0 bg-ink/30" onClick={close} aria-label="Close" />
      <div className="relative flex h-full w-full max-w-3xl flex-col bg-panel shadow-2xl">
        <div className="flex items-center justify-between border-b border-line px-6 py-3">
          <span className="font-mono text-xs text-muted">{findingId}</span>
          <button type="button" onClick={close} className="rounded-md p-1.5 text-muted hover:bg-canvas" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {isLoading || !finding ? <p className="text-sm text-muted">Loading…</p> : <FindingDetail f={finding} />}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{children}</dd>
    </div>
  );
}

function FindingDetail({ f }: { f: Finding }) {
  const [active, setActive] = useState(0);
  const ev = f.evidence[active];

  return (
    <article>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={f.severity} />
        <Tag>{f.control_domain}</Tag>
        <Tag>{f.fiscal_year}</Tag>
        <VerificationMark value={f.verification} withLabel />
      </div>
      <h2 className="mt-3 font-serif text-xl font-semibold leading-snug text-ink">{f.issue_summary}</h2>
      <p className="mt-1.5 text-sm text-ink-soft">
        {f.entity}
        {f.entity !== f.ministry && <span className="text-muted"> · {f.ministry}</span>}
        {f.system && <span className="text-muted"> · System: {f.system}</span>}
      </p>
      <p className="mt-1 text-xs text-muted">AGO observation: “{f.observation_title}”</p>

      {f.key_facts.length > 0 && (
        <ul className="mt-5 grid gap-2 sm:grid-cols-2">
          {f.key_facts.map((k) => (
            <li key={k} className="rounded-lg bg-canvas px-3 py-2 text-sm text-ink-soft">{k}</li>
          ))}
        </ul>
      )}

      <dl className="mt-6 grid gap-5 sm:grid-cols-2">
        <Field label="Risk / impact">{f.risk_impact}</Field>
        <Field label="Severity rationale">{f.severity_rationale}</Field>
        <Field label="Root cause">{f.root_cause ?? <span className="text-muted">Not stated in report</span>}</Field>
        <Field label="CIA impact">{f.cia_impact.length ? f.cia_impact.join(", ") : <span className="text-muted">—</span>}</Field>
        <Field label="Management response">{f.management_response ?? <span className="text-muted">Not stated</span>}</Field>
        {f.criteria_breached.length > 0 && (
          <Field label="Criteria not complied with">
            <ul className="list-disc space-y-0.5 pl-4">{f.criteria_breached.map((c) => <li key={c}>{c}</li>)}</ul>
          </Field>
        )}
        <Field label="Classification">
          {f.audit_type}
          {f.secondary_domains.length > 0 && <span className="text-muted"> · also {f.secondary_domains.join(", ")}</span>}
        </Field>
      </dl>

      <section className="mt-8">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Source evidence</h3>
          <a
            className="inline-flex items-center gap-1 text-xs text-brand hover:underline"
            href={urls.reportPdf(f.report_id, ev?.pdf_page)}
            target="_blank"
            rel="noreferrer"
          >
            Open report PDF <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        {f.evidence.length > 1 && (
          <div className="mt-3 flex gap-1.5">
            {f.evidence.map((e, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setActive(i)}
                className={`rounded-md px-2.5 py-1 text-xs ${i === active ? "bg-brand text-white" : "bg-canvas text-ink-soft hover:bg-line"}`}
              >
                Quote {i + 1} · p.{e.printed_page ?? e.pdf_page}
              </button>
            ))}
          </div>
        )}
        {ev && !ev.verified && (
          <div role="alert" className="mt-3 rounded-lg border border-high/30 bg-high-soft px-4 py-3 text-sm text-high">
            <p className="font-semibold">Needs review: this quote was not found in the report</p>
            <p className="mt-1">
              The AI cited it from page {ev.printed_page ?? ev.pdf_page}, but the text there doesn't match
              (best match {ev.match_score}%). The page is shown below without a highlight. Check it before relying on
              this finding.{f.verification === "unverified" ? " Until then it is left out of the dashboard counts and the briefing." : ""}
            </p>
          </div>
        )}
        {ev && (
          <>
            <blockquote className="mt-3 flex gap-2 rounded-lg border-l-4 border-brand bg-brand-soft/50 px-4 py-3 text-sm italic text-ink">
              <Quote className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden />
              <span>
                {ev.quote}
                <span className="ml-2 not-italic text-xs text-muted">
                  — {f.fiscal_year} report, printed page {ev.printed_page ?? "?"} (PDF page {ev.pdf_page}) ·{" "}
                  {ev.verified ? `matched ${ev.match_score}%` : "not found in source"}
                </span>
              </span>
            </blockquote>
            <img
              key={`${f.id}-${active}`}
              src={urls.evidenceImage(f.id, active)}
              alt={`Report page ${ev.printed_page ?? ev.pdf_page} with the quote highlighted`}
              className="mt-3 w-full rounded-lg border border-line"
              loading="lazy"
            />
          </>
        )}
      </section>
    </article>
  );
}

