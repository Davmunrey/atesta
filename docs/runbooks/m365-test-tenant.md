# Runbook: Microsoft 365 test tenant and the two app registrations

The owner's steps before the first real Microsoft 365 scan (issue #362; scanner-connectors spec,
"Microsoft 365 onboarding" and "Owner steps"; D12). No agent can take them. Every portal step
below was read on Microsoft Learn on 2026-11-23; the sources and their dates are at the end.
Anything not yet tried in a real tenant is marked **candidate**.

## Rules for this runbook

- **No secret leaves its place.** The Sign-in client secret goes from the Entra portal straight
  into AWS Secrets Manager. The scanner's private key is generated inside AWS and never leaves it.
  Neither goes into a chat, an issue, a pull request, the repository, a note or a screenshot.
- **No callback URL is copied.** After Microsoft redirects back, the address bar holds a one-time
  `code` and a `state`. Do not paste it anywhere; report the screen you see instead.
- **Read-only.** The scanner app lists only the generated read permissions (AGENTS.md rule 1).
  Nobody adds, removes or types a permission by hand.

## 0. The layout (owner's decision, 2026-11-23)

| Tenant | Plays | Licence | Holds |
|---|---|---|---|
| **Test tenant** | A customer | Microsoft 365 Business Premium, paid, 1 seat | Its own users and policies, which Atesta scans. Its Global Administrator signs in and consents |
| **Atesta dev** | Atesta | Microsoft Entra ID Free | The dev registrations "Atesta Sign-in (dev)" and "Atesta Scanner (dev)" |

Two tenants, so that the consent crosses tenants exactly as it will for every customer. Prod gets
its own registrations later, in Atesta's prod tenant with a verified domain (D12). The names
carry "(dev)" only so that the test tenant's Enterprise apps list is unambiguous. The code
matches application IDs, never names.

## 1. The test tenant (Business Premium)

1. Buy Microsoft 365 Business Premium with **1 seat** on a paid subscription. Do not start
   from a free trial. Microsoft: "Customers using a free tenant, or a trial subscription won't be
   able to create additional tenants", and step 2 creates one from this tenant. If you already
   started a trial, convert it to paid first.
2. Choose **Spain** as the country. The initial domain is `<name>.onmicrosoft.com`; a custom
   domain is not needed for testing.
3. The account that signs up is the tenant's **Global Administrator**. Turn on MFA for it. This
   is the admin who will consent: step 6 of onboarding checks that the consenting admin holds
   Global Administrator or Privileged Role Administrator **directly**. A role held only through a
   group is a candidate limit.
4. Optional, for a realistic first scan: add two or three test users and leave the default
   policies as they are. Atesta reads configuration; it needs no real mail or files.

**Candidates:** what Business Premium includes (Microsoft Entra ID P1, Intune, Defender for
Business are expected), its price and commitment terms, and where data is stored for a tenant
created with country Spain. None of these was checked here.

## 2. The Atesta dev tenant (Entra ID Free)

1. Sign in to the Azure portal (`https://portal.azure.com`), as the page's workforce steps do,
   with the test tenant's Global Administrator.
2. Go to **Entra ID > Overview > Manage tenants > Create**.
3. **Basics:** choose **Microsoft Entra ID** (a workforce tenant; not B2C, not Governed
   Workforce).
4. **Configuration:** organization name `Atesta dev`, an initial domain such as `atestadev`
   (whatever is free), country **Spain**. Then **Review + Create > Create**.
5. The creator is assigned Global Administrator of the new tenant. In the new tenant, create a
   cloud-only admin (`admin@<initial domain>.onmicrosoft.com`) with Global Administrator and MFA,
   and use it from now on. That way the dev apps do not depend on an account in the tenant they
   are tested against.

**Candidates:** that a Business Premium tenant with no Azure subscription can create it (the page
requires a paid customer and a subscription only for Governed Workforce), and that it costs
nothing (Entra ID Free).

All later steps run **in Atesta dev**. To switch, use the **Settings** icon in the top menu,
then **Directories + subscriptions**.

## 3. Register "Atesta Sign-in (dev)"

What it does: binds a connection to the tenant of a real admin. It has `openid profile` only and
no application permissions (spec step 3).

1. **Entra ID > App registrations > New registration.**
   - Name: `Atesta Sign-in (dev)`.
   - Supported account types: **Multiple Entra ID tenants**.
   - Leave the redirect URI empty here. Select **Register**.
2. Copy the **Application (client) ID** from Overview. It is not a secret; you will need it in
   section 5.
3. **Authentication > Add Redirect URI > Web:**
   `https://<dev web origin>/auth/m365/signin-callback`. The dev web origin comes from the
   guided infrastructure session (`docs/runbooks/deploy.md`). Use https and the exact path, add
   no front-channel logout URL, and leave the ID token and access token (implicit grant) boxes
   unticked.
