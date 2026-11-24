# ADR-008: Modular monolith with enforced boundaries

- Status: accepted (2026-11-12)

## Decision
One deployable backend with modules: identity, connections, scanning, compliance, evidence, ai,
billing. Modules interact only through `api.py`. `lint-imports` enforces it in CI. No
cross-module database joins.

## Shared kernel (accepted 2026-11-13)
`atesta_api.platform` (db, context, tenancy, audit, schema_check) is not a module. Modules may
import it; it imports no module. Only the identity module may import `platform.tenancy`, the code
that sets tenant context (ADR-012). Both rules are import-linter contracts.

## Extraction triggers
- > 200 scans/day or ingest slows the API: extract the ingest worker.
- AI cost/latency hurts UX: ai module behind its own queue.
- Enterprise isolation demand: dedicated tenant (separate account), not microservices.

## Consequences
One deploy, cheap refactors, clean due diligence. Requires discipline on boundaries.

## Amendment 1 (accepted by the owner 2026-11-23, notifications spec)

- **New module `notifications`.** It owns notification preferences, the delivery log, the mailer,
  the email templates and the notification jobs' logic. Like every module, it is reached only
  through its `api.py`.
- **Dependencies.**
  - It reads recipients through `identity.api` and due items through `compliance.api`.
  - Connections, scanning and compliance call `notifications.api` to queue a notice in the
    same transaction as the event that causes it.
  - It never joins another module's tables.
- **Why a module:** sending email and computing who receives what is a responsibility of its
  own. Inside identity or compliance it would grow a module that has nothing to do with email.
