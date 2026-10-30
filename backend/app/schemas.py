"""Data contracts. Classes ending in *Output are sent to Gemini as response schemas;
the *Record classes add fields that our own code fills in (ids, verification)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ControlDomain(str, Enum):
    ACCOUNT_LIFECYCLE = "Account provisioning and removal"
    PRIVILEGED_ACCESS = "Privileged access management"
    ACCESS_REVIEW = "Periodic access review"
    LEAST_PRIVILEGE = "Excessive access and segregation of duties"
    LOGGING_MONITORING = "Logging and monitoring of activities"
    SECURITY_CONFIG = "Security configuration and settings"
    DATA_PROTECTION = "Data protection and encryption"
    APPLICATION_CONTROLS = "Application controls and system validation"
    CHANGE_MANAGEMENT = "Change management"
    VENDOR_OVERSIGHT = "IT vendor oversight"
    OTHER = "Other IT control"


class AuditType(str, Enum):
    ITGC = "IT general controls"
    APPLICATION = "IT application controls"
    OTHER = "Other technology-related"


class Severity(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class CIA(str, Enum):
    CONFIDENTIALITY = "Confidentiality"
    INTEGRITY = "Integrity"
    AVAILABILITY = "Availability"


class Evidence(BaseModel):
    pdf_page: int = Field(description="The 'PDF page' number from the page label the quote was copied from.")
    quote: str = Field(description="Exact sentence copied verbatim from that page, 10-40 words. No paraphrasing or ellipses.")


class FindingOutput(BaseModel):
    observation_title: str = Field(description="AGO's heading for the observation this finding sits under.")
    ministry: str = Field(description="Supervising ministry, e.g. 'Ministry of Manpower'.")
    entity: str = Field(description="Audited entity, e.g. 'Public Service Division'. Same as ministry if audited directly.")
    system: str | None = Field(description="Named IT system, e.g. 'HRP', 'SSNet'. Null if none is named.")
    audit_type: AuditType
    control_domain: ControlDomain = Field(description="Primary control area that failed.")
    secondary_domains: list[ControlDomain] = Field(description="Other control areas involved, if any.")
    issue_summary: str = Field(description="One or two specific sentences on what control failed.")
    key_facts: list[str] = Field(description="Concrete facts stated by AGO: counts, durations, periods, scale.")
    root_cause: str | None = Field(description="Cause as stated in the report. Null if not stated; do not speculate.")
    risk_impact: str = Field(description="Risk or impact as described by AGO.")
    cia_impact: list[CIA]
    severity: Severity
    severity_rationale: str = Field(description="One sentence justifying the severity using the rubric.")
    criteria_breached: list[str] = Field(description="Policies or standards cited as not complied with, e.g. 'Government Instruction Manual on ICT and Smart Systems Management'.")
    management_response: str | None = Field(description="What the agency said it did or will do.")
    evidence: list[Evidence] = Field(description="1-3 verbatim quotes that support this finding.")


class ExtractionOutput(BaseModel):
    findings: list[FindingOutput]


class EvidenceRecord(Evidence):
    printed_page: str | None = None
    match_score: float = 0.0
    verified: bool = False


class FindingRecord(FindingOutput):
    id: str  # e.g. "fy2023_24-07"
    report_id: str
    fiscal_year: str
    evidence: list[EvidenceRecord]
    verification: str = "unverified"  # verified | partial | unverified
