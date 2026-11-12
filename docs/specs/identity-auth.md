# Spec: Identity, Cognito auth with mandatory MFA

- Requirement ids: FR-01, FR-13, NFR-03, NFR-10
- Status: draft
- ADRs: ADR-007, ADR-008, ADR-012 (proposed)
- Build order: 2 of 3 (depends on tenant-data-layer)

## Problem

The security lead of an SME supplier signs up, creates the organization and invites colleagues.
Atesta stores the security posture of its customers, so a stolen password must not be enough to
read it: MFA is mandatory for every user, with no opt-out. Auth code is a liability for one
builder, so it is bought (Cognito, Architecture tab "Build vs buy").

## Acceptance criteria

- [ ] Cognito user pool in eu-south-2: MFA `ON` (required), TOTP only (no SMS, no email OTP),
      email as username, self sign-up with verified email, password min 12 characters, deletion
      protection on. Pool defined in OpenTofu (infra PR).
- [ ] Web signs in with Authorization Code + PKCE against Cognito managed login.
- [ ] API accepts Cognito access tokens only: RS256 signature against cached JWKS, exact `iss`,
      `token_use == "access"`, `client_id` equal to the configured app client, `exp` with 60 s
      leeway. Anything else returns 401 with an error code only.
- [ ] Cognito holds identity only (`sub`, email). Organizations, memberships and roles live in
      Postgres. No Cognito groups.
- [ ] Tables `organizations`, `users`, `memberships`, `invitations` with RLS (model below).
- [ ] Endpoints, all in the OpenAPI spec:

| Method and path | Allowed | Effect |
|---|---|---|
| `GET /v1/me` | Authenticated | Provision user on first call; return profile and memberships |
| `POST /v1/orgs` | Authenticated | Create org; caller becomes `owner` |
| `GET /v1/orgs/{org_id}/members` | member+ | List members |
| `PATCH /v1/orgs/{org_id}/members/{user_id}` | owner | Change role |
| `DELETE /v1/orgs/{org_id}/members/{user_id}` | admin+ (owner to remove an owner or admin) | Remove member |
| `POST /v1/orgs/{org_id}/invitations` | admin+ | Create invitation; return accept link once |
| `GET /v1/orgs/{org_id}/invitations` | admin+ | List pending invitations |
| `DELETE /v1/orgs/{org_id}/invitations/{id}` | admin+ | Revoke invitation |
| `POST /v1/invitations/accept` | Authenticated | Accept with token; verified email must match |

- [ ] Roles: `owner` > `admin` > `member`. An org always keeps at least one owner: demoting or
      removing the last owner returns 409.
- [ ] Org routes return 404 (not 403) when the caller is not a member: no org enumeration.
- [ ] `identity.api` exposes the FastAPI dependencies `require_member` and
      `require_role(Role.ADMIN)`. They are the only code that sets `app.organization_id`.
- [ ] Audit events: `org.created`, `invitation.created`, `invitation.revoked`,
      `invitation.accepted`, `membership.role_changed`, `membership.removed`.
- [ ] Errors return stable codes (`auth.invalid_token`, `identity.last_owner`, ...). ES and EN
      texts live in the web i18n files; the API holds no user-facing prose.
- [ ] Access tokens, invitation tokens and `Authorization` headers are never logged.

## Out of scope

- Invitation email via SES: for now the inviting admin gets a copy-once link. SES comes with the
  notifications spec.
