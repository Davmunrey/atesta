# Spec: API keys v2 (scopes, read-only keys, rate limits, usage log)

- Issues: the decision is recorded in #338. Extends `evidence-ingestion-api.md`; decided in
  ADR-016 and ADR-012 amendment 6 (both accepted 2026-11-23). Delivered in three parts:
  - #332: scopes, rate limits, the usage log and the admin UI;
  - #341: the read routes for keys;
  - #333: the write routes for keys, with the MCP server.
- Status: draft

## Problem

An API key today carries one scope, `evidence:write`, and reads nothing. An AI agent or an
integration that should answer "where do we stand on the ENS?" cannot use it.

A key that could do everything would break least privilege. Today an admin also cannot see what
a key did, and nothing stops a runaway script from hammering the API.

## Acceptance criteria

**Scopes**
- [ ] **A key carries an explicit, non-empty set of scopes.** There is no default: the admin
  picks each one when creating the key. The scopes are:

  | Scope | Kind | Opens |
  | --- | --- | --- |
  | `compliance:read` | read | frameworks, measures and official texts, gaps, due items |
  | `incidents:read` | read | incidents and their reporting clocks |
  | `evidence:write` | write | `POST /api/v1/ingest/evidence` |
  | `assessment:propose` | write | self-assessment proposals (`mcp-server.md`) |
  | `routines:write` | write | incidents and their updates, training campaigns, access reviews |

- [ ] **A read scope never implies a write**, and a write scope never implies a read.
- [ ] **A read-only key** is one with only read scopes; the list labels it so.
- [ ] **Existing keys keep exactly `["evidence:write"]`.**
- [ ] **A route needing a scope the key lacks:** 403 `identity.api_token_scope`, naming the
  missing scope in the body.
- [ ] **Unknown scopes:** an unknown, repeated or empty scope list is 422 `request.invalid`.

**Rate limit**
- [ ] **Each key has its own limit,** from 1 to 600 requests per minute (default 60), chosen
  when it is created.
- [ ] **Counting:** the limit counts the key's accepted requests in the last 60 seconds,
  stored in Postgres. No new infrastructure.
- [ ] **Over the limit:** 429 with code `identity.api_token_rate_limited` and a `Retry-After`
  header (whole seconds, at least 1). The body carries the message in Spanish or English,
  following `Accept-Language` (Spanish by default).
- [ ] **A refused request** (401, 403, 429) is not counted.

**Usage log**
- [ ] **One row per accepted request:** time, method, route template (for example
  `/api/v1/incidents/{incident_id}`) and the scope used.
- [ ] **Never logged:** no body, no query string, no identifiers from the path and no customer
  content (rule 2).
- [ ] **Admins see it:** `GET /api/v1/orgs/{org_id}/api-tokens/{token_id}/usage` returns the
  last 100 rows, newest first, and the count over the last 24 hours. Admins only; others get
  403, and non-members 404.

**Read routes for keys** (prefix `/api/v1`, no organization in the path, no query string)
- [ ] `GET /api/v1/key`: the key's own name, prefix, scopes, limit and expiry. It needs no
  scope, but it is logged and counted.
