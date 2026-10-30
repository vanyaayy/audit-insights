import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, ChevronRight, Download, FileSpreadsheet } from "lucide-react";
import { api, urls, type Finding } from "../api";
import { Heatmap } from "../components/Heatmap";
import {
  Button, Card, CardHeader, Empty, ErrorNote, LinkButton, Loading, PageHeader, Section, ViewCue, focusRing,
} from "../components/ui";
import { SEVERITIES, severityFill, shortEntity, shortYear } from "../lib/format";
import { PlaceholderNotice } from "./Insights";

const SYSTEMS_SHOWN = 8;
const MAX_YEARS_SIDE_BY_SIDE = 6;

function Kpi({ label, value, hint, to }: { label: string; value: string | number; hint?: string; to?: string }) {
  const body = (
    <>
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      <div className="mt-1 flex items-center justify-between gap-2">
        {hint && <p className="text-xs text-muted">{hint}</p>}
        {to && (
          <span className="inline-flex items-center gap-0.5 text-xs font-medium text-brand">
            View <ChevronRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" aria-hidden />
          </span>
        )}
      </div>
    </>
  );
  const base = "block rounded-xl border bg-panel px-5 py-4 shadow-[0_1px_2px_rgba(15,27,45,0.04)]";
  return to ? (
    <Link to={to} className={`group ${base} border-line transition hover:border-brand/40 hover:shadow-md ${focusRing}`}>{body}</Link>
  ) : (
    <div className={`${base} border-line`}>{body}</div>
  );
}

