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
| ENS | Unreleased draft: 73 Annex II measures, full Spanish text, selection tables and application clauses | 78 candidate mappings; 20 documentary and six technical guides shared across packs. No qualified mapping review or customer assessment | Complete qualified review, scope/applicability workflow, articles/technical instructions/profiles/audits and release gates |
| NIS2 | Preparation template, official sources and 18 shared guides | Zero normative requirements or reviewed mappings; assessment disabled | Establish national jurisdiction/transposition and entity scope, import/review requirements and mappings |
| ISO/IEC 27001:2022 | Preparation template acknowledging Amd 1:2024; 26 shared guides | No licensed clauses/Annex A text, mappings or assessment | Obtain suitable content access/reuse rights, review requirements, scope, applicability and mappings |
| GDPR Article 32 | Preparation template with 14 shared guides | Zero normative requirements/mappings; not full GDPR coverage or a certification | Import/review Article 32 requirements, processing context and mappings; keep broader GDPR duties separate |
| DORA | Financial-sector preparation template with 20 shared guides | Zero normative requirements/mappings; no customer applicability decision | Verify entity scope, applicable RTS/ITS, requirements and reviewed mappings |
| SOC 2 | Assurance-report preparation template with 16 shared guides | No licensed criteria or reviewed mappings; not a certification | Establish licensed criteria, selected categories, system boundary, reporting period and reviewer |
| Synthetic Alpha/Beta | Development fixture only | Recorded sample states across five example controls | Useful for exercising UI and pipeline behavior; never relabel as ENS/NIS2 |

Evidence: `catalog/PREPARATION.md`, `catalog/frameworks/ens_rd311_2022/SOURCES.md`,
the six versioned packs, shared controls, `apps/api/tests/test_ens_pack.py` and
`apps/api/tests/test_preparation_templates.py`. The scoring gate explicitly excludes
all six preparation packs even when development draft visibility is enabled. A technical
PASS cannot make any of the 73 ENS measures pass: every measure retains a manual control.

## Required implementation sequence

1. Review the ENS draft against its official sources and customer scope. The 73 measure texts
   and selection tables are imported and independently compared; qualified review of all 78
   candidate mappings remains pending. Address the explicit coverage gaps before release.
2. Expand the five preparation templates into reviewed normative packs in demand order.
   The existing 26 bilingual guides include steps, evidence, verification and limits. Six
   technical candidates use pinned Prowler 5.49.0 checks; a candidate is not reviewed coverage.
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

Dashboard stack: #55, #63, #66, #68, #69, #70 (detail API), #71 (detail screen), #72
(readiness), #73 (preview loader/scoring guard), #74 (official ENS draft) and #75
(five preparation templates). The preparation UI extends that stack.
Connection runtime remains owned by the other session. No merge or deployment is included.
The local demo additionally includes independent release-gate work from #54.
