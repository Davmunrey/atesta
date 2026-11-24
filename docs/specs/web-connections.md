# Spec: Connections screen (Microsoft 365)

- Issues: #365 (screen), #366 (callback refusals). Part of #221.
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

## Out of scope

- Google Workspace onboarding (scanner-connectors PR 11) and its screen.
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
