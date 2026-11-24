# Spec: Email notifications

- Issue: #223 (feature). Sub-issues for each pull request are opened when it starts (rule 12).
- Builds on:
  - `recorded-routines.md`: policies, access reviews and incidents with their reporting clocks;
  - `manual-control-review.md` (`valid_until`) and `insights.md` (assignments and due dates);
  - `scanner-connectors.md` (connection and scan events);
  - `management-report.md`, `hosted-environment.md` (the `ses` module), `i18n-complete.md`,
    `claims-honesty.md`, `rbac.md`.
- Status: draft

## Problem

Atesta knows when something needs a person:
- a connection stops being read-only or loses access;
- a scan fails;
- a manual review or a policy is about to lapse;
- an NIS2 incident clock is running out.

Today it says so only inside the app, so a security lead who does not open Atesta that day finds
out late. For an NIS2 early warning (24 hours) or an audit, late is the same as never.

## Owner decisions (session, 2026-11-23)

Asked and answered in session; quoted where the answer chose a listed option.

| Topic | Decision |
|---|---|
| Events in v1 | Connection revoked or over-privileged; scan failed or blocked; reviews and other due items about to lapse; a weekly summary |
| Recipients | "Owners y admins, baja por tipo". Members receive only the due items of the measures assigned to them |
| Unsubscribe | Per type, one click (RFC 8058). Critical security email cannot be turned off |
| Provider and region | Amazon SES in **eu-south-2**, the region of all other data (ADR-007). The owner first chose eu-west-3 on a wrong premise from Claude; AWS lists SES endpoints in eu-south-2 (`email.eu-south-2.amazonaws.com`, AWS General Reference, "Amazon SES endpoints and quotas", read 2026-11-23). The owner then chose eu-south-2. ADR-007's only SES exception stays Cognito's own email |
| Weekly summary | Monday 08:00 Europe/Madrid. The first Monday of a month adds a link to the monthly report in the app; no attachment |
| Due-item notices | At 30, 7 and 1 day before the date, at most one digest a day per person and organization |
| Which due items | Manual control reviews (`valid_until`), policies to review, open access reviews with a due date, assigned measures with a due date |
| NIS2 and other incident clocks | Critical, cannot be turned off. Sent when a clock starts, 6 hours before it is due, and when it is overdue |
| Sender domain | Not chosen yet; decided in the guided infrastructure session. The sender is configuration |
| Sender name | "Atesta · <organization name>" (owner, 2026-11-24) |
| Language | The organization's, the same for every recipient (owner, 2026-11-24). Organizations gain a language, ES by default, that the owner sets in Ajustes (PR 2) |
| Critical email content | Only what happened and a link to the page that resolves it, never repair steps in the email ("Solo qué pasó + enlace a Conexiones") |
| Weekly summary with nothing new | Sent anyway, saying that nothing changed (owner, 2026-11-24) |
| Who changes the language | The owner only, in Ajustes. Claude's recommended option, taken under the owner's "Adelante" (2026-11-24) |
| Language of new members | The organization's language is used only for email for now; seeding new members' app language from it is a follow-up. Recommended option, same "Adelante" |
| Scan notices | Only for a scan's final failure, at most one per connection and day (Europe/Madrid). Activation scans are excluded: the admin is on the connections page. Recommended option, same "Adelante" |
| Incident clock milestones | Proportional. A clock of up to 72 hours is notified at its start, 6 hours before it is due and when it is due. A longer clock is notified at its start, 7 days and 1 day before, and when it is due. Recommended option, same "Adelante" |
| New module | ADR-008 amendment 1: module `notifications` (accepted in session) |
| Unsubscribe without signing in | ADR-012 amendment 7: context reason `unsubscribe_link` (accepted in session) |

Issue #223 asked for opt-in per person. The owner's later decision replaces that: owners and admins
receive every type by default and can turn off each non-critical type.

## Notification types

