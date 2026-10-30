import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileSpreadsheet, Search, X } from "lucide-react";
import { api, urls, type Finding } from "../api";
import { Button, Card, Empty, ErrorNote, Loading, PageHeader, SeverityBadge, VerificationMark, ViewCue, focusRing } from "../components/ui";
import { SEVERITIES, shortEntity, shortYear } from "../lib/format";
import { useFindingParam } from "../lib/useFindingParam";

const FILTERS = [
  { key: "year", label: "Report year", all: "All years" },
  { key: "entity", label: "Entity", all: "All entities" },
  { key: "domain", label: "Control area", all: "All control areas" },
  { key: "severity", label: "Severity", all: "All severities" },
  { key: "verification", label: "Source check", all: "Any" },
] as const;
type FilterKey = (typeof FILTERS)[number]["key"];

const severityRank = { High: 0, Medium: 1, Low: 2 };

const checkLabels: Record<string, string> = { verified: "Traced to source", review: "Needs review" };

function optionLabel(key: FilterKey, value: string): string {
  if (key === "entity") return shortEntity(value);
  if (key === "verification") return checkLabels[value] ?? value;
  return value;
}

function valueOf(f: Finding, key: FilterKey): string {
  return {
    year: f.fiscal_year,
    entity: f.entity,
    domain: f.control_domain,
    severity: f.severity,
    // Partly and fully unverified findings both need a person to check them.
    verification: f.verification === "verified" ? "verified" : "review",
  }[key];
}

const fieldCls = `w-full rounded-lg border bg-panel px-2.5 py-2 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15`;

