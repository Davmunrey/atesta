# Dashboard and framework readiness

Observed on 2026-11-14 across merged dashboard/catalog work and the local evidence integration.
Draft and local capabilities below are not claimed as merged or deployed.
This is an implementation inventory, not an assessment of a customer's legal compliance.

## What can be used now

| Capability | Observed implementation | Boundary |
| --- | --- | --- |
| Organization workspace | Sign-in, organizations, roles, members and invitations | Local verification uses fake Cognito; production hosted login is not established by these tests |
| Results overview | Stored framework scores, manual counts, scan coverage, evidence count | A score does not certify compliance; manual requirements are not passing requirements |
| Requirement register | Stored requirement states, filters, search, historical provenance and configuration detail | Reads recorded data; it cannot infer uncollected customer configuration |
| Implementation guidance | Catalog descriptions, safe reference links, manual/technical distinction and a next step for every state | Missing descriptions, references and mapping review are shown explicitly |
| Technical observation | Existing scan-as-of aggregation, gated on matching framework/catalog versions | No raw resources or individual connection drill-down; catalog drift yields no observation |
| Declared evidence, local integration | Named statements, optional HTTPS references and paginated history beside mapped and preparation controls; shared by common control | API #83 depends on draft #79; UI depends on #83. No binary upload, document retrieval/verification, automatic approval or assessment change |
| Manual review, local integration | Independent manual control review from #79 is present in the local baseline | #79 remains draft; evidence submission neither changes a decision nor pins evidence to it |

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
3. Finish live onboarding/collection with the connection workstream. Connection and scan
   endpoint work has merged through #77, #78, #81 and #82. Worker execution #84 has also
   merged; the local Docker runner remains with the other session in draft #85. Fixture scans and ingestion work; this does not verify real
   tenant consent, credentials or end-to-end cloud execution.
4. Integrate the independently reviewed manual workflow in draft #79, dependent evidence
   API #83 and the dependent evidence UI. Local statements and HTTPS references persist
   without changing assessments. Binary uploads, decision-to-evidence pinning, marking a
   review stale when new evidence arrives, owner assignment and applicability editing remain
   outstanding. A declaration is not a verified document or compliance approval.
5. Verify release conditions: genuine test-tenant captures, hosted authentication, public
   legal identity/content and required review. Release-gate work #54 has merged; that does
   not establish deployment or satisfaction of those gates. Merge the remaining reviewed
   stack in dependency order before production rollout.

## Reading the requirement states

`pass` means the recorded requirement passed within its recorded scope and date. `fail`
means at least one mapped control failed. `manual` may indicate documentary review or
missing/unassessed control data; it is not an approval. `not_evaluated` means no stored
result for that requirement in this assessment. `not_applicable` is a recorded assessment
outcome, never inferred from missing data. Technical check observations are shown separately.

Catalog and score versions are distinct. When they differ, preserve original outcomes and
label current guidance; do not reconstruct historical control outcomes using newer mappings.

## Current coordination

Merged dashboard/catalog stack: #55, #63, #66 and #68 through #76, including detail API,
detail screen, readiness inventory, preview/scoring guard, ENS draft, preparation templates
and their UI. The other session has merged #54, #77, #78, #81, #82 and #84.

Manual review #79 remains draft. Its earlier checks were green; integration of current main
and renewed verification are in progress. Evidence API #83 is dependent on #79, with head
`857caf145a495e0591e23a060a0b4dc831ba3032` including #79 base
`63ee11539b52f992b6a5b539423438acb3970ec9` and merged #81/#82. The evidence UI depends on #83.
Hardening #80 and the local Docker runner #85 remain owned by the other session.
The verification totals below apply to the pinned #79/#83 baseline, not to later worker changes.

Local evidence verification records 780 Python tests, 272 web tests, passing lint/types/module
boundaries/build and 15 browser checks. A real local API write persisted a synthetic statement
without changing the assessment; 375/768/1280px light and 1280px dark captures show no horizontal
overflow or serious/critical axe findings. These checks do not establish production readiness,
genuine cloud collection, legal content completeness or qualified catalog review.
