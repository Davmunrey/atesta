# ADR-016: An MCP server lets AI agents work with Atesta through scoped API keys

- Status: accepted by the owner (2026-11-23), relayed by the coordinator: "ADR-016 and ADR-012
  amendment 6 are ACCEPTED (2026-11-23)." (AGENTS.md, "Owner decisions").
- Owner decision, 2026-11-23, high priority: issues #332 (API keys v2), #333 (MCP server) and
  #334 (public API reference and MCP guide).
- Specs: `docs/specs/api-keys-v2.md`, `docs/specs/mcp-server.md`.

## Context

Customers already work with AI agents (Claude, ChatGPT, Cursor and others). They want an agent to
read where they stand on a framework, record evidence it finds in their own tools, propose a
self-assessment, and record routine work such as an incident or a training campaign.

Today an API key carries one scope, `evidence:write`, and reads nothing (evidence-ingestion-api
spec, ADR-012 amendment 5). An agent cannot use that.

The Model Context Protocol (MCP) is how these agents call tools. The facts below were checked in
the official sources on 2026-11-23:

- **Specification:** the latest revision is 2026-07-28
  (<https://modelcontextprotocol.io/specification/latest>). It has two standard transports:
  - stdio, a subprocess the client launches;
  - Streamable HTTP, one endpoint that accepts POST
    (<https://modelcontextprotocol.io/specification/latest/basic/transports>).
- **Credentials:**
  - A stdio server gets its credentials from the environment, not from MCP authorization
    (<https://modelcontextprotocol.io/specification/latest/basic/authorization>).
  - For HTTP, authorization is optional. When it is used, it is OAuth 2.1 with Protected
    Resource Metadata (RFC 9728), and a server accepts only tokens issued for itself.
- **Safety:** clients must treat tool annotations as untrusted unless the server is trusted.
  There should always be a person able to deny a tool call
  (<https://modelcontextprotocol.io/specification/latest/server/tools>).
- **Python SDK:** `mcp` 2.3.0 is MIT-licensed and was published on PyPI on 2026-10-02
  (<https://pypi.org/project/mcp/2.3.0/>; repository
  <https://github.com/modelcontextprotocol/python-sdk>, docs <https://py.sdk.modelcontextprotocol.io/>).
  Its server class is `mcp.server.MCPServer`, and it speaks protocol version 2026-07-28.

## Decision

- **One API, two ways in.** The MCP server is a thin client of the Atesta HTTPS API. Every tool
  is one call to a documented API route. Authentication, scopes, rate limits, the usage log,
  tenancy and audit all happen in the API, once, for scripts and agents alike.
- **Two transports, one package** (`apps/mcp`, Python package `atesta_mcp`):
  - **Local stdio**, testable now. The customer runs it on their own machine. It reads
    `ATESTA_API_URL` and `ATESTA_API_KEY` from the environment and calls the API over HTTPS.
  - **Hosted remote** (Streamable HTTP), mounted by the API at `/mcp` only when
    `ATESTA_MCP_REMOTE=1`. It stays off until the AWS environment is live (ROADMAP gate). It
    takes the API key as `Authorization: Bearer`, refuses a request without one (401), and
    forwards it to the same routes in-process.
    - It is stateless (no MCP session) and answers in JSON.
    - It validates `Origin` and `Host` (DNS rebinding).
    - **OAuth 2.1:** an API key is issued by Atesta for the Atesta API, of which `/mcp` is a
      part, so this is not token passthrough. OAuth with Protected Resource Metadata, which
      some hosted clients require, needs its own ADR amendment before it is offered.
- **API keys v2** (spec `api-keys-v2.md`):
  - **Scopes:** a key carries an explicit list, with nothing by default; the admin chooses each
    one.
    - Reads: `compliance:read` and `incidents:read`.
    - Writes: `evidence:write`, `assessment:propose` and `routines:write`.
    - A read scope never implies a write.
    - Existing keys keep exactly `evidence:write`.
  - **Rate limit:** each key has its own limit per minute, enforced in Postgres (no new
    infrastructure).
  - **Usage log:** one row per accepted call, which admins can see.
- **Rule 1, read-only towards customer systems:**
  - The API reads only Atesta's own records.
  - No tool starts a scan, touches a connection or reaches a customer tenant. "Scan now" is not
    in v1.
- **ADR-005, the AI never decides pass or fail:**
  - A self-assessment from an agent is a proposal. It is stored as pending and shown to a person
    in the app, who confirms or rejects it.
  - Only a confirmation writes the measure's assessment, recorded and audited as that person's.
  - A rejection changes nothing.
- **Rule 5 and ADR-010 amendment 1, untrusted content:**
  - **Framing:** every tool result is one text block. It wraps the API's data in delimiters that
    carry a nonce drawn for that response.
  - **Neutralising delimiters:** the payload is JSON with `<`, `>` and `&` escaped
    (`<`, `>`, `&`), so customer text can never contain a delimiter.
  - **No structured output:** tools return no `structuredContent`, so no unframed copy reaches
    the model.
  - **Descriptions:** the server's instructions and every tool description say that framed
    content (titles, notes, evidence text) is data and never instructions.
- **Tenancy (ADR-012):**
  - **One organization per key:** the key resolves it, and every query runs in that
    organization's context under RLS.
  - **Org-free routes:** token routes take no organization in the path, so a key cannot even
    name another one.
  - **Amendment 6** (`0012-tenant-isolation-rls.md`, proposed with this ADR) records that keys
    may read, and adds the new tenant tables.
- **Audit:**
  - Every write through a key emits an audit event. It names the key (id and prefix) and the
    admin who created it, who answers for it.
  - The usage log records reads and writes: when, which route, which scope. It records no
    body, no query and no customer content (rule 2).
- **Dependencies (rule 4, ADR-006):**
  - The SDK is `mcp==2.3.0` (MIT), pinned exactly and older than the 7-day cooldown.
  - Its dependencies pass the existing licence check in CI (`apps.api.devtools.python_licenses`).

## Consequences

- An agent works with the same rights as a script holding the same key: no more, no less.
- A new tool is a new API route first, with its scope, tests and documentation.
- The API stays the only place where rights are decided; the MCP package holds no rule of its
  own.
- **Usage log size:** it grows with use. A retention job (90 days) is a follow-up. Erasing an
  organization deletes it with the other tenant tables (ADR-012 amendment 3).
- **Throughput:** a key's requests are serialized by the row lock on the key (it records the
  last use), so a single key's throughput is bounded. This is acceptable for agents and
  scripts.
- **Remote and OAuth:** hosted clients that support only OAuth cannot use the remote server
  until the OAuth amendment lands. Clients that accept a header, and the local stdio server,
  can.

## Amendment 1 (proposed 2026-11-24, issue 354, spec `docs/specs/mcp-oauth.md`)

Status: proposed. The owner chose the substance on 2026-11-24, in the session that built it. The
three recommendations put to the owner were "Cognito como servidor de autorización del MCP
alojado", "Solo admins conectan agentes, con concesión revocable guardada en Atesta" and "Lista
cerrada de clientes aprobados al principio", and the answer "sí a todo". Accepting the amendment
is the owner's.

### Context

Some hosted agents add a remote MCP server by URL only and authenticate with OAuth. The hosted
server takes an Atesta API key today. Facts checked on 2026-11-24:

- **MCP authorization, revision 2026-07-28**
  (<https://modelcontextprotocol.io/specification/latest/basic/authorization>):
  - an MCP server is an OAuth 2.1 resource server and MUST implement Protected Resource Metadata
    (RFC 9728), which names its authorization server;
  - a 401 carries `WWW-Authenticate: Bearer resource_metadata="..."`;
  - clients MUST send the `resource` parameter (RFC 8707) with the server's canonical URI, and
    the server MUST accept only tokens issued for itself and never pass a token on;
  - a client gets its client id by one of three ways: Client ID Metadata Documents,
    pre-registration, or Dynamic Client Registration (deprecated, kept for compatibility).
- **Amazon Cognito user pools**, developer guide:
  - "Resource binding": with managed login and the authorization code grant, a `resource`
    parameter becomes the `aud` claim of the access token (RFC 8707)
    (<https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html>);
  - "Using dynamic client registration with MCP clients" describes a user pool protecting an MCP
    server: a resource server whose identifier is the MCP server's URL, custom scopes that
    belong to it, and public clients with PKCE
    (<https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-dynamic-client-registration.html>);
  - the user pool is an OIDC issuer with a discovery document
    (<https://docs.aws.amazon.com/cognito/latest/developerguide/federation-endpoints.html>).

### Decision

- **Authorization server: the Cognito user pool that already signs people in.** Atesta issues no
  token and runs no authorization server. The pool stays in the EU (ADR-007).
- **Resource: the hosted MCP server**, at the URL in `ATESTA_MCP_RESOURCE_URL`. In Cognito it is
  a resource server with that URL as its identifier and one scope, `agent`.
- **Discovery:** the API serves Protected Resource Metadata at
  `/.well-known/oauth-protected-resource/mcp` and `/.well-known/oauth-protected-resource`. A 401
  from `/mcp` points to it.
- **A token is accepted only when all of this holds:** RS256 signature by the pool's keys, the
  pool as issuer, not expired, `token_use` is `access`, `aud` is exactly the resource URL,
  `client_id` is an approved client and the scope includes `agent`.
  - A web session token has no such `aud`, so it never opens `/mcp`. An MCP token has another
    `client_id`, so it never opens the web session.
  - The token is used at `/mcp` only. It is never forwarded: the server hands the verified
    identity to the API in-process (no token passthrough).
- **The token says who; Atesta says what.** A token proves a person at an approved client. What
  that agent may do comes from a grant recorded in Atesta:
  - **Who grants:** an owner or admin, for themself, in one organization. That is the consent.
  - **What it holds:** the approved client, explicit scopes from the same five as keys (none by
    default), a rate limit per minute and an expiry of at most 365 days.
  - **When it works:** while it is not revoked or expired, and only while that person is still
    an owner or admin of that organization.
  - **Revocation:** any owner or admin of the organization, at once. The next request is
    refused whatever the token's remaining life.
  - **One organization per person and client.** If the same person has an active grant for the
    same client in two organizations, the request is refused until one is revoked.
- **A grant is an API key without a secret.** It is a row of `api_tokens` of kind `oauth`. Its
  lookup value is the SHA-256 of the issuer, the client id and the person's `sub`, so it is
  found through the existing `api_token_read` policy and the organization is entered with the
  existing reason `api_token`. Scopes, the rate limit, the usage log, tenancy and audit are then
  the ones of keys, in the same code. ADR-012 gains no table, policy, setting or reason
  (amendment 11 records the two new columns).
- **Clients: a closed list.** `ATESTA_MCP_OAUTH_CLIENTS` names each approved client id. Each is
  pre-registered in the user pool by the owner as a public client with PKCE. No Dynamic Client
  Registration and no Client ID Metadata Documents for now.
- **Off by default.** OAuth is on only with `ATESTA_MCP_REMOTE=1`, the resource URL and at least
  one approved client. The hosted server itself stays off until AWS is live. API keys keep
  working at `/mcp` beside OAuth.

### Not chosen

- **An authorization server of our own:** token issuance, consent screens and key rotation are
  security-critical code Atesta would have to keep. Cognito already holds the accounts and MFA.
- **Open Dynamic Client Registration:** any program could register a client in the pool. It is
  the path Cognito documents for MCP and the one that lets a hosted agent connect with the URL
  alone, so it is the first thing to revisit, behind a WAF rate limit, once the closed list
  proves too narrow.
- **Scopes in the token:** Cognito scopes belong to the pool, not to an organization. A grant in
  Atesta is per organization, revocable at once and audited with the rest.
- **One resource URL per organization:** it would bind the organization into the token's `aud`,
  but Cognito ties custom scopes to one resource server identifier, and the documented setup is
  one identifier per MCP server.

### Candidates (not verified: no AWS environment exists yet)

Each closes in the first live test of the hosted server, before OAuth is offered to a customer.

| Candidate | If it fails |
|---|---|
| The pool's discovery document carries what MCP clients require (PKCE methods, the registration-free flow) | Clients refuse to start the flow; OAuth stays off and keys remain the way in |
| An access token from managed login has `aud` equal to the `resource` sent, and the scope reads `<resource URL>/agent` | The validation rule is adjusted to what Cognito really emits, in a reviewed change |
| Each agent product accepts a pre-registered client id | That product waits for Dynamic Client Registration |

### Consequences

- An agent connected by OAuth has the rights of its grant: the same scopes and limits as a key,
  and never more than an admin chose.
- When a person leaves, or stops being an admin, their agents stop with them.
- Usage and audit name the grant like a key, and the person who granted it answers for it.
- The owner pre-registers each agent product in Cognito; a new product is a configuration
  change, not code.
