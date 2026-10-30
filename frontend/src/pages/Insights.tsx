import { useEffect, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FlaskConical, ListChecks, RefreshCw, Wrench } from "lucide-react";
import { api, urls, type Finding } from "../api";
import { Button, Card, Empty, ErrorNote, Loading, PageHeader, Section, SeverityBadge, SourceChip, Tag } from "../components/ui";
import { shortEntity, shortYear } from "../lib/format";
import { useFindingParam } from "../lib/useFindingParam";
import { useCanProcess } from "../lib/useCanProcess";

export function PlaceholderNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`flex items-start gap-2 rounded-lg border border-medium/30 bg-medium-soft px-3 py-2 text-xs text-medium ${compact ? "mb-3" : "mb-6"}`}>
      <FlaskConical className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        Sample briefing, written by hand over the real extracted findings for interface development.
        Use <strong>Regenerate</strong> on the Insights page to have Gemini write it.
      </span>
    </div>
  );
}

/** Citations: each opens the finding it refers to. */
function Sources({ ids, findings, stacked = false }: { ids: string[]; findings: Map<string, Finding>; stacked?: boolean }) {
  const { open } = useFindingParam();
  const items = ids.map((id) => findings.get(id)).filter((f): f is Finding => !!f);
  if (!items.length) return null;
  return (
    <div className="border-t border-line pt-3">
      <p className="mb-2 text-xs font-medium text-muted" title="Select a source to see its evidence">Sources ({items.length})</p>
      <div className={stacked ? "flex flex-col gap-1.5" : "flex flex-wrap gap-1.5"}>
        {items.map((f) => {
          const page = f.evidence[0]?.printed_page;
          return (
            <SourceChip
              key={f.id}
              block={stacked}
              onClick={() => open(f.id)}
              title={f.issue_summary}
              label={`${shortEntity(f.entity)} · ${shortYear(f.fiscal_year)}${page ? ` · p.${page}` : ""}`}
            />
          );
        })}
      </div>
    </div>
  );
}

