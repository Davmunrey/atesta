# Atesta

[![ci](https://github.com/Davmunrey/atesta/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Davmunrey/atesta/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Davmunrey/atesta/badge)](https://scorecard.dev/viewer/?uri=github.com/Davmunrey/atesta)

Continuous audit readiness for every compliance framework. Test once, comply with many.
Starting with ENS (RD 311/2022) and NIS2 for Spanish SMEs; ISO 27001, RGPD, DORA and SOC 2 follow
as framework packs.

Connect Microsoft 365 or Google Workspace with read-only access. Atesta scans daily, maps results
to common controls, scores every selected framework from the same evidence, guides the
organizational measures and exports an auditor-ready evidence pack.

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

Proprietary. All rights reserved: see `LICENSE`. Third-party notices in `THIRD_PARTY_NOTICES.md`.

## Security

How to report a vulnerability, and which control is held by which test: `SECURITY.md`.
