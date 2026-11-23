# Spec: Scanner and connectors (Microsoft 365, Google Workspace)

- Requirement ids: NFR-02, MF-02. Connector and scan requirements have no FR id in the repo yet.
- Status: approved, with the defaults of D1 to D13 (the owner delegated design and product
  decisions on 2026-11-13: "Tú decides siempre")
- ADRs: ADR-002, ADR-003, ADR-004 (amendment 1 accepted), ADR-005, ADR-006, ADR-007, ADR-008,
  ADR-011, ADR-012 (amendment 2 accepted)
- Build order: after the control model (built) and the catalog spec's loader and sync job
  (`checks` and `control_checks` rows from YAML). A score for a real framework also needs a pack
  with reviewed mappings (control-model spec). One spec for both connectors, built Microsoft 365
  first (Graph-only, then PowerShell services), then Google Workspace (owner decision,
  2026-11-13). AWS connector in v1.1. First customer scan: after the AWS spec (Fargate runner, S3,
  Secrets Manager in eu-south-2) and the live golden test.

## Problem

The security lead of an SME supplier must show an ENS or NIS2 auditor that Microsoft 365 or Google
Workspace is configured securely, and keep it that way between audits. Today that means
screenshots, spreadsheets and consultant days per audit, and the evidence is stale the day after.
Atesta must read the tenant configuration with read-only access only (rule 1), score it against
every framework the customer has from the same results (ADR-011), and keep the raw output as
evidence. A connector that silently loses checks would show controls as passing that were never
assessed, which is worse than no connector (ADR-005).

## Owner decisions (defaults adopted 2026-11-13)

The owner delegated these decisions; every default below is adopted. Each row still names what
would change with the alternative. Three defaults need the owner to act, not to decide: D8 (run
the provisioning runbook for pilot customers), D11 (legal review of the PowerShell modules) and
D12 (Microsoft Partner Program account and a verified domain).

| # | Question | Default in this spec | Alternative and its cost |
|---|---|---|---|
| D1 | 54 of 149 checks read PowerShell data and need an Entra directory role on Atesta's app: 38 through the Exchange Online session (Exchange 17, Defender 17, Admin center 3, Purview 1) and 16 through the Teams session. Accept Global Reader, which Microsoft labels PRIVILEGED and which carries two Service Health `allTasks` actions? | Graph-only first. The first M365 milestone requests the Graph set only (no directory role, no `Exchange.ManageAsApp`); the 54 are excluded and stored `not_evaluated`, reason `not_granted`; `active` needs no Global Reader. Global Reader, `Exchange.ManageAsApp` and the modules ship in PR 10 after D11 clears, as an upgrade of active connections (re-consent, role assignment, re-verification). Until then the verifier cannot read Exchange RBAC grants (Verifier limits) | Graph-only for good (95 checks); or a custom Exchange role group (Microsoft "Option 2") for the 38 Exchange-session checks, more customer setup (step 5b then expects that one role group), while the 16 Teams checks still need an Entra role or stay not assessed |
| D2 | `Directory.Read.All` or the granular read set? | Granular set (table below). `Directory.Read.All` enters the expected set only through an allowlist version bump, if the live golden shows a check or verifier step 4 fails without it | `Directory.Read.All` from day one: simpler, broader, and Microsoft says directory permissions may be deprecated |
| D3 | `ThreatHunting.Read.All` (arbitrary read-only KQL over Defender telemetry, 3 checks) | Not requested; the 3 checks are excluded with `--excluded-checks` and shown as not assessed | Opt-in through a second app registration ("Atesta Threat Hunting", own certificate, own admin consent), never extra permissions on "Atesta Scanner": admin consent grants everything a registration lists |
| D4 | Add `Policy.Read.DeviceConfiguration`, which Prowler's docs omit? | Yes, read-only, needed by 5 device registration checks (candidate until the live golden test) | Leave out, 5 checks not assessed |
| D5 | M365 credential model | One Atesta multi-tenant app, one certificate held only by M365 tasks (Credentials below); ADR-004 amended | One single-tenant app per customer with a per-org certificate: per-tenant blast radius, much heavier onboarding |
| D6 | Prowler requests an `apps.licensing` token (view and manage licences, no read-only variant) only when one of 5 Google checks fails, to add an edition note. The lookup is best effort (`except Exception`, WARNING, empty list) and never changes PASS or FAIL | Exclude the 5 checks with `--excluded-checks`, so no token for a write scope is ever requested (rule 1 read literally) | Keep the 5 checks and never authorize the scope: Google refuses the token (`unauthorized_client`) and the checks still score. Cost: one refused out-of-allowlist token request per failing check, which the live golden must expect. No Prowler patch or ADR-002 amendment needed |
| D7 | Google over-grant detection needs `admin.reports.audit.readonly` (the whole audit log, including Drive events with file titles). DWD authorizes scopes per client ID, so any process holding a key can mint every scope its client ID is authorized for | A second per-org "verifier" service account whose client ID is authorized only for `admin.reports.audit.readonly`; the customer adds two DWD entries. Google verification runs as a separate `verify` task whose role alone reads the verifier key; the scan task role cannot read it, and the key never enters the Prowler child. Cost: one more DWD entry, one more task start per scan, a third task role per org | One client ID with seven scopes: every process in the scan container, Prowler and its dependencies included, can read the whole audit log as any user. Or six scopes only: an over-granted scope cannot be detected, only never requested |
| D8 | Who creates the per-org Google service accounts | The owner, with a runbook script, for the pilot customers | Self-service provisioning job holding GCP IAM admin rights (later spec) |
| D9 | Google key custody | One JSON key per org service account in the credential store, rotated every 90 days | Keyless signJwt with workload identity federation (v1.1, needs a `setup_session` override, untested from Fargate) |
| D10 | Raw OCSF retention | The container strips `resources[].data.metadata` (full resource dumps, personal data) before upload; the manifest keeps the raw file's sha256 | Keep raw output as evidence; more personal data in the evidence store |
| D11 | Bundling ExchangeOnlineManagement and MicrosoftTeams (Microsoft licence terms) in Atesta's private image | The modules stay out of the image until the legal review clears; the Graph-only milestone does not wait for it (D1) | Bundle now for dev and golden tests; legal review before the first customer scan |
| D12 | Microsoft publisher verification | Launch gate for the first M365 customer (needs a Partner Program account and a verified domain; Owner steps) | Ship unverified; consent screen shows "Unverified" |
| D13 | Scan sizing and timeout | 2 vCPU, 4 GB, 60 min per attempt until the live golden test measures them | n/a: replaced by measurements |

## Acceptance criteria

### Connections

- [ ] Table `connections` (Data model below), tenant class, standard `tenant_isolation` policy,
      composite FKs and unique keys leading with `organization_id`. Onboarding state lives in a
      sealed cookie, not in a table.
- [ ] No connector secret in Postgres. `connections.credential_ref` and `verifier_credential_ref`
      hold references only; CHECKs accept only `aws-sm:<secret ARN in eu-south-2>` or
      `local:<name>`, and a Google reference must name that org's own secret, so a key, a PEM or
      another org's secret is rejected by the database.
- [ ] No API or worker process ever reads a connector secret. Secrets are resolved only inside the
      scanner container. `connections.api.get_credentials` is dropped from the planned interface.
- [ ] Microsoft 365 onboarding: Microsoft sign-in of the customer admin (tenant binding), then
      admin consent, then verification; from PR 10 a guided Global Reader assignment comes before
      verification (flow below). A callback whose `tenant` differs from the signed-in tenant, whose
      `state` does not match the sealed cookie, or whose cookie is missing, expired or for another
      org, is rejected.
- [ ] Google Workspace onboarding: per-org scan and verifier service accounts (D7), customer
      authorizes exactly the expected scopes for each client ID with domain-wide delegation, enters
      a super admin email, then verification (flow below).
- [ ] Read-only verification (CLAUDE.md rule 1) runs in the scanner image, before activation and
      before every scan, and fails closed. Granted must equal the expected set of the connection's
      allowlist version: any Graph application permission, delegated grant, Entra directory role,
      Exchange service principal pointer or Exchange role assignment held by the scanner app, and
      any Google scope or admin role held by the org's service accounts, outside it sets the
      connection `over_privileged` and blocks scans; anything missing sets `incomplete`. Grants the
      verifier cannot read are listed under Verifier limits, shown in onboarding and recorded in
      each verification report.
- [ ] The allowlist in `packages/core` (`atesta_core.connectors.readonly`) is versioned, pure and
      unit tested, and defines one exact expected set per provider and version, used by the
      verifier and the onboarding screens. It is written by hand, never derived from Microsoft's
      "least privileged" column (that column names a write permission for group listing). The
      scanner app registration's `requiredResourceAccess` is exported to the repo per environment;
      a unit test fails if it differs from the expected set, and the live golden reads the live
      registration through Graph and fails likewise.