- [ ] **`compliance:read` opens:**
  - `GET /api/v1/frameworks`: the frameworks in the organization's plan, with the readiness
    counts.
  - `GET /api/v1/frameworks/{framework_key}/measures`: each measure with its code, titles,
    proposed applicability, latest assessment (the organization's text is framed in MCP), owner
    due date and pending proposal, if any.
  - `GET /api/v1/frameworks/{framework_key}/measures/{code}`: the official text and its
    citation (source URL, section, source SHA-256, catalog version), the expected evidence with
    its guide references, and the common controls it maps to.
  - `GET /api/v1/gaps`: per framework, the measures that are not assessed, not implemented or
    partially implemented, with their owner's due date.
  - `GET /api/v1/due`: what falls due, the same items as the app's routines list.
- [ ] **`incidents:read` opens:** `GET /api/v1/incidents` (open incidents with their clocks) and
  `GET /api/v1/incidents/{incident_id}`.
- [ ] **The plan still decides:** a framework outside the plan is 403 `billing.plan_limit`, as
  in the app, and an unknown one is 404.

**Write routes for keys**
- [ ] **`routines:write` opens:**
  - `POST /api/v1/incidents` and `POST /api/v1/incidents/{incident_id}/updates`, with the same
    bodies and rules as the app's routes;
  - `POST /api/v1/training-campaigns`, which returns the campaign and its link once;
  - `POST /api/v1/access-reviews`, which creates a review with its accounts. Deciding and
    closing a review stay with a person in the app.
- [ ] **Authorship:** the author of what a key writes is the admin who created the key, as for
  ingestion.
- [ ] **Audit:** every write emits the route's usual audit event, plus `via: "api_token"`, the
  key's id and its prefix in the metadata.

**Admins (web, Integraciones)**
- [ ] **Create:** the form asks for a name, an expiry, the scopes (checkboxes grouped as
  "Leer" and "Escribir", none ticked) and the limit per minute.
  - The read-only preset ticks the two read scopes only.
  - The key is shown once, as today.
- [ ] **List:** each key shows its scopes and limit, and "Solo lectura" when it has only read
  scopes.
- [ ] **Usage:** each key opens its usage log: time, method, route and scope, with the 24-hour
  count.
- [ ] **Language:** strings are in ES and EN, with ICU plurals for counts.

## Out of scope

- **Changing a key's scopes or limit after creation:** revoke it and create a new one, so a
  key's rights never grow silently.
- **Scan control** ("scan now"), connections, members, billing: no scope opens them (rule 1;
  owner decision 2026-11-23).
- **Retention of the usage log:** deleting rows after 90 days is a follow-up job. Erasing an
  organization deletes them already.
- **OAuth for the hosted MCP server** (ADR-016).

## Design notes

**Data (migration 0025)**
- `api_tokens`:
  - gains `scopes text[]`, backfilled to `{evidence:write}`, CHECK non-empty and within the
    list above;
  - gains `rate_limit_per_minute int`, CHECK 1 to 600, default 60;
  - the old `scope` column and its CHECK are dropped.
- `api_token_usage` (tenant, RLS, append-only): `organization_id`, `id`, `token_id` (composite
  FK to `api_tokens`), `at`, `method`, `route`, `scope`. Indexed on
  `(organization_id, token_id, at)`, which the rate count uses.

**Request flow**
- `require_api_token` resolves the key as today.
- The new `require_scope(scope)` dependency then:
  1. checks the scope (403);
  2. counts the last 60 seconds under the key's row lock, which the last-use update already
     takes, so concurrent requests of one key cannot both slip under the limit (429);
  3. inserts the usage row.
- A refused request raises, so its transaction, and any row it wrote, rolls back.

**Errors and modules**
- **Messages:** the token routes' 401, 403 and 429 bodies carry `message` from
  `atesta_api/messages/{es,en}.json` (`api_token.*`).
- **Where the routes live:**
  - Compliance owns the read routes and the routine write routes, in its own
    `token_routes.py`. It reuses the functions behind the app's routes, so the answers match.
  - Identity owns keys, scopes, the rate limit and the usage log.
- **Contract:** `GET /api/v1/key` and the token routes appear in the OpenAPI contract with
  bearer security.

## Test plan

**Postgres**
- **Scopes:**
  - each token route refuses a key without its scope (403, the code names the scope);
  - a read-only key cannot write anywhere;
  - existing keys keep `evidence:write` (migration test).
- **Tenancy sweep:** every token route, called with a key of organization A, never returns or
  writes a row of organization B. The test seeds B with incidents, assessments and routines,
  and compares row counts before and after.
- **Rate limit:** the (n+1)th request in a minute gets 429 with `Retry-After`. Refused requests
  are not counted. ES and EN messages.
- **Usage log:**
  - the rows hold the route template and scope only, never a body or an id from the path;
  - an admin sees them, a contributor gets 403, and another organization gets 404.
- **Audit:** every token write emits its event with `via`, the key's id and its prefix.

**Elsewhere**
- **Route sweep:** the token routes are the reviewed public list, and every one refuses a
  missing key with 401.
- **Web unit:** the scopes and their groups, the read-only label, the usage panel, ES and EN.
