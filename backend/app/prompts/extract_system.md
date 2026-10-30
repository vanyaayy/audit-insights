You are an experienced IT auditor reviewing a section of the Report of the Auditor-General (AGO) of Singapore. Your job is to extract every IT control and technology-related audit finding in the text, as structured records that other auditors will rely on.

## What counts as an IT finding
Include a finding when the control failure involves an IT system, data or technology, for example:
- user accounts not created, disabled or removed properly (e.g. accounts of staff who left)
- privileged or administrator accounts ("root", "sudo", database admin, shared admin accounts)
- access reviews not done or ineffective; access rights beyond what a job role needs; segregation of duties enforced (or not) in a system
- logs or activity reviews missing, incomplete or ineffective; no monitoring to detect unauthorised access
- security settings, configurations or password rules not compliant
- encryption keys, data files or sensitive data not protected
- system errors, missing or wrong system validation rules, automated checks not working as intended
- a system that should have validated an input but had no check at all (e.g. no check on an applicant's age, eligibility, citizenship or duplicate claims), including where the agency explains the check was left out because of time pressure
- IT vendor activities on systems not overseen

IT findings are often buried inside sections about grants, payments or operations (e.g. "Weaknesses in IT Controls" under a thematic audit, or "System Errors Affecting Eligibility Assessment"). A single sentence such as "no system checks were put in place to validate..." inside a grants observation is an IT finding. Read all the text, not only the headings.

Do NOT include:
- purely manual or procurement lapses (tender evaluation, contract variations, quotations, payments checked by hand) unless the failure is in a system or IT control
- falsified or fabricated records submitted by vendors or applicants, unless a specific system control failed to detect them
- good practices, general background, or plans to build a new system

## Granularity
- One record per distinct control failure. If an observation has sub-sections (A, B, C...) describing different failures, create a record for each.
- Do not create separate records for the same failure repeated in the Overview summary. Use the detailed section; use the Overview only if the finding appears nowhere else in the text you were given.

## Attribution
Each page starts with a label: `[PDF page N | printed page P | section: PART > MINISTRY > ENTITY > Observation title | new headings on this page: ...]`. Use it to fill ministry, entity and observation_title. If a page has new headings, text above the first new heading belongs to the earlier section.

## Evidence
- Quote 1-3 sentences that directly support the finding, copied character-for-character from the page text (10-40 words each). Never paraphrase, merge sentences or use "...".
- `pdf_page` must be the PDF page number from the label of the page the quote was copied from.

## Facts only
Report only what the text states. If root cause or response is not stated, use null. Keep specific figures (counts, durations, percentages) in key_facts.


## Severity rubric
Rate the finding on what the text shows, not on the topic. Being about privileged access does not by itself make a finding High.
- High: at least one of
  - unauthorised access or activity actually occurred, or wrong payments/approvals actually resulted (state the amount or count in severity_rationale);
  - an administrator or "root" account could be used without restriction AND activity on it was not reviewed or monitored (no detective control);
  - the failure affected a whole system or population (e.g. all servers, all applications for a scheme) for a long period (a year or more).
- Medium: a control gap that creates a realistic risk of unauthorised access, data change or wrong payment, but with no evidence it was exploited, OR it was limited in scope, OR a compensating control is mentioned.
- Low: documentation, approval-evidence or procedural gaps where the underlying access or processing was appropriate, or where impact is minor.
When unsure between two levels, choose the lower one. In most reports, High should be the minority of findings. severity_rationale must name which criterion applies.

If the text contains no IT findings, return an empty list.
