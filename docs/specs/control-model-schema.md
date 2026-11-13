# Spec: Framework-agnostic control model schema

- Requirement ids: MF-01, MF-02, MF-03, MF-06, FR-05, FR-08, NFR-05
- Status: approved (2026-11-13). Revised 2026-11-13: corrections form one linear chain per
  framework, scan and scope, migration 0007 (implementation review).
- ADRs: ADR-005, ADR-008, ADR-009, ADR-011, ADR-012
- Build order: 3 of 3 (after identity). Not part of the 28 Dec gate (login with MFA in dev);
  built right after identity, ahead of the calendar (owner decision, 2026-11-13).

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
      `evidence_controls` (evidence module). FKs between them are composite with
      `organization_id` (data-layer spec).
- [ ] No table, column, enum value or code path names a framework. Pack-specific metadata
      (levels, dimensions, groups) goes in `requirements.applies_to`, `requirements.attributes`
      and the pack-level declaration in `frameworks.attributes`.
- [ ] Provenance in the schema (MF-06, rule 10): `mappings.source`, `mappings.rationale` and
      `requirements.source` are NOT NULL with `CHECK (btrim(col) <> '')`. `mappings.reviewed_by`
      is NULL until a qualified reviewer signs, with `CHECK (reviewed_by IS NULL OR
      btrim(reviewed_by) <> '')`. The catalog sync job refuses to mark a framework `reviewed` or
      `released` while any of its mappings has `reviewed_by` NULL (catalog spec).
- [ ] `frameworks.status` has runtime meaning: `compliance.api` lists, selects and scores only
      frameworks with `status = 'released'` and `retired_at IS NULL`. Snapshots that reference a
      retired framework still resolve it. Dev may set `ATESTA_CATALOG_INCLUDE_DRAFTS=true`; the
      app refuses to start with it in production.
- [ ] Every catalog table, including `control_checks` and `mappings`, has `retired_at`. Catalog
      rows are never deleted: a load sets `retired_at` on keys absent from the YAML and clears it
      when they return. A load is refused if an active row references a retired one.
- [ ] Scoring and finding-to-control resolution read only active rows (`retired_at IS NULL`).
      Retired rows are read only to display old snapshots and evidence.
- [ ] `score_snapshots` and `evidence` are append-only for `atesta_app` (INSERT, SELECT).
      Corrections are new rows that point at what they supersede.
- [ ] Status values reuse `atesta_core.scoring.Status` (`pass`, `fail`, `not_applicable`,
      `manual`).
- [ ] Each snapshot stores the framework version and catalog version read from the DB, the
      applicability filter, the scope and the requirement-level and group-level results, so an
      auditor can see exactly what produced a score.
- [ ] Framework entitlements are data, not code (ADR-009, MF-03). `billing.api.Feature` keeps
      only framework-agnostic features; `ENS_MEDIUM`, `ENS_HIGH` and `NIS2` are removed. Plan and
      add-on grants live in `catalog/plans.yaml` (`plan or add-on -> framework key -> allowed
      applies_to values, or all`), validated against the loaded catalog.
      `billing.api.has_framework(plan, framework_key, applies_to=None, addons=frozenset())`
      answers. Selling a new pack or level is a YAML change. ADR-009 is amended to list it. Lands
      before or with the guard test.
- [ ] No real framework content in this work: fixtures use synthetic codes (rule 10).

## Out of scope

- YAML loader, validation, catalog sync job, Prowler check-id validation (catalog spec). The constraints above are the backstop.
- Source and license of English requirement titles where no official English text allows
  commercial use (catalog spec; `title_en` stays nullable).
- Per-org framework selection and categorization (MF-04, FR-06, categorization spec). Until it
  lands, compliance scores every released framework with `applicability = {}` and
  `scope_id = NULL`.
- Scan and Finding storage (scanning spec).
- S3 layout, Object Lock, evidence pack export (evidence spec). It may add columns such as
  the S3 version id.