| Type | Trigger | Recipients | Can be turned off |
|---|---|---|---|
| `connection_alert` | Audit events `connection.revoked`, `connection.over_privileged` | Owners, admins | No |
| `incident_clock` | A reporting clock of an open incident reaches a milestone (see Owner decisions) | Owners, admins | No |
| `scan_problem` | Audit events `scan.failed`, `scan.blocked` of a non-activation scan, once per connection and day | Owners, admins | Yes |
| `due_digest` | Daily at 08:00 Europe/Madrid, when at least one item hits 30, 7 or 1 day before its date | Owners and admins: every item. Members: items of their assigned measures | Yes |
| `weekly_summary` | Monday 08:00 Europe/Madrid | Owners, admins | Yes |

Auditors never receive email. A person in several organizations receives each organization's
email separately.

## Acceptance criteria

### PR 1: foundation (module, preferences, sending, unsubscribe)

- [ ] **ADRs.** ADR-008 amendment 1 adds the module `notifications`. ADR-012 amendment 7 adds
      the context reason `unsubscribe_link` and the two tenant tables below.
- [ ] **Table `notification_preferences`** (tenant, standard `tenant_isolation`):
  - columns: `organization_id`, `user_id`, `kind`, `enabled`, `updated_at`;
  - primary key `(organization_id, user_id, kind)`;
  - CHECK `kind` is one of the three optional types;
  - a missing row means enabled.
- [ ] **Table `notification_deliveries`** (tenant, SELECT and INSERT, UPDATE only of the
      delivery status):
  - columns: `organization_id`, `id`, `user_id`, `kind`, `dedupe_key`, `status` (`queued`,
    `sent`, `failed`, `suppressed`), `provider_message_id`, `created_at`, `sent_at`;
  - unique `(organization_id, user_id, kind, dedupe_key)`, so a retried job never sends twice;
  - no subject, no body, no address. What was sent is rebuilt from the dedupe key and the data.
- [ ] **Preferences API**, for the signed-in person in one organization (member and above;
      auditors get 403):
  - `GET /api/v1/orgs/{org_id}/notifications/preferences` lists each type the person can
    receive, with `enabled` and `can_disable`;
  - `PUT` on the same path changes one optional type. A critical type answers 409
    `notifications.not_optional`;
  - each change writes `notification.preferences_changed` (metadata: `kind`, `enabled`).
- [ ] **Mailer.** `send(message)` behind a protocol, with two implementations in this PR:
  - `FileMailer` for local development: writes `.eml` files under `ATESTA_MAIL_DIR`;
  - `MemoryMailer` for tests.

  `SesMailer` arrives in PR 4 with the infrastructure, so the AWS SDK enters the dependency
  tree, after its cooldown and licence check, only when it is used. The sender comes from
  `ATESTA_MAIL_FROM`. With no mailer configured, nothing is sent and the delivery row ends
  `suppressed`.
