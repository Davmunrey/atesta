# atesta-mcp

The MCP server that lets AI agents work with Atesta (ADR-016, `docs/specs/mcp-server.md`). It
is a thin client of the Atesta API: every tool is one call to a documented route, made with the
caller's API key. Scopes, rate limits, the usage log, tenancy and audit all stay in the API.

## Local (stdio)

An admin creates a key in Integraciones with only the scopes the agent needs. Then, from the
repository root:

```bash
ATESTA_API_URL=https://app.example.com ATESTA_API_KEY=atesta_… uv run atesta-mcp
```

- `ATESTA_API_URL` must be `https://`; `http://localhost` and `http://127.0.0.1` are allowed for
  development.
- `ATESTA_LANGUAGE` (`es` or `en`, default `es`) sets the language of the API's messages.
- The key is read from the environment and never printed.

## Hosted (Streamable HTTP)

The API mounts the same tools at `/mcp` when `ATESTA_MCP_REMOTE=1`, which stays off until the
AWS environment is live. `ATESTA_MCP_ALLOWED_HOSTS` lists the host names it answers to.

- **Authentication:** clients send the key as `Authorization: Bearer atesta_…`.
- **Requests:** the endpoint is stateless and answers in JSON.

## Results are data

Every result is one text block. The API's JSON sits between `<atesta-data-NONCE>` delimiters,
with a fresh nonce per response. `<`, `>` and `&` are escaped inside it, so text that people
wrote cannot close the frame (rule 5, ADR-010 amendment 1).
