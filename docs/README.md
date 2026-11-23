# Documentation

Start with the question you have.

## What Atesta is and where it stands

- [README](../README.md): what it is, layout, quick start.
- [PRODUCT.md](../PRODUCT.md): product context, what is usable and what is not.
- [DESIGN.md](../DESIGN.md): visual and interaction design.
- [status/dashboard-readiness.md](status/dashboard-readiness.md): implementation inventory and
  what is missing per framework.
- [ROADMAP.md](../ROADMAP.md): the engineering order of work and its gates.

## How to change it

- [AGENTS.md](../AGENTS.md): the rules for every change (imported by `CLAUDE.md`).
- [GOVERNANCE.md](../GOVERNANCE.md): who decides what, where it is recorded, how releases work.
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
| [ADR-014: A read-only device agent that reports posture and never acts](adr/0014-device-agent.md) | proposed (2026-11-23) |
| [ADR-015: The repository is public](adr/0015-public-repository.md) | proposed (2026-11-23) |
| [ADR-016: An MCP server lets AI agents work with Atesta through scoped API keys](adr/0016-mcp-server-for-ai-agents.md) | proposed (2026-11-23) |

## Feature specs

- [api-keys-v2](specs/api-keys-v2.md)
- [auditor-dossier](specs/auditor-dossier.md)
- [claims-honesty](specs/claims-honesty.md)
- [console-shell](specs/console-shell.md)
- [consultancy-portfolio](specs/consultancy-portfolio.md)
- [content-model-v2](specs/content-model-v2.md)
- [control-evidence-statements](specs/control-evidence-statements.md)
- [control-model-schema](specs/control-model-schema.md)
- [cookie-information](specs/cookie-information.md)
- [dashboard-overview](specs/dashboard-overview.md)
- [device-agent](specs/device-agent.md)
- [evidence-ingestion-api](specs/evidence-ingestion-api.md)
- [framework-catalog-preview](specs/framework-catalog-preview.md)
- [framework-detail](specs/framework-detail.md)
- [hosted-environment](specs/hosted-environment.md)
- [i18n-complete](specs/i18n-complete.md)
- [identity-auth](specs/identity-auth.md)
- [infra-dev](specs/infra-dev.md)
- [insights](specs/insights.md)
- [landing-legal](specs/landing-legal.md)
- [local-dev-auth](specs/local-dev-auth.md)
- [management-report](specs/management-report.md)
- [manual-control-review](specs/manual-control-review.md)
- [mcp-server](specs/mcp-server.md)
- [organization-closure](specs/organization-closure.md)
- [organization-shell-design](specs/organization-shell-design.md)
- [rbac](specs/rbac.md)
- [readiness-cockpit](specs/readiness-cockpit.md)
- [recorded-routines](specs/recorded-routines.md)
- [requirement-register](specs/requirement-register.md)
- [scanner-connectors](specs/scanner-connectors.md)
- [tenant-data-layer](specs/tenant-data-layer.md)
- [web-shell](specs/web-shell.md)
- [workspace-ux](specs/workspace-ux.md)

## Scanner notes

- [prowler-coverage](scanner/prowler-coverage.md): where each pinned Prowler check lands, Prowler's
  own mappings compared, and what the PowerShell-backed M365 checks need.

## Runbooks

- [onboarding](runbooks/onboarding.md): a new customer, from contract to first review.
- [demo](runbooks/demo.md): a realistic demo organization on the local stack.
- [offboarding](runbooks/offboarding.md): export, closure and erasure at the end of a contract.
- [security-incident](runbooks/security-incident.md): triage, containment, fix and notification.
- [deploy](runbooks/deploy.md): from no AWS account to a running environment, rollback, and the
  monthly cost estimate.

Restore drills come with the first applied environment.

## Catalog

- [catalog/README.md](../catalog/README.md): common controls and framework packs.
- [catalog/PREPARATION.md](../catalog/PREPARATION.md): preparation templates and their limits.
- Sources behind each official pack:
  - [ENS](../catalog/frameworks/ens_rd311_2022/SOURCES.md)
  - [NIS2](../catalog/frameworks/nis2/SOURCES.md)
  - [GDPR, Art. 32 to 34](../catalog/frameworks/gdpr_art32/SOURCES.md)
  - [DORA](../catalog/frameworks/dora/SOURCES.md)

  Each pack's `coverage.yaml` lists every unit of its source.

## Security and legal

- [SECURITY.md](../SECURITY.md): reporting, controls and the tests that hold them.
- [security/device-agent-threat-model.md](security/device-agent-threat-model.md): STRIDE threat
  model of the device agent (design only).
- [legal/subprocessors.md](legal/subprocessors.md): draft sub-processor list for the DPA.
- [LICENSE](../LICENSE) and [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Components

- [apps/web](../apps/web/README.md), [apps/worker](../apps/worker/README.md),
  [scanner](../scanner/README.md), [infra](../infra/README.md).
