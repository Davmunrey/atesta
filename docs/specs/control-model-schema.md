# Spec: Framework-agnostic control model schema

- Requirement ids: MF-01, MF-02, MF-03, MF-06, FR-05, FR-08, NFR-05
- Status: draft
- ADRs: ADR-005, ADR-008, ADR-011, ADR-012 (proposed)
- Build order: 3 of 3 (depends on tenant-data-layer)

## Problem

One scan must score every framework a customer selects (ADR-011). If ENS measures become tables
or columns, every new pack (NIS2, ISO 27001) is a migration and a code path. The schema must hold
any pack as content, keep mapping provenance for auditors (MF-06) and keep evidence and scores
isolated per tenant.

## Acceptance criteria

- [ ] Catalog tables, global, owned by the compliance module: `frameworks`, `requirements`,
      `controls`, `checks`, `control_checks`, `mappings`. Natural text keys from the YAML. No
      `organization_id`. `atesta_app` has SELECT only; only `atesta_owner` writes.
- [ ] Tenant tables with the standard RLS policy: `score_snapshots` (compliance), `evidence` and
      `evidence_controls` (evidence module).
- [ ] No table, column, enum value or code path names a framework. Pack-specific metadata (levels,
      dimensions, groups) goes in `requirements.applies_to` and `requirements.attributes`.
- [ ] Every mapping row carries `source`, `reviewed_by` and `rationale` columns (MF-06).
- [ ] `score_snapshots` and `evidence` are append-only for `atesta_app` (INSERT, SELECT).
      Corrections are new rows.
- [ ] Status values reuse `atesta_core.scoring.Status` (`pass`, `fail`, `not_applicable`,
      `manual`).
- [ ] Each snapshot stores framework version, catalog version and the requirement-level results
      it scored, so an auditor can see exactly what produced a score.
- [ ] Retired catalog rows are kept (`retired_at`), never deleted, so old evidence and snapshots
      still resolve.
- [ ] No real framework content in this work: fixtures use synthetic codes (rule 10).

## Out of scope

- YAML loader, validation, catalog sync job, Prowler check-id validation (catalog spec, week of
  11 Jan). The sync job is what refuses to release a pack with unreviewed mappings.
- Per-org framework selection and ENS categorization (MF-04, FR-06, categorization spec).
- Scan, Finding and per-scan control results (scanning spec, week of 4 Jan).
- S3 storage, Object Lock, evidence pack export (evidence spec, week of 18 Jan).
- Exceptions and risk acceptance (FR-11).

## Design notes

### Shape

```text
checks --< control_checks >-- controls --< mappings >-- requirements >-- frameworks
                                  |                                        |
                    evidence_controls >-- evidence        score_snapshots -+
                    (tenant)                              (tenant)
```

### Catalog tables (global, read-only at runtime)

| Table | Key | Other columns |
|---|---|---|
| `frameworks` | `key` (e.g. `ens_rd311_2022`) | name, version, jurisdiction, source, license_notes, status (`draft`/`reviewed`/`released`), retired_at |
| `requirements` | (`framework_key`, `code`) | title_es, title_en, applies_to `text[]`, source, attributes `jsonb`, retired_at |
| `controls` | `key` (e.g. `ctl.mfa_all_users`) | title_es, title_en, description_es, description_en, manual, remediation_refs `text[]`, retired_at |
| `checks` | (`engine`, `check_id`) | engine (`prowler`/`atesta`), engine_version, retired_at |
| `control_checks` | (`control_key`, `engine`, `check_id`) | none |
| `mappings` | (`framework_key`, `requirement_code`, `control_key`) | rationale, source, reviewed_by |

- Columns mirror `catalog/**/_template.yaml` one to one, plus `requirements.attributes` (the
  extension point that keeps rule 9; template updated in the catalog spec).
- Natural keys, not uuids: YAML is the source of truth and the DB a projection, so a load is an
  idempotent upsert by key, and keys read the same in YAML, DB, logs and evidence manifests.
- Catalog version = the app release that shipped it (catalog is versioned with the code), read
  from a build constant. No catalog version table.

### Tenant tables

| Table | Module | Columns |
|---|---|---|
| `score_snapshots` | compliance | id, organization_id, framework_key (FK), framework_version, catalog_version, scan_id `uuid NULL` (no FK: scanning module), score `numeric(4,1) NULL`, passed, failed, manual, not_applicable, requirement_results `jsonb` (`{code: status}`), computed_at |
| `evidence` | evidence | id, organization_id, kind (`scan_output`/`document`/`attestation`), title, storage_key, sha256 `char(64)`, media_type, size_bytes, source_type (`scan`/`upload`/`user`), source_id `uuid NULL`, created_by `uuid NULL`, collected_at, created_at |
| `evidence_controls` | evidence | organization_id, evidence_id (FK), control_key (`text`, no FK: compliance module); PK (evidence_id, control_key) |

- `score` NULL means "not assessed", same contract as `atesta_core.scoring.score`.
- CHECK: `scan_output` and `document` rows require `storage_key` and `sha256`, and `sha256`
  matches `^[0-9a-f]{64}$` (NFR-05).
- `evidence_controls.control_key` is validated through `compliance.api` at write time
  (ADR-008: no cross-module FKs or joins). One piece of evidence serves every framework mapped to
  the control (MF-02).
- Trend index: `(organization_id, framework_key, computed_at DESC)` (FR-08).
- `requirement_results` is JSONB so a snapshot is one immutable, self-contained row per framework
  per scan. If per-requirement trend queries get slow, add a child table then.

### Scoring stays in packages/core

Tables store inputs and outputs. `atesta_core.frameworks.framework_results` computes. The
compliance module maps rows to core dataclasses; no scoring logic in SQL.

## Test plan

| Test | Proves |
|---|---|
| Migration up/down; schema linter passes with catalog tables on the global allowlist | Rule 3 with documented exceptions |
| `atesta_app` INSERT, UPDATE, DELETE on any catalog table: permission denied | Catalog read-only at runtime |
| `atesta_app` UPDATE, DELETE on `score_snapshots`, `evidence`: permission denied | Append-only |
| Org A cannot see org B snapshots or evidence; insert with B's id fails | Tenant isolation |
| CHECK constraints: bad kind, engine or status rejected; file evidence without sha256 rejected; malformed sha256 rejected | Integrity |
| Two synthetic frameworks mapped to shared controls; one control result set; `framework_score` from DB rows equals the expected score for both | "Test once, comply with many" end to end |
| Guard test: no framework identifiers (`ens_`, `nis2`, `iso27001`, `rd311`, ...) in `apps/api/src` or migrations, outside an allowlist | Rule 9 stays enforced |