export function Findings() {
  const { data, isLoading, error } = useQuery({ queryKey: ["findings"], queryFn: api.findings });
  const [params, setParams] = useSearchParams();
  const { open } = useFindingParam();
  const q = params.get("q") ?? "";

  const setParam = (key: string, value: string) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });

  const all = data ?? [];
  const options = useMemo(() => {
    const o = {} as Record<FilterKey, string[]>;
    for (const { key } of FILTERS) o[key] = [...new Set(all.map((f) => valueOf(f, key)))].sort();
    o.severity = SEVERITIES.filter((s) => o.severity.includes(s));
    return o;
  }, [all]);

  const rows = useMemo(() => {
    const needle = q.toLowerCase();
    return all
      .filter((f) => FILTERS.every(({ key }) => !params.get(key) || valueOf(f, key) === params.get(key)))
      .filter((f) => !needle || JSON.stringify(f).toLowerCase().includes(needle))
      .sort((a, b) => severityRank[a.severity] - severityRank[b.severity] || b.fiscal_year.localeCompare(a.fiscal_year));
  }, [all, params, q]);

  const active = FILTERS.filter(({ key }) => params.get(key));
  const needsReview = all.filter((f) => f.verification !== "verified").length;
  const exportQuery = new URLSearchParams();
  active.forEach(({ key }) => exportQuery.set(key, params.get(key)!));
  if (q) exportQuery.set("q", q);
  const filtered = active.length > 0 || !!q;

  if (isLoading) return <Loading />;
  if (error) return <ErrorNote error={error} />;

  return (
    <>
      <PageHeader
        title="Findings register"
      />

      <Card className="mb-5">
        <div className="grid grid-cols-2 gap-3 p-4 lg:grid-cols-5">
          <label className="col-span-2 lg:col-span-5">
            <span className="mb-1 block text-xs font-medium text-muted">Search</span>
            <span className="relative block">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted" aria-hidden />
              <input
                type="search"
                value={q}
                onChange={(e) => setParam("q", e.target.value)}
                placeholder="Systems, agencies, quotes…"
                className={`${fieldCls} border-line pl-8`}
              />
            </span>
          </label>
          {FILTERS.map(({ key, label, all: allLabel }) => (
            <label key={key}>
              <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
              <select
                value={params.get(key) ?? ""}
                onChange={(e) => setParam(key, e.target.value)}
                className={`${fieldCls} ${params.get(key) ? "border-brand text-brand" : "border-line text-ink"}`}
              >
                <option value="">{allLabel}</option>
                {options[key].map((v) => (
                  <option key={v} value={v}>{optionLabel(key, v)}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
        {filtered && (
          <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
            <span className="text-xs text-muted">Active filters:</span>
            {active.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setParam(key, "")}
                className={`inline-flex items-center gap-1 rounded-md bg-brand-soft px-2 py-1 text-xs text-brand transition hover:bg-brand hover:text-white ${focusRing}`}
                aria-label={`Remove ${label} filter`}
              >
                {label}: {optionLabel(key, params.get(key)!)}
                <X className="h-3 w-3" aria-hidden />
              </button>
            ))}
            {q && (
              <button type="button" onClick={() => setParam("q", "")} className={`inline-flex items-center gap-1 rounded-md bg-brand-soft px-2 py-1 text-xs text-brand transition hover:bg-brand hover:text-white ${focusRing}`}>
                “{q}” <X className="h-3 w-3" aria-hidden />
              </button>
            )}
            <Button size="sm" variant="ghost" onClick={() => setParams(new URLSearchParams())}>Clear all</Button>
          </div>
        )}
      </Card>

      {needsReview > 0 && params.get("verification") !== "review" && (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-high/30 bg-high-soft px-4 py-3">
          <p className="text-sm text-high">
            <strong>{needsReview} {needsReview === 1 ? "finding needs" : "findings need"} review.</strong>{" "}
            Some quoted evidence was not found in the report text. Unverified findings are left out of the dashboard and briefing; partly verified ones are counted but should be checked.
          </p>
          <Button size="sm" variant="danger" onClick={() => setParam("verification", "review")}>Show them</Button>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-soft">
          Showing <span className="font-semibold text-ink">{rows.length}</span> of {all.length} findings
        </p>
        <Button size="sm" href={`${urls.findingsCsv}?${exportQuery}`} download>
          <FileSpreadsheet className="h-3.5 w-3.5" /> Export {filtered ? "these" : "all"} to CSV
        </Button>
      </div>

      {rows.length === 0 ? (
        <Empty title="No findings match these filters">Try removing a filter.</Empty>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-canvas text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Severity</th>
                  <th className="px-4 py-2.5 font-medium">Finding</th>
                  <th className="px-4 py-2.5 font-medium">Entity / system</th>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Control area</th>
                  <th className="px-4 py-2.5 font-medium">Report</th>
                  <th className="px-4 py-2.5 font-medium"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((f) => (
                  <tr key={f.id} className="group cursor-pointer align-top transition-colors hover:bg-brand-soft/40" onClick={() => open(f.id)}>
                    <td className="px-4 py-3.5"><SeverityBadge severity={f.severity} /></td>
                    <td className="max-w-md px-4 py-3.5">
                      <p className="font-medium text-ink">{f.issue_summary}</p>
                      <p className="mt-1 truncate text-xs text-muted" title={f.observation_title}>AGO: {f.observation_title}</p>
                    </td>
                    <td className="px-4 py-3.5">
                      <p className="text-ink">{shortEntity(f.entity)}</p>
                      {f.system && <p className="mt-0.5 text-xs text-muted">{f.system}</p>}
                    </td>
                    <td className="hidden px-4 py-3.5 text-ink-soft lg:table-cell">{f.control_domain}</td>
                    <td className="whitespace-nowrap px-4 py-3.5">
                      <p className="text-ink-soft">{shortYear(f.fiscal_year)}</p>
                      <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted">
                        <VerificationMark value={f.verification} /> p.{f.evidence[0]?.printed_page ?? f.evidence[0]?.pdf_page}
                      </p>
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        type="button"
                        className={`rounded-md ${focusRing}`}
                        onClick={(e) => { e.stopPropagation(); open(f.id); }}
                        aria-label={`Open finding ${f.id}`}
                      >
                        <ViewCue label="Details" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
