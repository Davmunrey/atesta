# Framework requirements and implementation guidance

Status: implementation, 2026-11-13. Mode: Operate with inline reading guidance.
Route: `/app/framework?org=<id>&framework=<key>`. Extends the approved dashboard.

## Purpose and scope

Answer which requirements pass, fail, need human review or have no recorded evaluation;
show their mapped configurations and available implementation guidance. The other session
owns connection endpoints (#67). This increment does not change connections, collection,
scoring, catalog content, or customer configuration. Read-only actions need no mutation audit.
The repository currently has catalog templates only, not released ENS/NIS2 packs. Synthetic
demo content must remain explicitly labeled; never manufacture legal requirements or claims.

## Read contract

`GET /api/v1/orgs/{org_id}/frameworks/{framework_key}` requires organization membership.
All roles may read; outsiders receive the existing organization-not-found response. Missing,
retired and gated frameworks return the same framework-not-found response. Use module APIs
and the existing RLS request context. No new dependencies or migrations.

Use the latest stored organization-wide snapshot, ordered by timestamp and ID, including
corrections. Return its requirement statuses and original versions without rescoring. Include
current active requirements plus recorded codes removed from the catalog. Missing results
mean `not_evaluated`, never pass or not-applicable. Preserve unknown historical codes without
inventing titles or mappings. Mark current catalog membership and catalog-version mismatch.

Each current requirement includes bilingual titles, applicability labels, source and active
mapped controls. Controls include descriptions, manual/automated mode, remediation references,
mapping review status and configured check identifiers. These descriptions/references are
catalog guidance, not generated legal or vendor instructions. No guide present means explicit
missing guidance, with a practical general next step.

Only when framework and catalog versions match the recorded snapshot, derive control/check
observations using the existing scan-as-of API and aggregation rules. These are technical
observations distinct from the stored requirement result. Never join newer scans, findings,
or another tenant. Missing scans/checks and historical mismatches yield no observation.
Return no raw findings, personal resource details, storage locations, secrets or reviewer names.

## Interaction and acceptance

Link from each overview framework to its detail. Preserve organization context and provide
a return link. Show framework title, recorded assessment date/version, scope and mismatch
notice. A compact status filter and search narrow requirement rows; default to all results.
Each row opens in place to show what its state means, the next step, mapped controls,
technical checks and existing references. Distinguish manual review, missing evaluation,
and missing catalog guidance. Do not offer nonexistent edit/upload/scan actions.

Support loading, empty, missing framework, recoverable error, refresh, ES/EN, keyboard,
reduced motion, light/dark and 375/768/1280px without overflow. External links accept only
HTTP(S), otherwise render as text. Catalog text renders as plain text, never HTML.

## Direction contract

THESIS: a working requirement register that connects an observed gap to an actionable guide.
OWN-WORLD: retain paper/ink, yellow selection, blue links, existing type and semantic tokens.
STORY: choose framework, scan explicit states, open the relevant requirement, inspect the
configuration and references, then verify again after applying changes outside Atesta.
FIRST VIEWPORT: existing organization rail; back link, framework heading and provenance;
status filters above a broad, flat register. Mobile filters wrap and details stack.
FORM: code-led extension of the approved ledger. Native disclosure is the signature
interaction; clear spacing separates requirement status from control observations.
FINISH: bounded desktop/mobile review, independent finish reviewer, and documenter comparison
against the incumbent system. No replacement identity or raster assets.

## Verification

Test first with real PostgreSQL: all roles, membership/RLS, catalog gates, corrections,
scope exclusions, zero/null, historical catalog drift, retired rows, unassessed requirements,
active mappings, missing scan, as-of check observations and sensitive-field absence.
REA records red/green runs and a fresh-copy full verification. Browser tests cover filters,
disclosures, localization, recovery, safe references, themes, keyboard, axe and narrow widths.
