# ADR-012: Tenant isolation with Postgres row-level security

- Status: accepted (2026-11-12); revised and accepted 2026-11-13 (adversarial spec review, before
  any code). Banned-object list extended 2026-11-13 (implementation review, PR 30): rewrite rules
  and referential actions, which also run as the owner.

## Context
CLAUDE.md rule 3 requires `organization_id` on every table. Two kinds of data have no single
tenant: user identities (one person can belong to several orgs) and the framework catalog
(content shared by all tenants, ADR-011). Isolation must not depend on every query carrying a
correct `WHERE` clause. Postgres runs FK and unique checks without row security, and TRUNCATE
ignores RLS.

## Decision
- Table classes, closed list. Adding a table or policy outside them requires updating this ADR:
  - Tenant tables: `organization_id NOT NULL`, RLS, only the standard `tenant_isolation` policy on
    the transaction-local setting `app.organization_id`. Named exceptions, one extra `FOR SELECT`
    policy each: `memberships` (`own_memberships_read`), `invitations` (`invitation_token_read`).
  - Tenant root: `organizations`, keyed by `id`; `tenant_isolation` on `id` plus `FOR SELECT`
    `own_orgs_read`.
  - Global identity: `users`; `FOR SELECT` self or co-member, `FOR INSERT` and `FOR UPDATE` self
    only, no DELETE.
  - Catalog tables: no RLS, SELECT only for `atesta_app`.
  - `alembic_version`: no privilege for `atesta_app`.
- Read branches are `FOR SELECT` policies only. Every write passes `tenant_isolation` (or the
  self policy on `users`).
- Runtime role `atesta_app`: NOBYPASSRLS, owns nothing, member of no role, grants only from
  SELECT, INSERT, UPDATE, DELETE (never TRUNCATE, REFERENCES, TRIGGER). Migrations run as
  `atesta_owner`. Tables are not FORCEd, so owner-owned views must use `security_invoker`, and
  materialized views, SECURITY DEFINER functions, rewrite rules (other than a view's `_RETURN`)
  and FK actions other than NO ACTION or RESTRICT are banned: each runs as the owner.
- Tenant context is set only by `identity.api.enter_org_context()`, for four reasons: a
  membership check, a valid invitation acceptance, creation of an org with a server-generated
  id, and `job` for worker jobs (scanning spec). Only the identity module may import
  `platform.tenancy` (import-linter). Job payloads carry ids only.
- FKs between tenant tables are composite with `organization_id`; unique and exclusion
  constraints lead with it. Cross-module FKs only to `organizations.id`.
- A schema linter, in CI and in the deploy job, fails on any unclassified table, any policy or
  grant that differs from the reviewed snapshot, single-column tenant FKs, and banned objects.
  Third-party tables (for example Procrastinate) must be classified here before merge.

## Consequences
A forgotten filter returns nothing instead of leaking. Every request runs in one transaction,
committed before the response. Catalog loads and offboarding need the owner role or a role the
offboarding spec defines. The policy predicate costs a little per query; the setting helpers
inline, so indexes leading with `organization_id` keep it cheap. Policy changes need a new
migration and a snapshot update in the same PR.

## Amendment 2 (accepted 2026-11-13, scanner-connectors spec)
New table class "queue tables" for Procrastinate 3.10.0 (`procrastinate_jobs`,
`procrastinate_events`, `procrastinate_periodic_defers`, `procrastinate_workers`): no
`organization_id`, no RLS; job arguments are ids only, enforced by a test. `atesta_app` gets
SELECT, INSERT, UPDATE, DELETE and EXECUTE on Procrastinate's functions; its ENUM types are
allowed as third-party objects. Procrastinate defines no SECURITY DEFINER function. Its schema SQL
is applied by an Alembic migration as `atesta_owner`. Any `atesta_app` session can read every
job's ids; accepted because arguments hold ids only.

Implementation notes (scanner PR 1): the migration checks the sha256 of the wheel's `schema.sql`
before applying it, and revokes EXECUTE on Procrastinate's functions from PUBLIC. Procrastinate's
own foreign keys between queue tables use ON DELETE CASCADE and SET NULL; the schema linter allows
referential actions only when both tables are queue tables, which carry no RLS and from which
`atesta_app` may already delete. The worker refuses to start if any Atesta task has a parameter
other than `<name>_id: str`.

## Amendment 3 (accepted by the owner 2026-11-23, organization-closure spec)

- **New class, "operator tables":** `erasure_receipts`. It has no `organization_id` foreign key,
  because it outlives the organization it records, and no RLS.
- **Permissions:** `atesta_app` has no privilege on it. Only `atesta_owner` writes it, through
  the operator command `apps/api/devtools/erase_org.py`.
- **What erasure does:** it deletes an organization's rows from every tenant table, in the order
  of the database's own foreign keys, then the organization, then users left without any
  membership.
- **Allowed only after a closure request:** an owner must have requested closure through the API,
  and 30 days must have passed.
- **The receipt** holds row counts per table and the operator's note; no names or content.

## Amendment 4 (accepted by the owner 2026-11-23, recorded-routines spec)

- **New named read policy:** `training_campaigns` gets `training_token_read`, `FOR SELECT` on
  `token_sha256 = app_setting_text('app.training_token_sha256')`. It works like
  `invitation_token_read`: someone with a secret training link reads that one campaign, and
  nothing else, before the organization is known.
- **New setting:** `app.training_token_sha256`, set only by
  `identity.api.enter_training_link_context()`. The token itself travels in the URL fragment and
  the request body, never in a query string (400), and is never stored.
- **Fifth reason to enter an organization's context:** `training_link`, after a campaign was
  read through a valid link that is open and not past its closing date. Writes then pass
  `tenant_isolation` as usual. The only write is one acknowledgement row (a name and an email),
  with at most 1000 per campaign.
- **Why not a user context:** the people who confirm training are often not Atesta users, and
  making them sign up would stop the routine from being used.

## Amendment 5 (accepted by the owner 2026-11-23, evidence-ingestion-api spec)

- **New named read policy:** `api_tokens` gets `api_token_read`, `FOR SELECT` on
  `token_sha256 = app_setting_text('app.api_token_sha256')`, set only by
  `identity.api.enter_api_token_context()`. Like `invitation_token_read`, it lets a caller who
  holds a token read that one row before the organization is known.
- **Sixth reason to enter an organization's context:** `api_token`, after the token was found,
  not revoked and not expired. Writes then pass `tenant_isolation` as usual: the token's last use
  and the evidence it records.
- **Scope:** a token is write-only (`evidence:write`); no endpoint reads data with it.
- **Why not a user session:** tools in a customer's CI have no person signed in, and a person's
  session must not be copied into a pipeline.

## Amendment 6 (proposed 2026-11-23, ADR-016, api-keys-v2 and mcp-server specs)

- **Keys may read.** Amendment 5 made a key write-only. With ADR-016, a key carries explicit
  scopes, and its read scopes (`compliance:read`, `incidents:read`) open read routes.
  - **Entering the context:** the key is resolved as before, through `api_token_read`, and
    the request then enters the key's organization with the reason `api_token`.
  - **What a read sees:** it passes `tenant_isolation` like any other request. It can see only
    the key's own organization, because no token route takes an organization in its path.
- **New tenant tables, standard policy only:**
  - `api_token_usage`: append-only, SELECT and INSERT;
  - `assessment_proposals`: SELECT, INSERT, and UPDATE only to record a person's decision.
- **No new named policy, setting or context reason.**
