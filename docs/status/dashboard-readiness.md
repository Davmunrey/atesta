# Dashboard and framework readiness

Observed on 2026-11-24 at `main` `ead81a12a328d275672d38ffe1399f1809fe2f4c`.

This is an inventory of what the repository implements. It is not an assessment of any
customer, and merged code is not a deployed service: nothing runs in AWS yet
(`docs/specs/hosted-environment.md`). Every row names the spec and a test, so it can be checked.
When this file and `main` disagree, `main` is right and this file needs a pull request.

## What can be used now

Verified on the local stack (fake Cognito, local Postgres, fixture scans). "Spec" is a file in
`docs/specs/`; "test" is a file in `apps/api/tests/db/` unless a path says otherwise.

| Capability | Spec and test | Boundary |
| --- | --- | --- |
| Sign-in, organizations, members, invitations | `identity-auth.md`, `test_identity_http.py`, `test_invitation_flows.py` | Hosted sign-in with MFA waits for AWS |
| Roles: owner, admin, member, and an external auditor with an end date | `rbac.md`, `test_rbac.py`, `test_route_sweep.py` | The auditor reads; it never writes |
| Organization overview: first steps, records at a glance, what is due | `readiness-cockpit.md`, `test_overview.py`, `test_readiness.py` | Shows recorded rows only; nothing is estimated |
| ENS scope, self-assessment per measure, reviewer analysis, statement of applicability export | `requirement-register.md`, `test_requirement_register.py` | The organization records its own assessment. Atesta proposes applicability from the BOE tables; a person decides |
| Framework detail: measure text, selection rules, expected evidence, guides, technical observations | `framework-detail.md`, `test_framework_detail.py` | A technical observation never makes a measure pass: every ENS measure keeps a manual control |
| Evidence statements with optional HTTPS links, per common control | `control-evidence-statements.md`, `test_evidence.py`, `test_control_workspace.py` | A statement is a declaration. Atesta does not fetch or verify the link |
| Manual control review that cites its evidence | `manual-control-review.md`, `test_control_reviews.py` | A person approves; the AI and the scanner never do (ADR-005) |
| Recorded routines: access reviews, policies, training acknowledgements, incident register with reporting deadlines | `recorded-routines.md`, `test_routines.py`, `test_routines_b.py` | Deadlines are computed from what the organization recorded |
| Auditor dossier and monthly management report | `auditor-dossier.md`, `management-report.md`, `test_dossier.py`, `test_report.py` | Printed from recorded rows; no conformity statement |
| Portfolio for people in several organizations | `consultancy-portfolio.md`, `apps/web/tests/e2e/portfolio.spec.ts` | The summary is computed in the browser, one request per organization (#228) |
| Activity log, assignments, "Mi trabajo" | `insights.md`, `rbac.md`, `test_audit.py`, `test_rbac.py` | Audit events are append-only |
| API keys with scopes, a rate limit and a usage log | `api-keys-v2.md`, `test_api_keys_v2.py`, `test_key_reads.py`, `test_key_writes.py` | A key reaches only its own organization |
| Evidence ingestion API and ready-made scripts | `evidence-ingestion-api.md`, `test_ingestion.py` | Statements only; a link that is a credential is refused |
| MCP server for AI agents, local | `mcp-server.md`, `test_mcp_contract.py`, `apps/mcp/` | The hosted server is not available. An agent proposes; a person confirms (`test_proposals.py`) |
| Email notices, daily digest, weekly summary, one-click unsubscribe | `notifications.md`, `test_notifications.py`, `test_notify_daily.py`, `test_notify_events.py` | Mail is written to a local directory (`FileMailer`). No sender for SES exists yet |
| Plans enforced per framework | `billing-entitlements.md`, `test_billing.py`, `catalog/plans.yaml` | No payment provider. An operator sets the plan; prices are not in this repository |
| Data export, organization closure, erasure after 30 days | `organization-closure.md`, `test_org_closure.py` | Erasure is an operator command, run as `atesta_owner` |
| Microsoft 365 connection: sign-in, admin consent, read-only verification, activation | `scanner-connectors.md`, `web-connections.md`, `test_m365_onboarding.py`, `test_m365_activation.py`, `test_connection_verification.py` | Not run against a customer tenant. The live golden test is Gate B in `ROADMAP.md` |
| Scans: queue, one container per scan, ingestion, scoring snapshots | `scanner-connectors.md`, `test_scan_jobs.py`, `test_scan_ingest.py`, `test_scan_scoring.py` | Only the fixture and local Docker runners exist (`apps/worker/src/atesta_worker/scans.py`). No Fargate runner |
| Assistant that answers from the catalog with citations | `assistant.md`, `apps/web/tests/e2e/assistant.spec.ts` | It uses no AI model. The AI module is empty (`apps/api/src/atesta_api/modules/ai/api.py`) |
| Public site: landing, product, ENS, security, consultancies, API and MCP docs, legal pages | `landing-legal.md`, `public-api-docs.md`, `apps/web/tests/e2e/public-pages.spec.ts` | Legal pages are drafts until a lawyer reviews them; `pnpm check-legal` gates release |
| Spanish and English everywhere | `i18n-complete.md`, `apps/web/tests/unit/i18n.test.tsx`, `apps/api/tests/test_api_messages.py` | Official text published only in Spanish stays in Spanish |

## Framework packs

Counted from `catalog/frameworks/` on the commit above. Every pack is `status: draft` with
`assessment_enabled: false`; the catalog schema accepts nothing else today
(`apps/api/src/atesta_api/modules/compliance/catalog_schema.py`). A mapping counts as reviewed
when it names its reviewer.

| Pack | Version | Requirements | Mappings (reviewed) | Still missing |
| --- | --- | --- | --- | --- |
| ENS, RD 311/2022 | `2024-11-06.draft8` | 73 Annex II measures, Spanish | 106 (9) | Qualified review; articles, technical instructions and audit rules; release |
| NIS2, Directive (EU) 2022/2555 | `2022-2555.draft7` | 23, Spanish and English | 51 (3) | Spanish transposition; qualified review |
| NIS2 Implementing Regulation (EU) 2024/2690 | `2024-2690.draft2` | 162, Spanish and English | 162 (0) | Qualified review |
| GDPR Articles 32 to 34 | `2016-679.art32-34.draft7` | 14, Spanish and English | 39 (3) | Qualified review; the rest of the GDPR is out of the pack |
| LOPDGDD security provisions | `lo-3-2018.draft1` | 6, Spanish | 8 (0) | Qualified review |
| DORA, Regulation (EU) 2022/2554 | `2022-2554.draft8` | 22, Spanish and English | 62 (4) | Qualified review; remaining technical standards |
| DORA RTS (EU) 2024/1774 | `2024-1774.draft1` | 41, Spanish and English | 41 (0) | Qualified review |
| ISO/IEC 27001:2022 | `2022-amd1-2024.template1` | 0: template, no ISO text stored | 0 | Licensed content or identifiers with Atesta's own guides |
| SOC 2 | `2017-tsc-2022.template1` | 0: template, no AICPA text stored | 0 | Licensed criteria |

- **Common controls:** 44 in `catalog/controls/`: 20 documentary (`manual: true`) and 24 technical,
  23 of them with a pinned scanner check. Controls are shared across packs (ADR-011).
- **Sources:** each pack with requirements has a `SOURCES.md` and a `coverage.yaml` ledger of its
  official source. The ENS hashes can be recomputed from `source_records.json`
  (`apps/api/tests/test_ens_boe.py`).
- **Scanner:** Prowler 5.52.0, pinned (`scanner/expected/5.52.0/`).

## Not built, or built and not released

- **Hosted environment.** OpenTofu for dev and prod exists in `infra/` and is not applied. The
  owner postponed AWS until after the go/no-go of 2026-12-18 (`hosted-environment.md`).
  `docs/runbooks/deploy.md` is the path from no account to a running environment.
- **Evidence files.** Uploading a file as evidence (#222, #400) is in open pull requests #402
  and #412. Until they merge, evidence is statements and links. Malware scanning of uploads is
  not built (#401).
- **Live tenant collection.** No customer or test tenant has been scanned end to end (Gate B).
  Google Workspace: the API accepts the connection and the scanner has its read-only verifier
  (#390); the Connections page connects Microsoft 365 only (#365).
- **Operator portal.** Decided (ADR-017, `operator-portal.md`) and not built.
- **Payments.** No payment provider is integrated.
- **AI.** No generative model is called anywhere. ADR-010 sets the rules for when one is.
- **Device agent.** Designed (`device-agent.md`, ADR-014) and not built.
- **Released packs.** None. A pack is released by the owner after qualified review
  (AGENTS.md, "Owner decisions").
- **Penetration test, restore drill and external status page.** Gate A in `ROADMAP.md`.

## Reading the requirement states

`pass` means the recorded requirement passed within its recorded scope and date. `fail` means at
least one mapped control failed. `manual` means a documentary review or missing control data; it
is not an approval. `not_applicable` is a recorded outcome, never inferred from missing data.
The four values are `Status` in `packages/core/src/atesta_core/scoring.py`. On screen they read
Superado / No superado, never "cumple" (`claims-honesty.md`).

Catalog and score versions are distinct. When they differ, original outcomes are kept and
current guidance is labelled; history is never rebuilt with newer mappings.

## Where the work is tracked

Open work is in the [issue tracker](https://github.com/Davmunrey/atesta/issues), its order and
gates in [ROADMAP.md](../../ROADMAP.md), and what each release changed in
[CHANGELOG.md](../../CHANGELOG.md) and `changes/`. This file keeps no list of pull requests.
