# Spec: Connections screen (Microsoft 365 and Google Workspace)

- Issues: #365 (screen), #366 (callback refusals), #397 (shared patterns), #425 (Google
  Workspace). Part of #221.
- Builds on: `scanner-connectors.md` (Microsoft 365 onboarding, steps 1 to 6), `console-shell.md`,
  `rbac.md`, `i18n-complete.md`, `claims-honesty.md`.
- Status: draft

## Problem

The API runs the whole Microsoft 365 onboarding: create, sign in, consent (#314), then verify and
activate (#331). The web has no screen for it, so an admin cannot connect a tenant at all. The
consent callback redirects to `/app/connections`, which does not exist, so a successful consent
ends on a 404. Any refusal in a callback shows a raw JSON response, including the commonest one:
the admin selects Cancel on Microsoft's consent screen.

## Owner decisions (session, 2026-11-23)

- Build this screen next ("Pantalla conectar M365").
- It sits in the side navigation's *Organización* group, next to Integraciones.
- Google Workspace is shown as "Próximamente", with no action, until its onboarding ships
  (scanner-connectors PR 11). The landing page already uses the same label.
- The "Conectar Microsoft 365" step in Puesta en marcha waits until the dev environment is applied:
  until then every connect attempt in AWS answers 503.

## Acceptance criteria

### API (#365)

- [ ] `ConnectionOut`, and with it the list and the detail, adds two fields:
  - `consented` (boolean): true when sign-in and admin consent are recorded (`ms_tenant_id` and
    `consented_by_oid` both set);
  - `tenant_id` (string or null): the pinned `external_tenant_id`, else the consented
    `ms_tenant_id`.

  Both are tenant data of the caller's org only. The consenting admin's object id is never
  returned.

### API (#366)

- [ ] A refusal in `GET /auth/m365/signin-callback` or `GET /auth/m365/consent-callback` answers
      302 to `<web>/app/connections`:
  - with `?org=<org>&connection=<id>&error=<code>` once the sealed cookie has opened, its `state`
    matched, and the caller was checked as admin+ of the sealed org with the connection found;
  - with `?error=<code>` alone before that (no cookie, a wrong `state`, another user's cookie, a
    caller no longer admin, a connection gone).
- [ ] The code is one of a fixed set. The URL never carries Microsoft's `error`, `error_description`,
      `code`, `state` or `tenant`. The set:
  - `connections.signin_invalid`
  - `connections.consent_denied`
  - `connections.tenant_mismatch`
  - `connections.microsoft_unavailable`
  - `connections.state_invalid`
  - `connections.not_found`
  - `identity.forbidden`, `identity.not_found`, `identity.access_expired` (the caller lost
    access between the start and the callback)
- [ ] Every refusal deletes the `atesta_m365` cookie, so a retry starts a fresh sign-in.
- [ ] Nothing is stored and no audit event is written on a refusal; no code or state is logged
      (rule 2).
- [ ] The success path is unchanged: 302 to `?org=<org>&connection=<id>`.
- [ ] A request with no Atesta session still answers 401 JSON, as every route behind the session
      cookie does. Microsoft only ever sends back the browser that started the sign-in, which has
      a session.

### Web (#365)

- [ ] **Route and access.** `/app/connections?org=<id>`:
  - members, admins and owners can open it; auditors get the existing 403 message;
  - actions show for admins and owners only (UI hints; the API decides).
- [ ] **Navigation.** "Conexiones" sits in the side navigation's *Organización* group, before
      Integraciones, for contributors and above. Global search finds it.
- [ ] **List.** One row per connection that is not `disconnected`:
  - name and provider;
  - status as a badge with its icon and text, for every status: `pending_setup`, `verifying`,
    `active`, `incomplete`, `over_privileged`, `revoked`, `pending_provisioning`;
  - the Entra tenant once known (`tenant_id`, monospace);
  - the last verification date, or "Nunca".

  The empty state explains what connecting does and offers the add form.
- [ ] **Actions by state** (admins and owners):

  | State | Primary action | Secondary |
  |---|---|---|
  | Onboarding (`pending_setup`, `incomplete`, `over_privileged`, `revoked`), not consented | Conectar con Microsoft | Desconectar |
  | Onboarding and consented | Verificar | Conectar de nuevo, Desconectar |
  | `verifying` | (none; "Verificando…" with the activation scan's state) | Desconectar |
  | `active` | Escanear ahora | Desconectar |

- [ ] **Connect.** "Conectar con Microsoft" calls `POST .../m365/signin`. It then navigates only
      if the returned URL's origin is exactly `https://login.microsoftonline.com`; any other
      answer shows the generic error and navigates nowhere.
- [ ] **Verify.** "Verificar" calls `POST .../verify`. While any connection is `verifying`, the
      list and the scans refresh every 5 seconds, and stop once none is. A status change is
      announced in a polite live region.
- [ ] **Scan now.** "Escanear ahora" calls `POST .../scans`; `scanning.daily_limit` and
      `scanning.already_queued` show their existing texts.
- [ ] **Disconnect.** "Desconectar" asks for confirmation inline, as Members does for removal,
      then calls `DELETE`. The row leaves the list.
- [ ] **What the customer grants.** Each Microsoft 365 row has a disclosure "Permisos que
      concedes". On first open it fetches the detail and lists `expected_access.permissions`,
      the allowlist the verifier compares against, with the count and the words "solo lectura".
      For `incomplete` and `over_privileged` it also lists `last_verification.missing` and
      `extra`. The web never types a permission.
- [ ] **Add.** An admin adds a Microsoft 365 connection with a name (1–100 characters, default
      "Microsoft 365"). Billing refusals show their existing texts.
- [ ] **Google Workspace.** A row in the add area names Google Workspace with "Próximamente" and
      no control.
- [ ] **Return from Microsoft.**
  - `?connection=<id>` without `error` marks that row (`aria-current="true"`, the selected-row
    token) and shows a status notice naming the next step, "Verificar".
  - `?error=<code>` shows that code's existing message as an alert. A code outside the known
    error codes shows the generic message, so no text from the URL is ever rendered.
  - Both parameters are then removed from the address bar with `history.replaceState`, keeping
    `org`, so a reload does not repeat the notice.
- [ ] **i18n.** Every string is in `apps/web/messages/es.json` and `en.json`. The statuses, actions
      and notices come from the `connections` namespace; error texts from `errors`.
- [ ] **Rendering.** Checked rendered at 1280 and 375 pixels, light and dark, before it is called
      done (AGENTS.md, Interface work). At 375 pixels the table stacks with `data-label`, as
      Integraciones does.

## Shared console patterns (#397, owner 2026-11-24: "Align it all in the Google PR")

The console unification (#413 to #415) left this screen out; its coherence test exempted it. It
now uses the console's shared patterns, and the exemption is removed:

- [ ] **State badges.** Each connection status is a `Badge` state from `lib/severity.ts`:
  - `connectionActive` is `done`;
  - `connectionWaiting` is `pending`: setup, verification pending, provisioning, verifying;
  - `connectionIncomplete` is `missing`;
  - `connectionOverPrivileged` and `connectionRevoked` are `overdue`.

  No hand-drawn badge remains.
- [ ] **Detail disclosure.** Each connection's detail is a native `details` in a full-width row under
      it, styled as `row-section`. The first `toggle` fetches the detail. There is no custom
      `aria-expanded` button.
- [ ] **Codes.** Permission and scope lists use `var(--font-mono)` only.
- [ ] **Selected row.** `tr[aria-current="true"]` sits with the shared data-table rules.
- [ ] **Disconnect.** "Desconectar" is a `dashboard-button`. It opens a `confirm-row` that holds the
      question, a `button-danger` "Sí, desconectar" and a `dashboard-button` "Cancelar", as Members does.

## Google Workspace (#425)

Owner decisions, 2026-11-24:
- "Ambos para el piloto": both Microsoft 365 and Google Workspace go into the pilot;
- "After the unification pass": this screen waited for the console unification;
- "Existing admin + domain from the email": the screen recommends an existing super admin, and the
  primary domain comes from the email.

### API

- [ ] `ConnectionOut` adds:
  - `google_subject_set`: a super admin is named;
  - `primary_domain`: Google's primary domain, or null.

  The email itself is never returned (rule 2 spirit: the customer typed it once).

### Web

- [ ] **Add.** One form adds either provider, with a provider select (`.routine-form` field) and an
      optional name. An empty name takes the provider's name. "Próximamente" is removed.
- [ ] **Account column.** It is named "Tenant o dominio" and shows:
  - Microsoft 365: the tenant id, as before;
  - Google: the pinned customer id, or before the first verification the primary domain.
- [ ] **"Acceso en Google Workspace" disclosure**, for Google rows:
  1. **Authorize Atesta in Google.** The path in the Admin console: Seguridad, Acceso y control de
     datos, Controles de API, Gestionar la delegación de todo el dominio, Añadir nueva. Then the
     two entries. Each entry has its client ID and its exact comma-separated scope string, in
     mono, each with a `CopyButton`. While `pending_provisioning`, a sentence says Atesta is
     preparing the read-only accounts and shows them here when ready.
  2. **The super admin Atesta reads as.** This appears while provisioning or onboarding. A form
     takes an email, with a checkbox "Está en un dominio secundario" that reveals a primary domain
     field. It recommends an existing super admin, and says that:
     - Google records Atesta's reads as that user;
     - delegation reaches every user's data within the read-only scopes;
     - suspending the user or removing the role stops scans;
     - a new account costs a licence and adds a super admin.

     Once saved, the step reads "Superadministrador indicado (dominio <domain>)", and the form
     stays available to change it.
  3. **The last verification's missing and extra items**, as for Microsoft 365.
- [ ] **Actions by state** for Google rows (admins and owners):

  | State | Primary action | Secondary |
  |---|---|---|
  | `pending_provisioning` | (none: waiting for Atesta) | Desconectar |
  | Onboarding, provisioned, no super admin named | (none: the disclosure asks for the super admin) | Desconectar |
  | Onboarding, provisioned, super admin named | Verificar | Desconectar |
  | `verifying` | (none; Google may take up to 24 hours, and Atesta checks every hour) | Desconectar |
  | `active` | Escanear ahora | Desconectar |

- [ ] **Disconnect.** The confirmation names the Google step: delete Atesta's two delegation
      entries in the Admin console.
- [ ] **i18n.** Every string is in ES and EN and uses "tú". Scope strings and ids are data and stay
      untranslated.
- [ ] **Rendering.** Checked at 1280 and 375 pixels, light and dark.

### Tests

- Web unit tests:
  - Google actions by state;
  - the disclosure shows both client IDs and scope strings with copy buttons;
  - the super admin form sends `PUT .../google` with or without `primary_domain`;
  - the add form posts the chosen provider;
  - the badges come from the severity mapping;
  - disconnect uses the confirm row.
- The consistency test drops its exemption for this file.
- API test: `google_subject_set` and `primary_domain` appear, and the email never does.

## Out of scope

- The owner runbooks (#421) and the AWS key store.
- The Global Reader step and the PowerShell services (scanner-connectors step 5, PR 10).
- The Puesta en marcha step (owner decision above).
- Scan findings on this page; the overview's scan history stays where it is.
- Retrying a failed activation automatically: the admin selects "Verificar" again.

## Design notes

- **API.** Connections module: `routes.py` builds `ConnectionOut` explicitly instead of
  `from_attributes`, to add the two computed fields. `m365.py` turns refusals into redirects
  through one helper that takes the code. No new route, no data model change, no new
  dependency.
- **Typed client.** OpenAPI and the typed client are regenerated.
- **Web.**
  - `lib/api/connections.ts` holds the hooks (the `tokens.ts` pattern) and `isMicrosoftLogin(url)`.
  - `components/connections-view.tsx` holds the view; `app/(app)/app/connections/page.tsx` the page.
  - Navigation: `console-shell.tsx`, plus `orgConnections` in `lib/org.ts`.
- **Interface rules.** Operate mode, existing tokens and components only: `PageHeader`, `Panel`,
  badges with `data-severity`, `table-region`, `routine-form`, the inline confirm row. No modal
  (craft floor) and no new colour.
- **Security.**
  - Rule 1: the screen only shows the read-only allowlist, and never offers a write scope.
  - Rule 2: the web never logs the URL. It reads `error` and `connection` only to look them up
    in fixed sets, then drops them from the address bar.
  - The origin check before navigation keeps a compromised or misconfigured API answer from
    sending the admin anywhere but Microsoft.
- **Audit.** No new event. The page triggers the existing `connection.created`,
  `connection.verification_requested`, `scan.requested` and `connection.disconnected`.

## Test plan

- **API, DB tests** (`test_m365_onboarding.py`, `test_connections_http.py`):
  - each refusal is a 302 to the page with its code, keeps the store unchanged and deletes the
    cookie;
  - an unopenable cookie, a wrong `state`, another user's cookie and a demoted admin redirect
    without `org`;
  - Microsoft's `error_description` never appears in `Location`;
  - the list and detail return `consented` and `tenant_id`, before and after consent;
  - the consenting admin's object id is absent from both.
- **Web unit tests** (`tests/unit/connections-view.test.tsx`):
  - actions by state and role, as rows of the table above;
  - connect navigates only to `https://login.microsoftonline.com`;
  - an `error` from the URL shows its message, and an unknown one the generic message;
  - the permissions disclosure lists the fetched allowlist;
  - inline confirm before disconnect;
  - Google shows "Próximamente" with no control.
- **i18n guard** (`tests/unit/i18n.test.tsx`): every new key in both languages.
- **Rendered check:** the page at 1280 and 375 pixels, light and dark, with the local fake data.
