# Spec: Manual control review

- Requirement ids: FR-07, ADR-005, NFR-05
- Status: built (2026-11-23: every acceptance criterion is implemented and covered by the tests its test plan names)

## Problem

Every one of the 73 ENS measures keeps at least one manual control (documentary or organizational:
risk analysis, incident response, supplier review). Automated checks never decide those, and
nothing else can: they stay `manual` forever, so no requirement that maps to one can ever pass.
Today a security lead tracks those decisions in spreadsheets outside Atesta, and the auditor sees
a register where most of the work looks pending.

ADR-005 allows exactly two sources of control status: deterministic checks or human approval.
This spec adds the human approval, for manual controls only.

## Acceptance criteria

PR 1 (record and read reviews):

- [ ] Tenant table `control_reviews` (ADR-012): append-only for `atesta_app` (SELECT, INSERT),
      RLS `tenant_isolation`, registered as tenant and append-only in `platform/tables.py`. A new
      decision is a new row; the latest row for a control is its current review.
- [ ] A review records `status` (`pass` or `fail`), a `rationale` (1–2000 characters after
      trimming, no control characters other than line breaks and tabs), `valid_until` (a date
      after today in UTC and at most three years ahead), the reviewer's user id and the time.
- [ ] `POST /api/v1/orgs/{org_id}/controls/{control_key}/reviews` records a review. Admin or
      owner only (members get 403 `identity.forbidden`, non-members 404). Cookie writes need the
      web Origin, like every other write.
- [ ] Only active manual controls can be reviewed: unknown or retired → 404
      `compliance.control_not_found`; a control with `manual = false` → 409
      `compliance.control_not_manual`. A human never overrides an automated check here; that is
      exceptions and risk acceptance (FR-11).
- [ ] `GET` on the same path lists the control's reviews, newest first, for any member.
- [ ] Each recorded review writes the audit event `control.reviewed` (target the control key;
      metadata `status`, `valid_until`) in the same transaction. The rationale is not copied
      into audit metadata.
- [ ] Framework detail adds `review` to each control: the current review with `expired`
      (`valid_until` before today in UTC), or `null`. Tenant data only from the caller's org.
- [ ] Error codes have ES and EN texts.

PR 2 (scoring):

- [ ] A scan snapshot takes, for each active manual control, the latest review recorded no later
      than the scan's `ingested_at`. That review decides the control if it has not expired by
      then (`valid_until` on or after that UTC date); otherwise the control has no result, even
      when an older review would still hold. A retried snapshot job gives the same snapshot.
- [ ] A review never decides an automated control, whatever its row says.
- [ ] Recording a review defers `atesta:rescore_reviews` (organization id only) in the same
      transaction. The job writes, for every scoreable framework, a correction of the latest
      ingested scan's org-wide snapshot: check results as of that scan, reviews as of now. The
      correction supersedes the tip of that scan's chain, so the chain stays linear and earlier
      scans' snapshots are never rewritten. Without an ingested scan it does nothing.

PR 3 (screen):

- [ ] Each manual control in the framework detail shows its current review: decision, author
      (email from the member list, else "a member"), date, validity and an expired flag; or says
      that none is recorded and the control counts as pending. Automated controls show none.
- [ ] Owners and admins see "Record review": decision (radio), rationale (required, 2000
      characters), valid until (date between tomorrow and three years, default one year).
      Members never see the form; the API still decides. Errors show the API's ES/EN text.
- [ ] After saving, the register refetches and says the score updates within seconds.
- [ ] Accessible (axe WCAG 2.1 AA, keyboard, labels) and inside the strict CSP; no horizontal
      scroll at 375 px.

