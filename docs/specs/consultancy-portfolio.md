# Spec: portfolio view

- Issue: #192. Builds on `readiness-cockpit.md` and `recorded-routines.md`.
- Status: draft

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
- [ ] **No new access:** the page reads each organization through the endpoints its members
  already use (`readiness`, `routines/due`). Each request runs in that organization's own
  context, so no cross-tenant query exists (ADR-012).
- [ ] **Degrades per row:** if one organization fails to load, that row says so and the others still
  show.
- [ ] **Languages:** ES and EN; no compliance score, counts only (ADR-005).

## Out of scope

- Inviting or billing across organizations, and white-label branding.

## Test plan

- **Web unit:** two organizations ordered by urgency, the summary, a failing row, ES and EN.
- **e2e:** two organizations created by one person; the table at 375 and 1280 pixels, with axe.
