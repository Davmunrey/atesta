# Spec: public API reference and MCP guide

- Issue: #334. Builds on `api-keys-v2.md` and `mcp-server.md` (ADR-016, proposed). Follows
  `landing-legal.md` (public pages, L3 honesty) and `claims-honesty.md`.
- Status: draft

## Problem

Customers and integrators who want to connect their tools or an AI agent to Atesta have no
public page that says which routes a key may call, what each permission opens, or how to
connect an agent. They ask support, or guess.

## Acceptance criteria

**API reference (`/docs/api`)**
- [ ] **Built from the OpenAPI contract** the API exports (`src/lib/api/openapi.json`), so it
  cannot drift.
  - It lists every operation that an API key may call (tag `api-keys`), grouped by the
    permission it needs.
  - The permission comes from the contract (`x-atesta-scope`), which the API sets from each
    route's `require_scope`.
- [ ] **Each operation shows:**
  - its method and path;
  - a description in the reader's language;
  - its permission;
  - its request body fields, with type, whether required, and length or value limits.
- [ ] **The page explains:**
  - the `Authorization: Bearer` header;
  - that a query string is refused;
  - the rate limit and `Retry-After`;
  - the error body (`code`, `message`) and the codes specific to keys.
- [ ] **No overclaiming:** the page says what the API records and reads. It never says that
  Atesta certifies or that a result means compliance (claims-honesty).

**MCP guide (`/docs/mcp`)**
- [ ] **What an agent can do:** every tool the server offers, grouped as read or write, each
  with its permission. A test keeps the list equal to the server's tools.
- [ ] **The safety model, in plain words:**
  - the key has only the permissions the admin chose;
  - the agent never decides whether a measure passes, and a person confirms proposals;
  - results are framed as data;
  - nothing touches the organization's own systems.
- [ ] **Local setup:**
  - create a key in Integraciones;
  - install `atesta-mcp`, which is not publicly distributed yet: only pilot customers get it,
    from Atesta (owner decision, 2026-11-23);
  - a client configuration using `command`, `args` and `env` under `mcpServers`, as documented at
    <https://modelcontextprotocol.io/docs/develop/connect-local-servers> (checked 2026-11-23),
    with the key only in `env`.
- [ ] **Hosted server:** marked as not available yet (ADR-016). Once enabled, it takes the key
  as `Authorization: Bearer`. Clients that connect only with OAuth cannot use it yet.
- [ ] **Links:** both pages link to each other. Integraciones links to both.

**Both**
- [ ] **Language:** every word in ES and EN from the message files. Code, paths, field names
  and scopes stay as they are.
- [ ] **Shared design:** public layout (header, footer, light only) and the policy page
  structure already used by Cookies. No new styles.

## Out of scope

- An interactive "try it" console, and the session-authenticated routes the web app uses.
- Publishing the `atesta-mcp` package: it is internal for now (owner decision, 2026-11-23).

## Design notes

- **Contract:** the API adds `x-atesta-scope` to each key route in OpenAPI, and the ingestion
  route joins the tag `api-keys`.
- **Web:** `lib/api-reference.ts` reads the contract; the pages are static client components
  under `app/(public)/docs/`.

## Test plan

- **Unit:**
  - every `api-keys` operation in the contract appears on the page, with its permission and an
    ES and EN description;
  - the MCP guide's tool list equals the tools defined in `apps/mcp/src/atesta_mcp/server.py`;
  - ES and EN render.
- **Python:** every key route in OpenAPI carries the tag `api-keys`. Every one except
  `GET /api/v1/key` carries its scope.
