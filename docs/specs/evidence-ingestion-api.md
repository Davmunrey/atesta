# Spec: evidence ingestion API

- Issue: #169. Builds on `control-evidence-statements.md`, `recorded-routines.md` and `rbac.md`.
- Status: draft

## Problem

Much of an organization's evidence already exists in its own tools: a backup job reports that the
restore test passed; a dependency scan reports what it found; a deployment pipeline records who
approved a release. Today a person copies that into Atesta by hand, late or never. A token lets
the tool record it directly, with its own timestamp and reference.

## Acceptance criteria

**Tokens (admins)**
- [ ] **Create:** a name (1 to 100 characters) and an expiry from 1 to 365 days. The token is
  shown once. The API keeps its SHA-256 and a display prefix (the first 12 characters).
- [ ] **List:** name, prefix, created by and when, expiry, last use, and whether it is revoked.
  Admins only; auditors and contributors do not see tokens.
- [ ] **Revoke:** immediate and final.
- [ ] **One scope only:** `evidence:write`. A token cannot read anything.

**Ingestion (the token)**
- [ ] **Endpoint:** `POST /api/v1/ingest/evidence` with `Authorization: Bearer <token>`. The body has:
  - `control`: a common control key; it must be active in the catalog;
  - `title`: up to 200 characters;
  - `statement`: up to 4000 characters;
  - `source`: the tool, up to 50 characters, for example `github-actions`;
  - `reference_url` (optional): HTTPS, up to 2000 characters;
  - `external_id` (optional): up to 200 characters.
- [ ] **What it writes:** an evidence statement on that control. Its source is `api`; it names the
  token, and its author is the admin who created the token (who answers for it).
- [ ] **Idempotent:** a repeated `external_id` for the same token returns 200 with the first
  evidence id and writes nothing. A first write returns 201.
- [ ] **Refused:**
  - a missing, unknown, revoked or expired token (401, the same response for all four);
  - an unknown or retired control (422);
  - a token in a query string (400).
- [ ] **Recorded:** each accepted write updates the token's last use and emits an audit event
  (`evidence.ingested`). Creating and revoking tokens are audit events too.
- [ ] **Web:** an "Integraciones" page for admins: create (the token shown once, with a copy button
  and a curl example), list and revoke. Strings in ES and EN.

**Templates (#187)**
- [ ] **Use cases:** for admins, in Integraciones, each with its common control:
  - verified backup (`ctl.continuity_restore`);
  - approved deployment (`ctl.change_vulnerability_review`);
  - vulnerability scan (`ctl.change_vulnerability_review`);
  - log review (`ctl.activity_logging_review`).
- [ ] **Formats:** PowerShell (Windows scheduled task), bash (cron) and GitHub Actions.
- [ ] **Every template:**
  - reads the token from an environment variable or secret, never from the script;
  - sends an `external_id` that makes retries safe;
  - uses the Atesta address of the page that shows it;
  - writes the statement in the reader's language.
- [ ] **Tests:** the templates are checked by unit tests, by `bash -n` and a YAML parser, and by running the bash template against a local API.

## Out of scope

- Files: evidence storage needs AWS.
- Reading through the API, and any scope other than `evidence:write`.
- Per-token rate limits. Tokens are 256-bit random, so guessing one is not practical. A rate
  limit belongs to the edge (WAF) when it exists.

## Design notes

- **Tables** (tenant, RLS):
  - `api_tokens`: updated only to record last use or revocation;
  - `api_ingestions`: append-only; unique on organization, token and external id.
- **Evidence:** `source_type` gains `api`, which must name its token in `source_id`.
- **Database access:** the endpoint reads the token through a named read policy, `api_token_read`,
  keyed on the token's SHA-256. It then enters the organization's context for a new reason,
  `api_token`. This is ADR-012 amendment 5, proposed.
- **Secrets:** tokens are never logged (rule 2). The prefix identifies a token in the UI and in
  support conversations.

## Test plan

- **Postgres:**
  - create, list, revoke, roles;
  - ingestion: accepted, idempotent, refused (each 401 case, unknown control, query string);
  - the token reads only its own row and writes nothing else;
  - grants; evidence linked to the control with source `api`.
- **Web unit:** the token is shown once, a revoked token is shown as revoked, ES and EN.
- **e2e:** create a token, ingest with it through the real API, see the evidence, revoke it, and
  see the 401.
