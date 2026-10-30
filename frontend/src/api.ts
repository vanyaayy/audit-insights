// Types mirror backend/app/schemas.py and the API responses.

export type Severity = "High" | "Medium" | "Low";
export type Verification = "verified" | "partial" | "unverified";

export interface Evidence {
  pdf_page: number;
  quote: string;
  printed_page: string | null;
  match_score: number;
  verified: boolean;
}

export interface Finding {
  id: string;
  report_id: string;
  fiscal_year: string;
  observation_title: string;
  ministry: string;
  entity: string;
  system: string | null;
  audit_type: string;
  control_domain: string;
  secondary_domains: string[];
  issue_summary: string;
  key_facts: string[];
  root_cause: string | null;
  risk_impact: string;
  cia_impact: string[];
  severity: Severity;
  severity_rationale: string;
  criteria_breached: string[];
  management_response: string | null;
  evidence: Evidence[];
  verification: Verification;
}

export interface Report {
  id: string;
  file_name: string;
  fiscal_year: string;
  page_count: number;
  status: "queued" | "processing" | "done" | "failed";
  progress: string | null;
  error: string | null;
  model: string | null;
  created_at: string;
  processed_at: string | null;
  finding_count: number;
  bookmarks_corrected: number;
}

export interface DomainStats {
  total: number;
  by_year: Record<string, number>;
  years_present: number;
  entities: string[];
}

export interface EntityStats {
  entity: string;
  ministry: string;
  years: string[];
  count: number;
  domains: Record<string, number>;
}

export interface Stats {
  reports: string[];
  total_findings: number;
  by_year: Record<string, number>;
  by_severity: Partial<Record<Severity, number>>;
  by_verification: Partial<Record<Verification, number>>;
  domains: Record<string, DomainStats>;
  recurring_domains: string[];
  entities: EntityStats[];
  criteria_breached: [string, number][];
  systems: string[];
}

interface Grounded {
  finding_ids: string[];
  years: string[];
  entities: string[];
}

export interface Theme extends Grounded {
  name: string;
  summary: string;
  why_it_matters: string;
  recommendations: string[];
  audit_procedures: string[];
}

export interface RecurringIssue extends Grounded {
  issue: string;
  pattern: string;
}

export interface KeyInsight extends Grounded {
  insight: string;
}

export interface FocusArea extends Grounded {
  area: string;
  priority: Severity;
  rationale: string;
}

export interface InsightsData {
  executive_summary: string;
  themes: Theme[];
  recurring_issues: RecurringIssue[];
  key_insights: KeyInsight[];
  focus_areas: FocusArea[];
  stats: Stats;
  excluded_unverified: string[];
  placeholder?: boolean;
}

export interface InsightsRun {
  id: number;
  report_ids: string[];
  status: "queued" | "processing" | "done" | "failed";
  error: string | null;
  data: InsightsData | null;
  created_at: string;
}

export interface AppStatus {
  llm_configured: boolean; // a Gemini key is set, so uploads and regeneration can run
  model: string;
}

export interface UploadResult {
  file: string;
  report_id?: string;
  duplicate?: boolean;
  reason?: string | null; // why it was treated as a duplicate
  same_year?: string[]; // other reports already loaded for the same fiscal year
  overlaps?: { report_id: string; share: number }[]; // existing reports sharing most pages
  error?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<AppStatus>("/api/status"),
  reports: () => request<Report[]>("/api/reports"),
  findings: () => request<Finding[]>("/api/findings"),
  finding: (id: string) => request<Finding>(`/api/findings/${encodeURIComponent(id)}`),
  stats: () => request<Stats>("/api/stats"),
  insights: () => request<{ latest: InsightsRun | null; latest_done: InsightsRun | null }>("/api/insights/latest"),
  generateInsights: (report_ids: string[] = []) =>
    request<{ run_id: number }>("/api/insights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_ids }),
    }),
  upload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<UploadResult[]>("/api/reports", { method: "POST", body: form });
  },
  reprocess: (id: string) => request<{ status: string }>(`/api/reports/${id}/reprocess`, { method: "POST" }),
  remove: (id: string) => request<{ deleted: string }>(`/api/reports/${id}`, { method: "DELETE" }),
};

export const urls = {
  evidenceImage: (findingId: string, index: number) =>
    `/api/findings/${encodeURIComponent(findingId)}/evidence/${index}.png`,
  reportPdf: (reportId: string, page?: number) => `/api/reports/${reportId}/pdf${page ? `#page=${page}` : ""}`,
  findingsCsv: "/api/export/findings.csv",
  briefingPdf: "/api/export/briefing.pdf",
};
