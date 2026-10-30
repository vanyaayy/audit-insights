import type { Finding } from "../api";

export function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: "fy2024_25-02", report_id: "fy2024_25", fiscal_year: "FY2024/25",
    observation_title: "Weaknesses in Management of Most Privileged Operating System Account",
    ministry: "Ministry of Manpower", entity: "Ministry of Manpower", system: "WINS-EP",
    audit_type: "IT general controls", control_domain: "Privileged access management", secondary_domains: [],
    issue_summary: "A sudo command let 24 staff change the root password.", key_facts: ["24 staff"],
    root_cause: null, risk_impact: "Full root access", cia_impact: ["Availability"], severity: "High",
    severity_rationale: "Unrestricted root", criteria_breached: [], management_response: "Remediated",
    evidence: [{ pdf_page: 34, quote: "This command could be used by 24 MOM IT staff.", printed_page: "24", match_score: 100, verified: true }],
    verification: "verified",
    ...overrides,
  };
}

export const FINDINGS: Finding[] = [
  finding(),
  finding({
    id: "fy2022_23-07", report_id: "fy2022_23", fiscal_year: "FY2022/23", entity: "People's Association",
    ministry: "Ministry of Culture, Community and Youth", system: null, severity: "Medium",
    control_domain: "Account provisioning and removal", issue_summary: "Accounts of leavers were not removed.",
  }),
  finding({
    id: "fy2023_24-09", report_id: "fy2023_24", fiscal_year: "FY2023/24", entity: "Early Childhood Development Agency",
    ministry: "Ministry of Social and Family Development", system: "CMS", severity: "High",
    control_domain: "Application controls and system validation", issue_summary: "System errors in subsidy computation.",
    verification: "unverified",
    evidence: [{ pdf_page: 92, quote: "Made-up quote.", printed_page: "80", match_score: 41, verified: false }],
  }),
];
