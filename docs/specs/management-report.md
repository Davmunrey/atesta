# Spec: monthly report for management

- Issue: #204. Builds on `readiness-cockpit.md`, `recorded-routines.md`, `auditor-dossier.md`, `insights.md`.
- Status: draft

## Problem

In ENS SMEs, IT does the work and management reads a summary and signs. The dossier is per
framework and long. Management needs one page a month: what was done, where things stand, and what
falls due.

## Acceptance criteria

- [ ] **Endpoint:** `GET /orgs/{org}/report?month=YYYY-MM`. Any member may read it, auditors
  included. The month defaults to the current one; a malformed or future month gets 422.
- [ ] **Done in the month,** counted from the audit log within the month (Europe/Madrid boundaries):
  - measures assessed and assessments reviewed;
  - evidence recorded, by people and by tools;
  - policies approved, access reviews closed, trainings closed;
  - incidents recorded and closed, and reporting deadlines met;
  - people who joined.

  Counts only: no names, no content.
- [ ] **Status now,** per framework in progress: assessed, implemented, overdue, and the last
  security officer review. The report says this is the current status, not the status at the end
  of the month.
- [ ] **What falls due:** the same items as "Ahora" (routines/due).
- [ ] **Opening it** records `organization.report_viewed`.
- [ ] **Web page** `/app/report`, for every member:
  - a month picker;
  - the three sections;
  - a "no es una certificación" line;
  - a signature block, and a clean print, as in the dossier.

  Linked from the side menu and from the overview. ES and EN.

## Out of scope

- Sending it by email (needs SES; it comes with the hosted environment).
- Status at the end of a past month (it would need a snapshot per month).

## Test plan

- **Postgres:**
  - counts within the month and none from the next month;
  - another organization's events never appear;
  - 422 on a bad or future month;
  - auditors read it;
  - the audit event is written.
- **Web unit:** the sections, a month with no activity, ES and EN.
- **e2e:** the page at 375 and 1280 pixels, with axe.
