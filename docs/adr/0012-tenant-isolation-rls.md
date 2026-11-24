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

## Amendment 6 (accepted by the owner 2026-11-23, ADR-016, api-keys-v2 and mcp-server specs)

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

## Amendment 7 (accepted by the owner 2026-11-23, notifications spec)

- **Seventh reason to enter an organization's context:** `unsubscribe_link`. It is used only by
  `POST /api/v1/unsubscribe`, after the API has opened a sealed unsubscribe token and checked its
  age (60 days at most).
  - **What it may do:** set one optional notification preference to disabled, for the person
    and organization the token names, and write the audit event `notification.unsubscribed`.
  - **Why no session:** RFC 8058 one-click unsubscribe is a POST from the mail provider, with
    nobody signed in.
- **New tenant tables, standard policy only:**
  - `notification_preferences`: SELECT, INSERT and UPDATE;
  - `notification_deliveries`: SELECT and INSERT, and UPDATE only of the delivery status.
- **No named read policy and no new setting.** The token is sealed, not stored, so nothing is
  read before the organization is known.

## Amendment 8 (accepted 2026-11-24, ADR-017, operator-portal spec)

Status: accepted. The owner decided the substance and accepted the amendment on 2026-11-24,
relayed by the coordinator (ADR-017, "Owner decisions"; #405).

- **Second runtime role, `atesta_operator`:** used only by the operator service (ADR-017).
  - **Attributes:** LOGIN, NOSUPERUSER, NOBYPASSRLS, owns nothing, member of no role.
  - **Grants:** only through `rls_v1.grant()` (or its successor), like `atesta_app`, and never
    TRUNCATE, REFERENCES or TRIGGER.
  - **Defined in** `bootstrap.sql`, with no password.
- **It crosses tenants by design and never sets a tenant context.** No new context reason and no
  new setting. Isolation from content holds because the role has no privilege on content tables,
  not because of `app.organization_id`.
- **Closed column list.** Column-level grants only, no table-level SELECT. A table or column
  added here needs this amendment updated and both snapshots changed in the same reviewed pull
  request.

  | Table | SELECT columns | Writes |
  | --- | --- | --- |
  | `organizations` | `id`, `name`, `locale`, `created_at`, `trial_ends_at`, `closure_requested_at`, `closure_origin`, `suspended_at`, `suspension_reason` | UPDATE of `suspended_at`, `suspension_reason`, `closure_requested_at` (`closure_origin` is generated) |
  | `subscriptions` | `organization_id`, `plan`, `addons`, `note`, `updated_at` | INSERT of the same columns, UPDATE of all but `organization_id` |
  | `billing_profiles` (new) | every column | INSERT and UPDATE of every column but `organization_id` on UPDATE |
  | `memberships` | `organization_id`, `role` | none |
  | `invitations` | `organization_id`, `expires_at`, `accepted_at`, `revoked_at` | none |
  | `connections` | `organization_id`, `provider`, `status` | none |
  | `scans` | `organization_id`, `status`, `queued_at`, `finished_at` | none |
  | `api_tokens` | `organization_id`, `expires_at`, `revoked_at` | none |
  | `api_token_usage` | `organization_id`, `at` | none |
  | `audit_events` | `organization_id`, `action`, `occurred_at` | INSERT of `id`, `organization_id`, `action`, `target_type`, `target_id`, `metadata`, `request_id` |
  | `erasure_receipts` (operator) | `id`, `organization_id`, `closure_requested_at`, `erased_at`, `row_counts` | none |

  Every other tenant table, and `users`, gives `atesta_operator` no privilege. That covers
  assessments, evidence, statements, findings, check results, policies, training, incidents,
  access reviews, proposals and notification tables.
- **New named policies, all scoped `TO atesta_operator`:**
  - `operator_metadata_read`: `FOR SELECT USING (true)`, on each table in the list above that
    has RLS.
  - `operator_insert` (`FOR INSERT WITH CHECK (true)`) and `operator_update`
    (`FOR UPDATE USING (true) WITH CHECK (true)`) on `subscriptions` and `billing_profiles`;
    `operator_update` only on `organizations`. (Accepted text said one `operator_write` policy;
    a table holds one policy per name, so it is two. Amended with #445.)
  - `operator_audit_write` on `audit_events`: `FOR INSERT WITH CHECK (action LIKE 'operator.%'
    AND actor_user_id IS NULL)`. `actor_user_id` is also absent from the column grant.
  - `operator_audit_only` on `audit_events`: the same check, `AS RESTRICTIVE`. The standard
    `tenant_isolation` policy applies to every role and Postgres evaluates its
    `app_setting_uuid()` call for the operator's INSERT check, so the role needs EXECUTE on the
    two setting functions. The restrictive policy keeps the rule if the role ever sets
    `app.organization_id` itself (#445).
  - These are the only writes that do not pass `tenant_isolation`. For `atesta_app`, nothing
    changes: the policies do not apply to it.
- **New tenant table `billing_profiles`:** standard `tenant_isolation`, SELECT only for
  `atesta_app` (owners read it in the console), plus the operator policies above. Erasure
  deletes it like every tenant table.
- **New columns on the tenant root `organizations`:**
  - `suspended_at`, and `suspension_reason`, a text code held by a CHECK from a closed list; both
    NULL or both set;
  - `closure_origin` (`owner` or `operator`), NULL exactly when `closure_requested_at` is NULL.
    It is a stored generated column: `owner` when `closure_requested_by` is set, `operator`
    otherwise (#445);
  - `trial_ends_at`, 14 days after creation (operator-portal spec, owner answer 1), read by the
    operator role and written by no runtime role (#445).
  - `atesta_app` gains no write grant on them. Its table-level UPDATE on `organizations` becomes
    column-level UPDATE of `name`, `locale`, `updated_at`, `closure_requested_at` and
    `closure_requested_by` (#445).
- **New operator tables** (the class from amendment 3): no RLS, no `organization_id` foreign
  key, no privilege for `atesta_app`.
  - `operator_staff`: SELECT, INSERT, and UPDATE of role and `disabled_at`.
  - `operator_audit_events`: append-only, SELECT and INSERT.
  - `erasure_requests`: SELECT, INSERT, and UPDATE of the approval and cancellation columns.
  - Only `atesta_owner`, through the erasure runner, sets `executed_at` and the receipt link.
- **Linter and guard:**
  - **Grants snapshot:** the schema linter keeps a second grants snapshot for `atesta_operator`,
    read from `relacl` and `attacl` like the first.
  - **Content test:** a test enumerates every tenant table outside the list and asserts that
    the role has no table or column privilege on it.
  - **Startup guard:** the operator service runs the same guard as the API against its own role,
    and refuses to start under `atesta_app`. The API refuses to start under `atesta_operator`.
- **Why column grants and not SECURITY DEFINER functions or views:** the ban on SECURITY
  DEFINER functions above stands. ADR-017, "Database", gives the reasons.

## Amendment 9 (proposed 2026-11-24, api-keys-v2 spec, issue 353)

Status: proposed. The owner chose the substance on 2026-11-24, in the session that built it:
"Job del worker, limitado por la BD". Accepting the amendment is the owner's.

- **A third write class for tenant tables: retention tables.** Until now a tenant table was
  either writable or append-only. A retention table is insert-only while a row is young, and
  `atesta_app` may delete the row once it reaches the table's age limit. It can never update it.
  - The closed list is `RETENTION_DAYS` in `platform/tables.py`. Today it holds one table:
    `api_token_usage`, 90 days. It leaves the append-only list.
  - Adding a table to the list needs this amendment updated in the same reviewed pull request.
    Audit events, evidence and every other append-only table stay append-only.
- **Grant:** `atesta_app` gains DELETE on `api_token_usage`, through `rls_v1.grant()`. No UPDATE.
- **New named policy `retention`:** `AS RESTRICTIVE FOR DELETE USING (at < now() - interval
  '90 days')`, for every role.
  - A restrictive policy is ANDed with the permissive `tenant_isolation`. A DELETE by the
    runtime role therefore reaches only rows of the current organization that are 90 days old.
  - The limit is in the database, not in the job: a wrong date or a missing WHERE in the code
    deletes nothing younger.
  - `rls_v1.py` is unchanged. The standard tenant policy is the same; this is one more named
    policy on one table, written in migration 0030.
- **Who deletes:** each organization's daily job, in that organization's context with the reason
  `job`. No new context reason, no new setting and no cross-tenant path.
- **Guard and linter:**
  - **Startup guard:** the runtime role is refused if it holds UPDATE (table or column) on a
    retention table, or if the table has no restrictive DELETE policy named `retention` for
    every role.
  - **Schema snapshot:** the policy and the grant are in `schema_snapshot.json`, so a change to
    the age limit is a reviewed diff.
- **Unchanged:** erasing an organization still deletes these rows as `atesta_owner` (amendment 3),
  and `atesta_operator` still reads only `organization_id` and `at` (amendment 8).
- **Why not a job that runs as `atesta_owner`:** the worker would then hold a role that bypasses
  RLS on every table. A narrow grant plus a restrictive policy keeps the worker on the runtime
  role and gives it one new ability: deleting its organization's old usage rows.

## Amendment 10 (proposed 2026-11-24, consultancy-portfolio spec, issue 228)

Status: proposed. The owner chose the substance on 2026-11-24, in the session that built it. The
recommendation put to the owner was "Resumen de portfolio recorriendo las organizaciones una a
una, sin consulta global", and the answer "sí a todo, empieza por #228". Accepting the amendment
is the owner's.

- **One request may read several organizations, one transaction each.** "Every request runs in
  one transaction" (Consequences) gains one exception: the portfolio summary. After the request's
  own transaction has authenticated the caller, the API opens one further transaction per
  organization the caller belongs to, one at a time.
- **Each of those transactions is an ordinary member read:**
  - it enters the caller's user context, finds the caller's own membership of that organization
    and applies the same rules as `require_member` (unknown organization, expired access);
  - it then enters that organization's context with the reason `membership`;
  - it is read-only (`SET TRANSACTION READ ONLY`) and always rolled back.
- **What does not change:**
  - no query sees tenant rows of two organizations: `enter_org_context` still refuses a second
    organization in one transaction, and that refusal is what keeps the walk honest;
  - no policy, grant, setting or context reason is added, so the schema snapshot is unchanged;
  - only `identity.api` opens these transactions (`member_reads`), as it alone sets a context.
- **Bounded.** The walk stops at 250 organizations per request and reports how many it left out,
  so one person with many organizations cannot make a request of unbounded cost.
- **Why not one cross-tenant query:** it would need either a policy that lets a member read
  tenant rows outside the current context, on every table the summary touches, or a SECURITY
  DEFINER function, which this ADR bans. Both widen what a forgotten filter can leak. The walk
  costs more queries and keeps "a forgotten filter returns nothing".
