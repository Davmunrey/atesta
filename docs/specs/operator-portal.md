# Spec: operator portal

- Issue: #396.
- Status: accepted (2026-11-24, #405). ADR-017 and ADR-012 amendment 8 are accepted. It is built
  after the landing restructure and the console unification, because the `packages/ui` move
  touches all of `apps/web`.
- ADRs: ADR-017, ADR-012 (amendments 3 and 8), ADR-009 (amendments 2 and 3), ADR-008, ADR-007.
- Builds on: `billing-entitlements.md`, `organization-closure.md`, `identity-auth.md`, `rbac.md`,
  `tenant-data-layer.md`, `notifications.md`, `web-shell.md`.

## Problem

The Atesta team manages customer organizations with raw SQL and a command-line tool, both run
with the migration role. That role reads every customer's content.
- **Plans:** to change a plan, a person needs credentials that expose assessments, evidence and
  incidents.
- **Missing:** there is nowhere to record billing details, no way to suspend an organization for
  non-payment, and no overview of which organizations exist and whether their connections work.

The owner decided on 2026-11-24 (ADR-017, "Owner decisions") to build a separate operator
portal:
- **What staff see:** metadata only.
- **What staff do:** a short list of actions.
- **Who:** a staff team with three roles.

Customers onboard themselves; the portal never creates organizations or invites people.

## Roles and user stories

**Staff roles** are stored in `operator_staff.role`. They are unrelated to the customer roles in
`rbac.md`.

| Role | Can |
| --- | --- |
| `admin` | Everything below, plus staff management |
| `billing` | Read metadata; set plan and add-ons; read and edit billing details |
| `support` | Read metadata, with billing details limited to the legal name and whether they are complete |

**Stories:**
- **Support:** "As support, I find a customer's organization by name and see whether its
  connections are healthy and when it was last active. When a customer writes in, I can tell
  them what state their organization is in, without seeing their compliance data."
- **Billing:**
  - "As billing, after a contract is signed, I set the organization's plan and add-ons and
    record the legal name, tax ID, billing address and billing contact email that invoices will
    use."
  - "As billing, I filter organizations still on the default plan, or without billing details,
    to follow up."
- **Admin:**
  - "As an admin, I suspend an organization whose contract ended or whose invoices are unpaid,
    with a reason. Its members see a clear page, its owners can still export, and nothing is
    deleted. I reactivate it when it is settled."
  - "As an admin, when a customer leaves, I ask the owners to export, start the closure, and
    after the 30 days request erasure. A second admin approves it."
  - "As an admin, I give a new colleague the `support` role, and disable a leaver's access."

## Screens

All screens live in `apps/operator-web`. They are built from `@atesta/ui` (ADR-017, "Design
system").

1. **Sign-in:** the staff Cognito managed login, then the operator shell. The shell header reads
   "Portal de operaciones" or "Operations portal". The navigation has:
   - Organizaciones;
   - Organizaciones borradas (admin);
   - Equipo (admin);
   - Registro de operaciones (admin).
2. **Organization list:**
   - **Search:** by name (case-insensitive substring) or by exact organization id.
   - **Filters:**
     - state (`active`, `suspended`, `closing`);
     - plan (`starter`, `pro`, `business`, or "default", meaning no subscription row);
     - connection health "needs attention";
     - billing details missing.
   - **Sort:** by name, created date or last activity.
   - **Pages:** 50 rows per page.
   - **Columns:** name, state, plan, members, connection health and last activity.
   - **States:** shared `Loading`, `LoadError` and `Empty`, with a clearable search (DESIGN.md).
3. **Organization detail:** every field in "Metadata fields" below, grouped as Overview, Plan,
   Billing details, Usage, Connections and State. Actions show only to roles allowed to take
   them.
4. **Plan editor** (admin, billing):
   - a plan select, add-on checkboxes from `billing.api` (feature add-ons) and from
     `catalog/plans.yaml` (framework add-ons), and a required reason;
   - a preview line that says what changes: the connector limit and the frameworks gained or
     lost;
   - when the organization uses more connectors than the new plan allows, a notice that says
     existing connections keep working (billing-entitlements spec).
5. **Billing details form** (admin, billing):
   - **Fields:** legal name, tax ID, address line 1, address line 2 (optional), postal code,
     city, province or region, country (ISO 3166-1 alpha-2), billing contact email, and a
     required reason.
   - **Validation:** format checks only, with no external lookup. The tax ID format rules come
     from the official source, cited in the implementation pull request, never from memory.
6. **Suspend** (admin): a reason code, a required internal reason, and the organization's exact
   name typed to confirm. **Reactivate** (admin): a required internal reason.
7. **Export and close** (admin):
   - "Pedir a los propietarios que exporten" (ask the owners to export);
   - "Iniciar el cierre" (start closure), with the exact name typed;
   - "Cancelar el cierre" (cancel closure), only for a closure the operator started.
8. **Erase** (admin):
   - **Request:** the exact name typed, and a required reason.
   - **Approve:** a different admin approves the request, with the exact name typed again.
   - **Status:** pending approval, approved and waiting for the date, executed (with the
     receipt's row counts), or cancelled.
9. **Erased organizations** (admin): receipts from `erasure_receipts`, showing organization id,
   requested and erased dates, and total rows. No names, because erasure removed them.
10. **Team** (admin): staff list (email, role, enabled), with role change and disable. Creating
    the account in Cognito is an owner step in the runbook.
11. **Operations log** (admin): the operator trail, filterable by organization id, staff member
    and action.

## Metadata fields and their sources

These are all the fields the portal can show. Each source is a column in ADR-012 amendment 8's
grant list; nothing else is readable.

| Field | Source | Who sees it |
| --- | --- | --- |
| Name | `organizations.name` | all |
| Organization id | `organizations.id` | all |
| Language | `organizations.locale` | all |
| Created | `organizations.created_at` | all |
| Trial ends | `organizations.trial_ends_at` (owner answer 1); the trial has ended when that time has passed and the organization has no `subscriptions` row | all |
| Last activity | `max(audit_events.occurred_at)` over actions not starting with `operator.` | all |
| State | `active`; `suspended` when `suspended_at` is set; `closing` when `closure_requested_at` is set (both can hold) | all |
| Suspended since, reason | `organizations.suspended_at`, `suspension_reason` | all |
| Closure: started, by whom, erase date | `closure_requested_at`, `closure_origin` (`owner` or `operator`), `closure_requested_at` + 30 days (`identity` closure grace) | all |
| Plan | `subscriptions.plan`; "default (`business`)" when there is no row, from `billing.api.DEFAULT_PLAN` | all |
| Add-ons | `subscriptions.addons` | all |
| Plan note, set at | `subscriptions.note`, `subscriptions.updated_at` | all |
| Billing legal name, completeness | `billing_profiles.legal_name`; complete when every required field is set | all |
| Tax ID, address, billing contact email | `billing_profiles` | admin, billing |
| Members, by role | `count(memberships.organization_id)` grouped by `memberships.role` | all |
| Pending invitations | `invitations`, not accepted, not revoked and not expired (`accepted_at`, `revoked_at`, `expires_at`) | all |
| Connections, by provider and status | `count(*)` grouped by `connections.provider` and `connections.status` | all |
| Connection health | "OK" when every connection that is not `disconnected` is `active`; "needs attention" when any is `incomplete`, `over_privileged` or `revoked`; "none" when there is none | all |
| Connector use against the plan | connections not `disconnected`, against `billing.api.connector_limit(plan)` | all |
| Scans in the last 30 days, by outcome | `scans.status` where `queued_at` is within 30 days | all |
| Last scan finished | `max(scans.finished_at)` | all |
| Active API keys | `api_tokens`, not revoked and not expired | all |
| API calls in the last 30 days | `count(api_token_usage.organization_id)` where `at` is within 30 days | all |

The portal never shows:
- member names or emails;
- connection display names, tenant ids or domains;
- scan results;
- any framework, measure, evidence, policy, incident, training or access-review data.

## API

### Operator service (`atesta_operator`, admin host, prefix `/api/v1`)

- **Session:** every route needs a staff session.
- **Unauthenticated:** 401 `auth.invalid_token`.
- **Unknown staff or disabled:** 403 `operator.forbidden`.
- **Role not allowed:** 403 `operator.forbidden`.
- **Unknown organization:** 404 `operator.not_found`.
- **Writes:** every write takes `reason` (1 to 500 characters), stored only in the operator trail.

| Method and path | Roles | Effect |
| --- | --- | --- |
| `GET /me` | all | Staff profile: email, role |
| `GET /organizations?q=&state=&plan=&health=&billing=&sort=&page=` | all | Paged list, columns as in Screens |
| `GET /organizations/{org_id}` | all | Detail, fields by role as in Metadata fields; writes `organization.viewed` to the operator trail |
| `PUT /organizations/{org_id}/subscription` `{plan, addons, reason}` | admin, billing | Upsert `subscriptions`; an unknown plan or add-on is 422 `operator.invalid_plan` |
| `GET /organizations/{org_id}/billing-profile` | admin, billing | Full billing details, or 404 `operator.no_billing_profile` |
| `PUT /organizations/{org_id}/billing-profile` `{…fields, reason}` | admin, billing | Upsert `billing_profiles`; a field failing its format is 422 `operator.invalid_field` with the field name |
| `POST /organizations/{org_id}/suspension` `{reason_code, confirm_name, reason}` | admin | Suspend. 409 `operator.already_suspended`; 422 `operator.name_mismatch`; 401 `operator.recent_auth_required` if the sign-in is older than 15 minutes |
| `DELETE /organizations/{org_id}/suspension` `{reason}` | admin | Reactivate. 409 `operator.not_suspended` |
| `POST /organizations/{org_id}/export-request` `{reason}` | admin | Notify the owners; no data leaves to staff |
| `POST /organizations/{org_id}/closure` `{confirm_name, reason}` | admin | Start closure with origin `operator`. 409 `operator.closure_exists`; 422 `operator.name_mismatch`; recent sign-in required |
| `DELETE /organizations/{org_id}/closure` `{reason}` | admin | Cancel a closure the operator started. 409 `operator.closure_by_owner` when an owner started it |
| `POST /organizations/{org_id}/erasure-requests` `{confirm_name, reason}` | admin | Create a request. 409 `operator.no_closure` when no closure was started; 409 `operator.erasure_pending` when one is open |
| `POST /erasure-requests/{id}/approval` `{confirm_name}` | admin | Approve. 409 `operator.same_approver` when the approver requested it; 409 `operator.erasure_expired` after 7 days; recent sign-in required |
| `DELETE /erasure-requests/{id}` `{reason}` | admin | Cancel before it runs. 409 `operator.erasure_executed` afterwards |
| `GET /erasure-receipts` | admin | Receipts list |
| `GET /staff` | admin | Staff list |
| `PATCH /staff/{staff_id}` `{role?, disabled?, reason}` | admin | Change role or disable. 409 `operator.last_admin`; 409 `operator.self_change` for one's own row |
| `GET /operator-events?org_id=&staff_id=&action=&page=` | admin | Operator trail |

### Changes to the customer API (`atesta_api`)

- **`require_member`:** while the organization is suspended, it answers 403
  `identity.organization_suspended` on every route except:
  - `GET /api/v1/me`;
  - `GET /api/v1/orgs/{org}/export` (owner);
  - `POST` and `DELETE /api/v1/orgs/{org}/closure` (owner);
  - `GET /api/v1/orgs/{org}/billing-profile` (owner).

  API-key routes and the remote MCP endpoint answer the same 403.
- **`GET /api/v1/me`:** memberships carry:
  - `suspended` (bool) and `suspended_at`;
  - `suspension_reason`, for owners only, null for other roles;
  - `closure_origin`.
- **`GET /api/v1/orgs/{org}/billing-profile`** (owner): the billing details, read-only, or 404
  `billing.no_profile`.
- **Activity:** each event carries `actor_kind`, one of `member`, `system` or `atesta`. Operator
  events show as "Equipo de Atesta" or "Atesta team", with no staff identity.
- **Owner cancel:** `DELETE /api/v1/orgs/{org}/closure` by an owner, on a closure the operator
  started, answers 409 `identity.closure_by_operator`.
- **Worker:**
  - **Scans:** it enqueues no scheduled scan for a suspended organization, and a scan job that
    starts for one exits without running the scanner.
  - **Notifications:** no notification job sends to a suspended organization, except the service
    notices below.
- **Training links:** a training link of a suspended organization answers as a closed campaign
  does.
- **Unsubscribe:** one-click unsubscribe keeps working, because RFC 8058 and the user's choice
  do not depend on the plan.

### Customer side as built (build step 3, #463)

Amended 2026-11-24 where the text above was ambiguous or did not fit the code:
- **One enforcement point:** `identity.standing.enforce`, called by `require_member` and by the
  API-key check after each enters the organization's context. It reads `suspended_at` and
  `trial_ends_at` by primary key, and the plan only once the trial date has passed. The
  allowlists are matched against the request's own path with this organization's id, so any
  other spelling is refused.
- **The ended trial (owner answer 1):** when `trial_ends_at` has passed and there is no
  `subscriptions` row, every write answers 403 `billing.trial_ended`. What stays:
  - every read, export included;
  - an owner's `POST` and `DELETE /api/v1/orgs/{org}/closure`;
  - anyone's `PUT /api/v1/orgs/{org}/notifications/preferences`, a person's choice like the
    one-click unsubscribe;
  - training-link confirmations, which are the employees' records, not the organization's
    members' writes. Invitation acceptance is not an organization route and is unchanged.
- **Trial state:** `GET /api/v1/orgs/{org}/trial` returns `{ends_at, ended}` to every member,
  `ends_at` null once a plan is set. `/me` cannot carry it, because `subscriptions` is read only
  in the organization's own context.
- **API keys and MCP:** the remote MCP endpoint calls the key routes in-process, so the key
  check covers it. A key's refusal carries `message` in the caller's language, as the other key
  errors do (api-keys-v2 spec).
- **Worker:** the scheduled-scan chain keeps re-arming while suspended, so scans resume after
  reactivation; a scan that starts for a suspended organization ends `blocked` with
  `scanning.organization_suspended`, so none stays queued. A notice to a suspended organization
  is suppressed before its delivery is claimed, so a notice still due after reactivation can go.
- **Training link:** reading the suspension needs the organization's context, so the link
  handler enters it (reason `training_link`) before answering 410 `compliance.training_closed`.
- **Owner billing view:** `GET /api/v1/orgs/{org}/billing-profile` lives in identity next to
  the organization settings, calling `billing.api.billing_profile`; billing stays a module with
  no routes and no import of identity.
- **`errors.identity.closure_by_operator`:** the shared error component renders texts without
  values, so the text names no address ("El cierre lo inició Atesta: solo Atesta puede
  cancelarlo"). The settings page shows the contact address next to an operator closure.
- **Activity:** `actor_kind` is `atesta` for an `operator.*` action, `member` when the event
  names a person, `system` otherwise.

## Permissions matrix

| Action | admin | billing | support |
| --- | --- | --- | --- |
| List, search and filter organizations | yes | yes | yes |
| View organization detail (metadata) | yes | yes | yes |
| View tax ID, address and billing email | yes | yes | no |
| Set plan and add-ons | yes | yes | no |
| Edit billing details | yes | yes | no |
| Suspend, reactivate | yes | no | no |
| Ask owners to export | yes | no | no |
| Start or cancel an operator closure | yes | no | no |
| Request, approve, cancel erasure (never approve one's own) | yes | no | no |
| View erased-organization receipts | yes | no | no |
| View the operator trail | yes | no | no |
| Manage staff (never one's own row) | yes | no | no |

## Audit events

- **Two trails (ADR-017, "Audit"):**
  - **Customer trail:** customer-visible events go to the organization's `audit_events`, with
    `actor_user_id` NULL and scalar metadata only.
  - **Operator trail:** every row goes to `operator_audit_events`, with the staff id, role,
    reason and request id.
- **Metadata:** never carries a reason or a billing value, because the reason may hold internal
  notes and the values are personal data.

| Action | Customer `audit_events` | Metadata (customer-visible) | Operator trail |
| --- | --- | --- | --- |
| `operator.plan_changed` | yes | `plan`, `previous_plan`, `addons` (comma-separated) | yes |
| `operator.billing_profile_updated` | yes | `fields` (comma-separated names of changed fields) | yes |
| `operator.suspended` | yes | `reason_code` | yes |
| `operator.reactivated` | yes | none | yes |
| `operator.export_requested` | yes | none | yes |
| `operator.closure_started` | yes | `erase_after` (date) | yes |
| `operator.closure_cancelled` | yes | none | yes |
| `operator.erasure_requested` | yes | none | yes |
| `operator.erasure_approved` | yes | `not_before` (date) | yes |
| `operator.erasure_cancelled` | yes | none | yes |
| `organization.viewed` | no | none | yes |
| `organizations.searched` | no | none (the search text is not stored) | yes |
| `staff.role_changed`, `staff.disabled` | no | none | yes |
| `erasure.executed` | no (the organization no longer exists) | none | yes, written by the erasure runner with the receipt id |

## What a suspended customer sees

The console replaces every organization page with one full-page state, inside the normal shell:
- **What stays:** the organization switcher and the account menu, so a person in several
  organizations can switch.
- **What goes:** the organization navigation is hidden.
- **Owners also see:**
  - the reason;
  - the export link;
  - the closure link;
  - their billing details.

**Web keys** go in `apps/web/messages/es.json` and `en.json`, Spanish first:

| Key | ES | EN |
| --- | --- | --- |
| `suspended.title` | Organización suspendida | Organization suspended |
| `suspended.body` | El acceso a {org} está en pausa desde el {date}. Tus datos se conservan: no se ha borrado ni cambiado nada. | Access to {org} has been paused since {date}. Your data is kept: nothing has been deleted or changed. |
| `suspended.member` | Para saber más, habla con la persona propietaria de la organización. | To find out more, talk to your organization's owner. |
| `suspended.owner` | Motivo: {reason}. Para reactivarla, escribe a {email}. | Reason: {reason}. To reactivate it, write to {email}. |
| `suspended.reason.non_payment` | pago pendiente | payment pending |
| `suspended.reason.contract_ended` | contrato finalizado | contract ended |
| `suspended.reason.customer_request` | a petición de vuestra organización | at your organization's request |
| `suspended.reason.security_review` | revisión de seguridad | security review |
| `suspended.reason.other` | otro motivo | other reason |
| `suspended.ownerActions` | Mientras tanto puedes exportar los datos o cerrar la organización. | Meanwhile you can export the data or close the organization. |
| `suspended.export` | Exportar los datos | Export the data |
| `suspended.closure` | Cerrar la organización | Close the organization |
| `suspended.billing` | Ver los datos de facturación | View billing details |
| `errors.identity.organization_suspended` | Esta organización está suspendida. | This organization is suspended. |
| `errors.identity.closure_by_operator` | El cierre lo inició Atesta. Para cancelarlo, escribe a {email}. | Atesta started this closure. To cancel it, write to {email}. |
| `activity.actor.atesta` | Equipo de Atesta | Atesta team |
| `settings.billing.title` | Datos de facturación | Billing details |
| `settings.billing.empty` | Atesta aún no ha registrado tus datos de facturación. | Atesta has not recorded your billing details yet. |

- **Activity labels:** each `operator.*` action gets a sentence under `activity.actions.<action>`
  in both languages (DESIGN.md, "Activity").
- **Contact address:** `{email}` is the support address from configuration. It is an open
  question until the domain exists.

**Console as built (build step 3, #464).** Amended 2026-11-24 where the text above was ambiguous
or did not fit DESIGN.md:
- **Voice:** `suspended.reason.customer_request` reads "a petición de tu organización". DESIGN.md
  ("Voice") addresses the reader as "tú", never "vosotros", and a test holds it.
- **Owners' billing details** show on the suspended page itself, read-only, so
  `suspended.billing` ("Ver los datos de facturación") is not used. The closure link opens
  Ajustes, which a suspended organization's owner can still reach (without the language panel,
  whose save would be refused).
- **Trial notices** use the console's notice row: owners and admins see "Prueba de 14 días:
  termina el {date}." while it runs; everyone sees the read-only notice, in the overdue style,
  once it has ended (`org.trialEnds`, `org.trialEnded`).
- **Operator closure in Ajustes:** no cancel button; "El cierre lo inició Atesta. Para
  cancelarlo, escribe a {email}." (`settings.closingByAtesta`), with the address from
  `content/legal-entity.ts` (owner answer 9).

**Service notices** (notifications module, `apps/api/src/atesta_api/messages`, ES and EN). They
go to owners, and to admins where noted, and cannot be unsubscribed from, because they concern
the service itself:
- `notice.organization_suspended`, to owners and admins: subject and body naming the
  organization and the date;
- `notice.organization_reactivated`, to owners and admins;
- `notice.export_requested`, to owners: "Atesta te pide que exportes los datos de {org}" /
  "Atesta asks you to export {org}'s data", with the path to Ajustes, Exportar los datos;
- `notice.closure_started_by_operator`, to owners: the erase date, and how to contact Atesta.

## Acceptance criteria

**Separate application and isolation**
- [ ] The operator API is the package `apps/operator` (`atesta_operator`), in its own image. The
  customer API image contains no `atesta_operator` module (image test).
- [ ] Import-linter contracts:
  - `atesta_api` never imports `atesta_operator`;
  - `atesta_operator` imports only `atesta_api.modules.*.api`, `atesta_api.platform.db` and
    `atesta_api.platform.audit`, never `platform.tenancy`.
- [ ] **Tokens:** the operator API accepts only access tokens from the staff pool's app client.
  A customer-pool token gets 401, and the customer API gives a staff-pool token 401.
- [ ] **Session cookie:** the operator session uses its own key and its own cookie name. The
  cookie is host-only, HttpOnly, Secure and `SameSite=Strict`. A write without the portal's
  origin gets 403.
- [ ] **Session limits:** a session ends after 30 minutes idle and 8 hours in total. Suspend,
  closure and erasure approval need a sign-in within the last 15 minutes (401
  `operator.recent_auth_required`).
- [ ] **CSP:** the portal's CSP has `frame-ancestors 'none'` and `connect-src 'self'`.

**Staff identity and roles**
- [ ] **Staff pool settings:** a separate pool with no self sign-up and required MFA, without
  SMS:
  - passkeys with user verification required, counted as MFA
    (`MULTI_FACTOR_WITH_USER_VERIFICATION`);
  - password plus TOTP as the fallback.
- [ ] **Infra test:** a test over the HCL asserts these settings.
- [ ] **No staff row:** a valid staff token with no enabled `operator_staff` row gets 403
  `operator.forbidden`.
- [ ] **Matrix:** every route enforces the permissions matrix. A test walks the matrix for each
  role and route.
- [ ] **Staff changes:** the last enabled admin cannot be disabled or demoted (409
  `operator.last_admin`), and nobody changes their own row (409 `operator.self_change`).

**Database (ADR-012 amendment 8)**
- [ ] **Role:** `atesta_operator` is created by `bootstrap.sql`: NOBYPASSRLS, owns nothing,
  member of no role.
- [ ] **Grants:** its grants equal the closed column list, and the schema linter's second grants
  snapshot holds them.
- [ ] **No content:** for every tenant table not in the list, the role has no table or column
  privilege. On a seeded database, `SELECT` on `evidence`, `findings`, `incidents` or `policies`
  as the role fails with a permission error.
- [ ] **Customer trail:** the role can insert into `audit_events` only an `operator.*` action
  with no `actor_user_id`.
- [ ] **Startup guards:** the operator service refuses to start as `atesta_app`, and the API
  refuses to start as `atesta_operator`.
- [ ] **Customer role:** `atesta_app` has no privilege on `operator_staff`,
  `operator_audit_events` or `erasure_requests`, and only SELECT on `billing_profiles`.

**Organization list and detail**
- [ ] **List:** search, filters, sort and pages work as in Screens, over every organization.
- [ ] **Detail:** shows exactly the fields of "Metadata fields", and only to the roles listed
  there. Support's response carries no tax ID, address or billing email; the field is absent,
  not hidden by the UI.
- [ ] **Never returned:** no operator API response contains a member's email or name, a
  connection display name or tenant id, or any row of a content table. A response-shape test
  checks it.

**Plan and billing details**
- [ ] **Plan write:** setting a plan upserts `subscriptions`, and the next customer request uses
  it through `billing.api.entitlements`. No route compares plan names (ADR-009).
- [ ] **Plan refusal:** an unknown plan or add-on gets 422 `operator.invalid_plan`.
- [ ] **Billing write:** billing details upsert `billing_profiles`. An invalid field gets 422
  `operator.invalid_field` with the field name.
- [ ] **Owner view:** owners read their billing details in the console (Ajustes, Datos de
  facturación). Other roles get 403.

**Suspension**
- [ ] **What suspend does:** sets `suspended_at` and `suspension_reason`, and writes both
  trails. Members then get 403 `identity.organization_suspended` on every route but the
  allowlist, through the web, API keys and MCP alike.
- [ ] **Owners while suspended:** an owner of a suspended organization can export, request or
  cancel an owner closure, and read billing details.
- [ ] **Worker:** a suspended organization gets no scheduled scan and no notification, except
  the suspension notices.
- [ ] **Reactivation:** restores access with every row unchanged. A test compares row counts
  per table before suspension and after reactivation.
- [ ] **Suspended page:** the console shows it with the keys above, in ES and EN. Owners see the
  reason and their actions; other roles see the generic text.

**Export and closure**
- [ ] **Export request:** sends `notice.export_requested` to every owner and writes
  `operator.export_requested`. Staff receive no file, and no operator route returns export
  content.
- [ ] **Operator closure:** sets `closure_requested_at` with origin `operator`. Every member
  sees the existing closure banner and date.
- [ ] **Who cancels:** only an admin can cancel an operator closure. An owner's cancel gets 409
  `identity.closure_by_operator`, and an operator's cancel of an owner closure gets 409
  `operator.closure_by_owner`.

**Erasure**
- [ ] **Request:** needs an existing closure and the exact name.
- [ ] **Approval:** a second admin, different from the requester (409
  `operator.same_approver`), approves within 7 days, with the exact name and a recent sign-in.
- [ ] **No delete path:** the portal never deletes tenant rows. Its role cannot, by grant.
- [ ] **Runner:** the erasure runner, as `atesta_owner`, executes an approved request only once
  its closure date has passed:
  - it calls the existing `identity.erasure.erase_organization`;
  - it marks the request executed with the receipt id;
  - it writes `erasure.executed` to the operator trail.
- [ ] **Command:** `erase_org.py --request <id>` runs the same checks. Without an approved
  request, it refuses.
- [ ] **Cancel:** a cancelled or expired request is never executed.

**Audit**
- [ ] **Every write** writes the customer event and the operator trail row in one transaction,
  or neither.
- [ ] **Customer Activity:** shows operator events as "Equipo de Atesta" or "Atesta team",
  through `actor_kind`, never naming the staff member.
- [ ] **Append-only trail:** `operator_audit_events` is append-only for `atesta_operator`
  (UPDATE and DELETE denied).
- [ ] **What the trail holds:** no reason text and no billing value appears in customer
  metadata. The trail holds billing changes as field names only.

**Design system and i18n** (owner requirement, 2026-11-24)
- [ ] **Shared package first:** `packages/ui` (`@atesta/ui`) exists before the first portal
  screen. Tokens, base styles, fonts, `Loading`, `LoadError`, `Empty`, buttons, fields, data
  tables, state badges, error message, locale switcher, `format.ts`, the API error helper and
  `csp.ts` move there from `apps/web`, which imports them from the package. No visual change to
  the console: the existing tests and e2e pass unchanged.
- [ ] **Only existing tokens and shared components:** every portal screen uses only `@atesta/ui`
  tokens and components.
  - A component the portal needs is added to `@atesta/ui` and documented in DESIGN.md in the
    same pull request.
  - No component, colour, font, spacing or radius is defined inside `apps/operator-web`.
  - A lint check refuses CSS custom properties and colour literals there that are not from
    `tokens.css`.
- [ ] **Strings:** every portal string exists in ES and EN in `apps/operator-web/messages`,
  guarded by the same completeness test as the console. Counts use ICU plurals.
- [ ] **Review:** portal screens are checked at 1280 and 375 pixels and in dark mode, with axe in
  e2e, as for the console (AGENTS.md, "Interface work").
- [ ] **API contract:** the operator API uses the console's error envelope
  (`{"detail": {"code": …}}`). Its OpenAPI document generates the portal's typed client with the
  same script.

## Threat model summary

| Threat | Mitigation | Residual |
| --- | --- | --- |
| **Staff phishing:** a fake sign-in page steals a staff session | Passkeys are bound to the relying party ID, so a look-alike domain cannot use them; short sessions; recent sign-in for destructive actions; optional IP allowlist (ADR-017). Even a full staff session reaches no content | The password plus TOTP fallback can be relayed by a real-time phishing proxy. Mitigation if the owner wants: remove the fallback once every staff member has two passkeys (Cognito requires a second sign-in option to exist in the pool, not that each user uses it; to confirm at build) |
| **Privilege escalation:** support acts as billing or admin, or staff reach content | Roles are checked on the server for every route from `operator_staff`, never from the client; role changes are admin-only, audited, never on one's own row; content tables give the database role no privilege, so even SQL injection in the operator service cannot read content | A compromised admin account can promote another account; it is visible in the operator trail |
| **Cross-tenant leak:** an operator path shows one customer another's data | Customer-visible events are written only to the target organization; the customer API reads no operator table; staff tokens are refused by the customer API; operator responses carry metadata only | None identified beyond a wrong organization id typed by staff, which the typed-name confirmation catches for destructive actions |
| **Insider (rogue admin):** suspends, changes plans or closes to harm a customer | Every write shows in the customer's Activity at once, and suspension and closure also send service notices; the trail is append-only; erasure needs a second admin and a 30-day closure the customer sees from day one | Two colluding admins, or anyone holding the AWS account or the migration credential. Those are owner-level controls (CloudTrail, account access), outside the portal |
| **Customer app compromised** | Separate image, credentials, session key, identity pool and target group (ADR-017) | None from the app; shared AWS account and load balancer remain, governed by IAM |
| **Operator service compromised** | Metadata only; no erasure without the runner's checks (approved request, closure date passed) | An attacker in the service can forge approval rows and suspend everyone. The 30-day closure banner and notices give customers and the team time to notice before any erasure |
| **Billing contact redirected** to divert invoices | Change audited, field names visible to the customer; invoices are issued outside the app | Depends on the invoicing process outside the app checking changes |
| **CSRF or clickjacking** | `SameSite=Strict`, origin check on writes, `frame-ancestors 'none'` | None identified |

## Out of scope

- **Organizations and members:** creating organizations, inviting customer members, changing
  members or roles (owner decision 3).
- **Money:** invoices, payments, prices, payment methods (ADR-009 amendment 3).
- **Content:** any view of customer content, impersonation, or break-glass (ADR-017).
- **Staff accounts:** creating them in Cognito is an owner step in the runbook. The portal sets
  roles and disables access only.
- **Self-service plans:** customers changing their own plan.
- **Infrastructure:** applying it (owner). This spec defines what the infrastructure pull
  request must contain, not the HCL.
- **Customer documents:** DPA and security-page wording about staff access, a follow-up for the
  legal pages.
- **Billing rows:** binary evidence and backups follow the organization-closure spec. This spec
  adds only billing rows.

## Owner answers (2026-11-24)

The owner answered questions 1 to 3 on 2026-11-24, relayed by the coordinator. The coordinator
set 5 to 9 to the proposed default and told the owner, who did not object. Question 4 is
answered from the law below and stays open for the owner's tax adviser.

1. **Trial:** a self-onboarded organization gets a 14-day trial with full access ("Prueba de 14
   días"). When it ends, the organization becomes read-only until an operator sets a plan:
   members can read and export, and every write gets 403 `billing.trial_ended`. The trial end
   date is part of the organization metadata in the portal.
2. **Network access:** open, protected by MFA ("Abierto con MFA"; ADR-017 option A).
3. **Erasure with one admin:** a 72-hour cooling-off, cancellable, before the same admin can
   confirm ("Espera de 72 h"). With two or more admins, a second admin approves.
4. **Billing details after erasure (candidate, for the owner's adviser):** the retention duties
   attach to the invoices and accounting records, which live in the owner's invoicing system,
   not in Atesta:
   - Reglamento de facturación (RD 1619/2012) art. 19: invoices are kept for the period of the
     Ley General Tributaria (https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696);
   - Código de Comercio art. 30: books, correspondence and supporting documents for six years
     (https://www.boe.es/buscar/act.php?id=BOE-A-1885-6627);
   - LOPDGDD art. 32: data kept after a deletion request are blocked
     (https://www.boe.es/buscar/act.php?id=BOE-A-2018-16673).
   Atesta's `billing_profiles` is a working copy, so erasure deletes it with the organization
   (data minimisation). If the adviser says Atesta must keep it, it is blocked under LOPDGDD
   art. 32, readable by no role, and destroyed when the period ends.
5. **Operator reads:** customers see operator writes in Activity, not reads. The operator trail
   keeps reads; a customer gets their organization's read log on request.
6. **Connections:** status grouped by provider, as proposed.
7. **Support and billing details:** support sees only the legal name and whether billing details
   are complete, as proposed.
8. **Operator closures:** only an operator admin can cancel a closure the operator started.
9. **Support address:** hello@atesta.cloud, the public contact address, until a support address
   exists.

## Design notes

- **Build order:**
  1. `packages/ui` move, with no visual change (`ui-package.md`, #440).
  2. Migrations:
     - the role, grants, policies and snapshots;
     - `billing_profiles`;
     - the `organizations` columns;
     - the operator tables.
  3. Module `api.py` functions and the customer-side suspension, billing view and activity
     actor.
  4. The operator API.
  5. `apps/operator-web`.
  6. Infrastructure: staff pool, distribution, service, erasure runner.
  7. Runbooks: offboarding, plan setting, staff accounts.
- **Module functions** (ADR-008), each on an operator-role session, none joining another
  module's tables:
  - **identity:**
    - `organization_rows(session, query, filters, page)`;
    - `organization_metadata(session, org_id)`;
    - `member_counts(session, org_ids)`;
    - `invitation_counts(session, org_ids)`;
    - `last_activity(session, org_ids)`;
    - `suspend(session, org_id, reason_code)`;
    - `reactivate(session, org_id)`;
    - `start_operator_closure(session, org_id)`;
    - `cancel_operator_closure(session, org_id)`.
  - **billing:**
    - `subscriptions_for(session, org_ids)`;
    - `set_subscription(session, org_id, plan, addons, note)`;
    - `billing_profile(session, org_id)`;
    - `set_billing_profile(session, org_id, fields)`.
  - **connections:** `health_counts(session, org_ids)`.
  - **scanning:** `scan_counts(session, org_ids, since)`.
  - **notifications:** `queue_service_notice(session, org_id, kind)`.
  - The API-key counts come from identity, which owns `api_tokens`.
- **Module functions as built (build step 3, #461, #462).** Amended 2026-11-24 where the list
  above was ambiguous or did not fit the code:
  - **Refusals:** the functions raise `identity.api.OperatorError` with a bare code
    (`not_found`, `already_suspended`, `not_suspended`, `closure_exists`, `closure_by_owner`,
    `no_closure`, `erasure_pending`, `same_approver`, `cooling_off`, `erasure_expired`,
    `erasure_approved`, `erasure_cancelled`, `erasure_executed`). The operator API maps each to
    `operator.<code>` and its status; `cooling_off` and `erasure_approved` are 409s the API
    table above did not name. `billing.api.UnknownAddonError` becomes `operator.invalid_plan`.
  - **List filters across modules:** `organization_rows` takes `OrganizationFilters(state,
    within, exclude, sort)`. The plan, health and billing filters are other modules' data, so
    the operator service turns them into id sets (`within`, `exclude`) from
    `subscriptions_for(session, None)`, `health_counts(session, None)` and
    `billing_summaries(session, None)`, where `None` reads every organization. Search and sort,
    including by last activity, stay in identity.
  - **Added:** `identity.api_key_counts(session, org_ids, since)` (active keys, calls since);
    `identity.request_erasure`, `approve_erasure` and `cancel_erasure`, which hold the two rules
    the database cannot (a requester approves only as the sole enabled admin; a new request
    cancels an expired, unapproved one); `billing.billing_summaries(session, org_ids)` (legal
    name and completeness, what support sees) and `billing.known_addons()`.
  - **Renamed:** `scanning.scan_activity(session, org_ids, since)`, because `scan_counts` already
    exists for one organization (weekly summary).
  - **Connection health:** a fourth value, `pending`, when no connection needs attention but one
    is still being set up or verified (`pending_provisioning`, `pending_setup`, `verifying`):
    neither "OK" nor "needs attention" fits it.
  - **Audit trails are not written by these functions:** they return what the trails need
    (`suspended_at`, the erase date, the previous plan, the changed billing field names), and
    the operator service writes the customer event and the operator trail row in the same
    transaction.
  - **Open: `notifications.queue_service_notice` is not built.** Deferring a job inserts into
    the Procrastinate tables, and ADR-012 amendment 8's closed list gives `atesta_operator` no
    privilege on them. Service notices need either an amendment granting the role the defer
    path for one queue, or another trigger; the owner decides.
- **Composition:** the operator service composes these results per page of 50 organizations. At
  the expected number of organizations, this is a handful of grouped queries per page, not one
  per organization.
- **Suspension check:** `require_member` reads `organizations.suspended_at`, which is already in
  its context after `enter_org_context`. One indexed lookup per request.
- **Erasure runner:**
  - **What it is:** a scheduled one-off ECS task (`python -m apps.api.devtools.erase_org
    --pending`) that loops over approved, due requests.
  - **Credential:** it is the only scheduled holder of the migration credential.
  - **Schedule:** its schedule service in eu-south-2 is a candidate, checked at build time.
  - **Fallback:** the runbook command.
- **Database layer (build step 2, #445).** Amended 2026-11-24 where this spec and ADR-012
  amendment 8 were ambiguous or did not fit together; ADR-012 amendment 8 is updated to match.
  - **Trial end:** `organizations.trial_ends_at`, NOT NULL, default `now() + interval '14 days'`,
    so a new organization's trial ends 14 days after `created_at` (both take the transaction's
    `now()`). Existing organizations take the default when the column is added: their trial ends
    14 days after the migration runs, so none turns read-only the day enforcement ships, and the
    operator has those days to set their plans. `atesta_operator` reads it and never writes it:
    setting a plan is what ends the read-only state. Enforcement (`billing.trial_ended`) is build
    step 3.
  - **Closure origin is derived, not written:** `closure_origin` is a stored generated column,
    `owner` when `closure_requested_by` (a person) is set and `operator` when it is not, and NULL
    exactly when `closure_requested_at` is NULL. An owner's closure already records who asked; an
    operator closure sets only `closure_requested_at`. Nobody holds a write on `closure_origin`,
    and a CHECK (`closure_requested_by` only with `closure_requested_at`) means the operator
    role, which cannot write `closure_requested_by`, cannot cancel an owner's closure.
  - **`atesta_app` on `organizations`:** its table-level UPDATE becomes column-level UPDATE of
    `name`, `locale`, `updated_at`, `closure_requested_at` and `closure_requested_by`, so the
    customer role cannot lift a suspension or move a trial end, even through a bug.
  - **Policy names:** a table has one policy per name, so `operator_write` is split into
    `operator_insert` (`FOR INSERT`) and `operator_update` (`FOR UPDATE`). On `subscriptions`
    the operator updates every listed column but `organization_id`, as on `billing_profiles`.
  - **Customer trail from the operator role:** the standard `tenant_isolation` policy applies to
    every role and calls `app_setting_uuid()`, which Postgres evaluates for the operator's
    INSERT check. The role therefore gets EXECUTE on the two setting functions, and a second,
    restrictive policy `operator_audit_only` holds the `operator.%` and no-actor rule even if
    the role sets `app.organization_id` itself.
  - **Billing details columns:** `legal_name`, `tax_id`, `address_line1`, `address_line2`,
    `postal_code`, `city`, `region`, `country` (two capital letters), `contact_email`,
    `updated_at`. Every field is optional in the table (NULL means not recorded; empty text is
    refused); completeness is computed from `legal_name`, `tax_id`, `address_line1`,
    `postal_code`, `city`, `region`, `country` and `contact_email`. Format rules stay in the
    operator API (build step 4).
  - **Erasure requests as data:** `requested_at` takes the database default (the role cannot
    insert it); approval and cancellation each set a person and a time together; approval falls
    within 7 days of the request; the approver differs from the requester, or approves at least
    72 hours after the request (owner answer 3); an executed request was approved and not
    cancelled, and links its receipt; at most one request per organization is open (neither
    cancelled nor executed). Whether a self-approval is allowed at all (only when a single
    enabled admin exists) depends on `operator_staff`, so the operator API checks it; creating
    a request cancels an expired open one in the same transaction, by the same admin.
  - **Operator trail columns:** staff id and role (both NULL only for `erasure.executed`, written
    by the runner), action, organization id, target id, reason (at most 500 characters), request
    id, scalar metadata. No organization foreign key, so it outlives erasure.
  - **Where the models live:** `operator_staff` and `erasure_requests` in identity, which owns
    erasure (and now declares `erasure_receipts` too); `operator_audit_events` in
    `platform.audit`, next to the customer trail. The operator service reaches them through
    `identity.api` and `platform.audit` (ADR-017, "Code boundaries").
  - **Existing environments:** `atesta_owner` cannot create roles, so the bootstrap task runs
    once more before the first deploy with migration 0033 (deploy runbook). Until then that
    migration stops with an error and the running version stays.
- **Rule 2:** the operator service's logs carry no billing values, reasons or search text. Its
  engine uses `hide_parameters=True`, as the API's does.

## Test plan

- **Postgres:**
  - **Role:**
    - the operator role's grants equal the snapshot;
    - it is refused on every content table;
    - it can insert only `operator.*` audit rows;
    - it cannot update or delete `operator_audit_events`;
    - `atesta_app` cannot read the operator tables.
  - **Metadata queries:** each source query returns the expected counts on a seeded pair of
    organizations, with no cross-organization mix.
  - **Suspension:** the route allowlist (owner export, closure and billing allowed; every other
    route 403); API keys and remote MCP refused; reactivation keeps row counts.
  - **Closure origin:** the cancel rules for each origin.
  - **Erasure:**
    - same approver refused;
    - expiry;
    - the runner skips undue, cancelled and unapproved requests;
    - an approved, due request erases with a receipt;
    - `erase_org.py` without a request refuses.
- **Operator API:**
  - the permissions matrix for every route and role;
  - support's detail has no tax ID, address or email;
  - response-shape tests for the never-returned fields;
  - customer-pool token 401;
  - recent sign-in 401;
  - typed-name 422;
  - both trails written in one transaction (a failing commit leaves neither).
- **Customer API:**
  - `/me` suspension fields by role;
  - `actor_kind` in activity;
  - the owner billing view;
  - staff-pool token 401.
- **Static:**
  - import-linter contracts;
  - the customer API image has no `atesta_operator`;
  - the `apps/operator-web` lint refuses non-token colours and custom properties;
  - i18n completeness for both apps.
- **Infra (pytest over HCL, when the infrastructure pull request lands):**
  - staff pool settings (no self sign-up, MFA, no SMS, passkey user verification required);
  - a separate distribution with no caching on `/api/*` and `/auth/*`;
  - the operator target group reachable only from that distribution;
  - the runner task definition the only one with the migration secret besides deploy.
- **Web e2e (both apps, axe):**
  - the suspended page for owner and member;
  - Activity showing "Equipo de Atesta";
  - the portal list, detail, plan editor, billing form, suspend and erasure flows at 1280 and
    375 pixels, light and dark.
