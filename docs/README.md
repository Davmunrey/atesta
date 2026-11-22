# Documentation

Start with the question you have.

## What Atesta is and where it stands

- [README](../README.md): what it is, layout, quick start.
- [PRODUCT.md](../PRODUCT.md): product context, what is usable and what is not.
- [DESIGN.md](../DESIGN.md): visual and interaction design.
- [status/dashboard-readiness.md](status/dashboard-readiness.md): implementation inventory and
  what is missing per framework.

## How to change it

- [AGENTS.md](../AGENTS.md): the rules for every change (imported by `CLAUDE.md`).
- [CONTRIBUTING.md](../CONTRIBUTING.md): set up, checks, issue to merge, review.
- [specs/_template.md](specs/_template.md): start of every feature.

## Architecture decisions

| ADR | Status |
| --- | --- |
| [ADR-001: Python backend, Next.js frontend](adr/0001-python-backend-nextjs-frontend.md) | accepted (2026-11-12) |
| [ADR-002: Prowler as scan engine, pinned, wrapped not forked](adr/0002-prowler-scan-engine.md) | accepted (2026-11-12) |
| [ADR-003: Postgres-backed job queue](adr/0003-postgres-queue.md) | accepted (2026-11-12) |
| [ADR-004: One ephemeral Fargate task per scan](adr/0004-one-container-per-scan.md) | accepted (2026-11-12) |
| [ADR-005: AI explains, deterministic checks decide](adr/0005-ai-explains-checks-decide.md) | accepted (2026-11-12) |
| [ADR-006: No AGPL/GPL dependencies in network-facing services](adr/0006-no-agpl.md) | accepted (2026-11-12) |
| [ADR-007: AWS Spain region only](adr/0007-aws-spain-region.md) | accepted (2026-11-12) |
| [ADR-008: Modular monolith with enforced boundaries](adr/0008-modular-monolith.md) | accepted (2026-11-12) |
| [ADR-009: Single entitlements service gates plans and add-ons](adr/0009-entitlements.md) | accepted (2026-11-12) |
| [ADR-010: RAG with citations and guardrails; no fine-tuning](adr/0010-rag-with-guardrails.md) | accepted (2026-11-12) |
| [ADR-011: Framework-agnostic control model; frameworks are content packs](adr/0011-framework-agnostic-control-model.md) | accepted (2026-11-12) |
| [ADR-012: Tenant isolation with Postgres row-level security](adr/0012-tenant-isolation-rls.md) | accepted (2026-11-12) |
| [ADR-013: Third-party agent tooling is vendored, pinned and reviewed](adr/0013-agent-tooling.md) | accepted (2026-11-12) |

## Feature specs

- [control-evidence-statements](specs/control-evidence-statements.md)
- [control-model-schema](specs/control-model-schema.md)
- [cookie-information](specs/cookie-information.md)
- [dashboard-overview](specs/dashboard-overview.md)
- [framework-catalog-preview](specs/framework-catalog-preview.md)
- [framework-detail](specs/framework-detail.md)
- [identity-auth](specs/identity-auth.md)
- [infra-dev](specs/infra-dev.md)
- [landing-legal](specs/landing-legal.md)
- [local-dev-auth](specs/local-dev-auth.md)
- [manual-control-review](specs/manual-control-review.md)
- [organization-shell-design](specs/organization-shell-design.md)
- [scanner-connectors](specs/scanner-connectors.md)
- [tenant-data-layer](specs/tenant-data-layer.md)
- [web-shell](specs/web-shell.md)

## Catalog

- [catalog/README.md](../catalog/README.md): common controls and framework packs.
- [catalog/PREPARATION.md](../catalog/PREPARATION.md): preparation templates and their limits.
- [ENS sources](../catalog/frameworks/ens_rd311_2022/SOURCES.md): official texts behind the ENS
  draft.

## Security and legal

- [SECURITY.md](../SECURITY.md): reporting, controls and the tests that hold them.
- [LICENSE](../LICENSE) and [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Components

- [apps/web](../apps/web/README.md), [apps/worker](../apps/worker/README.md),
  [scanner](../scanner/README.md), [infra](../infra/README.md).
