# Spec: insights: progress over time, owners and activity

- Issue: #142. Builds on `requirement-register.md` and `workspace-ux.md`.
- Status: draft

## Problem

The owner asked for charts over time, owners, access and devices. Today an organization cannot see
how its self-assessment moves, who owns each measure or when it is due, and admins cannot see who
did what. Every figure must come from recorded rows; nothing is estimated or invented (PRODUCT.md).

## Acceptance criteria

**Progress over time** (members read)
- [ ] `GET …/frameworks/{fw}/register/history` returns one point per day, from the first recorded
      assessment to today. Each point counts, as of the end of that day: assessed requirements,
      implemented requirements and those that do not apply. Each is counted from the latest
      assessment of each requirement on or before that day, replayed from the append-only rows.
- [ ] The workspace shows four figures (assessed, implemented, do not apply, pending) and a line
      chart. "Implemented" is the emphasised series; "assessed" is grey context.
- [ ] **Chart, per the dataviz method:**
  - one y-axis;
  - 2 px lines;
  - a legend for the two series, and a direct label at the end of each;
  - crosshair and tooltip on hover and keyboard focus;
  - a table view with every value;
  - hidden when there are fewer than two days of history.
- [ ] Colours come from DESIGN.md tokens and pass the palette validator in light and dark mode.

**Recorded score** (members read)
- [ ] `GET …/frameworks/{fw}/trend` returns the organization-scope score snapshots in time order.
- [ ] The chart appears only when at least two snapshots exist.

**Owners and due dates** (admins write, members read)
- [ ] `POST …/frameworks/{fw}/register/{code}/assignment` records an owner and an optional due date,
      or clears both.
  - The owner must be a member of the organization; this is checked through `identity.api` (rule 8).
  - The table is append-only, with RLS; the latest row is current.
  - Audit event `requirement.assigned` carries no email.
- [ ] Each register item carries its owner and due date. The row shows the owner and flags a due date
      that has passed while the measure is still not implemented.
- [ ] An "Encargados" summary shows, per owner, the measures they hold that are not yet implemented, as
      ranked horizontal bars (one hue, largest first), plus a count of measures with no owner.

**Activity** (admins and owners read)
- [ ] `GET /api/v1/orgs/{org}/activity?days=30|90` returns daily event counts and the latest 50 events:
      when, actor email, action and target. Event metadata is never returned.
- [ ] An "Actividad" page draws daily counts as columns and lists the events with readable action names
      in ES and EN. Members do not see the navigation entry, and the API refuses them.

## Out of scope

- **Devices:** they need the on-device agent (`ROADMAP.md`, specification first). No device figure is shown
  until real device reports exist.
- **Per-user sign-in history:** Cognito holds it; reading it needs an ADR.
- **Notifications for due dates.**

## Design notes

- Charts are plain SVG React components. No chart library, so there is no new dependency and nothing
  to load past the strict CSP.
- Points are computed on the server, so the browser draws only what the API states.
- **Data:** `requirement_assignments` (organization_id, framework_key, requirement_code, owner_user_id
  NULL to clear, due_on, assigned_by, assigned_at), append-only, with RLS. Listed in ADR-012's table classes.

## Test plan

- **Core:** history replay. A later assessment replaces an earlier one on the same day; days without
  changes carry forward; "not applicable" is counted apart.
- **Postgres:**
  - RLS seed for the new table;
  - assigning a non-member is refused;
  - clearing works;
  - members get 403 on activity;
  - activity returns no metadata;
  - the audit event carries no email.
- **Web unit:** the chart renders its table view, the legend and the end labels; the owner bars are ranked;
  the overdue flag appears.
- **Playwright:** the workspace with history, rendered at 375 and 1280 in light and dark, with axe.