- SSO SAML/OIDC (FR-22, v2), MSP console (FR-15, v2), read-only auditor role, passkeys.
- Self-service MFA recovery: support runbook (admin resets the user's MFA in Cognito).
- Account and org deletion (NFR-08, offboarding spec).
- Cognito threat protection (paid tier). Revisit before the first paying customer.
- Web login screens (web spec).

## Design notes

### Data model (identity module)

| Table | Columns | Scope | RLS policy |
|---|---|---|---|
| `organizations` | id, name, created_at, updated_at | `id` is the tenant key | `id = app.organization_id` or `id` in the caller's memberships |
| `users` | id, cognito_sub (unique), email (unique on `lower(email)`), email_verified, display_name, locale (`es`/`en`, default `es`), created_at | Global (ADR-012) | `cognito_sub = app.subject` or `id` in memberships of `app.organization_id` |
| `memberships` | organization_id, user_id, role, created_at; PK (organization_id, user_id) | Tenant | `organization_id = app.organization_id` or `user_id = app.user_id` |
| `invitations` | id, organization_id, email, role, token_sha256, invited_by, expires_at (7 days), accepted_at, revoked_at, created_at | Tenant | Standard, or `token_sha256 = app.invitation_token_sha256` |

- `users` is global because one person can belong to several orgs (consultants now, MSP
  technicians in v2). It holds identity only, no customer data.
- No policy recursion: `users` reads `memberships`; `memberships` never reads `users`.

### Request flow

1. Verify the access token, take `sub`.
2. Open the transaction, set `app.subject`, select the user by `cognito_sub`. First call: fetch
   email and `email_verified` with Cognito `GetUser` (authorized by the access token itself, no
   IAM credentials) and insert the user.
3. Set `app.user_id`.
4. Org routes: check membership for `{org_id}`, then set `app.organization_id`; not a member
   returns 404.
5. The handler runs in the same transaction; commit at the end of the request.

### Invitations

- Token: 32 random bytes (`secrets.token_urlsafe`), stored only as SHA-256, shown once in the
  create response.
- Accept: the API sets `app.invitation_token_sha256` from the presented token, which makes only
  that invitation row visible. It then checks: not expired, revoked or accepted; caller's
  `email_verified` is true; emails match case-insensitively. Then it sets `app.organization_id`
  to the invitation's org, inserts the membership with the invited role and marks the
  invitation accepted.
- Holding the 256-bit token is what justifies entering the org context before a membership
  exists. No SECURITY DEFINER functions.

### Configuration

| Variable | Example |
|---|---|
| `ATESTA_COGNITO_REGION` | `eu-south-2` |
| `ATESTA_COGNITO_USER_POOL_ID` | pool id |
| `ATESTA_COGNITO_APP_CLIENT_ID` | app client id |

JWKS URL is derived from region and pool. JWKS cached in process; refetched on unknown `kid`,
at most once every 5 minutes.

Token lifetimes (app client): access and ID 30 min, refresh 12 h. One working day, then a full
login with MFA.

### Libraries

| Library | License | Use |
|---|---|---|
| PyJWT + cryptography | MIT, Apache-2.0/BSD | JWT and JWKS verification |
| boto3 | Apache-2.0 | Cognito `GetUser`, behind a `CognitoClient` protocol so tests use a fake |

## Test plan

| Area | Cases |
|---|---|
| JWT | Local RSA key and fake JWKS. Valid token; expired; wrong `iss`; wrong `client_id`; ID token (`token_use=id`) rejected; unknown `kid`; `alg=none` and HS256 rejected; tampered signature |
| Tenant isolation | User in org A gets 404 on org B routes; memberships visible only for own user and current org; users visible only self and co-members |
| Roles | member cannot invite (403); admin cannot change roles (403); last owner cannot be demoted or removed (409) |
| Invitations | DB never holds the raw token; expired, revoked and used tokens rejected; email mismatch rejected; unverified email rejected; accept creates membership with the invited role; a token reveals no other invitation |
| Audit | Each action writes exactly one event with the expected action and actor; no token in metadata |
| Logs | Capture logs during auth failures; the token string never appears |
| Cognito config | OpenTofu assertion: `mfa_configuration = "ON"`, software token MFA enabled, no SMS configuration (infra PR) |
| Manual | Sign-up and login with TOTP in the dev pool (backlog "done when"); needs the dev AWS account |
