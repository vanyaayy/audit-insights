import type { Severity } from "../api";

export const SEVERITIES: Severity[] = ["High", "Medium", "Low"];

export const severityClass: Record<Severity, string> = {
  High: "bg-high-soft text-high ring-high/20",
  Medium: "bg-medium-soft text-medium ring-medium/20",
  Low: "bg-low-soft text-low ring-low/20",
};

export const severityFill: Record<Severity, string> = {
  High: "#b42318",
  Medium: "#e48a2a",
  Low: "#98a2b3",
};

/** "FY2023/24" -> "FY23/24" */
export function shortYear(fy: string): string {
  const m = fy.match(/^FY(\d{2})(\d{2})\/(\d{2})$/);
  return m ? `FY${m[2]}/${m[3]}` : fy;
}

/** Long agency names read badly in tables; keep the part before any bracket. */
export function shortEntity(name: string): string {
  return name.replace(/\s*\(.*\)\s*$/, "");
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}