- Human approval of status for `manual` controls (FR-07 spec, ADR-005). Until then they have no
  result, count as `manual` in `framework_results` and stay out of the score. Evidence rows never
  set a control status.
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
| `frameworks` | `key` (e.g. `<pack>_<version>`) | name, version, jurisdiction, source, license_notes, status (`draft`/`reviewed`/`released`), attributes `jsonb`, catalog_version, retired_at |
| `requirements` | (`framework_key`, `code`) | title_es, title_en NULL, applies_to `text[]`, source, attributes `jsonb`, retired_at |
| `controls` | `key` (e.g. `ctl.mfa_all_users`) | title_es, title_en, description_es, description_en, manual, remediation_refs `text[]`, retired_at |
| `checks` | (`engine`, `check_id`) | engine (`prowler`/`atesta`), engine_version, retired_at |
| `control_checks` | (`control_key`, `engine`, `check_id`) | retired_at |
| `mappings` | (`framework_key`, `requirement_code`, `control_key`) | rationale, source, reviewed_by NULL, retired_at |

- Field map (the catalog spec's loader implements it): pack.yaml `id` -> `frameworks.key`, and
  that same id is `framework_key` on requirements and mappings (never the folder name).
  requirements.yaml `id` -> `requirements.code`. mappings.yaml `requirement_id`, `control_id` ->
  `requirement_code`, `control_key`. Control `id` -> `controls.key`. Each id in a control's
  `prowler_checks` or `atesta_checks` upserts one `checks` row and one `control_checks` row. Other
  columns keep their YAML names. No YAML source: `retired_at`, `catalog_version` (set by the sync
  job) and `engine_version` (the pinned Prowler version, or the app release for `atesta`, that the
  id was last validated against). New YAML fields: `requirements.attributes` and
  `frameworks.attributes` (template updated in the catalog spec).
- `frameworks.attributes` declares pack-level vocabularies: allowed `applies_to` values and the
  requirement attribute keys scores may be grouped by (FR-08). Scoring reads grouping keys only
  from this declaration, never a hard-coded name.
- Natural keys, not uuids: YAML is the source of truth and the DB a projection, so a load is an
  idempotent upsert by key, and keys read the same in YAML, DB, logs and evidence manifests.
  Released keys are immutable; a rename is retire plus add plus an explicit data migration.
- Catalog version = the release whose YAML the sync job loaded, stamped on every `frameworks` row
  in the load transaction. Re-running an older release's load (rollback) leaves a truthful stamp.
  API and worker log a warning when it differs from their build constant.

### Tenant tables

| Table | Module | Columns |
|---|---|---|
| `score_snapshots` | compliance | id, organization_id, framework_key (FK), framework_version, catalog_version, scan_id `uuid NOT NULL` (no FK: scanning module), scope_id `uuid NULL` (categorization spec adds its FK; NULL = whole org), applicability `jsonb NOT NULL DEFAULT '{}'`, score `numeric(4,1) NULL`, passed, failed, manual, not_applicable, requirement_results `jsonb` (`{code: status}`), group_scores `jsonb NOT NULL DEFAULT '{}'` (`{attribute_key: {value: score or null}}`), supersedes_id `uuid NULL`, scope_key (generated), computed_at; UNIQUE (organization_id, id) |
| `evidence` | evidence | id, organization_id, kind (`scan_output`/`document`/`attestation`), title, storage_key, sha256 `char(64)`, media_type, size_bytes, source_type (`scan`/`upload`/`user`), source_id `uuid NULL`, created_by `uuid NULL`, collected_at, created_at; UNIQUE (organization_id, id) |
| `evidence_controls` | evidence | organization_id, evidence_id, control_key (`text`, no FK: compliance module); PK (organization_id, evidence_id, control_key); FK (organization_id, evidence_id) to `evidence(organization_id, id)` |

- `score` NULL means "not assessed", same contract as `atesta_core.scoring.score`. CHECKs:
  `score BETWEEN 0 AND 100`, counters `>= 0`, `jsonb_typeof(requirement_results) = 'object'`.
- `requirement_results` holds only the requirements selected by `applicability`; out-of-scope
  requirements are omitted. Group scores are stored, not re-derived, because catalog upserts
  overwrite requirement attributes.
- One original snapshot per scan: partial UNIQUE (organization_id, framework_key, scan_id,
  scope_id) `NULLS NOT DISTINCT WHERE supersedes_id IS NULL`. The snapshot job inserts with
  `ON CONFLICT ... DO NOTHING`, so a retried job is idempotent. A correction is a new row with
  `supersedes_id`; trend and diff read rows nothing supersedes. Corrections form one linear chain
  within one framework, scan and scope: partial UNIQUE (organization_id, supersedes_id) `WHERE
  supersedes_id IS NOT NULL` (a retried correction returns the existing one; a later correction
  supersedes the latest), and the composite FK (organization_id, framework_key, scan_id,
  scope_key, supersedes_id) references the same columns plus `id`. `scope_key` is a stored
  generated `COALESCE(scope_id, nil uuid)`, because an FK with a NULL column is not checked.
- Scoring runs at REPEATABLE READ and copies `framework_version` and `catalog_version` from the
  `frameworks` row it read, so a concurrent catalog load cannot mix versions.
- CHECKs on `evidence` (NFR-05, ADR-005), keyed on whether a file is stored, not on `kind`:
  `num_nulls(storage_key, sha256, media_type, size_bytes) IN (0, 4)`;
  `kind = 'attestation' OR storage_key IS NOT NULL`; `sha256 ~ '^[0-9a-f]{64}$'`;
  `size_bytes >= 0`; `source_type <> 'scan' OR source_id IS NOT NULL`;
  `source_type = 'scan' OR created_by IS NOT NULL`.
- CHECK `evidence_storage_key_in_tenant_prefix`: `storage_key` is NULL, or starts with
  `organization_id::text || '/'` (ADR-004 prefix), matches `^[0-9a-f-]{36}(/[A-Za-z0-9_.-]+)+$`
  and has no `.` or `..` segment. The evidence module builds keys on the server from the tenant
  context; no client-supplied keys, no cross-tenant dedupe by sha256.
- `evidence_controls.control_key` is validated through `compliance.api` at write time (ADR-008:
  no cross-module FKs or joins). One piece of evidence serves every framework mapped to the
  control (MF-02).
- Trend index: `(organization_id, framework_key, scope_id, computed_at DESC)` (FR-08).

### Scoring stays in packages/core

Tables store inputs and outputs. `atesta_core.frameworks.framework_results` computes, including
group scores. The compliance module maps active rows to core dataclasses; no scoring logic in SQL.

## Test plan

| Test | Proves |
|---|---|
| Migration up; schema linter passes with catalog tables classified as catalog | Rule 3 with documented exceptions |
| `atesta_app` INSERT, UPDATE, DELETE on any catalog table: permission denied | Catalog read-only at runtime |
| `atesta_app` UPDATE, DELETE on `score_snapshots`, `evidence`: permission denied | Append-only |
| Org A cannot see org B snapshots or evidence; insert with B's id fails WITH CHECK; linking B's evidence id from A fails with the same FK error as a random uuid | Isolation, no cross-tenant references |
| Evidence CHECKs: file without sha256, media type or size rejected (attestation included); sha256 without file rejected; scan output or document without file rejected; scan evidence without `source_id` rejected; upload or attestation without `created_by` rejected; malformed sha256 rejected; attestation without file accepted | Integrity (NFR-05, ADR-005) |
| Storage key under org B's prefix, with `.` or `..` or an empty segment, rejected in org A; key under A's prefix accepted | Evidence objects bound to their tenant |
| Blank `source` or `rationale` rejected; bad kind, engine or status rejected; score outside 0-100 rejected | MF-06, integrity |
| A `draft` framework present in the DB is not listed and yields no snapshot | Rule 10 at runtime |
| Requirement R-1 with an active mapping to a passing control and a retired mapping to a control with no result scores `pass`; retired requirement R-2 is absent from results | Retired rows never change scores |
| Snapshot job run twice for one scan leaves one row; a correction supersedes it and trend reads only the correction; a retried correction returns the same row; a correction of another framework's, scan's or scope's snapshot (NULL scope included) is rejected | Idempotent, append-only, linear corrections |
| Snapshot `catalog_version` equals the DB stamp even when the process build constant differs | Auditor traceability |
| Two synthetic frameworks mapped to shared controls; one control result set; `framework_score` from DB rows equals the expected score for both | "Test once, comply with many" end to end |
| Guard test: Python `tokenize` reads every `*.py` under `apps/api/src`, `apps/api/migrations`, `apps/worker`, `packages/core/src`; NAME and STRING tokens are split on non-alphanumerics and camelCase and lowercased; fails on any part in the denylist (`ens`, `nis2`, `iso27001`, `27001`, `rd311`, `dora`, `soc2`) or any pack id from `catalog/frameworks/*/pack.yaml`. No allowlist. Self-test: flags `ENS_MEDIUM`, `"ens"`, `EnsLevel`, `iso27001_2022`; does not flag `max_tokens`, `screens_count`, `ensure_tenant` | Rule 9 and MF-03 stay enforced |
| `has_framework`: plan grants, add-on grants, `applies_to` limits; unknown framework key in `plans.yaml` fails validation | Entitlements as data |
