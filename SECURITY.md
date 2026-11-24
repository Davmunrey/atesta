# Security

Atesta holds read-only consent to customers' Microsoft 365 and Google Workspace tenants and
stores their security posture. This file says how to report a problem, what the repository
enforces and with which test, and what it does not yet do.

## Reporting a vulnerability

Do not open a public issue for a vulnerability.

- **Channels**, in order of preference:
  1. Email `security@atesta.cloud`.
  2. GitHub private vulnerability reporting, "Report a vulnerability" on the
     [Security tab](https://github.com/Davmunrey/atesta/security/advisories/new). The report is
     visible only to the owner.
- **security.txt:** both channels are published at `/.well-known/security.txt` on
  `atesta.cloud` and `app.atesta.cloud` (RFC 9116, `docs/specs/security-txt.md`). Each deploy
  renews its expiry date. The file is not signed yet.
- **Include:** the component (api, worker, web, scanner image, connector consent flow), the
  steps, and what you observed. Use only your own test tenant and synthetic data; never access
  another organization's data to prove a point.
- **Expect:** an acknowledgement and a fix or mitigation plan. Response targets will be published
  with the domain.

## Scope

In scope: this repository's code, the scanner image built from `scanner/`, the infrastructure in
`infra/`, and the hosted service once it exists. Out of scope: Microsoft, Google, AWS and other
providers' own services; reports from automated scanners with no demonstrated impact.

## What Atesta is exposed to

The failures that matter most, in order: one organization reading another's data; a connector
gaining write access to a customer system; a leaked credential or token; customer content steering
AI output (prompt injection); customer data processed outside the EU.

## Controls and what holds them

| Control | Rule | Held by |
| --- | --- | --- |
| Tenant isolation: every tenant table has `organization_id` and Postgres RLS; no context returns zero rows | AGENTS.md rule 3, ADR-012 | `apps/api/tests/db/test_rls.py` (`test_every_rls_table_fails_closed_and_shows_one_tenant`, `test_no_context_returns_zero_rows_everywhere`, `test_pooled_connection_never_carries_a_tenant`), `apps/api/tests/test_tables.py`, `apps/api/tests/db/test_identity_rls.py` |
| Only identity sets the tenant context | ADR-012 | import-linter contract in `pyproject.toml`, run by `uv run lint-imports`; `apps/api/tests/test_import_contracts.py` |
| Modules talk only through their `api.py` | rule 8, ADR-008 | import-linter contracts in `pyproject.toml` |
| Read-only connectors: the scanner app's grants are checked against the connection's allowlist before every scan; anything extra fails closed | rule 1 | `scanner/atesta_scanner/verify_m365.py`, `scanner/tests/test_verify_m365.py`, `apps/api/tests/db/test_connection_verification.py` |
| Secrets never reach scanner logs | rule 2 | `scanner/tests/test_scrub.py` |
| Raw resource dumps never leave the scan container | scanner-connectors spec D10 | `scanner/tests/test_strip.py` |
| Session tokens live only in AES-GCM sealed, HttpOnly cookies; PKCE, state and nonce checked; tokens never logged | web-shell spec | `apps/api/src/atesta_api/modules/identity/bff.py`, `apps/api/tests/db/test_bff.py` |
| Cookie-authenticated writes need the web origin | web-shell spec | `apps/api/tests/db/test_bff.py::test_cookie_writes_need_the_web_origin` |
| API responses are never cached or MIME-sniffed | web-shell spec | `apps/api/tests/test_response_headers.py` |
| Database server is authenticated (verify-full, pinned RDS CA) | tenant-data-layer spec | `apps/api/tests/test_db_tls.py` |
| Misconfigured startup is refused | tenant-data-layer spec | `apps/api/tests/db/test_guard.py`, `apps/api/tests/test_dev_guards.py` |
| Audit events are append-only and atomic with the action | definition of done | `apps/api/tests/db/test_audit.py` |
| AI never decides pass or fail; answers cite retrieved chunks | rules 5–6, ADR-005, ADR-010 | Design rule. The AI module is not built yet (`apps/api/src/atesta_api/modules/ai/api.py`), so no test holds it today |
| Locked, audited, cooled-down dependencies | ADR-006, ADR-013 | `.github/workflows/ci.yml` job `security` (pip-audit on the exported lock and the scanner requirements, semgrep), `apps/api/tests/test_ci_workflow.py`, `.github/dependabot.yml` (7-day cooldown) |
| No GPL or AGPL in the web bundle or the Python dependencies; LGPL only where listed | rule 4, ADR-006 | `apps/web/scripts/check-licenses.ts` (CI job `web`), `apps/api/devtools/python_licenses.py` (CI job `python`), `apps/api/tests/test_python_licenses.py` |
| Strict Content Security Policy for the static web | web-shell spec | `packages/ui/scripts/csp.ts`, run by `pnpm build` in CI |
| Uploaded evidence files are served only after GuardDuty Malware Protection for S3 reports them clean; a file with possible malware is blocked, kept under Object Lock, and owners and admins are told | evidence-malware-scanning spec, #401 | `apps/api/tests/db/test_evidence_malware.py`, `apps/api/tests/db/test_file_scan_job.py`, `apps/api/tests/test_malware_events.py`; the API role reads only versions tagged `NO_THREATS_FOUND` and only the scan role may write that tag (`infra/tests/test_infra.py`) |

## Trusted inputs and accepted gaps

What Atesta takes from outside, where the boundary is enforced, and which gaps are accepted on
purpose. An accepted gap is named here with the issue that would close it, so nobody mistakes it
for a control.

| Input | Trust | Boundary that holds it |
| --- | --- | --- |
| Prowler output from the scanner container | Untrusted data (rule 5) | `scanning/ingest.py`: the manifest's sha256 for every file (`atesta_core.manifest.verify_manifest`), strict OCSF parsing with NUL refused (`atesta_core.ocsf`), and every finding pinned to the connection's tenant (`pin_tenant`); a rejected scan writes no rows (`apps/api/tests/db/test_scan_ingest.py`) |
| Microsoft Graph answers to the verifier | Untrusted; read-only verification fails closed (rule 1) | `scanner/atesta_scanner/verify_m365.py`: a role it cannot name counts as extra, a read it may not make is `incomplete`; `graph.py` follows `@odata.nextLink` only under the Graph root, so the token never leaves Graph (`scanner/tests/test_verify_m365.py`) |
| The verifier's report (`verification.json`) back in the worker | Untrusted container output | `scanning/attempts.py` `_verification` reads only its fields, each as text; an unreadable report changes no connection (`apps/api/tests/db/test_scan_attempts.py`) |
| The M365 tenant a scan reaches | Pinned by the connection, never by the secret | The wrapper sets `AZURE_TENANT_ID` from the job's pin and refuses a secret that names a tenant (`scanner/atesta_scanner/invocation.py`, `scanner/tests/test_invocation.py`) |
| Catalog packs (frameworks, controls, mappings) | Trusted once the owner releases them after qualified review | `catalog/`, each pack's `SOURCES.md`; loaded as `atesta_owner`, read-only to the app role (ADR-012); release is an owner decision (GOVERNANCE.md) |
| Sign-in tokens | Trusted after signature, issuer and audience checks against Cognito's JWKS | `identity/cognito.py`, `apps/api/tests/db/test_bff.py` |
| Evidence statements and their links | Customer content: untrusted, never fetched, rendered as text | `evidence/links.py` refuses a link whose query or fragment carries a credential on every path into evidence: the web form, the ingestion API, policies, training campaigns, and `record_attestation` (#256; `apps/api/tests/db/test_ingestion.py`, `test_routines.py`, `test_routines_b.py`, `test_control_workspace.py`) |
| Uploaded evidence files | Customer content: untrusted, never executed, rendered or parsed (rule 5) | `evidence/files.py`: the API is the only writer to the store; the type comes from the extension allowlist and the content must match it; size is counted, not declared; the SHA-256 is computed over the bytes received and recomputed before every download, which is refused and audited on a mismatch (#222, #263); a download waits for a clean malware scan of the version it reads (#401); downloads are attachments with `nosniff` and a sandbox policy (`apps/api/tests/db/test_evidence_files.py`, `test_evidence_malware.py`) |
| GuardDuty malware scan results from the worker's queue | Untrusted until checked | `evidence/malware.py` `parse_scan_result`: the configured bucket and the uploaded-file key shape only; the result is recorded only for that exact key of that organization, under RLS, and the first result is final; an unknown status counts as failed (`apps/api/tests/test_malware_events.py`, `apps/api/tests/db/test_file_scan_job.py`) |
| API tokens for evidence ingestion | Write-only, stored as a sha256 | `identity/api_tokens.py`; a token in a query string is refused before parsing (`QueryFreeRoute`, `apps/api/tests/db/test_ingestion.py`) |
| OAuth access tokens at the hosted MCP server (off by default) | Trusted after signature, issuer, expiry, audience, approved client and scope checks; never forwarded | `identity/cognito.py` `verify_agent`, `apps/api/tests/test_agent_oauth.py`; what the agent may do comes from a grant an admin recorded, `apps/api/tests/db/test_agent_grants.py` (ADR-016 amendment 1) |
| Device agent reports | Evidence noise at worst: a device credential reads nothing | `docs/security/device-agent-threat-model.md`, including its own residual risks |

**Accepted gaps, not closed here:**

- **M365 verifier limits.** Until PR 10 the verifier opens no Exchange session, so Exchange
  service principal pointers, role groups and RBAC for Applications grants are not read. Roles
  held through groups and Azure RBAC stay candidates until the live golden test, and tokens issued
  before a revocation are not seen. Every report lists these limits
  (`scanner/atesta_scanner/verify_m365.py`, `M365_LIMITS`).
- **Google has no verifier yet.** Google scans fail closed (`scanner/atesta_scanner/run.py`,
  `verify_job`), so no Google connection is scanned until its verifier exists.
- **Capability links.** A link whose path is itself the capability ("anyone with the link") cannot
  be told apart from a normal link; only credentials in the query or fragment are refused
  (`evidence/links.py`).
- **Scores and ended connections.** A disconnected or revoked connection's results leave the
  score by the connection's current status, not as of the scan (`scanning/scoring.py`, `_as_of`).
- **Sign-in codes in load balancer logs.** The API never logs query strings (#257), but the load
  balancer's access logs record the sign-in callback's code and state. The code is single-use,
  short-lived and bound to the PKCE verifier held only in the sealed `atesta_auth` cookie; the log
  bucket is private, encrypted and retention-limited (`infra/modules/ecs/api.tf`).
- **Local Docker runner (development only).** The attempt's `out/` folder is opened to the
  container's user 10001 (`scanning/local.py`); `LocalDockerRunner` refuses to start outside a
  development `ATESTA_ENV`.
- **Malware scanning has the limits of its scanner.** GuardDuty reports a file it cannot scan
  (password-protected, over its quotas) as unsupported, and Atesta then refuses the download;
  it cannot catch a threat its engine does not know. The local development stack has no scanner
  and marks files `not_scanned`. Results that cannot be placed wait in a dead-letter queue that
  nothing alarms on yet (evidence-malware-scanning spec, Out of scope).
- **Evidence lock in governance mode.** Stored evidence is retained 365 days under S3 Object
  Lock in governance mode, and the bucket policy denies the bypass to every principal (#263).
  Whoever can change that policy can still lift the lock; compliance mode would close this and
  would also block GDPR erasure for a year (hosted-environment spec).
- **Open hardening work:** agents cannot yet be told apart from the owner on GitHub, and review is
  not enforced on the critical paths (#261). The owner creates the agents' identity first.
- **Owner decisions pending:** disclosure timing and a safe-harbour statement for researchers
  (#260).

## Data handling

- **Residency:** every data store and all compute in AWS eu-south-2 (Spain). The only exception
  today is Cognito email through SES in eu-west-3 (Paris). Nothing is processed outside the EU
  (ADR-007, amendment 1).
- **What is stored:** user identity (Cognito), organizations and members, connector consent
  metadata, scan results with resource metadata stripped, evidence statements, manual reviews,
  audit events.
- **What is never stored:** customer passwords, write-capable credentials, customer document
  contents in logs.
- **Retention and deletion:** not yet specified. A retention and offboarding policy is a release
  gate before the first customer.

## Repository hardening

The repository is public since 2026-11-22; the code stays proprietary (`LICENSE`). Every
setting below was applied through the GitHub API and read back the same day.

**Committed in this repository:** actions pinned to full commit SHAs with their version, tested
(`apps/api/tests/test_ci_workflow.py`); read-only top-level permissions in every workflow, with
write scopes only on the job that needs them; a timeout on every job; checkout without persisted
credentials; locked installs; a 7-day dependency cooldown; the `main` ruleset as code
(`.github/rulesets/main-branch.json`), tested against the CI jobs; `CODEOWNERS`; OpenSSF Scorecard
(`.github/workflows/scorecard.yml`).

**Enforced by GitHub:**

- Ruleset on `main`: no deletion or force-push; changes only through a pull request, squash
  merge only, conversations resolved; every CI job required. Nobody bypasses it, the owner
  included; in an emergency the owner disables the ruleset, which GitHub records.
- Secret scanning with push protection; Dependabot alerts and security updates.
- Private vulnerability reporting.
- Default workflow token read-only, and workflows cannot approve pull requests.
- Pull requests from any outside contributor's fork wait for the owner's approval before
  their workflows run.
- Branches deleted on merge.

**History scan:** gitleaks 8.30.1 (MIT, release checksum verified) over all 138 commits on
2026-11-22 reported 6 matches, all test data or public identifiers: truncated PKCS#8 headers in
`scanner/tests/test_scrub.py` and `apps/api/tests/db/test_connections_table.py`, Microsoft Graph
permission ids in `packages/core/src/atesta_core/connectors/readonly.py`, and a test session key
that decodes to `0123456789abcdef0123456789abcdef`. No credential was found. Those six are
listed by fingerprint in `.gitleaksignore`, and the CI `secrets` job runs the same pinned,
checksum-verified gitleaks on every pull request's commits and weekly over the whole history.

**Not used:** CodeQL. Its terms allow it only on code released under an OSI-approved licence,
or with a paid GitHub Advanced Security licence
([GitHub CodeQL Terms and Conditions](https://github.com/github/codeql-cli-binaries/blob/main/LICENSE.md)).
Atesta's code is proprietary, so static analysis is semgrep in the CI `security` job.

## Known limits

- Atesta is not certified against ENS, ISO/IEC 27001 or SOC 2, and it does not certify its
  customers. It prepares evidence.
- The service is not deployed. Infrastructure in `infra/` has not been applied.
- No independent penetration test has been run.
- Secret scans catch known patterns and high-entropy strings, not every secret a human could recognise.
