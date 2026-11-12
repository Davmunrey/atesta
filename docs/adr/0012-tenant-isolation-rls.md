# ADR-012: Tenant isolation with Postgres row-level security

- Status: proposed (2026-11-12)

## Context
CLAUDE.md rule 3 requires `organization_id` on every table. Two kinds of data have no single
tenant: user identities (one person can belong to several orgs) and the framework catalog
(content shared by all tenants, ADR-011). Isolation must not depend on every query carrying a
correct `WHERE` clause.

## Decision
- Tenant tables: `organization_id NOT NULL` plus an RLS policy on the transaction-local setting
  `app.organization_id`. Runtime role `atesta_app` cannot bypass RLS; migrations run as
  `atesta_owner`.
- Global tables, closed list: `users` (identity only, own RLS policy), catalog tables (read-only
  for `atesta_app`), `alembic_version`. Adding a table to this list requires updating this ADR.
- Tenant context is set only by `identity.api`, after a membership check or a valid invitation
  acceptance.
- A schema-linter test fails CI for any table outside the list that lacks `organization_id`, RLS
  or the standard policy.
- Cross-module foreign keys only to `organizations.id`.

## Consequences
A forgotten filter returns nothing instead of leaking. Every request runs in one transaction.
Catalog loads need the owner role (deploy step). The policy predicate costs a little per query;
indexes leading with `organization_id` keep it cheap.