- [ ] Disconnecting or revoking the org's last Google connection disables both of the org's
      service accounts and deletes their keys (owner runbook step within one business day until
      D8's job exists); the secrets are scheduled for deletion and `connection.disconnected`
      records it.
- [ ] Endpoints in the OpenAPI spec (table below). Errors return stable codes; ES and EN texts in
      the web i18n files.
- [ ] Audit events for every user-visible action (table below), ids only.

### Scanner image and wrapper

- [ ] `scanner/Dockerfile`: `python:3.13-slim` (trixie) pinned by digest, the same digest as
      `apps/Dockerfile` (#298); Prowler 5.52.0 from a
      hash-locked requirements file; PowerShell's native runtime packages installed with apt as
      the upstream 5.52.0 image does (`libicu76`, `libunwind8`, `libssl3`, `libcurl4`,
      `ca-certificates`); PowerShell 7.6.10 from the tarball with the sha256 the upstream 5.52.0
      image pins; no MSAL.PS; `POWERSHELL_TELEMETRY_OPTOUT=1`; non-root uid 10001.
- [ ] From PR 10 (D1, D11): ExchangeOnlineManagement and MicrosoftTeams at exact versions at or
      above 3.6.0 and 6.6.0, installed at build time for all users, each the newest release older
      than 7 days when that PR is opened.
- [ ] Nothing is installed at scan time: no `--init-modules`, no PowerShell Gallery access.
- [ ] Entrypoint is the Atesta wrapper `atesta-scan` (`scanner/atesta_scanner/`, mode `verify` or
      `scan`), not `prowler`. The wrapper fetches the credential, verifies, runs Prowler as a child
      process with a minimal environment, scrubs logs, strips personal-data fields, writes
      outputs and a manifest, and maps exit codes.
- [ ] The wrapper never passes `--push-to-cloud`, `--fixer`, `--status`, `--scan-secrets-validate`,
      `--tenant-id`, `--init-modules` or `--log-level DEBUG`/`INFO`. A unit test asserts the exact
      argv per provider.
- [ ] Image build fails if `prowler <provider> --list-checks-json` differs from the committed lists
      `scanner/expected/5.52.0/m365.json` (149 checks) and `googleworkspace.json` (65 checks).
      `m365-powershell.json` lists the 54 PowerShell-backed checks, excluded until PR 10.
- [ ] Scanner containers reach only the per-provider egress allowlist (Runners); everything else
      is denied and logged.

### Scan lifecycle

- [ ] Procrastinate 3.10.0 on the existing Postgres (ADR-003). Its four tables are classified in
      ADR-012 as queue tables before merge (amendment below). Job arguments are ids only.
- [ ] `scanning.api.queue_scan` inserts the `scans` row and defers `run_scan` in the same
      transaction (`SyncPsycopgConnector` on the session's psycopg connection, data-layer spec). A
      partial unique index allows one `queued` or `running` scan per connection; a violation is
      409 `scanning.already_queued` (schedule: skipped).
- [ ] "Scan now" has a daily budget (owner, 2026-11-23, #265): at most 6 `user` scans per
      connection per calendar day in Europe/Madrid. The 7th request is refused with 429
      `scanning.daily_limit`, a `retry_at` (the next Madrid midnight, ISO 8601 in UTC) and a
      `Retry-After` header in seconds; no scan row and no audit event are written. `schedule` and
      `activation` scans are never counted or refused. Every `user` scan queued that day counts,
      whatever its outcome.
- [ ] Every job enters tenant context only through
      `identity.api.enter_org_context(session, org_id, ContextReason.JOB)`. A job whose org and
      scan ids do not match finds no row and fails without retry.
- [ ] One scan attempt is one container run (Google: a `verify` run, then the scan run; D7): one
      Fargate `RunTask` per run in AWS (runner requirements below, built in the AWS spec), one
      `docker run` locally. No shared disk between attempts.
- [ ] Retries (Infrastructure tab): 3 retries of transient failures, after 300, 600 and 900 s
      (`RetryStrategy(max_attempts=3, wait=300, linear_wait=300,
      retry_exceptions=(ScanTransientError, OperationalError))`; a lost database connection is
      as transient as a failed engine run). Permanent failures (verification refused,
      connection not active) are never retried. A `run_scan` job that ends without a result
      (an unexpected error, or a database error on its last attempt) fails its scan with
      `scanning.engine_failed`, so no scan stays `queued` or `running` for good.
- [ ] Each scan end emits one structured `scan.finished` event (ids, provider, status, attempts,
      duration, error_code); a unit test asserts its fields. The failure-rate alert (more than 5%
      failed over 24 h, at least 20 scans, computed from these events, never by a cross-tenant
      query) is specified and built in the AWS spec.
- [ ] Per-attempt wall-clock timeout `ATESTA_SCAN_TIMEOUT_SECONDS` (default 3600); on timeout the
      runner stops the container and the attempt counts as transient.
- [ ] Daily schedule per active connection without cross-tenant reads: a `schedule_scan` job per
      connection re-defers itself 24 h ahead with `queueing_lock = "sched:<connection_id>"`.
- [ ] No two attempts of one connection run at once (`lock = "conn:<connection_id>"`). All Google
      Workspace scans share `lock = "gws-policy-api"` (1 QPS per GCP project, no increase).
      `run_scan` has no `queueing_lock` (Procrastinate locks below).

### Ingest, coverage and scoring

- [ ] Ingest reads only the manifest and files under `<org_id>/scans/<scan_id>/attempt-<n>/out/`
      of the attempt that exited 0, checks every sha256, and treats every string as untrusted data
      (rule 5).
- [ ] Tenant pin: every M365 finding has `cloud.org.uid` equal to the connection's tenant GUID;
      every Google finding has `cloud.account.uid` equal to the pinned customer id. One mismatch
      rejects the whole scan (`scanning.tenant_mismatch`).
- [ ] Findings keyed by (check id from `metadata.event_code`, `resources[0].uid`), never by
      `finding_info.uid` (it embeds resource names and changes on rename).
- [ ] Coverage: every expected check gets one `scan_check_results` row. An expected check with no
      finding is `not_evaluated`, never `pass` (ADR-005).
- [ ] Control results come only from catalog rows (`checks`, `control_checks`, active only). No
      framework name appears in this code (rule 9 guard test covers the new paths).
- [ ] After ingest commits, `snapshot_scores` calls `compliance.api.snapshot_framework` at
      REPEATABLE READ for every released framework, with the scan id. Idempotent per scan.
- [ ] The stripped OCSF file and manifest are registered as `evidence` (`scan_output`, source
      `scan`) and linked to every control the scan produced a result for. Scan outputs are
      write-once (Runners).

### Local development (no AWS)

- [ ] `ScanRunner`, `ScanStore` and `CredentialStore` protocols with local implementations:
      `LocalDockerRunner`, `LocalScanStore` (a directory laid out like the S3 prefix) and
      `LocalCredentialStore` (files outside the repo, mode 0600 enforced). `FixtureRunner`
      replays committed OCSF fixtures (synthetic first, recorded later) without Docker or
      credentials; like the wrapper, it drops findings of the checks its `job.json` excludes.
      The dev worker runs it with `ATESTA_SCAN_RUNNER=fixture`, `ATESTA_SCAN_STORE_DIR`,
      `ATESTA_SCAN_FIXTURES` and `ATESTA_SCANNER_EXPECTED`; `ATESTA_SCAN_RUNNER=docker` adds
      `ATESTA_SCAN_IMAGE`, `ATESTA_SCAN_CREDENTIALS_DIR`, `ATESTA_M365_CREDENTIAL_REF` (default
      `local:m365-scanner`) and `ATESTA_SCAN_NETWORK` (default `atesta-scan`). A credential file
      is `<name>.json` for `local:<name>`, holding the variables the wrapper expects.
- [ ] `docker compose` profile `scanner` builds the image. `uv run atesta-dev-scan` loads the
      synthetic catalog fixture `apps/api/tests/fixtures/catalog/` as `atesta_owner` (two synthetic
      frameworks, controls mapped to ids from the committed expected check lists; outside
      `catalog/frameworks/`), then runs ingest and scoring from a synthetic OCSF fixture with
      `ATESTA_CATALOG_INCLUDE_DRAFTS=true`, no network and no credentials, and fails unless it
      writes one snapshot per synthetic framework.
- [ ] Credentials reach the local container only on stdin (`docker run -i`; the wrapper reads stdin
      to EOF in local mode), never as `-e`, command-line values or a file mount.
- [ ] `LocalDockerRunner`, `LocalScanStore`, `LocalCredentialStore`, `FixtureRunner` and `local:`
      credential refs are dev-only: API and worker startup fail when `ATESTA_ENV=prod` and any of
      them is configured, and `connections.api.record_verification` refuses a `local:` ref in prod.
      One test per case, as in the local-dev-auth spec.
- [ ] Until the AWS spec's Fargate runner runs in eu-south-2, connections exist only for
      Atesta-owned test tenants; no customer tenant is connected or scanned (ADR-007).

### Golden tests

- [ ] Synthetic OCSF fixtures, committed in PR 3 under
      `scanner/fixtures/synthetic/{m365,googleworkspace}/`, hand-built from the committed expected
      check lists, no tenant data. They cover PASS, FAIL, MANUAL, muted, a service with no
      findings, a wrong tenant id and an unexpected check id. A unit test validates every finding
      against `py_ocsf_models` 0.10.0 `DetectionFinding`, the model Prowler 5.52.0 writes
      (Apache-2.0, dev dependency). Recorded anonymized fixtures from the live golden are added
      beside them later; the offline golden runs on both.
- [ ] Offline golden in CI (no tenant): expected check lists, catalog check ids, wrapper argv,
      image contents (pwsh and, from PR 10, module versions), `pwsh -NoProfile -NonInteractive
      -Command '$PSVersionTable.PSVersion.ToString()'` prints 7.6.10 as uid 10001 with the root
      filesystem read-only, and fixture ingest compared with committed expected results.
- [ ] Live golden (owner-run, test tenants): verify and scan against the M365 test tenant and the
      Google test tenant; records duration, peak memory and connect latency, and re-records the
      anonymized fixtures. Required before the first customer and for every Prowler bump
      (ADR-002). After each tenant re-creation the owner re-runs onboarding (consent, role,
      domain) before the golden run. Its results close the candidates listed below.

## Out of scope

- AWS connector (v1.1).
- Remediation, Prowler fixers and any write action on customer systems (rule 1). Prowler 5.52.0
  ships one M365 fixer that runs `Set-OrganizationConfig`; the `--fixer` flag exists only for
  the AWS provider, the wrapper never passes it, and the Global Reader role cannot write.
- Fargate runner, S3 bucket, Secrets Manager, KMS, IAM roles, egress control and the scan
  failure-rate alert (AWS spec). This spec fixes the requirements they must meet (Runners below).
- Self-service Google service account provisioning (D8).
- Keyless credentials: Google signJwt with federation, Microsoft federated credentials (v1.1).
- Connector limits per plan and daily-monitoring entitlement (ADR-009) until the org plan is stored
  (billing spec). Until then dev schedules every active connection daily.
- Customer notifications (notifications spec); web screens beyond the error codes (web spec).
- Findings retention and offboarding (NFR-08, offboarding spec).
- Muting and exceptions (FR-11). No Prowler mutelist is passed; a muted finding is stored with its
  status code.
- Government clouds (Prowler states they are not supported yet).
- Atesta gap checks (Google SPF, DKIM, DMARC; per-user 2SV) with engine `atesta`: catalog spec
  and a later scanner PR.

## Design notes

### Modules and public interfaces

| Module | Adds to `api.py` | Used by |
|---|---|---|
| connections | `create_connection`, `get_connection`, `list_connections`, `scan_target(session, org_id, connection_id) -> ScanTarget` (provider, external ids, credential refs, Google subject, allowlist version; never a secret), `record_verification(session, org_id, connection_id, report)`, `active_connection_ids(session, org_id)` | scanning, routes |
| scanning | `queue_scan(session, org_id, connection_id, trigger, requested_by)`, `latest_check_results(session, org_id) -> list[CheckResult]`, `get_scan` | routes, worker |
| compliance | `scoreable_framework_keys(session)` (released, not retired) next to `snapshot_framework` | scanning job |
| evidence | `register_scan_output(session, org_id, scan_id, key, sha256, size, media_type)` | scanning job |

Worker jobs live in `apps/worker` and call only these `api.py` functions. The scanner package
`scanner/atesta_scanner/` imports nothing from `apps/api`; it imports `atesta_core` for the
allowlist.

### Data model

| Table | Module | Columns |
|---|---|---|
| `connections` | connections | id, organization_id, provider (`m365`/`google_workspace`), status, display_name, external_tenant_id `text NULL` (M365 tenant GUID or Google customer id, set by the first successful verification, then immutable), ms_tenant_id NULL and consented_by_oid NULL (from the M365 sign-in and consent callbacks), allowlist_version NULL, primary_domain NULL, google_subject_email NULL, google_client_id NULL, credential_ref NULL, google_verifier_client_id NULL, verifier_credential_ref NULL, granted `jsonb NOT NULL DEFAULT '{}'` (the last verification report: `granted` permission, scope and role ids, `missing`, `extra` and `limits`; shown on the connection detail), verified_at NULL, revoked_at NULL, created_by, created_at, updated_at; UNIQUE (organization_id, id); partial UNIQUE (organization_id, provider, external_tenant_id) WHERE revoked_at IS NULL |
| `scans` | scanning | id, organization_id, connection_id (no FK: connections module), provider, trigger (`schedule`/`user`/`activation`), status, attempts, engine (`prowler`), engine_version, image_digest NULL, output_prefix NULL, manifest_sha256 NULL, error_code NULL, expected_checks, evaluated_checks, requested_by NULL, queued_at, started_at NULL, finished_at NULL, ingested_at NULL; UNIQUE (organization_id, id); partial UNIQUE (organization_id, connection_id) WHERE status IN ('queued', 'running') |
| `scan_check_results` | scanning | organization_id, scan_id, engine, check_id, status (`pass`/`fail`/`manual`/`not_evaluated`), reason NULL (`no_findings`/`excluded`/`not_granted`), pass_count, fail_count, manual_count; PK (organization_id, scan_id, engine, check_id); FK (organization_id, scan_id) |
| `findings` | scanning | id, organization_id, scan_id, engine, check_id, status (`pass`/`fail`/`manual`), muted, severity, service, resource_type, resource_uid, resource_name, region, message, created_at; UNIQUE (organization_id, id); FK (organization_id, scan_id); index (organization_id, scan_id, check_id) |

- Statuses: connections `pending_provisioning`, `pending_setup`, `verifying`, `incomplete`,
  `active`, `over_privileged`, `revoked`, `disconnected`; scans `queued`, `running`, `collected`,
  `succeeded`, `partial`, `failed`, `blocked`. `text` plus CHECK (data-layer conventions).
- CHECKs: both refs match
  `^(aws-sm:arn:aws:secretsmanager:eu-south-2:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]{1,512}|local:[a-z0-9][a-z0-9-]{0,62})$`;
  on Google rows `credential_ref` names `atesta/<env>/google/<organization_id>-??????` or
  `local:google-<organization_id>`, and `verifier_credential_ref` names
  `atesta/<env>/google-verifier/<organization_id>-??????` or
  `local:google-verifier-<organization_id>` (Secrets Manager appends six random characters);
  `status <> 'active' OR external_tenant_id IS NOT NULL`; an active Google connection has both
  refs, both client ids and `google_subject_email`; M365 rows have both refs NULL (the platform
  credential is not per connection).
- Grants for `atesta_app`: `connections`, `scans` SELECT, INSERT, UPDATE (a removed connection
  becomes `disconnected`, never deleted); `scan_check_results` and `findings` INSERT, SELECT
  (append-only).
- `findings.message` (Prowler's `status_extended`) and `resource_name` may hold names and email
  addresses: tenant data under RLS, escaped on display, never sent to logs or to the AI as
  instructions.
- Ingest idempotency: `scans.ingested_at` is set in the same transaction as the inserts; a
  retried ingest that finds it set returns.

### Credentials

| Connector | Credential | Where it lives | Who reads it |
|---|---|---|---|
| M365 | One Atesta certificate (passwordless PFX) for the multi-tenant "Atesta Scanner" app | AWS: Secrets Manager in eu-south-2 under a customer-managed KMS key. Local: `LocalCredentialStore` | M365 verify and scan tasks only, at start |
| M365 sign-in | Credential of the "Atesta Sign-in" app (`openid profile` only, no application permissions, grants nothing in customer tenants) | API secret store | API, for the code exchange |
| Google scan | One service account JSON key per Atesta org, in Atesta's dedicated GCP project | Same stores as M365, `atesta/<env>/google/<org_id>` | That org's Google verify and scan tasks |
| Google verifier (D7) | One more service account key per org, client ID authorized only for `admin.reports.audit.readonly` | `atesta/<env>/google-verifier/<org_id>` | That org's Google verify task only |

- The wrapper fetches the credential at start (task role in AWS, stdin locally) and places it
  only in the Prowler child process environment (`M365_CERTIFICATE_CONTENT`, `AZURE_CLIENT_ID`;
  `GOOGLEWORKSPACE_CREDENTIALS_CONTENT`, `GOOGLEWORKSPACE_DELEGATED_USER`). The M365 secret never
  names a tenant (D5): the wrapper sets `AZURE_TENANT_ID` from the job's pinned tenant and refuses
  a secret that carries one, so a scan reaches only the pinned tenant. It
  never writes it to disk, logs it, or puts it in the manifest. Prowler then mints its own
  short-lived tokens.
- Prowler 5.52.0 accepts neither a pre-issued token nor a remote signer for M365 or Google, so the
  long-lived private key must be inside the scan container for the task's lifetime. ADR-004's
  "short-lived tenant credentials" is amended (below).
- Blast radius: task roles are per org and per provider (Runners), so Google tasks cannot read the
  M365 certificate and a Google scan task cannot read the verifier key. Within M365 nothing is
  isolated: every M365 role reads the one certificate, and that certificate reads every
  consenting tenant. Mitigations: certificate only (Microsoft advises against secrets), app
  instance property lock on, two overlapping certificates during yearly rotation, deny-by-default
  egress (Runners), Secrets Manager read only by M365 roles, and Atesta's kill switch (deactivate
  the app or remove the certificate). D5 is the alternative.
- Google keys: at most 10 per service account (GCP hard limit); rotation creates the new key,
  updates the secret, then deletes the old key. The runbook writes a new key only to a tmpfs
  path, stores it in the credential store, then deletes the file; it never lands on persistent
  disk or in shell history. Atesta's GCP organization must exempt the dedicated project from the
  default key-creation block for orgs created on or after 2024-05-03 (Owner steps).

### Microsoft 365 onboarding

App registrations in Atesta's Entra tenant, separate for dev and prod (Microsoft recommends it):
"Atesta Scanner" (multi-tenant, application permissions below, certificate only, instance
property lock on, redirect URI `/auth/m365/consent-callback`) and "Atesta Sign-in"
(multi-tenant, `openid profile` only, no application permissions, redirect URI
`/auth/m365/signin-callback`). Redirect URIs are https, fixed and exactly registered; per-request
data travels only in the sealed cookie.

The Sign-in app redeems codes as a confidential web client, with PKCE and a client secret:
Microsoft documents `client_secret` as "required for confidential web apps" (OAuth 2.0
authorization code flow, read 2026-11-23, #314). Its secret can only redeem sign-in codes for an
app with no permissions, so it is a secret, not a certificate. It is held in Secrets Manager,
passed to the API as `ATESTA_M365_SIGNIN_CLIENT_SECRET` and rotated at least every 180 days; the
Scanner app stays certificate only. With `ATESTA_M365_SIGNIN_CLIENT_ID`, the secret and
`ATESTA_M365_SCANNER_CLIENT_ID` unset, onboarding answers 503 `connections.microsoft_unavailable`.

1. An org admin creates the connection: `pending_setup`.
2. `POST /api/v1/orgs/{org_id}/connections/{id}/m365/signin` seals {org_id, connection_id,
   user_id, `state` (32 random bytes), nonce, PKCE verifier} in an `atesta_m365` cookie (sealed as
   in the BFF login, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/auth`, 10 min; no DB row) and
   returns the authorize URL of the sign-in app on the `organizations` endpoint (code + PKCE,
   `openid profile`).
3. `GET /auth/m365/signin-callback` (session cookie; caller still admin+ of the sealed org) checks
   `state`, exchanges the code and validates the ID token (signature, audience, nonce, expiry,
   issuer for its `tid`). An ID token without `oid` or `tid` is rejected
   (`connections.signin_invalid`, as are a missing or other user's cookie and a wrong `state`;
   `connections.state_invalid` keeps meaning a connection that no longer admits the change);
   `sub` is never used for the binding (it is pairwise per app). It
   re-seals the cookie with `tid`, `oid` and a new `state`, then redirects to
   `https://login.microsoftonline.com/{tid}/adminconsent?client_id=<scanner app>&state=<new
   state>&redirect_uri=<registered>`.
4. `GET /auth/m365/consent-callback` (same access) is accepted only with the sealed `state`,
   `admin_consent=True`, no `error`, and `tenant` equal to the sealed `tid`. Microsoft warns that
   the callback's `tenant` can be forged, hence step 3. A refusal is `connections.consent_denied`
   (`error` present or `admin_consent` not `True`) or `connections.tenant_mismatch` (another
   tenant, or one other than the tenant pinned by an earlier verification). It stores
   `ms_tenant_id` and `consented_by_oid` on `connections`, writes `connection.consent_granted`,
   deletes the cookie (single use) and redirects to the static connection page. Granting Graph application permissions needs Privileged Role
   Administrator or a role with that right, such as Global Administrator.
5. From PR 10 (D1): the screen shows the scanner Application ID and verified publisher, and guides
   the customer to assign Global Reader to the enterprise app whose Application ID matches. Portal
   steps say to compare the Application ID, not the name. The PowerShell snippet selects the
   service principal with `Get-MgServicePrincipal -Filter "appId eq '<scanner app id>'"` and stops
   unless exactly one object is returned. Consent does not assign roles, and Atesta cannot assign
   one with read-only access.
6. `POST .../verify` (admin+) needs an M365 connection that is still onboarding and holds
   `ms_tenant_id` and `consented_by_oid` (else 409 `connections.state_invalid`). It sets
   `verifying`, records `connection.verification_requested` and queues the connection's
   **activation scan** (#331). M365 scans verify at step 0 in the same container, so the
   verification and the first scan are one run, with no separate `verify` job.
   - An activation scan may run on a `verifying` connection, and only an activation scan may. Its
     `job.json` pins `ms_tenant_id` (the tenant is pinned to `external_tenant_id` only by this
     verification) and carries `admin_oid`, the consenting admin's object id. Scheduled and user
     scans carry no `admin_oid`.
   - Besides the read-only checks, the wrapper confirms that `admin_oid` holds Global
     Administrator (`62e90394-69f5-4237-9190-012177145e10`) or Privileged Role Administrator
     (`e8611ab8-c189-46e8-94e1-60213ab1f814`) in that tenant, from the role assignments where it is
     the principal. Otherwise the verdict is `incomplete`, missing `consenting_admin_role`. This
     way a non-admin of a tenant that already consented for another Atesta org cannot link it. A
     role held only through a group is a candidate limit until the live golden.
   - Pass: `record_verification` pins the tenant (it must equal `ms_tenant_id`), sets `active`, the
     scan goes on and the daily schedule chain starts. A refusal gives the connection its status
     (`incomplete`, `over_privileged`, `revoked`) and ends the scan `blocked`. A verified tenant
     other than `ms_tenant_id` ends it `blocked` with `scanning.tenant_mismatch` and activates
     nothing.

Nothing logs the query string of either callback. Revocation by the customer: Enterprise apps,
Atesta Scanner, Properties, Delete (restorable for 30 days), or revoke its permissions, and remove
the Global Reader assignment (from PR 10). Atesta detects it at the next verification (token or
grant check fails), sets `revoked`, stops scans and records `connection.revoked`. Tokens issued
before revocation may work until they expire (candidate).

### Microsoft 365 permission allowlist

Expected set v1 (Graph-only), application permissions on Microsoft Graph
(`00000003-0000-0000-c000-000000000000`), all read and admin-consent only:

| Permission | Id | Why |
|---|---|---|
| AccessReview.Read.All | d07a8cc0-3d51-4b77-b3b0-32704d1f69fa | Access review checks |
| AuditLog.Read.All | b0afded3-3588-46d8-8b3d-9842eff778da | userRegistrationDetails (MFA) |
| Policy.Read.All | 246dd0d5-5bd0-4def-940b-0421030a5b68 | Conditional access and tenant policies |
| Policy.Read.DeviceConfiguration | bdba4817-6ba1-4a7c-8a01-be9bc7c242dd | Device registration policy (D4) |
| RoleManagementPolicy.Read.Directory | fdc4c997-9942-4479-bfcb-75a36d1138df | PIM policies |
| RoleManagement.Read.Directory | 483bed4a-2ad3-4361-a73b-c83ccdbdc53c | Roles, role assignments, verifier |
| SecurityIdentitiesHealth.Read.All | f8dcd971-5d83-4e1e-aa95-ef44611ad351 | Defender for Identity health |
| SecurityIdentitiesSensors.Read.All | 5f0ffea2-f474-4cf2-9834-61cda2bcea5c | Defender for Identity sensors |
| SharePointTenantSettings.Read.All | 83d4163d-a2d8-4d3b-9695-4ae3ca98f888 | SharePoint settings |
| DeviceManagementServiceConfig.Read.All | 06a5fe6d-c49d-46a7-b082-56b1b14103c7 | Intune settings (Prowler's choice, candidate) |
| DeviceManagementConfiguration.Read.All | dc377aa6-52d8-4e23-b271-2a7ae04cedf3 | Intune compliance policies |
| DeviceManagementManagedDevices.Read.All | 2f51be20-0bb4-4fed-bf7b-db946066c75e | Managed devices |
| Organization.Read.All | 498476ce-e0fe-48b0-b801-37ba7e2685c6 | Provider init; all Teams cmdlets |
| User.Read.All | df021288-bdef-4463-88db-98f22de89214 | Users |
| GroupMember.Read.All | 98830695-27a2-44f7-8c18-0c3ebc9698f6 | Groups (read-only option) |
| Application.Read.All | 9a5d68dd-52b0-4cc2-bd40-abcf44ac3a30 | Apps, service principals, verifier (steps 3, 5c) |
| Domain.Read.All | dbb9058a-0e50-45d7-ae91-66909b5d4664 | Provider init (`/domains`) |
| GroupSettings.Read.All | f3c4f514-c65a-43f5-bfce-1735872258dd | Group settings |
| LicenseAssignment.Read.All | e2f98668-2877-4f38-a2f4-8202e0717aa1 | subscribedSkus |
| DelegatedPermissionGrant.Read.All | 81b4724a-58aa-41c1-8a55-84ef97466587 | Verifier step 4 (delegated grants of the scanner app; candidate) |
| Directory.Read.All | 7ab1d382-f21e-4acd-a863-ba3e13f7da61 | Not in the expected set (D2); becomes expected only by an allowlist version bump |
| ThreatHunting.Read.All | dd98c7f5-2d42-42d3-a0e4-633161547251 | Never on Atesta Scanner (D3) |

- Expected set v2 (PR 10) adds Office 365 Exchange Online (`00000002-0000-0ff1-ce00-000000000000`)
  `Exchange.ManageAsApp` (`dc50a0fb-09a3-484d-be87-e023b12c6440`) and the directory role Global
  Reader (`f2ef992c-3afb-46b9-b7cf-a126ee74c451`) at scope `/`, nothing else. Its name says
  "Manage", but session rights come from the Entra role in the token, here Global Reader. v1
  expects no directory role.
- Never requested: `OnPremDirectorySynchronization.Read.All` (Microsoft: application permissions
  not supported). Prowler still emits a finding for `entra_seamless_sso_disabled` and
  `entra_directory_sync_object_takeover_blocked`: PASS when no organization has on-premises sync
  (cloud-only), MANUAL for a hybrid tenant whose sync settings cannot be read. Both are ordinary
  expected checks. Also never requested: Skype and Teams Tenant Admin API `application_access`
  (Microsoft: configuring it may cause failures; the certificate path does not use it).
- Excluded checks while D3 is off: `entra_app_registration_no_unused_privileged_permissions`,
  `defenderxdr_critical_asset_management_pending_approvals`,
  `defenderxdr_endpoint_privileged_user_exposed_credentials` (reason `not_granted`). Until PR 10,
  also the 54 in `m365-powershell.json` (reason `not_granted`).

### Google Workspace onboarding

1. An org admin creates the connection. If the org has no service accounts yet: status
   `pending_provisioning`, and the owner runs the runbook (`scanner/runbooks/google_sa.sh`, gcloud)
   that creates the org's scan and verifier service accounts and keys in Atesta's dedicated GCP
   project, stores the keys in the credential store and defers `register_google_client` (a job,
   so it enters context with reason `job`; the ref CHECKs reject another org's secret). Then
   `pending_setup`.
2. The screen shows both client IDs, each with its exact comma-separated scope string, and the
   path: Admin console, Security, Access and data control, API controls, Manage Domain Wide
   Delegation, Add new. A super admin must do it, and a second super admin approves if
   multi-party approval is on.
3. The customer enters the super admin email to impersonate and the primary domain
   (`PUT .../google`). Onboarding explains: Google logs Atesta's reads as that user; delegation
   reaches the data of all users within the granted scopes; a suspended, renamed or demoted
   account stops scans; a dedicated account can push `directory_super_admin_count` from 4 to 5
   (FAIL).
4. `POST .../verify` runs the scanner image in `verify` mode. Google says changes can take up to
   24 hours, so `unauthorized_client` keeps the connection `verifying` and the job re-defers
   itself hourly for 24 h before `incomplete`.
5. When the org's last Google connection that is not disconnected becomes `disconnected` or
   `revoked`, both service accounts are disabled and their keys deleted (Connections criteria).

Scope allowlist, all under `https://www.googleapis.com/auth/`. Scan client:
`admin.directory.user.readonly`, `admin.directory.domain.readonly`,
`admin.directory.customer.readonly`, `admin.directory.orgunit.readonly`,
`admin.directory.rolemanagement.readonly`, `cloud-identity.policies.readonly` (the six Prowler
requests). Verifier client: `admin.reports.audit.readonly` only (D7). Never requested:
`apps.licensing`, `apps.alerts`, `apps.groups.settings`, `admin.directory.user.security`: Google
describes each as manage, delete or "view and manage" access.

One service account per Atesta org closes a confused-deputy hole: with one shared client ID, an
org A user could enter a super admin of domain B, which already authorized that client ID for org
B, and Prowler's domain check would pass. With a per-org client ID, domain B has authorized only
org B's. Revocation by the customer: delete the clients in the same Admin console page; Google says
dependent apps stop immediately.

### Read-only verification

Runs in the scanner image (`atesta-scan verify`), so only a container that already holds the
credential uses it. M365: step 0 of `atesta-scan scan` in the same container. Google: a separate
`verify` run that holds both keys and runs no Prowler, then the scan run re-checks steps 1 and 2
with the scan key only (D7). Output is a JSON report of ids and verdicts.

| Step | Microsoft 365 | Google Workspace |
|---|---|---|
| 1 Token | Client credentials with the certificate for Graph. Failure: `revoked` (scans) or `incomplete` (onboarding) | Delegated token with the scan key for exactly the six Prowler scopes, and with the verifier key for the reports scope. Google requires an exact scope match, so success proves those were authorized; `unauthorized_client` means missing |
| 2 Identity pin | `GET /organization` id equals `ms_tenant_id` (first verification pins `external_tenant_id`) | `customers.get('my_customer')` id equals the pinned one; subject's domain is in `domains.list`; `users.get(subject)` is a super admin |
| 3 Granted permissions | `GET /servicePrincipals(appId='<scanner>')`, then `/appRoleAssignments`: the set of (resource, app role id) equals the expected set of the connection's allowlist version; second gate: every role name has a `Read` segment and no segment containing `Write`, `Manage`, `Send`, `Create`, `Delete` or `Update` (`User.Read.All` and `Policy.Read.DeviceConfiguration` pass, `User.ReadWrite.All` fails), except `Exchange.ManageAsApp` | Reports `activities.list` (`admin`, event `AUTHORIZE_API_CLIENT_ACCESS`) for each client ID: `API_SCOPES` equals that client's expected set; `REMOVE_API_CLIENT_ACCESS` means revoked. Then `roleAssignments.list(customer='my_customer')`, all pages, with the scan key and `admin.directory.rolemanagement.readonly`: any assignment whose `assignedTo` equals either service account's IAM `uniqueId` gives `over_privileged`. Re-reads on every scan use event time with a 1 h overlap before the last verification (admin log events lag a few minutes) |
| 4 Delegated grants | `/servicePrincipals/{id}/oauth2PermissionGrants` is empty (`DelegatedPermissionGrant.Read.All`, candidate) | n/a (no consent screen) |
| 5 Directory roles | `/roleManagement/directory/roleAssignments?$filter=principalId eq '<sp id>'`: none (v1), exactly Global Reader at `/` (v2) | In step 3 |
| 5b Exchange RBAC (v2) | After `Connect-ExchangeOnline`: `Get-ServicePrincipal` returns no object whose AppId is the scanner app (Atesta never creates the Exchange pointer; Option 1 needs none, Option 2 and RBAC for Applications both need it), and `Get-ManagementRoleAssignment -RoleAssignee <sp object id>` returns nothing. Any result: `over_privileged` | n/a |
| 5c Roles through groups (candidate) | `GET /servicePrincipals/{id}/transitiveMemberOf` contains no directoryRole and no group with `isAssignableToRole = true` | n/a |
| 5d Azure RBAC (candidate) | App-only token for `https://management.azure.com` and `GET /subscriptions` list no subscription; any subscription means an Azure role: `over_privileged` | n/a |
| 6 Binding (onboarding only) | `consented_by_oid` holds Global Administrator or Privileged Role Administrator | Only a super admin can authorize the org's client IDs (DWD) or assign them a role; both are checked in step 3 |

- Verdicts: `ok`, `incomplete` (something missing; actionable message), `over_privileged`
  (anything extra; scans blocked until the customer removes it), `revoked`, `transient` (429,
  5xx, network; retried with the scan).
- Google retention: the grant events are read at activation; each scan reads only events since
  the last verification (with the overlap), so the 6-month retention of admin events never removes
  the evidence needed.
- The token's `roles` claim is a fast pre-check only: Microsoft says `roles` and `wids` are not an
  exhaustive list of what the caller holds. Step 3 is authoritative.
- Verifier limits (shown in onboarding, recorded in every report): until PR 10 the M365 verifier
  has no Exchange session, so Exchange service principal pointers, role groups and RBAC for
  Applications grants to the scanner app are not read (D1); steps 5c and 5d until the live golden
  confirms them (a step that proves impossible moves here and its criterion narrows); a Google
  admin role assigned to a group that contains a service account (candidate); tokens issued
  before revocation.

### Scanner image

| Layer | Pin | Note |
|---|---|---|
| Base | `python:3.13.x-slim-trixie@sha256:<digest>`, the same digest as `apps/Dockerfile` | Prowler requires Python >=3.10,<3.14, so 3.13 is the newest it allows (#298). Prowler's own image stays on 3.12; only the base differs from it, the PowerShell and apt pins do not. Debian 13 (trixie) |
| PowerShell runtime libs | `libicu76`, `libunwind8`, `libssl3`, `libcurl4`, `ca-certificates` from the Debian 13 archive of the pinned base | Required by .NET on Debian 13 (no ICU: the app fails to start); upstream installs the same |
| Prowler | 5.52.0, wheel sha256 `b9134bdbf4899cbb2ef36e1bb1432d97b2af19a155d7f9861086f780a3ca0a96`, hash-locked deps; resolved with the 7-day cooldown, Prowler alone exempted by its publish date (`--exclude-newer-package`) | Apache-2.0 |
| PowerShell | 7.6.10 x64 tarball, upstream sha256 | MIT. Needed from PR 5: with certificate auth the M365 provider always starts `pwsh`; without it every M365 scan exits 1 |
| ExchangeOnlineManagement | PR 10: exact version, >= 3.6.0, >= 7 days old | Microsoft licence terms (D11) |
| MicrosoftTeams | PR 10: exact version, >= 6.6.0, >= 7 days old | Use tied to the customer's subscription (D11) |
| MSAL.PS | not installed | Used only by Prowler's client-secret Exchange path; last release 2021-11-19 |
| `atesta_scanner`, `atesta_core` | from the repo | Wrapper and allowlist |

`HOME` is a tmpfs so PowerShell can write its caches with a read-only root filesystem (offline
golden). The extracted PowerShell is about 172 MB.

### Prowler invocation

```text
prowler m365 --certificate-auth -M json-ocsf -o /work/out -F prowler --no-banner \
  --log-level ERROR --log-file /work/prowler.log -z \
  --excluded-checks <m365-powershell.json until PR 10> <D3 checks>
prowler googleworkspace -M json-ocsf -o /work/out -F prowler --no-banner \
  --log-level ERROR --log-file /work/prowler.log -z --excluded-checks <D6 checks>
```

- `-z` (`--ignore-exit-code-3`): FAIL findings do not change the exit code. Exit 1 is a provider
  init failure.
- Output is one JSON array, `/work/out/prowler.ocsf.json`, of OCSF Detection Findings.
- D6 checks: `security_session_duration_limited`, `security_dlp_drive_rules_configured`,
  `drive_shared_drive_members_only_access`, `drive_shared_drive_managers_cannot_override`,
  `drive_shared_drive_disable_download_print_copy` (the only five that read `provider.editions`,
  and only on FAIL).

Wrapper exit codes: 0 done; 10 verification refused (permanent); 11 credential unavailable; 12
verification transient; 20 Prowler failed; 30 output invalid (missing file, bad JSON, wrong
tenant). The runner adds 21 timeout. All but 10 are transient.

### Scan lifecycle

| Job | Args | Lock | Retry | Effect |
|---|---|---|---|---|
| `schedule_scan` | organization_id, connection_id | queueing_lock `sched:<connection_id>` | 3, transient database errors only (a lost job would end the chain) | If the connection is active: `queue_scan(trigger=schedule)` (skipped on `already_queued`); always re-defers itself +24 h while the connection is not `disconnected` or `revoked` |
| `register_google_client` | organization_id, connection_id, both client ids, both credential refs | none | none | Owner runbook result; sets `pending_setup` |
| `verify_connection` | organization_id, connection_id | `conn:<connection_id>` | none (re-defers hourly up to 24 h while `verifying`) | Runs `verify` mode, `connections.api.record_verification` |
| `run_scan` | organization_id, scan_id | `conn:<connection_id>` (M365), `gws-policy-api` (Google); no queueing_lock | 3, transient only | Below |
| `ingest_scan` | organization_id, scan_id | none | 3 | Ingest, coverage, control results, evidence |
| `snapshot_scores` | organization_id, scan_id | none | 3 | One snapshot per released framework |
| `retry_stalled_jobs` | none (periodic, 5 min) | none | n/a | `get_stalled_jobs` (worker heartbeat) then `retry_job` |

Procrastinate 3.10.0 locks (`sql/schema.sql:99`, `:209-260`, `:366-396`): a job waits behind
every job with the same `lock` that is `doing`, or `todo` with a lower id, including one waiting
for a retry; `queueing_lock` is unique among `todo` jobs only, and a retry returns the same row to
`todo`. Hence `run_scan` relies on the `scans` partial unique index, not a queueing lock (a retry
could otherwise violate it), and a Google scan in retry backoff delays all Google scans by up to
1,800 s and an M365 scan in backoff delays `verify_connection` of that connection: accepted for
v1, measured in the live golden test.

`run_scan`, one attempt:

1. Transaction: enter org context (`job`); lock the scan row; return if it is past `running`;
   read `ScanTarget`; block (`scanning.connection_not_active`) if not active; set `running`,
   `attempts = job.attempts + 1`; the worker writes `job.json` (ids, expected tenant id, credential
   refs, Google subject, excluded checks, allowlist version; no secret) to
   `<org_id>/scans/<scan_id>/attempt-<n>/`; commit.
2. Runner calls with no transaction open (Google: `verify` run, then scan run), bounded by the
   timeout.
3. Transaction: exit 0 sets `collected` and defers `ingest_scan`; exit 10 sets `blocked` and
   records the verification report on the connection; a transient exit records `error_code` and
   raises `ScanTransientError` while `job.attempts < 3`, otherwise sets `failed`. Each terminal
   status writes an audit event and the `scan.finished` event.

"Scan now" (`POST .../scans`) returns 409 `scanning.already_queued` when the connection has a scan
`queued` or `running`.

Each scan reads the customer's whole tenant, and Microsoft Graph and Google's APIs throttle per
tenant and per app, so manual scans have a budget (#265): 6 `user` scans per connection per
Madrid calendar day. `queue_scan(trigger=user)` counts that connection's `user` scans queued since
the last Madrid midnight, read from the database clock, before it inserts; the 7th returns 429
`scanning.daily_limit` with `retry_at` (the next Madrid midnight in UTC) and `Retry-After`. The
day follows the Madrid calendar, so it is 23 h long in March and 25 h in October. The one-active
index already serialises requests for a connection, so two concurrent requests cannot both pass
the count. `schedule` and `activation` scans keep their own cadence and are not counted. The
count reads the tenant's own scans through the `(organization_id, id)` index; no new index.

### Runners

| | Local (this spec) | Fargate (AWS spec builds it to these requirements) |
|---|---|---|
| Start | `docker run -i --rm --user 10001 --read-only --tmpfs /work --tmpfs /home/scanner --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 4g --network atesta-scan` | One `RunTask` per run, task definition pinned to the image digest |
| Ids | `-e` with ids only | `containerOverrides.environment` with ids only. ECS overrides have no `secrets` member and are plain key-value pairs |
| Credential | `LocalCredentialStore` file streamed to the container's stdin | Wrapper reads the secret with the task role |
| Network | `atesta-scan` network whose only way out is an allowlisting proxy with the Fargate host list; `FixtureRunner` and `atesta-dev-scan` use `--network none` | No public IP. Egress only through an allowlisting proxy or AWS Network Firewall domain/SNI allowlist. M365: login.microsoftonline.com, graph.microsoft.com, management.azure.com (step 5d); from PR 10 outlook.office365.com and the Teams PowerShell endpoints. Google: oauth2.googleapis.com, admin.googleapis.com, cloudidentity.googleapis.com. AWS only through VPC endpoints in eu-south-2 (S3, Secrets Manager, KMS, CloudWatch Logs). Everything else denied and logged (host list: candidate) |
| Tenant scoping | Mount `<root>/<org_id>/scans/<scan_id>/attempt-<n>/out/` read-write and that attempt's `job.json` read-only, nothing else | Task role per org and provider (`overrides.taskRoleArn`): `scan-m365-<org_id>` reads only the M365 certificate; `verify-gws-<org_id>` reads only that org's two Google keys; `scan-gws-<org_id>` reads only `atesta/<env>/google/<org_id>`. S3: PutObject only under `<org_id>/scans/*/attempt-*/out/*`, GetObject only `<org_id>/scans/*/attempt-*/job.json`; a bucket policy denies these roles PutObject without `s3:if-none-match` (multipart parts exempted with `s3:ObjectCreationOperation`), `s3:DeleteObject*`, `s3:PutObjectAcl` and any write to `*/job.json`; versioning on. Created with a permissions boundary. Three roles per org: 333 orgs per account by default (1,000 roles), 3,333 at most |
| Output | `LocalScanStore` | S3 under the tenant prefix, eu-south-2 |
| Logs | Wrapper's own JSON lines only | Same, to CloudWatch in eu-south-2 |
| Timeout | Kill the container | `StopTask` |

### Ingest

1. Read `manifest.json` from the `out/` of the attempt that exited 0; check the sha256 and size of
   each listed file; reject above `ATESTA_OCSF_MAX_BYTES` (default 100 MB, revisit after the live
   golden test).
2. Parse with a strict model of only the fields Atesta keeps; ignore the rest.
3. Tenant pin (criteria above).
4. Insert `findings`: `status_code` PASS, FAIL, MANUAL to `pass`, `fail`, `manual`; `status`
   Suppressed sets `muted`; severity, `resources[0]` uid, name, type, `group.name` (service),
   region; `message` from `status_extended`.
5. Coverage (next section), then control results, evidence registration, `ingested_at`, then
   defer `snapshot_scores`, all in one transaction.

### Coverage

Expected checks per provider come from the committed `--list-checks-json` output for the pinned
version, minus excluded checks (reason `excluded` or `not_granted`).

- Every expected check with at least one finding: `fail` if any unmuted FAIL, else `pass` if any
  PASS, else `manual`.
- Every expected check with none: `not_evaluated`, reason `no_findings`. Prowler emits nothing,
  and no error finding, when a PowerShell connect times out (10 s commands, 15 s connects) or a
  Google Policy API page fails (no retries, 1 QPS); both look exactly like this.
- A whole Prowler service with zero findings on an attempt that is not the last raises
  `ScanTransientError` once more (cold-start connects). After the last attempt the scan ends
  `partial`, ingested with those checks `not_evaluated`. Excluded checks are not expected, so a
  Graph-only scan never trips this.
- A check id in the output but not expected rejects the scan (`scanning.output_invalid`): the
  image and the expected list disagree.

### Findings to controls to scores

- In-scope checks for an org: active `control_checks` rows whose check belongs to a provider of an
  active connection (provider known from the expected lists).
- Check results used: for each active connection, its latest ingested scan
  (`scanning.api.latest_check_results`). One connection's scan never erases another's results.
- Control status: `fail` if any in-scope check is `fail`; `pass` if every in-scope check is
  `pass`; `manual` if none fails and at least one is `manual`; no result otherwise (any
  `not_evaluated` check keeps the control unassessed, ADR-005). Controls with `manual: true` have
  no checks and no result here.
- `snapshot_scores` runs at REPEATABLE READ and calls `compliance.api.snapshot_framework` for each
  key from `compliance.api.scoreable_framework_keys`, with `applicability = {}` and
  `scope_id = NULL` until categorization lands (control-model spec).
- Evidence: the stripped OCSF file and manifest become `evidence` rows (`scan_output`, source
  `scan`, `source_id` = scan id, key `<org_id>/scans/<scan_id>/attempt-<n>/out/<file>`, which
  passes the evidence key CHECK) linked through `evidence_controls` to every control with a result.

### Logs and personal data (rule 2)

- Prowler's stdout, stderr and log file never reach the container log stream. At ERROR, Prowler
  logs PowerShell stderr and unparseable PowerShell output, which can hold tenant data; the PFX is
  sent to `pwsh` as a command string (`[Convert]::FromBase64String("...")`), so a PowerShell error
  echoing that line would carry the key (candidate). The Google provider logs the impersonated
  email at INFO and every user's email at DEBUG.
- The wrapper scrubs the Prowler log (exact secret values and their base64 forms, JWT-shaped
  strings, base64 runs over 200 characters) and stores it in `out/` as `prowler.log` for support.
  Its own log lines carry ids, phases, exit codes and counts only.
- Before upload the wrapper removes `resources[].data.metadata` from the OCSF file (D10): it is
  the full pydantic dump of each resource (users, mailboxes, transport rules) and M365 models
  declare no redacted fields.
- `google_subject_email` is stored in `connections` and never logged; it reaches the container
  through `job.json`, not through overrides.

### Endpoints

| Method and path | Allowed | Effect |
|---|---|---|
| `POST /api/v1/orgs/{org_id}/connections` | admin+ | Create (`provider`, `display_name`) |
| `GET /api/v1/orgs/{org_id}/connections` | member+ | List with status |
| `GET /api/v1/orgs/{org_id}/connections/{id}` | member+ | Detail, last verification report, verifier limits, setup data (client IDs, scope strings, permission list) |
| `POST /api/v1/orgs/{org_id}/connections/{id}/m365/signin` | admin+ | Seals the `atesta_m365` cookie; returns the authorize URL |
| `GET /auth/m365/signin-callback` | session cookie, still admin+ of the sealed org | Fixed registered redirect URI; step 3; redirects to `/adminconsent` |
| `GET /auth/m365/consent-callback` | session cookie, still admin+ of the sealed org | Fixed registered redirect URI; step 4; redirects to the static connection page |
| `PUT /api/v1/orgs/{org_id}/connections/{id}/google` | admin+ | Subject email and primary domain |
| `POST /api/v1/orgs/{org_id}/connections/{id}/verify` | admin+ | Queue verification |
| `DELETE /api/v1/orgs/{org_id}/connections/{id}` | admin+ | `disconnected`; returns the customer-side revocation steps; Google: starts the service account disable step |
| `POST /api/v1/orgs/{org_id}/connections/{id}/scans` | admin+ | Scan now |
| `GET /api/v1/orgs/{org_id}/scans`, `GET .../scans/{id}` | member+ | Scans with coverage |
| `GET /api/v1/orgs/{org_id}/scans/{id}/findings` | member+ | Paged findings |

All JSON endpoints are under `/api/v1` (web-shell spec). The callbacks follow the BFF login
pattern of the identity module; nothing logs the query string.

### Audit events and error codes

Audit events: `connection.created`, `connection.consent_granted`, `connection.verified`,
`connection.incomplete`, `connection.over_privileged`, `connection.revoked`,
`connection.disconnected`, `scan.requested`, `scan.succeeded`, `scan.partial`, `scan.failed`,
`scan.blocked`.

Error codes (ES and EN texts in the web i18n files): `connections.state_invalid`,
`connections.consent_denied`, `connections.tenant_mismatch`, `connections.signin_invalid`,
`connections.microsoft_unavailable`, `connections.admin_not_verified`,
`connections.incomplete_permissions`, `connections.missing_directory_role`,
`connections.over_privileged`, `connections.dwd_not_authorized`,
`connections.subject_not_super_admin`, `connections.revoked`, `scanning.connection_not_active`,
`scanning.already_queued`, `scanning.daily_limit`, `scanning.timeout`, `scanning.engine_failed`,
`scanning.tenant_mismatch`, `scanning.output_invalid`.

### Proposed ADR changes (same PR as the spec)

- ADR-004 amendment: the scan task fetches the connector credential at start with its per-org,
  per-provider task role and holds it only for the task's lifetime; the M365 certificate is one
  Atesta credential for all M365 tenants (D5); scan outputs are write-once and egress is
  deny-by-default; the image entrypoint is the Atesta wrapper.
- ADR-012 amendment: new class "queue tables" for `procrastinate_jobs`, `procrastinate_events`,
  `procrastinate_periodic_defers`, `procrastinate_workers`: no `organization_id`, no RLS, job
  arguments ids only (a test enforces it), `atesta_app` gets SELECT, INSERT, UPDATE, DELETE and
  EXECUTE on Procrastinate's functions; its Postgres ENUM types are allowed as third-party
  objects. Procrastinate 3.10.0 defines no SECURITY DEFINER function. Its schema SQL is applied by
  an Alembic migration as `atesta_owner`. Any `atesta_app` session can read every job's ids; that
  is accepted because arguments hold ids only.
- ADR-002 note: the wrapper may choose Prowler flags and exclude checks; it never patches Prowler.

### PR plan (each under ~400 lines, rule 7; split further if one grows)

1. Procrastinate, queue tables, ADR-012 amendment, worker skeleton in `job` context.
2. `scans`, `scan_check_results`, `findings` with RLS, grants and the active-scan index.
3. Synthetic OCSF fixtures, strict parser, tenant pin, `FixtureRunner`.
4. Coverage, control results, `snapshot_scores`, evidence registration, `atesta-dev-scan` with the
   synthetic catalog.
5. Scanner image (runtime libs, pwsh, no Exchange or Teams modules), expected lists, wrapper argv,
   env and exit codes, offline golden.
6. Wrapper log scrub, metadata strip, manifest, write-once output layout.
7. `connections`, versioned allowlist in `atesta_core` with the registration export test, create,
   list, get and delete endpoints, dev-only guards.
8. M365 sign-in and consent callbacks.
9. M365 Graph-only verifier, `LocalDockerRunner`, live golden M365 (milestone: first real M365
   scan of an Atesta test tenant scored in dev). Onboarding verification is the activation scan
   with step 6 (#331); the live golden needs the owner's app registrations (D12).
10. M365 PowerShell services after D11: modules, expected set v2, Global Reader step, step 5b,
    connection upgrade.
11. Google onboarding (two service accounts, runbook, disconnect step), verifier.
12. Google scan and live golden Google.

### Owner steps (cannot be automated from here)

| Step | Who | Blocks |
|---|---|---|
| Dev: a separate "Atesta dev" Entra ID Free tenant holds the dev app registrations (Scanner, Sign-in); the scanner certificate is generated inside AWS (owner, 2026-11-23; `docs/runbooks/m365-test-tenant.md`). Prod: Atesta's tenant with a DNS-verified custom domain | Owner | PR 9 live golden |
| M365 test tenant: paid Microsoft 365 Business Premium, not a trial, since a trial tenant cannot create the Atesta dev tenant (owner, 2026-11-23; the E5 developer sandbox needs Visual Studio or partner eligibility). Steps in `docs/runbooks/m365-test-tenant.md` | Owner | PR 9 live golden |
| Cloud Partner Program account verified as PGA (D12) | Owner | First M365 customer |
| Legal review of the Exchange and Teams module terms (D11) | Owner and counsel | PR 10 |
| GCP organization, dedicated project, key-creation exemption | Owner | PR 11 |
| Google Workspace test tenant with a super admin | Owner | PR 12 |

### Facts checked (2026-11-13)

| Fact | Source |
|---|---|
| Prowler 5.49.0 is the latest PyPI release (2026-11-12), Apache-2.0, Python >=3.10,<3.14; the wheel read has sha256 `e5ed98...705`, equal to PyPI | https://pypi.org/pypi/prowler/json; `pip download prowler==5.49.0`, `prowler-5.49.0.dist-info/METADATA` |
| `scanner/Dockerfile` pins Prowler 5.49.0 on `python:3.12-slim` and installs no PowerShell | `/home/user/atesta/scanner/Dockerfile` |
| M365 certificate auth reads `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `M365_CERTIFICATE_CONTENT` (`m365_provider.py:437`); `--tenant-id` with it raises an error; managed identity excluded; the Google provider reads only `GOOGLEWORKSPACE_*` variables (`googleworkspace_provider.py:246`, `:305-359`) | Prowler 5.49.0 `prowler/providers/m365/m365_provider.py` (`setup_powershell`, `validate_arguments`), `lib/arguments/arguments.py`; https://docs.prowler.com/user-guide/providers/microsoft365/authentication.md |
| With certificate auth the provider always starts `pwsh`; a missing binary ends the run with exit 1. Provider init never tests the Exchange or Teams connection and imports modules only with `--init-modules`; a failed Exchange connect logs and returns False | Prowler 5.49.0 `m365_provider.py` `setup_powershell` (391-454), `lib/powershell/m365_powershell.py:231-239`, `lib/powershell/powershell.py`, `providers/common/provider.py` |
| The PFX is passed to PowerShell as a command string; PowerShell stderr is logged at ERROR; Exchange connects with the certificate (`m365_powershell.py:234`) | Prowler 5.49.0 `lib/powershell/m365_powershell.py` (`init_credential`), `lib/powershell/powershell.py` |
| Prowler docs require PowerShell 7.4+ and ExchangeOnlineManagement >= 3.6.0, MicrosoftTeams >= 6.6.0; MSAL.PS is used only by the client-secret Exchange path | https://docs.prowler.com/user-guide/providers/microsoft365/authentication.md; https://docs.prowler.com/developer-guide/m365-details.md; `m365_powershell.py` |
| Upstream image: base `python:3.12.16-slim-trixie`, apt installs `libicu76 libunwind8 libssl3 libcurl4 ca-certificates` before PowerShell 7.6.10 from the tarball with pinned sha256 `e261cabc...e10d`; sets `POWERSHELL_TELEMETRY_OPTOUT=1`; the x64 tarball (sha256 checked locally) extracts to 172 MB and its `pwsh.runtimeconfig.json` (net10.0) does not set invariant globalization | https://raw.githubusercontent.com/prowler-cloud/prowler/5.49.0/Dockerfile; local `sha256sum`, `du` |
| `python:3.12-slim` is `3.12/slim-trixie` (Debian 13), whose Dockerfile keeps only `ca-certificates`, `netbase`, `tzdata` as runtime packages; .NET on Linux fails to start without ICU unless invariant mode is set; manual PowerShell installs may miss dependencies; Debian 13 .NET dependencies include `libicu76` | https://raw.githubusercontent.com/docker-library/official-images/master/library/python; https://raw.githubusercontent.com/docker-library/python/master/3.12/slim-trixie/Dockerfile; https://github.com/dotnet/runtime/blob/main/docs/design/features/globalization-invariant-mode.md; https://learn.microsoft.com/en-us/powershell/scripting/install/install-other-linux (updated 2026-09-09); https://learn.microsoft.com/en-us/dotnet/core/install/linux-debian (updated 2026-04-23) |
| 149 M365 checks in 10 services; 54 depend on PowerShell data (Exchange-session: Exchange 17, Defender 17, Admin center 3, Purview 1; Teams session: 16), 95 on Graph only; the Entra service also opens an Exchange session but prefers Graph `accountEnabled`; Prowler ships no ENS mapping for M365 or Google | Prowler 5.49.0 `providers/m365/services/*/*.metadata.json`; `admincenter_service.py:18-23`, `defender_service.py:69-97`, `exchange_service.py`, `purview_service.py:13-16`, `teams_service.py:16-22`, `entra_service.py:64-67, 1053-1065`; per-check client attributes; `prowler/compliance/m365/`, `prowler/compliance/googleworkspace/` |
| Only non-GET Graph call is `POST /security/runHuntingQuery` (read); every data cmdlet is `Get-*` | Prowler 5.49.0 grep over `providers/m365`; `m365_powershell.py` verb inventory |
| Prowler 5.49.0 ships one M365 fixer running `Set-OrganizationConfig -DelayedDelicensingEnabled $true`; the `--fixer` flag is defined only in the AWS provider's arguments | Prowler 5.49.0 `providers/m365/services/exchange/exchange_organization_delicensing_resiliency_enabled/*_fixer.py`; grep `"--fixer"` in `providers/*/lib/arguments/` |
| `--excluded-checks` (nargs +), `--log-file`, default log level CRITICAL, `--list-checks-json` exits before provider init; api.github.com is called only for `--version` | Prowler 5.49.0 `lib/cli/parser.py` (156-158), `__main__.py`, `config/config.py:263-267` |
| PowerShell commands time out at 10 s and connects at 15 s; a failed connect leaves empty data and the checks emit no finding | Prowler 5.49.0 `lib/powershell/powershell.py`, `m365_powershell.py`, `services/purview/*`, `services/teams/*` |
| Without directory-sync permission both sync checks still report: PASS per cloud-only organization, MANUAL for hybrid ones | Prowler 5.49.0 `entra_service.py:969-973`, `entra_seamless_sso_disabled.py:36-52`, `entra_directory_sync_object_takeover_blocked.py:38-67` |
| OCSF output: one JSON array `<name>.ocsf.json` built with `py_ocsf_models` (pinned `py-ocsf-models==0.10.0`, Apache-2.0); `metadata.event_code` = CheckID; `finding_info.uid` built from `resource_name`; M365 `cloud.org.uid` = tenant GUID; `resources[].data.metadata` is the unredacted resource dump | Prowler 5.49.0 `lib/outputs/ocsf/ocsf.py:9-16`, `lib/outputs/finding.py`, `lib/check/models.py`, `METADATA`; https://pypi.org/pypi/py-ocsf-models/0.10.0/json |
| Graph application permission ids listed above, including `DelegatedPermissionGrant.Read.All` `81b4724a-58aa-41c1-8a55-84ef97466587`; all admin-consent only | https://learn.microsoft.com/en-us/graph/permissions-reference (updated 2026-11-07) |
| Least-privileged read permission per endpoint; `Directory.Read.All` is only the higher-privileged option; the group-list page names a write permission as least privileged | https://learn.microsoft.com/en-us/graph/api/{user-list, directoryrole-list, domain-list, organization-get, group-list, ...}?view=graph-rest-1.0; microsoft-graph-docs-contrib `includes/permissions` |
| Listing a service principal's `oauth2PermissionGrants` app-only: least privileged `Directory.Read.All`; `transitiveMemberOf` of a service principal: least privileged `Application.Read.All` | https://learn.microsoft.com/en-us/graph/api/serviceprincipal-list-oauth2permissiongrants?view=graph-rest-1.0 (updated 2025-07-23); https://learn.microsoft.com/en-us/graph/api/serviceprincipal-list-transitivememberof?view=graph-rest-1.0 (updated 2025-09-04) |
| `GET /directory/onPremisesSynchronization` does not support application permissions | https://learn.microsoft.com/en-us/graph/api/onpremisesdirectorysynchronization-get?view=graph-rest-1.0 |
| Exchange app-only: `Exchange.ManageAsApp`, RBAC from the Entra role, Global Reader supported, use the `.onmicrosoft.com` domain as `-Organization`; Option 2 custom role groups through `New-ServicePrincipal` and `Add-RoleGroupMember`, sample selects the app by `DisplayName`; Option 3 "RBAC combines permissions from all sources" | https://learn.microsoft.com/en-us/powershell/exchange/app-only-auth-powershell-v2 (updated 2026-08-27) |
| RBAC for Applications grants (`Application Mail.Send`, `Application Exchange Full Access`, `Application EWS.AccessAsApp`) are "independent of the unscoped grants in Microsoft Entra ID" and a union with them; they need a `New-ServicePrincipal` pointer | https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac (updated 2026-10-27) |
| Azure roles can be assigned to any service principal | https://learn.microsoft.com/en-us/azure/role-based-access-control/overview (updated 2025-10-15) |
| Teams app-only: Entra role required, `Organization.Read.All` for all cmdlets, do not configure the Teams Tenant Admin API permission | https://learn.microsoft.com/en-us/microsoftteams/teams-powershell-application-authentication (updated 2026-06-24) |
| Global Reader, Global Administrator, Privileged Role Administrator template ids; Global Reader is privileged and includes Service Health `allTasks` | https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference (updated 2026-11-12) |
| Admin consent endpoint and parameters; app permissions need `/.default`, which requests every permission in the registration's required permissions; never trust the callback `tenant`; Privileged Role Administrator needed for Graph app roles | https://learn.microsoft.com/en-us/entra/identity-platform/v2-admin-consent (updated 2026-06-15); https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/grant-admin-consent |
| `oid` needs the `profile` scope; `sub` is pairwise per app | https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference (updated 2026-06-15) |
| Unregistered redirect URIs fail; Microsoft recommends one shared redirect URI with per-request data in `state` | https://learn.microsoft.com/en-us/entra/identity-platform/reply-url (updated 2026-06-15) |
| Certificates over secrets; separate dev and prod registrations; https redirect URIs; app instance property lock default on for new apps since June 2026 | https://learn.microsoft.com/en-us/entra/identity-platform/security-best-practices-for-app-registration; .../reply-url; .../howto-configure-app-instance-property-locks |
| `appRoleAssignments` and `roleAssignments` listing and their permissions; `roles` and `wids` claims are not exhaustive | https://learn.microsoft.com/en-us/graph/api/serviceprincipal-list-approleassignments?view=graph-rest-1.0; .../rbacapplication-list-roleassignments; https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference |
| Service principal sign-in log records certificate sign-ins, grouped by resource name or ID | https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-service-principal-sign-ins (updated 2026-02-26) |
| Customer revocation path and 30-day restore | https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/delete-application-portal |
| E5 developer sandbox: eligibility (Visual Studio Pro/Enterprise, ISV Success or eligible partner tiers, Premier/Unified), MCA billing account with an active Azure subscription, may be recreated every 90 days. Publisher verification: verified CPP account that is the PGA, publisher domain not `*.onmicrosoft.com`, email domain matching or DNS-verified | https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq (updated 2026-11-06); https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview (updated 2026-06-15) |
| Module licences: PowerShell MIT; ExchangeOnlineManagement under Microsoft licence terms; MicrosoftTeams use tied to the customer's subscription; MSAL.PS MIT, last release 2021-11-19 | PowerShell Gallery `FindPackagesById()`; the linked LICENSE files |
| Google provider: service account JSON plus domain-wide delegation only; env `GOOGLEWORKSPACE_CREDENTIALS_CONTENT`, `GOOGLEWORKSPACE_DELEGATED_USER`; six read-only scopes; 65 checks | Prowler 5.49.0 `providers/googleworkspace/googleworkspace_provider.py` (`SCOPES`, `setup_session`), `services/*/*.metadata.json` |
| Five checks read `provider.editions` only on FAIL; the lookup asks for an `apps.licensing` token from the same credentials (`googleworkspace_provider.py:182`), catches every exception, logs a WARNING and returns an empty list | Prowler 5.49.0 `googleworkspace_provider.py:160-191`, `lib/licensing.py:107-137`; the five checks' `execute` |
| Google API calls are not retried (`num_retries=0`); a failed Policy API page drops its checks' findings | google-api-python-client 2.163.0 `googleapiclient/http.py`; Prowler 5.49.0 `lib/service/service.py` |
| Delegated access is limited by the scopes authorized for the client ID; exact scope match required (`unauthorized_client` otherwise) | https://developers.google.com/identity/protocols/oauth2/service-account (updated 2026-03-23); https://docs.cloud.google.com/identity/docs/how-to/setup-policies (updated 2026-11-10) |
| Any prebuilt or custom admin role except Super Admin can be assigned to a service account; `roleAssignments.assignedTo` can be a service account's IAM `uniqueId`; the Groups API accepts a service account group admin without domain-wide delegation | https://support.google.com/a/answer/9807615 (updated 2026-11-10); https://developers.google.com/workspace/admin/directory/reference/rest/v1/roleAssignments (updated 2026-09-04); https://docs.cloud.google.com/identity/docs/how-to/setup (updated 2026-11-10) |
| Only a super admin can use the Policy API; 1 QPS per project and per customer, no increase | https://docs.cloud.google.com/identity/docs/concepts/overview-policies; https://docs.cloud.google.com/identity/docs/how-to/list-get-policies |
| DWD setup path, multi-party approval, up to 24 h propagation, immediate stop on delete; all users' data reachable | https://knowledge.workspace.google.com/admin/apps/control-api-access-with-domain-wide-delegation |
| `AUTHORIZE_API_CLIENT_ACCESS` and `REMOVE_API_CLIENT_ACCESS` events with `API_SCOPES`; readable with `admin.reports.audit.readonly`; kept 6 months; admin log events lag a couple of minutes | https://developers.google.com/workspace/admin/reports/v1/appendix/activity/admin-domain-settings; https://knowledge.workspace.google.com/admin/reports/data-retention-and-lag-times (updated 2026-11-10) |
| `apps.licensing`, `apps.alerts`, `admin.directory.user.security` have no read-only variant for the methods involved | Discovery documents for licensing v1, alertcenter v1beta1, directory_v1 (fetched 2026-11-13); https://developers.google.com/identity/protocols/oauth2/scopes |
| 10 keys per service account; new GCP orgs block key creation by default; `gcloud iam service-accounts keys create` writes the private key to an output file | https://docs.cloud.google.com/iam/quotas; https://docs.cloud.google.com/resource-manager/docs/manage-baseline-constraints; `gcloud iam service-accounts keys create --help` (Google Cloud SDK 570.0.0) |
| ECS `ContainerOverride` members: command, cpu, environment, environmentFiles, memory, memoryReservation, name, resourceRequirements (no secrets); `TaskOverride.taskRoleArn`; overrides limited to 8192 characters | https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ContainerOverride.html; .../API_TaskOverride.html; .../API_RunTask.html |
| ECS injects Secrets Manager secrets at container start; the app and logs can read them | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html |
| Secrets Manager appends six random characters to the secret name in its ARN | https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_examples.html; .../troubleshoot.html |
| S3 bucket policies can enforce conditional writes with `s3:if-none-match`; multipart parts need an `s3:ObjectCreationOperation` exemption; CopyObject into an enforced prefix fails | https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html |
| IAM roles per account: 1,000 default, 10,000 maximum | https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html |
| Procrastinate 3.10.0 (2026-09-23, MIT classifier; 3.11.0 is inside the 7-day cooldown); `RetryStrategy` wait = `wait + linear_wait * attempts`; `lock` blocks behind `doing` and lower-id `todo` jobs with no `scheduled_at` condition; `queueing_lock` unique among `todo` only; retry sets the same row back to `todo`; `JobContext.job`; `get_stalled_jobs`, `retry_job`; four tables, no SECURITY DEFINER | https://pypi.org/pypi/procrastinate/json; wheel sha256 `949ad25b4377c30e03a9d0e053d15dfa47ef02b3f12ae8a7f3254686183c152c`: `retry.py`, `jobs.py`, `job_context.py`, `manager.py`, `worker.py:165-189`, `sql/schema.sql:99, 209-260, 366-396` |
| Docker bind mounts keep host ownership unless userns remapping is configured ("file ownership must be pre-arranged"); uid 10001 cannot read a 0600 file owned by another uid | https://docs.docker.com/engine/security/userns-remap/; local `setpriv --reuid=10001` test (no Docker daemon in the sandbox) |
| Web routes live under `/api/v1`; CloudFront sends `/api/*` and `/auth/*` to the API; the BFF login keeps its pending state in a sealed cookie | `origin/main:docs/specs/web-shell.md`; identity module `routes.py`, `bff.py` (branch `claude/brave-franklin-e60jws-26`) |

### Engine bump to 5.52.0 (2026-11-23, issue #243)

The facts above cite Prowler 5.49.0, where they were read. Moving the pin re-checked each one that
depends on Prowler against the 5.52.0 wheel; line numbers in the files below shift, content does
not, unless the row says so.

| Fact | Source |
|---|---|
| Prowler 5.52.0 published 2026-11-23T14:54:59Z; wheel sha256 `b9134bdb...a96`, sdist `054b9415...48c`, equal to the lock; Python >=3.10,<3.14. Its requirements add only `opentelemetry-api==1.45.2` (2026-10-29), already in the lock at that version. The re-lock changes no other package; the `pymongo` override still applies (`huaweicloudsdkcore` 3.1.204 still pins 4.15.1; the lock keeps 4.19.0, no OSV advisory) | https://pypi.org/pypi/prowler/5.52.0/json; `scanner/requirements.txt` diff; https://pypi.org/pypi/huaweicloudsdkcore/3.1.204/json; https://api.osv.dev/v1/query |
| Upstream `Dockerfile` identical at 5.49.0 and 5.52.0 (base digest, PowerShell 7.6.10 and its sha256, apt packages) | https://raw.githubusercontent.com/prowler-cloud/prowler/5.52.0/Dockerfile |
| `--list-checks-json` for M365 and Google, and `powershell_checks.py`, give byte-identical lists (149, 65, 54). No M365 or Google `*.metadata.json` changes; under `providers/m365/services` only the two Defender outbound anti-spam checks (no `KeyError` with preset policies), `entra_service.py` (Graph URL from the region) and the fixer (region argument) change | `scanner/expected/README.md`; recursive diff of the two wheels |
| With no `--region`, M365 stays on the commercial cloud: `M365Global` keeps `login.microsoftonline.com`, `graph.microsoft.com` and `outlook.office365.com`, and adds no `-ExchangeEnvironmentName` or `-TeamsEnvironmentName`. New `--region M365Custom`, `--m365-authority-host` and `--m365-graph-endpoint`; the wrapper passes none | Prowler 5.52.0 `providers/m365/lib/regions/regions.py`, `lib/powershell/m365_powershell.py`, `lib/arguments/arguments.py` |
| Certificate auth still reads `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `M365_CERTIFICATE_CONTENT` (`m365_provider.py:494`) into the same `CertificateCredential` (`:656-662`); the Google provider still reads only `GOOGLEWORKSPACE_*` (`googleworkspace_provider.py:247, :307-362`), `SCOPES` unchanged. Neither provider gains a token or signer input | Prowler 5.52.0 `m365_provider.py`, `googleworkspace_provider.py` |
| The Google provider now calls `GcpProvider.validate_service_account_key` before use: the key must be `type: service_account` with `token_uri` `https://oauth2.googleapis.com/token` or `https://accounts.google.com/o/oauth2/token`. Importing the provider with sockets and DNS disabled makes no outbound call at either version (the one socket both open is urllib3's local IPv6 probe), and loads no new third-party package (new: stdlib `getpass`, `termios`) | Prowler 5.52.0 `providers/gcp/gcp_provider.py:40-45, 908-939`; import probe in the pull request |
| `--fixer` is still defined only in `providers/aws/lib/arguments/arguments.py`; M365 still ships one fixer. `lib/cli/parser.py`, `lib/check/models.py`, `lib/outputs/finding.py` and `lib/powershell/powershell.py` are unchanged. `lib/outputs/ocsf/ocsf.py` now closes the array when the last batch is empty. 5.51.0 adds an ENS M365 compliance CSV under `out/compliance/`; the wrapper reads only `prowler.ocsf.json` | Prowler 5.52.0 source; `scanner/atesta_scanner/run.py` |
| Not re-checked offline: the egress host list and the live behaviour of both providers. The live goldens (M365, Google) run before any customer scan uses 5.52.0 | Candidates below |

### Python 3.13 (2026-11-23, issue #298)

| Fact | Source |
|---|---|
| Prowler 5.52.0 requires Python `>=3.10,<3.14`, so 3.13 is the newest it allows | https://pypi.org/pypi/prowler/5.52.0/json |
| `python:3.13.18-slim-trixie` is the newest 3.13 patch tag; index digest `e48f59cd...ed90`, last pushed 2026-11-08 (more than 7 days before the change). The same tag and digest are in `apps/Dockerfile` and `scanner/Dockerfile` | https://hub.docker.com/v2/repositories/library/python/tags?name=3.13. |
| Re-locking `requirements.txt` and both `build-requirements.txt` for 3.13 with the header flags changes no version or hash; `typing-extensions` loses four `via` lines (for 3.13 uv no longer lists aiohttp, aiosignal, pyopenssl or referencing as needing it). `uv lock` drops only the cp312 wheel entries | `scanner/requirements.txt`, `uv.lock` diffs |
| The 3.13 image builds every sdist-only dependency with the hash-locked setuptools, and the offline golden gives the committed lists (149, 65, 54) | `scanner/golden.sh` on the built image |

### Candidates (not verified; each closes in the named test)

| Candidate | Closes in |
|---|---|
| The 5 `entra_device_registration_*` checks need `Policy.Read.DeviceConfiguration` | Live golden M365 |
| `admincenter_users_admins_reduced_license_footprint` gets 403 app-only (`licenseDetails`: application not supported) | Live golden M365 |
| Permission needed by the beta `/legacy/policies` call (`entra_policy_guest_invitations_restricted_to_allowed_domains`) | Live golden M365 |
| `DeviceManagementServiceConfig.Read.All` is the right permission for `GET /deviceManagement` (Microsoft page returned 404) | Live golden M365 |
| `GET /servicePrincipals/{id}/oauth2PermissionGrants` succeeds app-only with `DelegatedPermissionGrant.Read.All` (Microsoft lists only `Directory.Read.All`) | Live golden M365 onboarding; if it fails, D2 must add `Directory.Read.All` because the verifier needs it |
| A Graph-only scan completes without the Exchange and Teams modules (failed connects only log) | Live golden M365 (PR 9) |
| `transitiveMemberOf` shows directory roles and role-assignable groups (5c); ARM issues an app-only token to the scanner app and lists no subscription without a role (5d) | Live golden M365 |
| Global Reader can run `Get-ServicePrincipal` and `Get-ManagementRoleAssignment` app-only (5b) | Live golden M365 in PR 10, with a positive test: assign "Application Mail.Read" to the test tenant's scanner service principal and expect `over_privileged` |
| Global Reader is enough for the Teams `Get-Cs*` cmdlets; Teams works without `application_access` | Live golden M365 (PR 10) |
| `Connect-ExchangeOnline` fails when Prowler passes a custom domain (`tenant_domains[0]`) as `-Organization` | Live golden M365 (PR 10) with a custom-domain tenant; upstream issue if confirmed |
| One `/adminconsent` grants the Graph and Exchange permissions together | Live golden M365 upgrade (PR 10) |
| Admin consent works without publisher verification | Live golden M365 onboarding (D12) |
| A PowerShell error can echo the certificate command line into stderr | Wrapper scrub unit test with a forged error; live golden log review |
| A timed-out PowerShell command can shift output to the next command | Live golden M365 (PR 10) output review; upstream issue if confirmed |
| Tokens issued before revocation keep working until expiry (up to about 90 min) | Not tested; documented as a limit |
| Exact egress host list per provider; Prowler, MSAL, the Google client and pwsh honour the proxy | Live golden behind a deny-by-default proxy that logs every CONNECT |
| One Prowler Google scan stays under the Policy API quota | Live golden Google (429 count) |
| `AUTHORIZE_API_CLIENT_ACCESS` lists the full scope set after an edit, and the Reports query can filter by client ID | Live golden Google onboarding |
| `roleAssignments` shows a role on a service account under its IAM `uniqueId`; Google allows a role on a group that contains a service account | Live golden Google; until then the second is a Verifier limit |
| `users.get` `isAdmin` means super admin for the subject check | Live golden Google |
| A mechanism to record Google token requests for the live golden | To be found; not part of the pass condition until then |
| Cross-tenant confused deputy with a shared Google client ID (design reasoning, not tested) | Design argument; per-org service accounts avoid it |
| PowerShell runs with a read-only root filesystem and `HOME` on tmpfs | Offline golden image test |
| A paid or trial M365 tenant can stand in for the E5 developer sandbox | Owner step |
| 2 vCPU, 4 GB, 60 min are enough (no vendor sizing exists) | Live golden measurements (D13) |
| Fargate and every AWS service used are available in eu-south-2 within ENS scope | AWS spec (ADR-007 check per service) |

## Test plan

| Test | Proves |
|---|---|
| Migrations up; schema linter passes with `connections`, `scans`, `scan_check_results`, `findings` as tenant tables and the four Procrastinate tables as queue tables | ADR-012 with the amendment |
| Org A cannot see or reference org B connections, scans, findings; single-column FK absent; `atesta_app` UPDATE or DELETE on `findings`, `scan_check_results` denied | Isolation, append-only |
| Ref CHECKs reject a PEM, a JSON key, an ARN outside eu-south-2, free text and a Google ref naming another org's secret; accept the `aws-sm:` and `local:` forms of the org's own | No secrets in the DB |
| `atesta_core.connectors.readonly`: the expected set passes; one extra app role (including an allowed-but-not-expected one such as `Directory.Read.All`), a write-named role, an unexpected directory role, a delegated grant, an Exchange pointer or role assignment, an extra Google scope, a Google role assignment each give `over_privileged`; a missing one gives `incomplete`; every allowlisted Graph name passes the second gate; no `ReadWrite` name; the exported registration equals the expected set | Rule 1 logic |
| M365 onboarding with a fake identity provider: missing, expired or other-org cookie; wrong `state`; ID token without `oid`; `admin_consent` not `True`; `error` present; `tenant` different from the signed-in `tid`: each rejected with its code; happy path reaches verification | Tenant binding |
| Verifier against recorded Graph and Google responses (httpx mock): each verdict; `roles` claim pre-check never overrides step 3; binding fails for a non-admin `oid`; a recorded `roleAssignments` page containing the org service account's `uniqueId` gives `over_privileged`; the report lists the verifier limits | Fail closed |
| Wrapper argv per provider equals the expected list; none of the forbidden flags appear; Prowler child env holds only the listed variables; `LocalDockerRunner` passes the credential on stdin only (no env, argv or mount carries it) | Invocation contract |
| Wrapper log scrub: a forged Prowler log containing the test certificate base64, a JWT and a 300-char base64 run comes out without them; wrapper stdout holds no secret | Rule 2 |
| Wrapper strips `resources[].data.metadata`; manifest has the raw and stripped sha256 | D10 |
| Runbook dry run: no key file remains after exit | Key custody |
| Exit code mapping: 0, 3 with `-z`, 1, missing output, wrong tenant, verification refused | Retry classification |
| `run_scan` with `FixtureRunner` forced to fail transiently: 3 retries at 300, 600, 900 s then `failed` with one `scan.finished` carrying its fields; a retried `run_scan` returns to `todo` without error; a permanent failure is not retried | Retry policy |
| Two "Scan now" calls, and "Scan now" while a scan is running: 409; `schedule_scan` skips on `already_queued` and re-defers itself after a failed scan | Locks and schedule chain |
| A 7th "Scan now" on one Madrid day: 429 `scanning.daily_limit` with `retry_at` and `Retry-After`, no row, no event; 6 `user` scans queued before the last Madrid midnight and any number of `schedule` scans do not count; the Madrid day is 23 h on 2026-03-29 and 25 h on 2026-10-25 | Daily budget (#265) |
| Job with org A id and org B scan id: no row, no retry | Job context |
| Every registered task's arguments are uuids, a Google client id or a credential ref only; an email, token or key in a job argument fails the test | ADR-012 amendment, rule 2 |
| Startup with `ATESTA_ENV=prod` and any local runner, store or credential store configured fails; `record_verification` refuses a `local:` ref in prod | Dev-only local path |
| Synthetic fixtures validate against `py_ocsf_models` 0.10.0 `DetectionFinding` | Fixture fidelity |
| Ingest of fixtures: tenant mismatch rejects the scan; unexpected check id rejects it; missing service gives `partial` with `not_evaluated` rows; repeated ingest inserts nothing | Ingest contract |
| Control evaluation: one `not_evaluated` check keeps a control unassessed; FAIL wins; a second connection's older results are kept | ADR-005, multi-connection |
| `atesta-dev-scan`: two synthetic frameworks mapped to shared synthetic controls; one fixture scan yields one snapshot per framework; rerun leaves one each | Snapshot trigger, idempotent |
| Scan output evidence row passes the evidence CHECKs and links to the controls with results | Evidence |
| Rule 9 guard over the new paths passes | No framework code |
| Offline golden in CI: `--list-checks-json` equals committed lists (149, 65); every catalog `prowler_checks` id exists in them; image has pwsh 7.6.10 starting as uid 10001 on a read-only root filesystem (from PR 10 the pinned module versions), no MSAL.PS | Pinned engine |
| Live golden (owner-run, M365 test tenant with a custom domain and Defender, MDI and Intune licences; Google test tenant): verify and scan pass; the test tenant's service principal sign-in log for Atesta Scanner over the scan window shows only the Microsoft Graph (and, from PR 10, Office 365 Exchange Online and Teams) resources, export attached to the run record; duration, memory, connect latency and 429 count recorded; candidates above closed or reported | Real behaviour, sizing |
| Manual: Spanish and English onboarding texts, privileged-role warning shown before the Global Reader step (PR 10), verifier limits shown | Definition of done |
