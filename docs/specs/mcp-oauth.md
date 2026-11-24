# Spec: OAuth 2.1 for the hosted MCP server

- Issue: #354. Builds on `mcp-server.md` and `api-keys-v2.md`.
- ADRs: ADR-016 amendment 1 and ADR-012 amendment 11 (both proposed), ADR-007, ADR-005.
- Status: draft. The owner chose the three decisions on 2026-11-24 ("sí a todo"). Off by
  default: nothing here runs until the hosted server is turned on in AWS.

## Problem

The hosted MCP server takes an Atesta API key. Some hosted agents connect to a remote server by
URL only and sign the person in with OAuth. They cannot use Atesta today.

## Decisions (owner, 2026-11-24)

1. The authorization server is the Cognito user pool that signs people in.
2. Only owners and admins connect agents, through a revocable grant stored in Atesta.
3. Clients come from a closed list of approved ones.

## Acceptance criteria

**Configuration**
- [ ] OAuth is on only when `ATESTA_MCP_REMOTE=1`, `ATESTA_MCP_RESOURCE_URL` (https, no query,
  no fragment, no trailing slash) and `ATESTA_MCP_OAUTH_CLIENTS` are set. The clients value is
  a comma-separated list of `client_id=Name`.
- [ ] A malformed value stops the API from starting. Unset, everything below answers as today:
  the metadata routes are 404 and only API keys open `/mcp`.

**Discovery**
- [ ] `GET /.well-known/oauth-protected-resource/mcp` and `GET
  /.well-known/oauth-protected-resource` return the same Protected Resource Metadata
  (RFC 9728): `resource` (the URL), `authorization_servers` (the pool's issuer),
  `scopes_supported` (`<resource>/agent`), `bearer_methods_supported` (`header`) and
  `resource_name`. No session is needed and nothing tenant-specific is read.
- [ ] A 401 from `/mcp` carries `WWW-Authenticate: Bearer resource_metadata="<the first URL>",
  scope="<resource>/agent"`.

**Token validation** (before any MCP handling)
- [ ] Accepted only when: RS256 by the pool's keys, the pool as issuer, not expired,
  `token_use` is `access`, `aud` is exactly the resource URL, `client_id` is in the list and
  the scope includes `<resource>/agent`. Anything else is 401, with the same body as a bad key.
- [ ] A web session token is refused at `/mcp`. An MCP token is refused as a web session.
- [ ] The token is never sent to an API route: the verified identity travels in-process only,
  where no request from outside can set it. An OAuth token sent straight to `/api/v1/...` is
  401.
- [ ] A token is never logged.

**Grants**
- [ ] `GET /api/v1/orgs/{org_id}/agent-clients` lists the approved clients (id and name) for
  owners and admins; empty when OAuth is off.
- [ ] `POST /api/v1/orgs/{org_id}/agent-grants` records a grant for the caller: `client_id`
  (must be approved), `scopes` (at least one, from the five of keys), `rate_limit_per_minute`
  (1 to 600, default 60) and `expires_in_days` (1 to 365). Owners and admins only.
  - The same person cannot hold two active grants for one client in one organization (409
    `identity.agent_grant_exists`).
  - With OAuth off, the route answers 409 `identity.agent_oauth_off`.
- [ ] Grants appear in the existing key list with `kind: "oauth"` and the client's name, and
  are revoked through the existing key route, by any owner or admin. Their usage shows in the
  existing usage route.
- [ ] `agent_grant.created` and `agent_grant.revoked` are audited with the client id, scopes
  and limit, never a token.

**Using a grant**
- [ ] A verified token resolves to the person's active grant for that client. None, a revoked
  or an expired one: 401.
- [ ] The person must still be an owner or admin of the grant's organization at that moment;
  otherwise 401.
- [ ] Two active grants of the same person and client in different organizations: 401, until
  one is revoked.
- [ ] From there the request is a key's request: scopes (403 names the scope), the rate limit
  (429 with `Retry-After`), one usage row, tenancy by the grant's organization, and audit
  events that name the grant and the person.

**Languages:** every new error text exists in Spanish and English.

## Out of scope

- The console screen to grant and revoke (issue 459). The API routes above are enough
  to test the whole flow.
- Dynamic Client Registration and Client ID Metadata Documents (ADR-016 amendment 1, Not
  chosen).
- Registering the resource server and the clients in Cognito: owner steps in AWS, added to the
  deploy runbook when the hosted server is turned on.
- The edge: CloudFront sends only `/api/*` and `/auth/*` to the API today. `/mcp` and
  `/.well-known/oauth-protected-resource*` need their own behaviours before the hosted server
  can be reached; that belongs to turning it on.
- Step-up authorization: scopes come from the grant, not from the token.

## Test plan

- **Unit:** settings parsing; the metadata document; the token rules, one test per refusal
  (wrong audience, unknown client, missing scope, id token, expired, wrong issuer, bad
  signature), with tokens signed by a throwaway key served from a fake JWKS.
- **Postgres:** create, list, revoke; a member and an auditor cannot grant; duplicate grant 409;
  a grant resolves to its organization and scopes; revoked, expired, demoted admin and
  two-organization cases are 401; scope 403, rate limit 429 and the usage row; audit events.
- **Hosted server:** with OAuth on, `/mcp` without credentials gives the challenge header; a
  valid token lists tools and calls a read tool through the grant; an API key still works; an
  OAuth token sent to `/api/v1/key` directly is 401.
- **Contract:** the new routes are in the OpenAPI contract; the route sweep knows the two
  public metadata routes.
