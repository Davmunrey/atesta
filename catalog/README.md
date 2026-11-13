# Control catalog

Atesta's core IP, framework-agnostic (ADR-011): common controls, framework packs, and the
many-to-many mappings between them. Versioned with the code; every catalog release re-indexes the
RAG corpus (ADR-010).

## Layout

```text
catalog/
  controls/                 Common Atesta controls, one YAML per control
  frameworks/<pack>/
    pack.yaml               Framework metadata and version
    requirements.yaml       Requirements copied from the official text
    mappings.yaml           Requirement -> control mappings
```

Pack order: ENS (wedge) -> NIS2 -> ISO 27001 -> RGPD art. 32 -> DORA -> SOC 2 and others on demand.

## Rules

- Requirement ids, titles and levels are copied from official sources and verified by a qualified
  reviewer before release. Never written from memory.
- Every mapping records `source` and `reviewed_by` (MF-06).
- Every `prowler_checks` id must exist in the pinned Prowler version (validated in CI).
- `manual: true` controls are organizational: evidence comes from documents, not scans.
- A new pack ships only with 3+ customers/deals asking and >= 60% mapping to existing controls.

## Preparation content

See [the preparation inventory](PREPARATION.md) for the six planned frameworks. NIS2,
ISO/IEC 27001, GDPR Article 32, DORA and SOC 2 currently contain scope/source templates and
candidate preparation controls, with no imported normative requirements or mappings.

`ens_rd311_2022` contains the 73 Annex II measures from the official BOE publication, with
category/dimension tables and application clauses. Its 78 mappings and 26 common-control
guides are candidates awaiting qualified review. Read the pack's `SOURCES.md` for provenance,
technical limits and missing scope. No draft is a certification or a customer assessment.

Run `uv run python -m apps.api.devtools.preview_catalog` to validate all repository packs.
The optional `--import` writes immutable drafts only to a loopback `atesta_dev` database,
using `ATESTA_MIGRATION_DATABASE_URL` and an explicit development `ATESTA_ENV`. Exact reimports
are no-ops; changed existing rows fail transactionally and require an explicit migration.
This command does not publish reviewed/released packs or update production.
Configure the optional owner-capable URL separately from the application login; the commented
example in `apps/api/.env.example` documents its shape. Validation without `--import` needs no
database credentials. `uv run --env-file apps/api/.env python -m apps.api.devtools.preview_catalog --import`
loads local settings explicitly; it does not infer the migration URL from the application URL.

Preview packs set `assessment_enabled: false`: they remain visible with the existing local
draft flag but cannot receive scan scores. Candidate technical mappings retain documentary
review. Preparation controls do not establish equivalence to a normative requirement.