PR 4 (a pass cites its evidence, #262):

- [ ] A review cites evidence: `evidence_ids`, 0 to 20 distinct ids, in the request. A `pass`
      cites at least one; a `fail` may cite none. A `pass` without any gives 422
      `compliance.review_evidence_required`.
- [ ] Every cited id is evidence of the caller's org linked to the reviewed control, checked
      through `evidence.api`. Any other id (another control's, another org's, unknown) gives 422
      `compliance.review_evidence_invalid`: the same answer for all three, so another org's ids
      reveal nothing. Nothing is written on a refusal.
- [ ] The row stores the citations: `control_reviews.evidence_ids uuid[] NOT NULL DEFAULT '{}'`,
      at most 20 (CHECK). Rows stay append-only. Reviews recorded before this change read as
      citing none (`evidence: []`) and keep deciding their control until they expire; only new
      reviews must cite.
- [ ] `ReviewOut.evidence` lists each cited item (id, title, kind, collected_at) in the
      framework detail, the review history and the auditor dossier.
- [ ] The `control.reviewed` audit event adds `evidence_count`; titles are never copied into it.
- [ ] Screen: the review form lists the control's evidence, newest first, as checkboxes. A
      `pass` needs one checked. With no evidence recorded, the form says to record evidence first
      and offers `fail` only. Each review shows the titles it cites, or that it cites none.
- [ ] Error codes have ES and EN texts.

## Out of scope

- Uploading documents as evidence (needs the S3 evidence store, #222). A cited item is an
  evidence statement or a scan output today.
- A second approver (four-eyes) and review reminders before `valid_until`.
- `not_applicable`: applicability is decided per requirement and scope (FR-06), not per control.
- Withdrawing a review. A new `fail` review replaces it; expiry ends it.
- Rescoring when a review expires between scans: the next scan or review picks it up. A daily
  rescore job can follow.
- A score for an org that has never completed a scan (snapshots belong to a scan).
- AI-drafted rationales (AI-xx specs). ADR-005: an AI draft is never a review.

## Design notes

- Module: compliance (control status is compliance data). New `reviews.py` router, mounted by
  `install_compliance`; models in `compliance/models.py`. No other module's internals.
- Table `control_reviews`: id, organization_id, control_key `text` (no FK to the global
  catalog, like `evidence_controls`; checked through the catalog at write time), status,
  rationale, valid_until `date`, reviewed_by `uuid` (users.id, no cross-module FK, ADR-008),
  reviewed_at `timestamptz default now()`. CHECKs on status and rationale length. UNIQUE
  (organization_id, id); index (organization_id, control_key, reviewed_at DESC).
- The rationale is customer content: never logged, never in audit metadata (rule 2), rendered as
  text only (rule 5).
- Expiry is computed on read against today's UTC date; nothing rewrites rows.
- Citations (#262) are an array on the review row, not a link table. A review and its
  citations are written once and never change, the set is bounded at 20, and evidence is
  append-only, so a cited id never dangles. An array needs no new tenant table and no
  cross-module FK (ADR-008). A `pass` must cite evidence because ADR-005 lets a human approve a
  manual control, and an auditor rejects an approval with nothing to open (ARTEX principle 1:
  findings keep their receipts).

## Test plan

- DB: `atesta_app` cannot UPDATE or DELETE `control_reviews`; RLS hides another org's rows; the
  CHECKs reject an unknown status and an empty or 2001-character rationale.
- HTTP: owner and admin record; member 403; non-member 404 on write and read; unknown and retired controls 404; automated control 409;
  `valid_until` today, in the past and over three years 422; blank or control-character
  rationale 422; history newest first; one audit event per review without the rationale.
- Scoring: pass and fail reviews move the score; the latest review as of the scan wins; a
  review after the scan, an expired latest review and a review of an automated control do not
  count; rescoring writes a linear chain on the latest scan only, and nothing without a scan.
- Web: member sees the review without a form; expired and empty states; admin records and the
  register refetches; an API refusal shows its text; automated controls offer no form. e2e:
  owner records a review with axe clean at 375 and 1280 px and no CSP violation.
- Detail: a manual control shows its latest review, `expired` once `valid_until` has passed, and
  never another org's review.
- Citations (#262): a `pass` without evidence 422; a `fail` without evidence 201; evidence of
  another control, of another org and an unknown id each 422 with the same code and no row; 21
  ids 422; a duplicate id is stored once; the detail, history and dossier list the cited titles;
  a review recorded before the change reads `evidence: []`; the audit event carries
  `evidence_count`, never a title; the DB CHECK refuses 21 ids. Web: the form offers the
  control's evidence, needs one for `pass`, offers only `fail` without evidence, and the review
  shows the cited titles.