- [ ] **Message format.**
  - Plain text only, in the organization's language (ES or EN), with texts from
    `apps/api/src/atesta_api/messages`.
  - It contains only titles, dates, counts, the organization's name and links into the app.
    No justification, note, finding detail, evidence content or file name (issue #223, rule 2).
  - Every optional type carries:
    - `List-Unsubscribe: <https://<web>/api/v1/unsubscribe?token=…>`;
    - `List-Unsubscribe-Post: List-Unsubscribe=One-Click`;
    - in the body, a link to the web page `/unsubscribe#token=…`, because a person's click is a
      GET and the page asks before acting. The token travels in the fragment, which browsers
      never send, as training links do. The page is served with `Referrer-Policy: no-referrer`.
  - The one-click URL carries the token in its query string, as RFC 8058 requires. The API's
    logs drop query strings, and CloudFront has no access logging. If edge logging is ever
    turned on, these tokens would be logged. Each one can only turn off one optional type and
    expires after 60 days.
- [ ] **Unsubscribe token.** It is sealed with AES-GCM under its own key,
      `ATESTA_NOTIFICATIONS_KEY` (32 bytes, base64), and bound to the name `unsubscribe`.
  - It holds organization, user, type and issue date, and expires after 60 days.
  - A token for a critical type is never issued.
  - The worker issues tokens, so it holds this key and never the session-cookie key.
  - Without the key, the route answers 503 `notifications.unavailable` and optional email is
    not sent.
- [ ] **`POST /api/v1/unsubscribe?token=…`** needs no session; it is RFC 8058 one-click.
  - It opens the token, enters the organization with reason `unsubscribe_link`, sets that one
    preference to disabled, and writes `notification.unsubscribed`.
  - It answers 200 whether or not the preference was already off. An invalid or expired token
    answers 400 `notifications.link_invalid`.
  - It reads nothing else, and the token never reaches a log: the log-redaction spec already
    drops every query string from log records, and a test pins it for this route.
- [ ] **Web.**
  - `/unsubscribe#token=…` takes the token from the fragment and removes it from the address bar.
    It explains what will stop, offers one button that POSTs, and shows the result. It does not
    act on GET.
  - `/app/notifications?org=` lists the person's types with switches. A critical type shows as
    on and locked, with the reason.
  - The page is reached from the account menu. ES and EN strings.

### PR 2: immediate notices

- [ ] **Organization language and sender.**
  - `organizations.locale` (`es` or `en`, default `es`) can be changed by owners in Ajustes,
    which records the audit event `organization.locale_changed`.
  - Every email uses it, and its sender is `Atesta · <organization name>` with the address from
    `ATESTA_MAIL_FROM`. The name is encoded per RFC 2047 and cannot break the header.
- [ ] **Critical email content.** It says what happened and links to the page that resolves it,
      `/app/connections` or the incident, without repair steps.

- [ ] **Connection and scan events.** In the same transaction as the audit event, the
      connections and scanning modules call `notifications.api.queue_event(...)`, which defers a
      `notify_event` job. The job arguments are ids only (ADR-012 amendment 2).
  - The job resolves the recipients, applies preferences and writes one delivery row per
    recipient, keyed `<event id>`.
  - It then sends each email. Up to 3 retries with backoff; a failure never blocks the event's
    own transaction.
- [ ] **Incident clocks.** When an incident is created or updated, compliance calls
      `notifications.api.schedule_clock_notices(...)`. It defers jobs at the clock's start, at 6
      hours before its due time, and at its due time.
  - At run time the job recomputes the clock with `atesta_core.clocks`. It sends only if the
    clock is still running (start, 6 h) or still unmet (due). The dedupe key is
    `<incident id>:<clock ref>:<milestone>`.
  - The email names the incident's title, the framework and clock title from the pack, and the
    due time in Europe/Madrid. It does not say whether a notification is legally owed
    (`incidents.py`: Atesta shows due times).

### PR 3: daily digest and weekly summary

- [ ] **Daily chain.** One `notify_daily` chain per organization, deferred to 08:00
      Europe/Madrid each day, the same pattern as `schedule_scan` (queueing lock
      `daily:<organization>`).
  - It is started at organization creation. Identity defers it by task name through the shared
    kernel, without importing notifications.
  - For organizations that already exist, it is restarted idempotently when someone opens their
    notice preferences.
  - A job that runs outside the 08:00 hour only re-arms itself.
- [ ] **Due digest.** It collects the items whose date is exactly 30, 7 or 1 day after today in
      Europe/Madrid:
  - manual control reviews by `valid_until`;
  - policies by last approval plus `review_months`;
  - open access reviews by `due_on`;
  - assigned measures by the assignment's `due_on`.

  These come from `compliance.api` (`due_items`). Owners and admins receive every item. A member
  receives only the assignments that are theirs: control reviews, policies and access reviews
  are organization-level and go to owners and admins. One email per person and organization,
  keyed `<date>`, and none when nothing is due.
- [ ] **Weekly summary.** On Monday the same job sends it, keyed `<ISO week>`. It contains:
  - each active framework's latest share of requirements passed, worded as `claims-honesty.md`
    requires;
  - scans of the last 7 days by status;
  - connections that are not active;
  - due items in the next 7 days and overdue items;
  - links into the app.

  The first Monday of a month adds the link to that month's management report. A week with
  nothing new is still sent, and says so. Compliance supplies the scores and due counts
  (`weekly_compliance`), scanning the scan counts (`scan_counts`), and connections the number
  not active (`inactive_connection_count`). The worker composes them, so no module imports
  another's internals.

### PR 4: infrastructure (owner applies)

- [ ] **SES.** The existing `ses` module is instantiated in eu-south-2 for notifications, with
      its own configuration set. The task roles of the API and the worker get `ses:SendEmail`
      limited to that identity and configuration set.
- [ ] **`SesMailer`:** SES v2 `SendEmail` in eu-south-2 with the configuration set from
      `ATESTA_SES_CONFIGURATION_SET`, through the AWS SDK added in this PR.
- [ ] **Key.** `ATESTA_NOTIFICATIONS_KEY` lives in Secrets Manager and is given to the API and
      worker tasks.
- [ ] **Variables.** `ATESTA_MAIL_FROM` and `ATESTA_SES_CONFIGURATION_SET` are wired to the
      ECS tasks.
- [ ] **Owner steps.** These go in `docs/runbooks/deploy.md`: the sender domain, DKIM, MAIL
      FROM and DMARC records, and requesting production access for SES.

## Out of scope

- SMS, Slack, Teams or webhooks.
- Choosing days, times or thresholds per organization.
- HTML email.
- Notices to auditors or to people outside the organization.
- Sending the monthly report as an attachment.
- Bounce and complaint processing beyond SES's own suppression list (candidate below).

## Design notes

- **Module `notifications`** (ADR-008 amendment 1).
  - It owns the two tables, the mailer, the templates and the jobs' logic.
  - Its `api.py` exports `queue_event`, `schedule_clock_notices`, `start_daily_chain` and the
    routers.
  - It reads recipients through `identity.api` (owners, admins, locale, email) and due items
    through `compliance.api`; nothing imports its internals.
- **Worker.** New tasks `notify_event`, `notify_clock` and `notify_daily` call the module's
  `api.py`, as the scan tasks do.
- **Data minimization.**
  - Email bodies hold titles and dates, which are customer content the customer chose to show
    its own people.
  - Delivery rows hold no content.
  - Addresses are read at send time and never stored again.
- **Security.**
  - No write scope anywhere (rule 1).
  - Nothing logs an address, a token or a body (rule 2).
  - The unsubscribe route can only disable one optional preference for the person the token
    names.
  - Templates are plain text, so a policy title cannot inject markup.
- **Audit.** `notification.preferences_changed` and `notification.unsubscribed`. Sending itself
  is recorded in `notification_deliveries`, not as audit events.

## Candidates to check before PR 4

| Candidate | Check |
|---|---|
| SES suppresses addresses that bounced or complained when the account-level suppression list is on | AWS SES documentation, then the dev account |
| A new SES account starts in the sandbox and needs a production access request | AWS SES documentation; owner step |
| Gmail and Yahoo accept RFC 8058 one-click with a sealed token in the URL | Live test with the dev sender |

## Test plan

- **DB tests.**
  - Preferences: defaults, change, a critical type refused, isolation between organizations.
  - Delivery dedupe on retry.
  - Unsubscribe: a valid token, an expired one, one forged for another org or user, and one
    for a critical type that was never issued.
  - Recipients by role, auditors excluded.
- **Unit tests.**
  - Templates in ES and EN; no forbidden fields in any body, checked by a guard test.
  - Headers on optional types only.
  - Token sealing bound to its name.
  - Due-date selection at 30, 7 and 1 days across the Madrid day boundary.
  - Clock milestones.
- **Web unit tests.** The preferences page, the locked critical rows and the unsubscribe page,
  which never acts on GET. Rendered at 1280 and 375 pixels, light and dark.
- **Worker test.** Every new task takes only `<name>_id: str` parameters (existing guard).