4. **API permissions:** Microsoft adds the delegated Microsoft Graph `User.Read` to every new
   registration. Remove it from the list, which must end **empty**. `openid profile` is requested at sign-in and needs no entry here.
5. **Certificates & secrets > Client secrets > New client secret.**
   - Do this step **during the infrastructure session**, with the Secrets Manager console open in
     eu-south-2.
   - Description: `dev-<yyyy-mm>`. Expires: **Custom, 180 days** (the spec's rotation; Microsoft
     caps secrets at 24 months and recommends under 12).
   - The **Value** is shown once. Paste it straight into the Secrets Manager secret that the
     session creates for `ATESTA_M365_SIGNIN_CLIENT_SECRET`, then leave the page. Never copy it
     anywhere else.
   - Why a secret here and not a certificate: this app has no permissions, and a secret can only
     redeem its sign-in codes. Before the first customer it moves to a certificate (#363).
6. **Authentication > App instance property lock > Configure:** **Enable property lock** and
   **All properties** must be ticked. Since June 2026 it is on by default for new apps; check it
   anyway, then **Save**.

## 4. Register "Atesta Scanner (dev)"

What it does: receives the customer's admin consent for the read-only Graph application
permissions and authenticates to Graph with a certificate only.

1. **Entra ID > App registrations > New registration.**
   - Name: `Atesta Scanner (dev)`.
   - Supported account types: **Multiple Entra ID tenants**.
   - Select **Register**. Copy the **Application (client) ID**.
2. **Authentication > Add Redirect URI > Web:**
   `https://<dev web origin>/auth/m365/consent-callback`. Same rules as in section 3.
3. **Permissions come from the code, not from clicks.** From a fresh checkout of `main`, run:

   ```bash
   uv run python -c "import json; from atesta_core.connectors.readonly import required_resource_access; print(json.dumps(required_resource_access('m365-v1'), indent=2))"
   ```

   It prints the `requiredResourceAccess` block for allowlist `m365-v1`: one resource, Microsoft
   Graph (`00000003-0000-0000-c000-000000000000`), with 20 entries, all `"type": "Role"`.
   These are application permissions, every one read-only and admin-consent only. The verifier
   compares the consented grants with this same allowlist, so nothing else will pass.
4. Open **Manifest** (the Microsoft Graph app manifest editor). Replace the whole value of
   `"requiredResourceAccess"`, including the default `User.Read` entry, with the printed array.
   Then **Save**. Replacing the block is what removes the default delegated `User.Read`. If it
   stayed, the verifier's step 4 would find an extra delegated grant and the connection would
   end `over_privileged`.
5. **API permissions** must now show 20 Microsoft Graph permissions:
   - all of type **Application**, each name ending in `.Read.All`, `.Read.Directory` or
     `.Read.DeviceConfiguration`;
   - **no Delegated** row, and no `User.Read`.

   Do **not** select **Grant admin consent for Atesta dev**: Atesta dev is not scanned. Consent
   happens in the test tenant during onboarding.
6. **Certificates & secrets > Certificates > Upload certificate:**
   - Upload the **public** certificate (`.cer`, `.pem` or `.crt`) that the infrastructure session
     generates inside AWS. Its private key, a passwordless PFX, stays in Secrets Manager. Only the
     M365 scan and verify tasks can read it.
   - Description: `dev-<yyyy-mm>`. Record the **Thumbprint** and the expiry date; neither is
     secret.
   - Check that **Client secrets** and **Federated credentials** both show 0. This app never gets
     a secret.
7. **Authentication > App instance property lock > Configure:** **Enable property lock** and
   **All properties** ticked. **Save**.

## 5. Where each value goes

| Value | Secret | Goes to | When |
|---|---|---|---|
| Sign-in Application (client) ID | No | API task variable `ATESTA_M365_SIGNIN_CLIENT_ID` | Infrastructure session |
| Sign-in client secret Value | **Yes** | Secrets Manager, read by the API as `ATESTA_M365_SIGNIN_CLIENT_SECRET` | Infrastructure session, typed only into the console |
| Scanner Application (client) ID | No | API task variable `ATESTA_M365_SCANNER_CLIENT_ID`, and `AZURE_CLIENT_ID` in the scanner credential secret | Infrastructure session |
| Scanner private key (PFX) | **Yes** | Generated in AWS; `M365_CERTIFICATE_CONTENT` in the scanner credential secret | Infrastructure session; never exported |
| Scanner certificate thumbprint and expiry | No | Owner's operations notes, for the yearly rotation with two overlapping certificates | After step 4.6 |
| Atesta dev tenant ID | No | Nothing: the sign-in uses the `organizations` endpoint | n/a |
| Test tenant ID | No | Nothing to configure: the connection records it at consent | n/a |

Until all three `ATESTA_M365_*` values are set, onboarding answers 503
`connections.microsoft_unavailable`, by design.

## 6. Check before the first consent

| Check | Sign-in (dev) | Scanner (dev) |
|---|---|---|
| Supported account types | Multiple Entra ID tenants | Multiple Entra ID tenants |
| Redirect URIs (Web) | exactly `.../auth/m365/signin-callback` | exactly `.../auth/m365/consent-callback` |
| API permissions | none | 20 Application, 0 Delegated |
| Credentials | 1 client secret, at most 180 days | 1 certificate, 0 secrets, 0 federated |
| App instance property lock | on, all properties | on, all properties |

## 7. The first onboarding (live golden of #331)

1. In dev Atesta, as an org owner or admin, create a Microsoft 365 connection and connect it
   (the connect screen, or the API until that screen ships).
2. Microsoft's sign-in opens. Sign in with the **test tenant's** Global Administrator, not the
   Atesta dev admin.
3. The consent screen lists the 20 read permissions of "Atesta Scanner (dev)". The publisher may
   show as unverified: admin consent without publisher verification is a candidate the live
   golden checks (spec, D12). Accept.
4. Back in Atesta, start the verification. Expected result:
   - the connection becomes `active`;
   - the activation scan reaches `collected`;
   - the daily schedule starts.
5. Report back the connection status, the scan status and any error code shown, for example
   `connections.incomplete_permissions`, `connections.consent_denied` or
   `scanning.tenant_mismatch`. Never send a URL, a token or a screenshot of the address bar.

## 8. Undo

- **Revoke as a customer would:** in the test tenant, go to **Entra ID > Enterprise apps >
  Atesta Scanner (dev) > Properties > Delete**. It can be restored for 30 days. Atesta marks the
  connection `revoked` at its next verification.
- **Retire a credential:** in Atesta dev, delete the secret or the certificate under
  **Certificates & secrets**, and delete its Secrets Manager entry in the same session.
- **Drop the dev tenant:** select **Delete directory** on its Overview page, once no app is in
  use.

## Candidates still open

| Candidate | Settled by |
|---|---|
| What Business Premium includes; its price and commitment; the data location for country Spain | The purchase screens and the tenant's admin center, step 1 |
| A paid Business Premium tenant with no Azure subscription can create a workforce tenant, and Entra ID Free costs nothing | Step 2 done |
| Admin consent to an unverified multi-tenant app works | Step 7.3 |
| The role check sees a role held only through a group | Live golden (spec, Verifier limits) |

## Sources (all read 2026-11-23)

| Fact | Source (page's last update) |
|---|---|
| Only paid customers can create a workforce tenant; a free tenant or trial cannot. Path Entra ID > Overview > Manage tenants > Create; the creator becomes Global Administrator; Delete directory | https://learn.microsoft.com/en-us/entra/fundamentals/create-new-tenant (2026-07-31) |
| Path Entra ID > App registrations > New registration; account type label "Multiple Entra ID tenants"; application (client) ID on Overview | https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app (2026-06-05) |
| Web redirect URIs under Authentication > Add Redirect URI | https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri (2026-05-14) |
| `User.Read` is added automatically to a new registration; permissions can be removed | https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-configure-app-access-web-apis (2025-01-27) |
| Manifest editor under Manifest; `requiredResourceAccess` holds `resourceAppId` and `resourceAccess` `{id, type}` | https://learn.microsoft.com/en-us/entra/identity-platform/reference-microsoft-graph-app-manifest (2025-02-03) |
| Certificates upload as .cer, .pem or .crt and show a thumbprint. Secrets last at most 24 months, under 12 recommended, and "should not be used in production environments"; the Value is shown once | https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-credentials (2026-11-17) |
| Property lock: Authentication > App instance property lock; "Since June 2026 ... Enabled by default for new applications" | https://learn.microsoft.com/en-us/entra/identity-platform/howto-configure-app-instance-property-locks (2026-10-02) |
| Business plans are designed for up to 300 users | https://learn.microsoft.com/en-us/office365/servicedescriptions/office-365-platform-service-description/office-365-plan-options (2025-07-18) |
| The E5 developer sandbox is only for Visual Studio Pro or Enterprise subscribers and some partner programs, hence a paid tenant | Microsoft 365 Developer Program FAQ, read in session on 2026-11-23 (issue #362) |
| The generated block has 1 resource and 20 entries, all `Role` | `uv run python -c "...required_resource_access('m365-v1')..."` on `main` at 309a62a |
