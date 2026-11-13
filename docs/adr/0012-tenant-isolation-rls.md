# ADR-012: Tenant isolation with Postgres row-level security

- Status: accepted (2026-11-12). Revision of 2026-11-13 (adversarial spec review, before any
  code) pending approval.

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
  materialized views and SECURITY DEFINER functions are banned.
- Tenant context is set only by `identity.api.enter_org_context()`, for four reasons: a
  membership check, a valid invitation acceptance, creation of an org with a server-generated
  id, and `job` for worker jobs (scanning spec). Only the identity module may import
  `platform.tenancy` (import-linter). Job payloads carry ids only.
- FKs between tenant tables are composite with `organization_id`; unique constraints lead with
  it. Cross-module FKs only to `organizations.id`.
- A schema linter, in CI and in the deploy job, fails on any unclassified table, any policy or
  grant that differs from the reviewed snapshot, single-column tenant FKs, and banned objects.
  Third-party tables (for example Procrastinate) must be classified here before merge.

## Consequences
A forgotten filter returns nothing instead of leaking. Every request runs in one transaction,
committed before the response. Catalog loads and offboarding need the owner role or a role the
offboarding spec defines. The policy predicate costs a little per query; the setting helpers
inline, so indexes leading with `organization_id` keep it cheap. Policy changes need a new
migration and a snapshot update in the same PR.