export function Insights() {
  const qc = useQueryClient();
  const { hash } = useLocation();
  const insights = useQuery({
    queryKey: ["insights"],
    queryFn: api.insights,
    refetchInterval: (q) => (["queued", "processing"].includes(q.state.data?.latest?.status ?? "") ? 3000 : false),
  });
  const findingsQ = useQuery({ queryKey: ["findings"], queryFn: api.findings });
  const findings = useMemo(() => new Map((findingsQ.data ?? []).map((f) => [f.id, f])), [findingsQ.data]);

  const generate = useMutation({
    mutationFn: () => api.generateInsights(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["insights"] }),
  });

  const data = insights.data?.latest_done?.data;
  const canProcess = useCanProcess();

  // Links like /insights#recurring land on the section once it has rendered.
  useEffect(() => {
    // Wait for findings too: they fill in the source lists and shift the layout.
    if (hash && data && findingsQ.data) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash, data, findingsQ.data]);

  if (insights.isLoading) return <Loading />;
  if (insights.error) return <ErrorNote error={insights.error} />;

  const latest = insights.data?.latest;
  const running = latest && ["queued", "processing"].includes(latest.status);
  const failedSinceDone = latest?.status === "failed" && latest.id !== insights.data?.latest_done?.id;

  const onRegenerate = () => {
    if (window.confirm("Regenerate the briefing with Gemini? This makes one API call over all extracted findings.")) {
      generate.mutate();
    }
  };

  const toc = data
    ? [
        { id: "summary", label: "Executive summary" },
        { id: "focus", label: "Focus areas", n: data.focus_areas.length },
        { id: "themes", label: "Themes", n: data.themes.length },
        { id: "recurring", label: "Recurring issues", n: data.recurring_issues.length },
        { id: "insights", label: "Key insights", n: data.key_insights.length },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Cross-report briefing"
        actions={
          <>
            <Button
              onClick={onRegenerate}
              disabled={!canProcess || !!running || generate.isPending}
              title={canProcess ? undefined : "Regenerating needs a Gemini API key in backend/.env (see README)"}
            >
              <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} /> {running ? "Generating…" : "Regenerate"}
            </Button>
            {data && <Button href={urls.briefingPdf} download variant="primary"><Download className="h-4 w-4" /> Download briefing</Button>}
          </>
        }
      />

      {!canProcess && data && (
        <p className="-mt-4 mb-6 text-xs text-muted">
          Prepared in advance with Gemini. Regenerating needs a Gemini API key in backend/.env (see README).
        </p>
      )}

      {failedSinceDone && (
        <div role="alert" className="mb-6 rounded-lg border border-high/30 bg-high-soft px-4 py-3 text-sm text-high">
          <p>
            <strong>The last regeneration didn't complete</strong>, so the previous briefing is shown.
            {/quota|429/i.test(latest!.error ?? "") ? " The Gemini quota was used up." : /503|demand|timed out/i.test(latest!.error ?? "") ? " Gemini was busy; try again in a few minutes." : ""}
          </p>
          <details className="mt-1 text-xs">
            <summary className="cursor-pointer select-none">Technical details</summary>
            <p className="mt-1 break-words font-mono">{latest!.error}</p>
          </details>
        </div>
      )}

      {!data ? (
        <Empty title="No briefing yet">Process at least one report, then select Regenerate.</Empty>
      ) : (
        <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-10">
          <div className="min-w-0">
            {data.placeholder && <PlaceholderNotice />}

            <Section id="summary" title="Executive summary">
              <Card className="px-6 py-5">
                <p className="font-serif text-[17px] leading-relaxed text-ink">{data.executive_summary}</p>
                <p className="mt-3 text-xs text-muted">
                  Based on {data.stats.total_findings} verified findings from {data.stats.reports.map(shortYear).join(", ")}
                </p>
              </Card>
            </Section>

            <Section id="focus" title="Focus areas for the next audit cycle">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {data.focus_areas.map((a) => (
                  <Card key={a.area} className="flex flex-col gap-3 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="font-semibold leading-snug text-ink">{a.area}</h3>
                      <SeverityBadge severity={a.priority} />
                    </div>
                    <p className="flex-1 text-sm text-ink-soft">{a.rationale}</p>
                    <Sources ids={a.finding_ids} findings={findings} stacked />
                  </Card>
                ))}
              </div>
            </Section>

            <Section id="themes" title="Themes">
              <div className="space-y-5">
                {data.themes.map((t, i) => (
                  <Card key={t.name} className="overflow-hidden">
                    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-canvas/60 px-6 py-3.5">
                      <h3 className="flex items-center gap-3 font-serif text-lg font-semibold text-ink">
                        <span className="grid h-7 w-7 place-items-center rounded-full bg-brand text-xs font-semibold text-white">{i + 1}</span>
                        {t.name}
                      </h3>
                      <div className="flex flex-wrap gap-1.5">
                        <Tag>{t.finding_ids.length} findings</Tag>
                        <Tag>{t.entities.length} entities</Tag>
                        <Tag>{t.years.map(shortYear).join(", ")}</Tag>
                      </div>
                    </header>
                    <div className="space-y-4 px-6 py-5">
                      <p className="text-sm leading-relaxed text-ink">{t.summary}</p>
                      <p className="text-sm text-ink-soft"><span className="font-medium text-ink">Why it matters: </span>{t.why_it_matters}</p>
                      <div className="grid gap-4 md:grid-cols-2">
                        {t.recommendations.length > 0 && (
                          <div className="rounded-lg border border-line p-4">
                            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-soft"><Wrench className="h-3.5 w-3.5" aria-hidden /> Recommendations for agencies</p>
                            <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-ink">{t.recommendations.map((r) => <li key={r}>{r}</li>)}</ul>
                          </div>
                        )}
                        {t.audit_procedures.length > 0 && (
                          <div className="rounded-lg border border-brand/20 bg-brand-soft/50 p-4">
                            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand"><ListChecks className="h-3.5 w-3.5" aria-hidden /> Suggested audit procedures</p>
                            <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-ink">{t.audit_procedures.map((p) => <li key={p}>{p}</li>)}</ul>
                          </div>
                        )}
                      </div>
                      <Sources ids={t.finding_ids} findings={findings} />
                    </div>
                  </Card>
                ))}
              </div>
            </Section>

            <Section id="recurring" title="Recurring issues">
              <div className="grid gap-4 md:grid-cols-2">
                {data.recurring_issues.map((r) => (
                  <Card key={r.issue} className="flex flex-col gap-2 p-5">
                    <h3 className="font-semibold text-ink">{r.issue}</h3>
                    <p className="flex-1 text-sm text-ink-soft">{r.pattern}</p>
                    <Sources ids={r.finding_ids} findings={findings} stacked />
                  </Card>
                ))}
              </div>
            </Section>

            <Section id="insights" title="Key insights">
              <div className="grid gap-4 md:grid-cols-2">
                {data.key_insights.map((k) => (
                  <Card key={k.insight} className="flex flex-col gap-3 p-5">
                    <p className="flex-1 text-sm text-ink">{k.insight}</p>
                    <Sources ids={k.finding_ids} findings={findings} stacked />
                  </Card>
                ))}
              </div>
            </Section>
          </div>

          <nav aria-label="On this page" className="hidden lg:block">
            <div className="sticky top-8">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">On this page</p>
              <ul className="space-y-0.5 border-l border-line">
                {toc.map((t) => (
                  <li key={t.id}>
                    <a href={`#${t.id}`} className="-ml-px flex items-center justify-between border-l-2 border-transparent py-1.5 pl-3 pr-1 text-sm text-ink-soft transition hover:border-brand hover:text-brand">
                      {t.label}
                      {t.n !== undefined && <span className="text-xs text-muted">{t.n}</span>}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
        </div>
      )}
    </>
  );
}
