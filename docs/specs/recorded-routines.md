# Spec: recorded routines

- Issues: #165 (part A), #166 (part B). Builds on `control-evidence-statements.md`, `rbac.md` and `readiness-cockpit.md`.
- Status: draft

Organizational measures are evidenced by what people do: reviewing access, approving policies,
completing training, handling incidents. Done inside Atesta, each routine leaves its own record,
with who, what and when. Completing one writes an ordinary evidence statement on its common
control, so it shows wherever evidence is read.

**What Atesta never does:**
- decide whether a measure is met (ADR-005);
- change a customer system (rule 1). Revoking an account happens in the customer's own system;
  Atesta records the decision.

## Part A (#165)

**Access reviews**
- [ ] **Create (admins):** a title, the system reviewed and an optional due date, with the
  accounts. Each account is a name or address, at most 320 characters, plus an optional detail
  such as a role or group, at most 200. A review holds 1 to 2000 accounts. The web form accepts
  pasted lines or a CSV file read in the browser; no file is uploaded.
- [ ] **Decide (contributors and admins):** keep or revoke each account, with an optional note.
  Decisions are append-only, and the latest one for each account wins.
- [ ] **Close (admins):** possible only once every account has a decision. Closing stamps the
  time and the person, and writes an evidence statement on `ctl.access_review`, for example:
  "Revisión de accesos «Q4» (Microsoft 365): 15 cuentas revisadas, 12 mantener, 3 retirar.
  Cerrada el 23 nov 2026 por ana@…". The statement is written in the language of the person who
  closes the review.
- [ ] **Locked once closed:** a closed review takes no more decisions (409).

**Policies**
- [ ] **Register (admins):** a title, an HTTPS link to where the document lives, and a review
  period from 1 to 36 months.
- [ ] **Approve (admins):** a version, the approver's name and date, and an optional SHA-256 of
  the file. Approvals are append-only. Each one writes an evidence statement on
  `ctl.security_governance`.
- [ ] **Read:** the list shows the latest version, its approval and the next review date (last
  approval plus the period).

**Evidence that falls due**
- [ ] **Endpoint:** `GET /orgs/{org}/routines/due` returns:
  - policies whose next review is within 30 days, or overdue;
  - policies never approved;
  - open access reviews past their due date.
- [ ] **"Ahora":** each of these is an item, with a link.

## Part B (#166)

**Training acknowledgements**
- [ ] **Create (admins):** a title, an HTTPS link to the material and a closing date. The secret
  link is shown once; the API keeps only its SHA-256, as with invitations.
- [ ] **Confirm (anyone with the link, no account):** the confirmation page asks for a full name
  and an email, and records the acknowledgement once per email.
  - **Refused:** a closed campaign (410), an unknown link (404), more than 1000 confirmations
    (409) and a repeated email (200, unchanged).
  - **Database access:** the public endpoint reads the campaign through a named read policy keyed
    on the token's SHA-256, then writes in the organization's context. This is ADR-012 amendment
    4, proposed.
- [ ] **Close (admins):** writes an evidence statement on `ctl.people_awareness` with the count.

**Incidents**
- [ ] **Record (contributors and admins):** a title, when the incident was detected, and two
  flags: significant, and affects personal data.
- [ ] **Reporting clocks:** they come from framework packs as content (rule 9), in
  `reporting_clocks`. Each clock has a title in ES and EN, a duration in hours, what it starts
  from (detection, or another clock), the condition (significant or personal data) and the
  requirement it serves. Durations are copied from the official text:
  - NIS2 Art. 23(4)(a), (b) and (d): 24 h, 72 h, and one month after the notification;
  - GDPR Art. 33(1): 72 h.
- [ ] **Updates (append-only):** an update for a clock stops it. Notes and closing are updates too.
- [ ] **Overdue:** a clock past due appears in "Ahora".

## Out of scope

- Sending email. Links are copied and shared by the organization.
- File uploads: evidence storage needs AWS.
- Revoking access in the customer's system.

## Test plan

- **Postgres:**
  - every endpoint, with its role rules and RLS isolation;
  - append-only behaviour, and the latest decision winning;
  - close preconditions, and the evidence statement and its control link;
  - due items.
  - Part B adds the public link (unknown, closed, cap, duplicate, never another organization) and clocks computed from pack content.
- **Web unit:** forms, CSV parsing, decision flow, due items in "Ahora", ES and EN.
- **e2e:** one routine end to end, with axe at 375 and 1280 pixels.
