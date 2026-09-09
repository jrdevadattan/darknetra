# Turning a gap into a useful records request

Give case-specific suggestions a human investigator can act on. Do not dump a generic checklist or request everything. Prioritize the few gaps that could materially clarify the current question; continue independent supported work while records are absent.

For each suggestion, use short prose or a table with these fields:

- **Needed:** the particular record or export, including the minimum useful fields.
- **From:** likely record custodian and the human route to ask through. If unknown, say who should identify the custodian. Do not invent a person, email or portal.
- **Scope:** the supplied case/document/transaction/consignment identifier and the narrow event period with timezone. State missing identifiers or dates; do not fabricate them.
- **Purpose:** which uncertainty it could clarify, and what it would still not prove. Refer to the actual source/document that raised the gap.
- **Bring back:** a case-scoped, redacted text/CSV export, original supported file or qualified report, with export date, timezone and provenance/integrity information where available. Keep originals with their custodian. Never request credentials, seed phrases or private keys.
- **State:** Suggested — not sent; Awaiting records; or Received — only when the user actually supplies the record. A suggestion is not a completed check or evidence.

If the relevant jurisdiction, reference or period is missing, ask a focused follow-up for it while giving the useful general custodian route. Do not assume a court order or disclosure power. For formal access to confidential records, the case officer's legal unit must determine the applicable process. Do not generate final compulsory instruments or invent legal deadlines. The assistant drafts the information checklist only and never sends it.

When a requested file is later uploaded, compare its actual coverage and fields to the earlier gap. Mark only the supplied portion received, list any remaining gaps and perform the supported review. A response may contradict the working hypothesis; include that outcome. Do not automatically add requested documents or hypothetical relationships to the evidence graph.

## Custodian suggestions, selected by the actual case gap

| Missing material | Likely custodian / human route | Narrow useful return |
| --- | --- | --- |
| Transaction context | Financial-crime team; relevant institution's records/compliance unit through the designated legal liaison | Case-linked transaction export, network/asset, transaction references, units, event timestamps/timezone, export scope and provenance. Any account-level disclosure requires the applicable human legal process. |
| Shipment chronology | Carrier records team through the case officer; customs custodian when a customs record is relevant | Specified consignment's scan events for the relevant period, timezone, event-code definitions, and explanation of gaps if recorded. No broad recipient/sender data collection. |
| Sample or forensic result | Responsible laboratory and evidence custodian | Supplied sample/document reference, custody/receipt dates, signed result, examination scope and limitations. Do not infer a substance from a photograph. |
| Log coverage | Responsible system owner/records team or authorized forensic examiner | Relevant redacted export interval, schema/event definitions, timezone and clock notes, collection method, hash/manifest if available and known gaps. No live collection or deanonymization. |
| Original media or unreadable document | Uploader, document custodian or qualified forensic lab | Original supported file plus provenance, or a redacted text/CSV export and the document/page references it represents. Full PDF/Office extraction is not installed here. |
| Case chronology or statement gap | Assigned case officer and departmental case-records custodian | Redacted existing chronology/statement excerpt and document reference relevant to the question. Exclude confidential-source identities and operational plans. |
| Foreign-held records / unclear legal route | Case officer's legal/prosecution liaison and the appropriate international-cooperation unit | Confirmed jurisdiction, custodian, purpose and scope for legal review; verify the current official route before specifying any formal request. |

## Official starting points, checked 2026-09-08

These references describe institutional remit, not a connected service or authorization to obtain records. Recheck them when giving current or jurisdiction-specific guidance. If they are inaccessible, say the route needs confirmation; do not improvise.

- [MHA Internal Security-II Division](https://www.mha.gov.in/en/divisionofmha/internal-security-ii-division) lists mutual legal assistance matters and links the applicable published guidance. For an Indian case involving foreign-held records, the human legal liaison should confirm the current route and requirements there.
- [MHA overview of the I4C scheme](https://www.mha.gov.in/en/division_of_mha/cyber-and-information-security-cis-division/Details-about-Indian-Cybercrime-Coordination-Centre-I4C-Scheme) describes coordination and the cybercrime forensic laboratory ecosystem. Ask the case officer to identify the appropriate approved support channel; do not claim access to police systems or laboratories.

## SYNTHETIC example

The uploaded SYNTHETIC parcel CSV has an arrival scan but no handover event. Suggest: “Ask the carrier records custodian through the case officer for scan events for consignment SYNTHETIC-PARCEL-001 during the supplied date range, with timezone and event-code definitions. This could clarify whether the export omits a recorded handover; it would not identify the sender or establish parcel contents. Bring back a redacted CSV with export date and provenance. Suggested — not sent. The time range has not been supplied; please provide it.”
