# Dashboard overview

Status: implementation, 2026-11-13. Operate surface: `/app/org?org=<id>`.
The user requested the complete dashboard design and authorized autonomous decisions.
Preserve the approved visual identity and existing organization/member workflows.

## Scope and coordination

The other workstream owns connections (#64), onboarding and scanner execution. This increment
reads existing results only. No connection, scanner execution, migration or scoring changes.
Ship a small read API first, then the dashboard UI. Follow #55 and #63 in the PR stack.

## Read contract

`GET /api/v1/orgs/{org_id}/overview` requires membership (every role); outsiders receive the
same 404 as other organization routes. All tenant queries use the request's RLS context and
explicit organization filters. Read operations do not emit mutation audit events.

- List only frameworks allowed by the existing released/non-retired catalog gate.
- For each framework, return the latest stored organization-wide snapshot by `computed_at`,
  then ID for deterministic ties. Corrections participate; narrower scopes are excluded.
  Preserve recorded framework/catalog versions, timestamp, counts and nullable score. Do not
  recalculate old snapshots against today's catalog or average frameworks into one score.
- Return at most five recent scans, ordered by queue time then ID. Include provider, status,
  coverage and timestamps. Never expose storage keys, tenant identifiers, raw findings or logs.
- Count evidence records without retrieving their contents or storage locations.
- An empty organization has no scans or evidence, and frameworks have no snapshot. Absence
  is not zero compliance. Generate the TypeScript contract from OpenAPI.

## Dashboard behavior

The first viewport answers which frameworks have results, what needs review and how complete
the latest collection was. A framework ledger displays named results, status counts and
recorded dates. Expand a row for its counts, scope and provenance. Search filters framework
names and keys; empty search results can be cleared. A refresh control refetches the same
organization. Recent collections retain failed, blocked and partial states explicitly.

Show useful loading, empty and retryable error states; do not substitute stale results from
another organization. Preserve organization switching and role-aware member/invitation links.
All UI copy is ES/EN. A recorded synthetic local run is visibly labeled as development data;
never present synthetic framework scores as ENS/NIS2 results. No fake scan/export buttons.

## Direction contract

THESIS: a review workspace centered on a framework ledger, not a wall of KPI cards.
OWN-WORLD: inherit paper, ink, yellow selection, blue links, Newsreader headings and Plex
text/data. Use restrained semantic statuses; no new decorative palette or font assets.
STORY: inspect recorded results, distinguish gaps from failures, expand provenance, then
review collection coverage. Team administration stays available in the organization rail.
FIRST VIEWPORT: persistent organization rail at left; organization title and refresh above
a wide result ledger; compact collection summary alongside, stacking below on mobile.
FORM: extend the existing organization surface in code. No new visual world or concept seed;
autonomous direction is authorized. The signature interaction expands a ledger row in place.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review,
the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Verification

Test first: authentication, every role, RLS across two organizations, catalog gates, scoped
snapshots, corrections/ties, null score, bounded recent scans and absence of sensitive fields.
Browser: empty/data/error/loading, filters, detail disclosure, refresh, organization switching,
ES/EN, keyboard, axe, light/dark, 375/768/1280px and long names. Capture with REA, rerun all
checks from a fresh copy/database, inspect desktop/mobile and request an independent finish
review. The optional design-context launcher is unavailable; use committed product/tokens.
