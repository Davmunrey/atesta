# Atesta

Continuous ENS / NIS2 audit readiness for Spanish SMEs.

Connect Microsoft 365 or Google Workspace with read-only access. Atesta scans daily, maps every
result to ENS (RD 311/2022) Annex II measures, guides the organizational measures and exports an
auditor-ready evidence pack.

> Readiness tool. Atesta does not issue certificates.

## Repository layout

```text
apps/
  api/        FastAPI service (modular monolith)
  worker/     Background jobs: schedule, ingest, report
  web/        Next.js + TypeScript UI
scanner/      Container image: pinned Prowler + Atesta custom checks
packages/
  core/       Pure domain logic: scoring, diff
catalog/      ENS / NIS2 / ISO control catalog (YAML)
infra/        OpenTofu (AWS eu-south-2)
docs/adr/     Architecture decision records
docs/specs/   One spec per feature, written before code
```

## Quick start

```bash
uv sync --all-packages
uv run ruff check .
uv run mypy
uv run lint-imports
uv run pytest
uv run uvicorn atesta_api.main:app --reload
```

## Source of truth

Product, business and technical plan: the "Atesta" project doc (Roadmap, Business plan,
Requirements, Architecture, Code plan, Infrastructure). Decisions that change architecture get an
ADR in `docs/adr/`.

## License

Proprietary. All rights reserved. Third-party notices in `THIRD_PARTY_NOTICES.md`.
