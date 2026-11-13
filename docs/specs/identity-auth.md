# Spec: Identity, Cognito auth with mandatory MFA

- Requirement ids: FR-01, FR-13, NFR-03, NFR-04, NFR-10
- Status: approved (2026-11-13)
- ADRs: ADR-007 (amendment 1), ADR-008, ADR-012
- Build order: 2 of 3 (depends on tenant-data-layer). Cognito resources: infra-dev spec (next).

## Problem

The security lead of an SME supplier signs up, creates the organization and invites colleagues.
Atesta stores the security posture of its customers, so a stolen password must not be enough to
read it. TOTP MFA is required on every sign-in after the first, with no opt-out: Cognito issues
tokens for the session that completes sign-up before TOTP is enrolled (gated by password plus the
emailed code), and the next sign-in forces enrollment. Auth code is a liability for one builder,
so it is bought (Cognito, Architecture tab "Build vs buy").

## Acceptance criteria

- [ ] Cognito user pool in eu-south-2 (OpenTofu, infra-dev spec), all set in the first apply
      because username settings are immutable: MFA `ON`, TOTP only (no SMS, no email OTP), email
      as username, `case_sensitive = false`, `auto_verified_attributes = [email]`,
      `attributes_require_verification_before_update = [email]`, account recovery by verified
      email only, self sign-up, password min 12 characters, deletion protection on,
      `user_pool_tier = "ESSENTIALS"`.
- [ ] Managed login, not the classic hosted UI: domain with `managed_login_version = 2` and an
      `aws_cognito_managed_login_branding` style for the web app client (an API-created client
      has none and cannot use managed login without it).
- [ ] App client: public (no secret), Authorization Code + PKCE only, scopes `openid email`, never
      `aws.cognito.signin.user.admin`, `explicit_auth_flows = [ALLOW_REFRESH_TOKEN_AUTH]` (no SRP,
      password or custom flows), `email` not writable. Callback and sign-out URLs for localhost and
      the dev web origin.
- [ ] Spanish first (NFR-10): the web adds `lang=es` to every authorize request, `lang=en` when
      the user chose English. The verification and reset email template has a Spanish subject and
      Spanish text first, English below. Template text lives in an infra i18n file, not in `.tf`.