export function Overview() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const findings = useQuery({ queryKey: ["findings"], queryFn: api.findings });
  const insights = useQuery({ queryKey: ["insights"], queryFn: api.insights });

  const bySeverityYear = useMemo(() => severityByYear(findings.data ?? []), [findings.data]);
  const systems = useMemo(() => systemsInvolved(findings.data ?? []), [findings.data]);
  const [allSystems, setAllSystems] = useState(false);

  if (stats.isLoading) return <Loading />;
  if (stats.error) return <ErrorNote error={stats.error} />;
  const s = stats.data!;
  if (!s.total_findings) {
    return (
      <>
        <PageHeader title="Overview" />
        <Empty title="No findings yet">
          Upload AGO reports on the <Link className="text-brand underline" to="/reports">Reports</Link> page to begin.
        </Empty>
      </>
    );
  }

  const high = s.by_severity.High ?? 0;
  const recurring = s.recurring_domains.filter((d) => s.domains[d].years_present >= 2).length;
  const ministries = new Set(s.entities.map((e) => e.ministry)).size;
  // Side by side suits a handful of years; beyond that both charts need full width.
  const manyYears = s.reports.length > MAX_YEARS_SIDE_BY_SIDE;
  // Stats leave out findings whose quotes weren't found; count them from the full list.
  const needsReview = (findings.data ?? []).filter((f) => f.verification !== "verified").length;
  const briefing = insights.data?.latest_done?.data;

  return (
    <>
      <PageHeader
        title="IT controls across AGO reports"
        actions={
          <>
            <Button href={urls.findingsCsv} download><FileSpreadsheet className="h-4 w-4" /> Export findings (CSV)</Button>
            <Button href={urls.briefingPdf} download variant="primary"><Download className="h-4 w-4" /> Download briefing</Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="IT findings" value={s.total_findings} hint={`from ${s.reports.length} reports`} to="/findings" />
        <Kpi label="High severity" value={high} hint={`${Math.round((high / s.total_findings) * 100)}% of findings`} to="/findings?severity=High" />
        <Kpi label="Recurring control areas" value={recurring} hint="in 2+ report years" to="/insights#recurring" />
        <Kpi label="Entities affected" value={s.entities.length} hint={`across ${ministries} ministries`} />
        {needsReview ? (
          <Kpi label="Needs review" value={needsReview} hint="quotes not found in the report" to="/findings?verification=review" />
        ) : (
          <Kpi label="Needs review" value={0} hint="every finding traced to its source page" />
        )}
      </div>

      {briefing && (
        <Section
          title="Executive summary"
          action={<LinkButton to="/insights" size="sm">Open full briefing <ArrowRight className="h-3.5 w-3.5" /></LinkButton>}
        >
          <Card className="px-6 py-5">
            {briefing.placeholder && <PlaceholderNotice compact />}
            <p className="font-serif text-[15px] leading-relaxed text-ink">{briefing.executive_summary}</p>
          </Card>
        </Section>
      )}

      <Section title="Patterns across reports">
        <div className={`grid gap-6 ${manyYears ? "" : "lg:grid-cols-5"}`}>
          <Card className={`min-w-0 ${manyYears ? "" : "lg:col-span-3"}`}>
            <CardHeader title="Findings by control area and year" />
            <div className="p-3"><Heatmap stats={s} /></div>
          </Card>
          <Card className={`flex min-w-0 flex-col ${manyYears ? "" : "lg:col-span-2"}`}>
            <CardHeader title="Severity by report year" />
            <div className={`${manyYears ? "h-72" : "min-h-72 flex-1"} px-2 py-4`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bySeverityYear} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid vertical={false} stroke="#e3e8ef" />
                  <XAxis
                    dataKey="year"
                    interval={manyYears ? "preserveStartEnd" : 0}
                    minTickGap={6}
                    tickFormatter={(y: string) => (manyYears ? y.replace(/^FY/, "") : y)}
                    tick={{ fontSize: manyYears ? 11 : 12, fill: "#6b7a8f" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#6b7a8f" }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: "#f6f7f9" }} contentStyle={{ borderRadius: 8, borderColor: "#e3e8ef", fontSize: 12 }} />
                  {SEVERITIES.map((sev) => (
                    <Bar key={sev} dataKey={sev} stackId="s" fill={severityFill[sev]} maxBarSize={44} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-4 border-t border-line px-5 py-3 text-xs text-ink-soft">
              {SEVERITIES.map((sev) => (
                <span key={sev} className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: severityFill[sev] }} aria-hidden />
                  {sev}
                </span>
              ))}
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Who is affected">
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Most affected entities" />
            <ul className="divide-y divide-line">
              {s.entities.slice(0, 8).map((e) => (
                <li key={e.entity}>
                  <Link
                    to={`/findings?entity=${encodeURIComponent(e.entity)}`}
                    className={`group flex items-center gap-4 px-5 py-3 transition hover:bg-brand-soft/40 ${focusRing}`}
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-canvas text-sm font-semibold text-ink ring-1 ring-inset ring-line">
                      {e.count}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{shortEntity(e.entity)}</p>
                      <p className="truncate text-xs text-muted">
                        {yearSpan(e.years)} · {Object.keys(e.domains).join(" · ")}
                      </p>
                    </div>
                    <ViewCue />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title="IT systems involved" />
            {systems.length ? (
              <div className="flex flex-wrap gap-2 p-4">
                {(allSystems ? systems : systems.slice(0, SYSTEMS_SHOWN)).map((x) => (
                  <Link
                    key={`${x.system}-${x.entity}`}
                    to={`/findings?entity=${encodeURIComponent(x.entity)}&q=${encodeURIComponent(x.system)}`}
                    className={`inline-flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs shadow-sm transition hover:border-brand/40 hover:bg-brand-soft ${focusRing}`}
                  >
                    <span className="font-medium text-ink">{x.system}</span>
                    <span className="text-muted">{shortEntity(x.entity)}</span>
                    <span className="rounded bg-canvas px-1.5 font-semibold text-ink-soft ring-1 ring-inset ring-line">{x.count}</span>
                  </Link>
                ))}
                {systems.length > SYSTEMS_SHOWN && (
                  <Button size="sm" variant="ghost" onClick={() => setAllSystems((v) => !v)}>
                    {allSystems ? "Show fewer" : `Show all ${systems.length}`}
                  </Button>
                )}
              </div>
            ) : (
              <p className="px-5 py-6 text-sm text-muted">No systems named.</p>
            )}
          </Card>
          <Card>
            <CardHeader title="Policies most often not complied with" />
            {s.criteria_breached.length ? (
              <ul className="divide-y divide-line">
                {s.criteria_breached.slice(0, 8).map(([c, n]) => (
                  <li key={c} className="flex items-center gap-4 px-5 py-3">
                    <p className="min-w-0 flex-1 text-sm text-ink">{c}</p>
                    <span className="text-xs text-muted">{n} {n === 1 ? "finding" : "findings"}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-6 text-sm text-muted">No policies cited.</p>
            )}
          </Card>
          </div>
        </div>
      </Section>
    </>
  );
}

function severityByYear(findings: Finding[]) {
  const rows = new Map<string, Record<string, number | string>>();
  for (const f of findings) {
    if (f.verification === "unverified") continue;
    const row = rows.get(f.fiscal_year) ?? { year: shortYear(f.fiscal_year), High: 0, Medium: 0, Low: 0 };
    row[f.severity] = (row[f.severity] as number) + 1;
    rows.set(f.fiscal_year, row);
  }
  return [...rows.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, r]) => r);
}

/** Named IT systems with their entity and number of findings, most frequent first.
 * A finding can name several systems ("SSNet, CMS"). */
function systemsInvolved(findings: Finding[]) {
  const counts = new Map<string, { system: string; entity: string; count: number }>();
  for (const f of findings) {
    if (!f.system || f.verification === "unverified") continue;
    for (const system of f.system.split(/,\s*/).map((x) => x.trim()).filter(Boolean)) {
      const key = `${system}|${f.entity}`;
      const row = counts.get(key) ?? { system, entity: f.entity, count: 0 };
      row.count += 1;
      counts.set(key, row);
    }
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.system.localeCompare(b.system));
}

/** "FY21/22, FY23/24" for a few years; "FY06/07–FY25/26 · 12 years" once the list gets long. */
function yearSpan(years: string[]): string {
  const sorted = [...years].sort();
  if (sorted.length <= 3) return sorted.map(shortYear).join(", ");
  return `${shortYear(sorted[0])}–${shortYear(sorted[sorted.length - 1])} · ${sorted.length} years`;
}
