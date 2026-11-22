# Security

Atesta holds read-only consent to customers' Microsoft 365 and Google Workspace tenants and
stores their security posture. This file says how to report a problem, what the repository
enforces and with which test, and what it does not yet do.

## Reporting a vulnerability

Do not open a GitHub issue for a vulnerability.

- **Channel:** pending. A `security@` address on Atesta's own domain, plus a
  `/.well-known/security.txt` served by the web app, is a release gate: no customer is onboarded
  before both exist. Until then, report to the repository owner (GitHub `Davmunrey`) directly.
- **Include:** the component (api, worker, web, scanner image, connector consent flow), the
  steps, and what you observed. Use only your own test tenant and synthetic data; never access
  another organization's data to prove a point.
- **Expect:** an acknowledgement and a fix or mitigation plan. Response targets will be published
  with the channel.

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
| No GPL or AGPL in the web bundle | rule 4, ADR-006 | `apps/web/scripts/check-licenses.ts`, run by CI job `web` |
| Strict Content Security Policy for the static web | web-shell spec | `apps/web/scripts/csp.ts`, run by `pnpm build` in CI |

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

**Committed in this repository:** actions pinned to full commit SHAs, checkout without persisted
credentials, locked installs (`uv sync --locked`, `pnpm install --frozen-lockfile`), a 7-day
dependency cooldown, and the CI jobs above.

**Owner settings, applied on 2026-11-22:** Dependabot alerts and Dependabot security updates on;
branches deleted on merge; squash commits take the pull request's title and body.

**Unavailable on the current plan** (private repository on GitHub Free; the API returns HTTP 403):
branch protection and rulesets, so no check can be made required; secret scanning with push
protection. Until the plan changes, CI green is a convention the reviewer keeps (see
`AGENTS.md`, "How a pull request lands").

## Known limits

- Atesta is not certified against ENS, ISO/IEC 27001 or SOC 2, and it does not certify its
  customers. It prepares evidence.
- The service is not deployed. Infrastructure in `infra/` has not been applied.
- No independent penetration test has been run.
- No secret scanning runs over the git history yet.
