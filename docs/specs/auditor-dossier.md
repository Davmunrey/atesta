# Spec: auditor dossier

- Issue: #185. Builds on `requirement-register.md`, `control-evidence-statements.md`, `recorded-routines.md`, `claims-honesty.md`.
- Status: draft

## Problem

ENS SMEs prepare for an audit by collecting evidence from many places. IT does the work; management
reads a summary and signs. The auditor wants everything ordered by requirement. Today Atesta holds
the pieces on separate pages, and assembling them by hand takes days.

## Acceptance criteria

- [ ] **One dossier per framework,** at `GET /orgs/{org}/frameworks/{key}/dossier` and a printable web
  page. Any member may read it, auditors included. Opening it records an audit event,
  `framework.dossier_viewed`.
- [ ] **Cover:** organization, framework name and version, catalog version, and when it was
  generated. It also states that the dossier is not a certification (claims-honesty).
- [ ] **Management summary:**
  - measures assessed, implemented, partial, not implemented and not applicable;
  - overdue measures;
  - the latest security officer review (date, reviewer, conclusions);
  - the state of the routines: policies to review, open access reviews past their date, trainings
    to close, and open incidents with missed reporting deadlines.

  All of these are counts and dates, never a compliance score (ADR-005).
- [ ] **Statement of applicability:** the same rows as the applicability export.
- [ ] **Evidence by requirement:** for each requirement, its common controls, with:
  - the latest scan observation of each automated control;
  - the current review of each manual control;
  - the evidence statements linked to each control (title, date, source, text, link).

  Requirement text stays official; nothing is paraphrased.
- [ ] **Routines:**
  - policies with their latest approval;
  - access reviews, trainings and incidents closed in the last 12 months.
- [ ] **Printing:** the web page prints cleanly to PDF from the browser. Navigation is hidden, sections
  start on new pages, and links show their address.
- [ ] **Languages:** ES and EN for every label. Official texts stay in their published language.

## Out of scope

- Server-side PDF rendering and file attachments (evidence storage needs AWS).
- Signing inside Atesta: the cover has an empty signature block, as in the applicability export.

## Test plan

- **Postgres:** the dossier composes the pieces of a seeded organization; counts match the register;
  another organization's evidence never appears; the audit event is written; auditors can read it.
- **Web unit:** the summary, a requirement with its evidence, ES and EN.
- **e2e:** the page at 375 and 1280 pixels, with axe.
