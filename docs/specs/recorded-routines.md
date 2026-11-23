# Spec: recorded routines

- Issues: #165 (part A), #166 (part B). Builds on `control-evidence-statements.md`, `rbac.md` and `readiness-cockpit.md`.
- Status: built (2026-11-23: every acceptance criterion is implemented and covered by the tests its test plan names)

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
  link is shown once and carries the token in the URL fragment; the API keeps only its SHA-256,
  as with invitations.
- [ ] **Confirm (anyone with the link, no account):** the public page shows the title and the
  material, then asks for a full name and an email. One acknowledgement per email.
  - **Refused:** a closed campaign or one past its closing date (410), an unknown link (404),
    more than 1000 acknowledgements (409). A repeated email returns 200 and changes nothing.
  - **The token never travels in a query string** (400), as with invitations.
  - **Database access:** the public endpoint reads the campaign through a named read policy,
    `training_token_read`, keyed on the token's SHA-256. It then enters the organization's
    context for a fifth reason, `training_link`, and writes under `tenant_isolation`. This is
    ADR-012 amendment 4, proposed.
- [ ] **Read (members):** campaigns with their counts; a campaign with its acknowledgements.
- [ ] **Close (admins):** writes an evidence statement on `ctl.people_awareness` with the count.
  A closed campaign takes no more acknowledgements.
- [ ] **Due:** an open campaign past its closing date appears in "Ahora", as a reminder to close it.

**Incidents**
- [ ] **Record (contributors and admins):** a title, when the organization became aware of the
  incident, and two flags: significant, and affects personal data. Incidents are append-only;
  their history is their updates.
- [ ] **Reporting clocks:** they come from framework packs as content (rule 9), in
  `reporting_clocks`. Each clock has:
  - a key, unique in its pack, and a title in ES and EN;
  - a duration in hours or in months;
  - what it starts from: becoming aware, or another clock of the same pack being met;
  - the flag it needs (significant, or personal data);
  - the requirement it serves, which must exist in the pack.

  Durations are copied from the official text:
  - NIS2 Art. 23(4)(a) and (b): 24 h and 72 h from becoming aware of the significant incident;
    (d): one month after the notification under (b);
  - GDPR Art. 33(1): 72 h after becoming aware of the breach.
  - DORA, Delegated Regulation (EU) 2025/301, Art. 5(1): initial notification 24 h at the latest from
    becoming aware (the 4 h from classification is not modelled), intermediate report 72 h after it,
    final report one month after that.
- [ ] **Updates (append-only, contributors and admins):** a note, a clock met (once per clock),
  or closing. A closed incident takes no more updates (409).
- [ ] **Clock states**, computed from pack content and updates: met (with the time), running
  (with the due time), overdue, or waiting for the clock it starts from. A clock is computed
  only from packs that are active in the catalog.
- [ ] **Closing** writes an evidence statement on `ctl.incident_response`: when the
  organization became aware, when the incident closed, and each clock met and on time or late.
- [ ] **"Ahora":** each running or overdue clock of an open incident is an item, with its due
- [ ] **Criteria next to the flags (#181):** packs may name, in `incident_criteria`, the requirement
  that defines each flag (for example NIS2 Art. 23(3) for significant, GDPR Art. 33(1) for personal
  data). The form shows that requirement's official text, per active framework, in the reader's
  language when an official text exists. Atesta shows the text; the organization decides (ADR-005).
  time.

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