- [ ] Email (NFR-04, ADR-007 amendment 1): a pool in eu-south-2 cannot use SES in its own
      Region, so Cognito email goes through SES in eu-west-3 (Paris), an EU exception listed in
      ADR-007. Dev uses the default sender (capped at 50 emails a day; builder's own addresses).
      Prod uses `email_sending_account = DEVELOPER` with a verified domain identity in eu-west-3
      with DKIM, and SES production access before the first external user signs up.
- [ ] This spec ships a minimal apps/web sign-in redirect and callback page that completes
      Authorization Code + PKCE and calls `GET /v1/me`. Other screens belong to the web spec.
- [ ] API accepts Cognito access tokens only: RS256 against cached JWKS, exact `iss`,
      `token_use == "access"`, `client_id` equal to the app client, `scope` contains `openid` and
      not `aws.cognito.signin.user.admin`, `exp` with 60 s leeway. Anything else returns 401
      `auth.invalid_token`.
- [ ] Profile data comes from the Cognito `/oauth2/userInfo` endpoint called with the caller's
      access token. The API calls no Cognito user pool operation that needs the admin scope.
- [ ] Cognito holds identity only (`sub`, email). Organizations, memberships and roles live in
      Postgres. No Cognito groups.
- [ ] Tables `users`, `memberships`, `invitations` and the identity policies on `organizations`
      (model below; `organizations` itself comes from the data-layer spec).
- [ ] Endpoints, all in the OpenAPI spec:

| Method and path | Allowed | Effect |
|---|---|---|
| `GET /v1/me` | Authenticated | Provision or refresh the user; return profile and memberships |
| `POST /v1/orgs` | Authenticated | Create org; caller becomes `owner` |
| `GET /v1/orgs/{org_id}/members` | member+ | List members |
| `PATCH /v1/orgs/{org_id}/members/{user_id}` | owner | Change role |
| `DELETE /v1/orgs/{org_id}/members/{user_id}` | admin+ (owner to remove an owner or admin) | Remove member |
| `POST /v1/orgs/{org_id}/invitations` | admin+ (owner to invite an `owner`) | Create invitation; return accept link once |
| `GET /v1/orgs/{org_id}/invitations` | admin+ | List pending invitations |
| `DELETE /v1/orgs/{org_id}/invitations/{id}` | admin+ | Revoke invitation |
| `POST /v1/invitations/accept` | Authenticated | Accept with token in the JSON body |

- [ ] Roles: `owner` > `admin` > `member`. An org always keeps at least one owner: demoting or
      removing the last owner returns 409 `identity.last_owner`, also under concurrent requests.
- [ ] An invitation's role never exceeds the inviter's: an admin invites `admin` or `member`;
      otherwise 403 `identity.role_not_allowed`.
- [ ] Accept re-checks the inviter in the same transaction: `invited_by` must still be a member
      with a role at least the invited role, or the invitation is rejected like a revoked one.
- [ ] Accept never changes an existing membership: an existing member gets 409
      `identity.already_member`, role unchanged, invitation still pending. Plain INSERT, never
      upsert.
- [ ] Org routes return 404 (not 403) when the caller is not a member: no org enumeration.
- [ ] `identity.api.enter_org_context(session, org_id, reason)` is the only caller of
      `set_tenant_context()` with an org id. Reasons (ADR-012): `membership` (from
      `require_member` and `require_role`), `invitation`, `org_creation`, `job` (worker only,
      scanning spec).
- [ ] Audit events: `org.created`, `invitation.created`, `invitation.revoked`,
      `invitation.accepted`, `membership.role_changed`, `membership.removed`.
- [ ] Errors return stable codes. ES and EN texts live in the web i18n files; the API holds no
      user-facing prose.
- [ ] Access tokens, invitation tokens and `Authorization` headers are never logged, including
      on the successful provisioning path.

## Out of scope

- Invitation email via SES: the inviting admin gets a copy-once link. SES comes with the
  notifications spec.
- SSO SAML/OIDC (FR-22, v2), MSP console (FR-15, v2), read-only auditor role, passkeys.
- Self-service MFA recovery. Support runbook: confirm the request through a channel other than
  the account email (another owner or admin of the org, or the contract contact), then call
  `AdminUserGlobalSignOut`, `AdminResetUserPassword`, `AdminDeleteSoftwareToken`, in that order.
  Never `AdminDeleteSoftwareToken` alone: the next password sign-in would enroll whoever holds the
  password. Access tokens already issued stay valid until `exp` (30 min max).
- API-side MFA check on the `amr` claim. Per the verifier's reading of AWS docs, Cognito adds
  `acr` and `amr` only when the authorize request sends `acr_values` (Essentials or higher), and
  the feature is still rolling out (candidate, recheck in the dev pool). Revisit before the first
  paying customer. Until then MFA rests on `mfa_configuration = ON`, asserted in OpenTofu.
- Account and org deletion (NFR-08, offboarding spec).
- Cognito threat protection and user activity logs (Plus plan). Revisit before the first paying
  customer.

## Design notes

### Data model (identity module)

| Table | Columns | Class (ADR-012) |
|---|---|---|
| `organizations` | from the data-layer spec | Tenant root |
| `users` | id, cognito_sub (unique), email (non-unique index on `lower(email)`), email_verified, display_name, locale (`es`/`en`, default `es`), created_at, updated_at | Global identity |
| `memberships` | organization_id, user_id, role, created_at; PK (organization_id, user_id); index on `user_id` | Tenant, one extra read policy |
| `invitations` | id, organization_id, email, role, token_sha256 (indexed, not unique: tenant unique keys lead with `organization_id`, and 256-bit tokens do not collide), invited_by, expires_at (7 days), accepted_at, revoked_at, created_at; UNIQUE (organization_id, id) | Tenant, one extra read policy |

- `users` is global because one person can belong to several orgs (consultants now, MSP
  technicians in v2). It holds identity only, no customer data.
- Identity is `cognito_sub`, never email. `email` and `email_verified` are a cache of Cognito,
  always written together from a userInfo response. Email is not unique: a deleted and re-created
  Cognito user gets a new `sub`, and a freed address can be registered by someone else; under RLS
  a unique conflict on an invisible row could never be repaired. A re-created Cognito user is a
  new Atesta user; support re-invites them.

### Policies

Read branches are separate `FOR SELECT` policies, so they never grant a write. Every write passes
`tenant_isolation`, or the self policies on `users`. Settings are read through the data-layer
helpers.

| Table | Policies | `atesta_app` grants |
|---|---|---|
| `organizations` | `tenant_isolation` on `id`; FOR SELECT `own_orgs_read`: `id` in the caller's visible memberships | SELECT, INSERT, UPDATE |
| `users` | FOR SELECT `self_or_comember_read`: `cognito_sub = app.subject` or `id` in memberships of `app.organization_id`; FOR INSERT and FOR UPDATE `self_write`: `cognito_sub = app.subject` | SELECT, INSERT, UPDATE |
| `memberships` | `tenant_isolation`; FOR SELECT `own_memberships_read`: `app.organization_id` unset and `user_id = app.user_id` | SELECT, INSERT, UPDATE, DELETE |
| `invitations` | `tenant_isolation`; FOR SELECT `invitation_token_read`: `token_sha256 = app.invitation_token_sha256` | SELECT, INSERT, UPDATE, DELETE |

- Inside an org context only that org's memberships are visible, so the owner count and member
  list are correct even without an org filter.
- No recursion: `organizations` and `users` read `memberships`; `memberships` reads neither.
- Checked on Postgres 16 (2026-11-13): no context returns 0 everywhere; self-insert into another
  org and self role escalation fail; a co-member's `users` row cannot be updated; an unfiltered
  UPDATE in org A context touches only A; the token branch grants no UPDATE.

### Request flow

1. Verify the access token, take `sub`.
2. Set `app.subject`, select the user by `cognito_sub`. If no row, and always on `GET /v1/me` and
   before invitation acceptance: call userInfo with the access token, then
   `INSERT ... ON CONFLICT (cognito_sub) DO UPDATE` (parallel first calls yield one row).
   `email_verified` arrives as the string `"true"` or `"false"`; anything else counts as false.
3. Set `app.user_id`.
4. Org routes: check membership for `{org_id}`, then `enter_org_context(..., membership)`; not a
   member returns 404.
5. The handler runs in the same transaction, committed before the response (data-layer spec,
   Request transaction).

### Org creation

`POST /v1/orgs` generates the org id in Python (uuid4, never from the request), calls
`enter_org_context(..., org_creation)`, then inserts the organization, the owner membership and
`org.created` in one transaction. The context must exist before the INSERT: `tenant_isolation`
is the WITH CHECK, and INSERT ... RETURNING must pass the SELECT policy.

### Invitations

- Token: 32 random bytes (`secrets.token_urlsafe`), stored only as SHA-256, shown once.
- Link: `{ATESTA_WEB_BASE_URL}/invite#token=<token>`. The fragment never reaches a server, so no
  load balancer or access log records it. The invite page reads it, removes it with
  `history.replaceState`, keeps it in `sessionStorage` across the login redirect and sends it in
  the JSON body. The accept endpoint returns 400 `identity.token_in_query` if the request has any
  query string, checked by the route class before body parsing, authentication or userInfo.
- Accept: refresh the user from userInfo; set `app.invitation_token_sha256`, which makes only that
  row visible; check `email_verified` and an email match that ignores ASCII case only (Unicode
  case folding merges distinct mailboxes, e.g. `ß`/`ss`); invitation emails must be ASCII
  (422 otherwise), as Cognito and SES carry; then
  `enter_org_context(..., invitation)` and claim atomically:
  `UPDATE invitations SET accepted_at = now() WHERE token_sha256 = :h AND accepted_at IS NULL AND
  revoked_at IS NULL AND expires_at > now() RETURNING organization_id, role`. Zero rows: re-read
  to pick the error code. Then the inviter re-check and the already-member check, then INSERT the
  membership. A primary key conflict on that INSERT (concurrent accept of another invitation to the
  same org) also returns 409 `identity.already_member`, never 500. Any failure rolls back the claim.
- Revoke: `UPDATE ... SET revoked_at = now() WHERE id = :id AND accepted_at IS NULL AND
  revoked_at IS NULL`.
- Holding the 256-bit token is what justifies entering the org context before a membership
  exists. No SECURITY DEFINER functions.

### Concurrency

- Last owner: a role change or removal that targets an owner first runs
  `SELECT user_id FROM memberships WHERE organization_id = :org AND role = 'owner' FOR UPDATE`
  and proceeds only if it returns more than one row. Do not lock the `organizations` row: every
  tenant FK points at it, so that lock would block inserts across the org.
- Accept and revoke race safely through the conditional UPDATEs above.

### Configuration

| Variable | Example |
|---|---|
| `ATESTA_COGNITO_REGION` | `eu-south-2` |
| `ATESTA_COGNITO_USER_POOL_ID` | pool id |
| `ATESTA_COGNITO_APP_CLIENT_ID` | app client id |
| `ATESTA_COGNITO_DOMAIN` | managed login domain, for `/oauth2/userInfo` |
| `ATESTA_WEB_BASE_URL` | base of the accept link |

JWKS URL is derived from region and pool. JWKS cached in process; refetched on unknown `kid`, at
most once every 5 minutes. Token lifetimes: access and ID 30 min, refresh 12 h.

### Libraries

| Library | License | Use |
|---|---|---|
| PyJWT + cryptography | MIT, Apache-2.0/BSD | JWT and JWKS verification |
| httpx | BSD-3-Clause | userInfo and JWKS fetch, behind an `IdentityProvider` protocol so tests use a fake |

## Test plan

| Area | Cases |
|---|---|
| JWT | Local RSA key and fake JWKS. Valid token; expired; wrong `iss`; wrong `client_id`; ID token rejected; `scope` without `openid` rejected; `scope` with the admin scope rejected; unknown `kid`; `alg=none` and HS256 rejected; tampered signature |
| Provisioning | First `GET /v1/me` with a fake provider inserts one user and returns no memberships; two concurrent first calls yield one row; an email change at the provider shows on the next `GET /v1/me`; two users with the same email and different subs coexist |
| Org creation | `POST /v1/orgs` as `atesta_app` (RLS on) creates the org and an owner membership, writes one `org.created`; caller then gets 200 on the members route |
| Tenant isolation | 404 on org B routes; no org context: own memberships only; org A context: only A rows even without a WHERE; users visible to self and co-members only; from org A context, inserting a membership for org B fails, updating a co-member's `users` row affects 0, updating an invitation through the token branch affects 0 |
| Roles | member cannot invite (403); admin cannot change roles (403); admin invites as owner (403); owner invites as owner (201); last owner cannot be demoted or removed (409); two owners demoting each other concurrently leave exactly one owner |
| Invitations | DB never holds the raw token; expired, revoked and used tokens rejected; email mismatch and unverified email rejected; invitation from a removed or demoted inviter rejected; existing member gets 409 and keeps the role; sole owner accepting a member invitation stays owner; accept with a query string returns 400 with or without a body or token, and calls no userInfo; a verified `x@straße.de` or a Kelvin-sign address cannot accept an invitation for `x@strasse.de` or `kate@...`; ASCII case still matches; a non-ASCII invitation email is 422; revoke racing accept never leaves both timestamps set; a token reveals no other invitation |
| Audit | Each action writes exactly one event with the expected action and actor; no token in metadata |
| Logs | Logs captured on auth failures and on the successful provisioning and accept paths never contain a token |
| Cognito config | OpenTofu assertions for every pool, domain and client setting in the criteria (infra-dev spec) |
| Manual | In dev: sign-up, TOTP enrollment at the second sign-in, login with TOTP; pages in Spanish with `lang=es` and English with `lang=en`; managed-login access token gets `NotAuthorizedException` on `UpdateUserAttributes` |
