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
