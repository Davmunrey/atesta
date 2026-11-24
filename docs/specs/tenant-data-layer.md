# Spec: Multi-tenant data layer

- Requirement ids: NFR-02, NFR-03, FR-13, MF-01
- Status: approved (2026-11-13). Revised 2026-11-13: grants snapshot and startup guard cover
  column-level, PUBLIC and grant-option privileges; linter checks rules, FK actions, exclusion
  and expression keys and class overlaps (implementation review).
- ADRs: ADR-006, ADR-008, ADR-012
- Build order: 1 of 3 (identity and control-model specs depend on it)

## Problem

Every Atesta table holds data of many customer organizations. One query that forgets
`WHERE organization_id = ...` leaks one customer's security posture to another: a fatal incident
for a compliance vendor. Isolation must not depend on every query being written correctly.

## Acceptance criteria

- [ ] SQLAlchemy 2 (sync, typed `Mapped[]`) and Alembic, one migration history for the monolith
      in `apps/api/migrations/`.
- [ ] Postgres 18 (#299). Roles and schema grants come from one idempotent file,
      `apps/api/migrations/bootstrap.sql`, with no passwords. The test fixture runs it as
      superuser; the infra spec runs it as the RDS master user.
  - `atesta_owner` owns every table and runs migrations (USAGE, CREATE on schema `public`;
    Postgres 15+ no longer grants CREATE to PUBLIC).
  - `atesta_app` is the only runtime role: NOSUPERUSER, NOBYPASSRLS, owns nothing, member of no
    role, USAGE but no CREATE on `public`.
- [ ] `atesta_app` privileges are explicit: per table only from SELECT, INSERT, UPDATE, DELETE.
      Never TRUNCATE (it ignores RLS), REFERENCES or TRIGGER; never `GRANT ALL` or
      `ALTER DEFAULT PRIVILEGES`. No privilege on `alembic_version`. Append-only tables get
      INSERT, SELECT; catalog tables SELECT.
- [ ] This spec creates the tenant root `organizations(id, name, created_at, updated_at)` with RLS
      and `tenant_isolation` keyed on `id`, SELECT only for `atesta_app`. The identity spec adds
      its read policy, write grants and endpoints.
- [ ] Every tenant table has `organization_id uuid NOT NULL` (FK to `organizations(id)`,
      `ON DELETE RESTRICT`), an index leading with `organization_id`, RLS enabled, the standard
      `tenant_isolation` policy and no other policy unless ADR-012 names it.
- [ ] FKs between two tenant tables are composite: `(organization_id, x_id)` references
      `parent(organization_id, id)`, and the parent declares `UNIQUE (organization_id, id)`. Every
      unique constraint other than one on `id` alone starts with `organization_id`. FK and unique
      checks bypass RLS, so a single-column FK accepts another tenant's id.
- [ ] Table classes are the closed list in ADR-012. Views use `security_invoker = true`; no
      materialized views; no SECURITY DEFINER functions.
- [ ] Tenant context is transaction-local only. Policies read settings only through
      `app_setting_uuid()` and `app_setting_text()`. No context means zero rows: never an error,
      never all rows.
- [ ] `platform.tenancy.set_tenant_context()` is the only code that writes `app.*` settings,
      always with `set_config(name, value, true)`. Import-linter contracts: `atesta_api.platform`
      imports no module; only `atesta_api.modules.identity` imports `atesta_api.platform.tenancy`.
- [ ] One DB session per request, committed before the response is sent (Request transaction
      below). A failed commit returns an error code, never 2xx.
- [ ] Engine: `hide_parameters=True` and `echo=False` in every environment, so bound values
      (document text, emails) never reach exception text or logs (rule 2).
- [ ] App to Postgres traffic is TLS 1.2+ with server authentication (NFR-03, client side).
      `platform/db.py` sets `sslmode` and `sslrootcert` itself, never from the URL.
      `ATESTA_DB_SSLMODE` defaults to `verify-full` with the Amazon RDS CA bundle, pinned in the
      repo (`platform/certs/`, source URL and SHA-256 in its README) and shipped in the wheel and
      the image; neither the URL, `PGSSLROOTCERT` nor `~/.postgresql/root.crt` can replace it.
      `make_engine` accepts only `verify-full` and `disable`; modes that do not authenticate the
      server are refused at engine creation, so API, migrations and worker are all covered. Only
      local and CI set `ATESTA_DB_SSLMODE=disable`. The host must be the RDS endpoint name (not an
      IP or CNAME), because `verify-full` checks it.
- [ ] API startup fails on any condition in Startup guard below.
- [ ] `audit_events` plus `platform.audit.record()`, writing in the caller's transaction;
      append-only by grant.
- [ ] Migrations are immutable once merged, forward-only, and import no application code. RLS
      SQL comes from frozen helpers in `apps/api/migrations/rls_v1.py`. A policy change is a
      `rls_v2.py` plus a migration that reapplies it to every affected table.
- [ ] CI runs DB tests against a Postgres 18 service container pinned by digest, with
      `ATESTA_TEST_DATABASE_URL` set. Locally DB tests skip when the URL is unset. When `CI` is
      `true` and the URL is unset, the pytest session fails before any test. `compose.yaml` starts
      the same image digest for local runs.

## Out of scope

- RDS provisioning, DB credentials in Secrets Manager, CloudTrail trail, and the server side of
  NFR-03: `rds.force_ssl = 1`, `ssl_min_protocol_version = TLSv1.2`, KMS at rest (infra spec).
- pgvector (AI spec). Procrastinate tables (scanning spec): the linter fails on any unclassified
  table, so that spec must place them and update ADR-012.
- Read replicas, partitioning, PgBouncer.
- Org offboarding and erasure (NFR-08, offboarding spec). It runs as `atesta_owner` or a
  dedicated role that spec defines, never as `atesta_app`.

## Design notes

### Layout

```text
apps/api/src/atesta_api/
  platform/              Shared kernel, not a module. Imports no module. Empty __init__.py.
    db.py                make_engine() (the only Engine factory), sessionmaker, Base with naming
                         convention, TenantMixin, DbSession
    context.py           TenantContext (read-only value type, any module may import it)
    tenancy.py           Organization model (tenant root), set_tenant_context(); identity only
    audit.py             AuditEvent model, record()
    schema_check.py      Table-class registry and linter queries (tests and deploy job)
  modules/<m>/models.py  ORM models, private to the module
apps/api/migrations/     bootstrap.sql, rls_v1.py, env.py (imports platform and every module's
                         models), versions/
```

ADR-008 gains a "Shared kernel" paragraph; its module list is unchanged. Models reference
`organizations.id` by table name through `TenantMixin`, so modules never import `tenancy`.

### Tenant context

| Setting | Value | Read by |
|---|---|---|
| `app.subject` | Cognito `sub` from a verified token | `users` policies |
| `app.user_id` | `users.id` of the caller | identity read policies |
| `app.organization_id` | Active org, set by `identity.api` (ADR-012 entry points) | Every tenant table |
| `app.invitation_token_sha256` | Hash of a presented invitation token | `invitations` read policy |

The first migration creates two functions owned by `atesta_owner`, `LANGUAGE sql STABLE`, not
SECURITY DEFINER. The planner inlines them, so an index on `organization_id` still applies
(checked with EXPLAIN on Postgres 16):

```sql
CREATE FUNCTION app_setting_uuid(name text) RETURNS uuid LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting(name, true), '')::uuid $$;
CREATE FUNCTION app_setting_text(name text) RETURNS text LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting(name, true), '') $$;
```

Standard policy (`rls_v1.tenant_policy_sql(table)`):

```sql
ALTER TABLE t ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON t
  USING (organization_id = app_setting_uuid('app.organization_id'))
  WITH CHECK (organization_id = app_setting_uuid('app.organization_id'));
```

- `NULLIF`: after a transaction that called `set_config(name, value, true)` ends, Postgres resets
  that setting to `''`, not NULL, for the rest of the session, and `''::uuid` raises. The reset is
  per name, so on a pooled connection one setting can be `''` while another is NULL. NULL compares
  false, so a missing setting returns no rows.
- Pool safety: transaction-local settings die with the transaction. Session-level settings are
  forbidden: no `SET app.`, `SET SESSION app.`, `set_config(..., false)`, `-c app.` options or
  `ALTER ROLE/DATABASE ... SET app.`. A static test checks the repo; the startup guard checks the
  database.
- Tables are not `FORCE`d, so `atesta_owner` bypasses RLS. That keeps catalog loads and
  offboarding simple, and is why owner-owned views, materialized views and SECURITY DEFINER
  functions are banned.

### Request transaction

`platform.db.get_db()` is a yield dependency: one session, commit on success, rollback on any
exception. It is used only through `DbSession = Annotated[Session, Depends(get_db,
scope="function")]` (FastAPI 0.121+). Function scope commits before the response is sent; the
default request scope commits after the client already has a 2xx. Every dependency and handler
takes `DbSession`; any other use of `get_db` (bare, another scope, qualified, keyword or aliased,
on a route or an `include_router`) is forbidden, because mixed scopes create two sessions and the
tenant context would sit on a different transaction from the writes. READ COMMITTED.

### What RLS does and does not do

RLS stops a query that forgets the tenant filter. It does not stop app code that sets the wrong
context. `app.organization_id` is set in one place, `identity.api.enter_org_context()`, for the
closed list of reasons in ADR-012. Role checks stay in the app (`identity.api.require_role`).

### Startup guard

On a fresh pooled connection, startup fails if the runtime role:

- is superuser or has BYPASSRLS;
- is a member of any role (`pg_auth_members.member`; the RDS master user's automatic grant on the
  role, where the runtime role is `roleid`, is allowed);
- has the privileges of the owner of any table, view, sequence, function or schema in `public`
  (`pg_has_role(current_user, owner, 'USAGE')`);
- holds TRUNCATE on any table, CREATE on `public`, a write privilege on an append-only or catalog
  table, or any privilege on `alembic_version`. Table-level checks use `has_table_privilege`
  (it counts PUBLIC and inherited grants); column grants are checked with
  `has_any_column_privilege`, which `has_table_privilege` does not see;
- holds UPDATE on a retention table, or the table lacks its restrictive DELETE policy
  `retention` (ADR-012 amendment 9);
- has an `app.*` default in `pg_db_role_setting` (role, database or all roles), or any of the four
  settings is non-empty on the fresh connection (checked by name: placeholders are not in
  `pg_settings`, and this also catches `-c app.*` in the DSN);
- connected without TLS 1.2 or 1.3 (`pg_stat_ssl` for `pg_backend_pid()`), unless
  `ATESTA_DB_SSLMODE=disable`.

### Conventions

| Topic | Rule |
|---|---|
| Primary keys | Tenant tables: `id uuid`, uuid4 generated in Python. Catalog tables: natural text keys (control-model spec). |
| Timestamps | `created_at timestamptz NOT NULL DEFAULT now()`; `updated_at` only where rows change. |
| Enumerations | `text` + CHECK constraint, not Postgres ENUM (cheap to extend). |
| Constraint names | Naming convention on `MetaData`, so autogenerate diffs are stable. |
| Schema source | Every table, column, index, unique constraint and FK is declared on a model. Migrations use raw SQL only for what autogenerate ignores (RLS, policies, grants, functions). `env.py` limits autogenerate to tables in `Base.metadata`. |
| Tenant FKs | Composite with `organization_id` (criterion above). |
| Cross-module FKs | Only to `organizations.id` (tenant root, in `platform`). Other cross-module references are plain columns validated through the owning module's `api.py` (ADR-008). |
| Deletes | `ON DELETE RESTRICT` to `organizations`. Offboarding goes through each module's `api.py` with the role the offboarding spec defines. |
| Migrations | Forward-only: `downgrade()` raises. Rollback is a new migration or an RDS snapshot restore. |

### Drivers, sync vs async, licenses

| Choice | Decision | Why |
|---|---|---|
| Driver | psycopg 3 | Procrastinate (ADR-003) depends on `psycopg[pool]`; one driver for both. Transactional enqueue uses Procrastinate's `SyncPsycopgConnector` with the session's raw psycopg connection. `SQLAlchemyPsycopg2Connector` is not used: it needs psycopg2. |
| License | psycopg is LGPL-3.0 | Used unmodified as a library (ADR-006 amendment 1). |
| ORM / migrations | SQLAlchemy 2, Alembic | MIT. |
| Sync vs async | Sync | One builder, low load, simpler tests; FastAPI runs sync endpoints in a threadpool. Revisit on ADR-008 triggers. |

### Audit events

`audit_events(id, organization_id, actor_user_id NULL, action, target_type, target_id, metadata
jsonb, request_id, occurred_at)`.

- `action` is a dotted code, e.g. `org.created`.
- `record()` takes typed scalar fields only, so secrets, tokens and document contents cannot reach
  `metadata` (rule 2).
- Grants: `atesta_app` INSERT, SELECT.
- Events always belong to an org. User-level events (sign-up, sign-in, MFA, password reset) are
  not here. Their only record is CloudTrail, whose event history keeps 90 days, so the infra spec
  adds a trail to S3 in eu-south-2 before the first external user signs up.

### Schema linter

`platform.schema_check` holds the table-class registry from ADR-012 and the queries. It runs as a
test and, after `alembic upgrade`, in the deploy job against the target database. It covers every
schema except `pg_catalog`, `information_schema` and `pg_toast`, ignoring extension-owned objects:

1. Every table and foreign table is in exactly one class; anything unclassified, or registered
   in two classes, fails. Views are governed by items 4 and 6; materialized views are banned.
2. Tenant tables: `organization_id uuid NOT NULL` with an FK to `organizations(id)`, index leading
   with it, RLS enabled.
3. Policies of every table (name, command, permissive, roles, `qual`, `with_check` from
   `pg_policies`) equal a checked-in snapshot. Any added, removed or changed policy fails until
   the snapshot changes in the same reviewed PR.
4. Privileges granted to `atesta_app` or to PUBLIC on every relation in `public`, table and
   column level and with any grant option, read from the ACLs (`aclexplode` on `relacl` and
   `attacl`), equal a checked-in grants snapshot. Migrations grant only through
   `rls_v1.grant()`, never with raw `GRANT` text (static test).
5. FKs between tenant tables include `organization_id` on both sides; unique constraints and
   exclusion constraints on tenant tables lead with `organization_id` (compared with `=` in an
   exclusion constraint), except a unique key on `id` alone. Key columns only: INCLUDE columns do
   not count, and an expression is never `organization_id`.
6. Views have `security_invoker = true`; no materialized views; no SECURITY DEFINER functions; no
   rewrite rules other than a view's `_RETURN`; FK actions only NO ACTION or RESTRICT. Rule actions
   and referential actions run as the table owner, so they would bypass RLS and grants.

## Test plan

| Test | Proves |
|---|---|
| Schema linter (all six checks) passes on head | Rule 3 holds for every future object |
| Linter negative fixtures: extra `USING (true)` policy, altered `tenant_isolation` predicate, unclassified table, table in two classes, view without `security_invoker`, materialized view, SECURITY DEFINER function, rewrite rule (table and view), CASCADE or SET DEFAULT FK, single-column tenant FK, tenant table without FK to `organizations`, unique key not led by `organization_id` (plain, expression only, tenant only in INCLUDE), exclusion constraint not led by `organization_id WITH =`, TRUNCATE, column, PUBLIC and grant-option grants: each fails. `(organization_id, expr)` and `(id) INCLUDE (...)` stay clean | The linter catches each fail-open object |
| Cross-tenant matrix on a probe table, orgs A and B: context A sees only A; insert with B's id fails WITH CHECK; update and delete of B rows affect 0; TRUNCATE denied; child row pointing at B's parent fails with the same FK error as a random id | RLS isolation, no cross-tenant references |
| No context: every table with RLS (found from `pg_class.relrowsecurity`) returns 0 rows, no error | Fail closed |
| Pool reuse, `pool_size=1`, real commits: transaction sets context A and commits; next transaction has the same `pg_backend_pid()`, every `app.*` setting is empty and every RLS table returns 0 rows | No leak across the pool |
| Startup guard: one test per condition (owner role granted with INHERIT; BYPASSRLS role granted with INHERIT FALSE, SET TRUE; `pg_write_all_data` granted; UPDATE on `audit_events`; TRUNCATE on a tenant table; `ALTER ROLE ... SET app.organization_id`; `-c app.user_id` in the DSN); clean setup starts | Defense in depth |
| `audit_events`: UPDATE and DELETE as `atesta_app` denied; `record()` in a rolled-back transaction leaves no row, in a committed one exactly one | Append-only, atomic with the action |
| Request transaction: a handler whose INSERT fails at commit returns an error and stores no audit event | No 2xx for lost writes |
| Engine from `make_engine()`: an INSERT carrying a marker string fails (RLS WITH CHECK, CHECK violation); marker absent from exception text and captured logs. No `create_engine(` outside `platform/db.py` | `hide_parameters` everywhere (rule 2) |
| Engine connect args (captured before libpq): with `ATESTA_DB_SSLMODE` unset, `sslmode` is `verify-full` and `sslrootcert` the bundled RDS CA, even with `sslmode`/`sslrootcert` in the URL and `PGSSLROOTCERT` set; `disable` sets no root certificate; `allow`, `prefer`, `require`, `verify-ca` raise; the bundle's SHA-256 is pinned and it holds the three eu-south-2 roots; the wheel config ships it. The default engine against the CI container (no TLS) fails with an SSL error; the API refuses to start with `ATESTA_DB_SSLMODE=prefer`; the guard still raises on a plaintext connection when TLS is required | Server authentication by default; no plaintext fallback |
| Static checks: no session-level `app.*` setting in any `.py`, `.sql`, `.sh`, `.ts(x)` or `.(m)js` file under `apps/` (tests, `node_modules`, `.venv` and build output excluded; a self-test plants a worker `.py` and a `.sql` file); no `set_config(` on `app.` outside `platform/tenancy.py`; no bare `Depends(get_db)`; a walk of the app's effective dependency graph finds `get_db` only at function scope, and flags bare, request-scope, qualified, keyword, aliased and router-level forms in a throwaway app; migrations import nothing from `atesta_api` | Pool safety, immutable migrations |
| On a copy of the source tree, `lint-imports` fails on a deliberate import of `platform.tenancy` from an existing module, a new module, a `platform` module and a new top-level file (a `protected` contract), and on a new module importing identity internals (independence over `atesta_api.modules.*`); the unmodified copy passes | Only identity sets context; rule 8 for new modules |
| Alembic: upgrade head on an empty DB as `atesta_owner`, then `alembic check` (with `compare_server_default`) finds no diff; a second DB built with `Base.metadata.create_all` has the same constraints (name and `pg_get_constraintdef`), indexes (`indexdef`) and columns (default, nullability, type, generation) on every model table, because `alembic check` does not compare CHECKs or partial-index predicates; `NAMING_CONVENTION` equals a frozen copy, since migrations build names through it. New migrations name constraints with `op.f()` | Models and migrations agree |
| `CI=true` without `ATESTA_TEST_DATABASE_URL`: pytest exits non-zero; set but unreachable URL errors, never skips | DB tests cannot be skipped silently |

DB fixtures. Session setup runs `bootstrap.sql` as superuser and migrates as `atesta_owner`; test
code runs as `atesta_app`.

- `db_rollback`: one outer transaction per test, rolled back. Only for tests that run a single
  application transaction: inside it a commit only releases a SAVEPOINT, so a
  `set_config(..., true)` value survives for the rest of the test.
- `db_commit`: real commits, as in production. Required for context-lifetime tests, the startup
  guard and any multi-request test. Teardown as `atesta_owner` truncates every non-catalog table
  and drops roles the test created.
