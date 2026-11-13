# Dashboard and framework readiness

Observed on 2026-11-13 against main `6ded2e6` and the open dashboard PR stack.
This is an implementation inventory, not an assessment of a customer's legal compliance.

## What can be used now

| Capability | Observed implementation | Boundary |
| --- | --- | --- |
| Organization workspace | Sign-in, organizations, roles, members and invitations | Local verification uses fake Cognito; production hosted login is not established by these tests |
| Results overview | Stored framework scores, manual counts, scan coverage, evidence count | A score does not certify compliance; manual requirements are not passing requirements |
| Requirement register | Stored requirement states, filters, search, historical provenance and configuration detail | Reads recorded data; it cannot infer uncollected customer configuration |
| Implementation guidance | Catalog descriptions, safe reference links, manual/technical distinction and a next step for every state | Missing descriptions, references and mapping review are shown explicitly |
| Technical observation | Existing scan-as-of aggregation, gated on matching framework/catalog versions | No raw resources or individual connection drill-down; catalog drift yields no observation |

## What is missing by framework

| Framework | Repository pack | Requirement/configuration coverage | Required completion |
| --- | --- | --- | --- |
| ENS | No authored or released pack; only `_template` exists | Unknown, not 0% compliance; no real mappings or per-control guides published | Populate official requirement content, applicability, reviewed common-control mappings and verified guidance; validate and release the pack |
| NIS2 | No authored or released pack; only `_template` exists | Unknown; no real requirement-level customer assessment can be claimed | Establish applicable jurisdiction/version, capture official requirements, review applicability and mappings, validate and release |
| Other planned packs | Not implemented | Unknown | Follow the demand/reuse gate in `catalog/README.md`; do not invent pack-specific code |
| Synthetic Alpha/Beta | Development fixture only | Recorded sample states across five example controls | Useful for exercising UI and pipeline behavior; never relabel as ENS/NIS2 |

Evidence: `catalog/frameworks/_template/`, `catalog/controls/_template.yaml`,
`catalog/README.md`, `apps/api/tests/fixtures/catalog/synthetic.yaml` and the released-pack
gate in `apps/api/src/atesta_api/modules/compliance/scoring.py`.

## Required implementation sequence

1. Complete the first real content pack. Every requirement needs its official source and
   applicability; every mapping needs rationale, source and qualified review. Validate check
   identifiers against the pinned scanner. Rule 10 forbids publishing remembered legal text.
2. Supply actionable, bilingual control guides: expected configuration, prerequisites,
   system-owner steps, source documentation, required evidence and verification procedure.
   A generic next-step explanation is not a complete vendor-specific remediation guide.
3. Finish live onboarding/collection with the connection workstream. At this observation,
   #67 owns create/list/get/disconnect endpoints. Fixture scans and ingestion already work;
   this does not verify real tenant consent, credentials or end-to-end cloud execution.
4. Add the user workflow for documentary evidence, assignment and review. The current
   screen explains pending work but does not upload documents, assign owners, change
   applicability, approve manual requirements or record exceptions.
5. Verify release conditions: genuine test-tenant captures, hosted authentication, public
   legal identity/content and required review. #54 remains a draft release gate, not a
   deployment. Merge the reviewed stack in dependency order before production rollout.

## Reading the requirement states

`pass` means the recorded requirement passed within its recorded scope and date. `fail`
means at least one mapped control failed. `manual` may indicate documentary review or
missing/unassessed control data; it is not an approval. `not_evaluated` means no stored
result for that requirement in this assessment. `not_applicable` is a recorded assessment
outcome, never inferred from missing data. Technical check observations are shown separately.

Catalog and score versions are distinct. When they differ, preserve original outcomes and
label current guidance; do not reconstruct historical control outcomes using newer mappings.

## Current coordination

Dashboard stack: #55, #63, #66, #68, #69, #70 (detail API), and #71 (detail screen).
Connection runtime remains owned by the other session. No merge or deployment is included.
The local demo additionally includes independent release-gate work from #54.
