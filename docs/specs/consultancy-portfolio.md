# Spec: portfolio view

- Issue: #192. Builds on `readiness-cockpit.md` and `recorded-routines.md`.
- Status: built (2026-11-23: every acceptance criterion is implemented and covered by the tests its test plan names). The server-side summary (#228) is added below.

## Problem

A consultancy looks after several client organizations in Atesta. To know which one needs
attention today, it has to open each one. Management in a group of companies has the same problem.

## Acceptance criteria

- [ ] **Where:** `/app` shows the portfolio when the person belongs to more than one organization;
  with one organization it shows the same table with one row.
- [ ] **One row per organization:**
  - the person's role;
  - frameworks in progress;
  - measures assessed out of the total, summed over the frameworks in progress (an untouched
    framework would inflate the total). With none in progress, the row says "not started";
  - overdue measures;
  - pending routines, with how many are overdue;
  - the date of the last assessment.

  Each row links to the organization's summary.
- [ ] **Order:** most urgent first. That is the most overdue items (measures plus overdue routines),
  then the most pending routines, then by name.
- [ ] **Summary:** organizations, how many have something overdue, and how many have not started any
  framework.
- [ ] **No new access:** each organization is read in its own context, with the caller's own
  membership, so no cross-tenant query exists (ADR-012). Since #228 one request does it
  ("Server-side summary" below); before, the page called `readiness` and `routines/due` once
  per organization.
- [ ] **Degrades per row:** if one organization fails to load, that row says so and the others still
  show.
- [ ] **Languages:** ES and EN; no compliance score, counts only (ADR-005).

## Server-side summary (#228)

The page made two requests per organization. A consultancy with hundreds of clients would make
hundreds of requests to draw one table. One endpoint now returns the table.

Owner decision, 2026-11-24 (ADR-012 amendment 10, proposed): the API walks the caller's
organizations one at a time, each in its own tenant context, and no query sees two of them.

- [ ] `GET /api/v1/portfolio` returns one row per organization the caller belongs to: id, name,
  the caller's role and `summary`.
- [ ] `summary` holds the same numbers the page computed: frameworks in progress, measures
  assessed and their total over those frameworks, overdue measures, pending routines, how many
  of those are overdue, and the last assessment. It comes from the functions behind `readiness`
  and `routines/due`, so the two answers cannot differ.
- [ ] **Order:** most urgent first, by the rule above, decided by the server. The pure rule
  lives in `packages/core`.
- [ ] **Each organization in its own transaction**, read-only, entered through the caller's own
  membership. An organization the caller does not belong to never appears.
- [ ] **Degrades per row:** when one organization cannot be read (expired auditor access, or an
  error while reading it), its `summary` is `null` and the others still show. The error's type
  and the organization id are logged, never its message (rule 2).
- [ ] **Bounded:** at most 250 organizations are read, in name order; `not_shown` says how many
  were left out, and the page says so.
- [ ] **Read-only:** the endpoint writes nothing and emits no audit event.
- [ ] **Session only:** it needs a signed-in person. API keys cannot call it: a key belongs to
  one organization.
- [ ] **The page** makes this one request. While it loads, each row says so; if it fails, each
  row says it could not be loaded. Nothing else on the page changes.

## Out of scope

- Inviting or billing across organizations, and white-label branding.

## Test plan

- **Core unit (#228):** the summary of several frameworks ignores untouched ones in the totals;
  the order is overdue, then pending, then name.
- **Postgres (#228):** two organizations of one person with different numbers, equal to what
  `readiness` and `routines/due` answer for each; another person's organization is absent; an
  auditor whose access expired gets that row with `summary: null`; one organization that fails
  does not hide the other; nothing is written; no credentials gives 401; the walk never holds
  two organizations in one transaction; the cap and `not_shown`.

- **Web unit:** two organizations ordered by urgency, the summary, a failing row, ES and EN.
- **e2e:** two organizations created by one person; the table at 375 and 1280 pixels, with axe.
