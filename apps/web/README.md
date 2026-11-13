# apps/web

Next.js static export (App Router, TypeScript strict, Tailwind CSS). Spec:
`docs/specs/web-shell.md`. No Node server in production: CloudFront serves `out/` and routes
`/api/*` and `/auth/*` to the API.

```bash
pnpm install          # pnpm 10, minimumReleaseAge 7 days (pnpm-workspace.yaml)
pnpm dev              # http://localhost:3000; /api and /auth rewritten to ATESTA_API_URL (default :8000)
pnpm test             # vitest unit tests
pnpm typecheck && pnpm lint
pnpm build            # static export to out/, then CSP hashes to csp-policy.json
pnpm check-licenses   # fails on GPL, AGPL or undeclared licenses
```

## API contract

`src/lib/api/openapi.json` and `error-codes.json` are written by the API's contract test;
`schema.d.ts` is generated from them. Tests on both sides fail when either is stale. After an
API change:

```bash
ATESTA_UPDATE_API_CONTRACT=1 uv run pytest apps/api/tests/test_api_contract.py   # repo root
pnpm gen:api                                                                       # apps/web
```

Every error code needs a message under `errors.<code>` in both message files (tested); an
unknown code shows `errors.unknown`, never the raw code.

- Spanish first: `messages/es.json`, then `messages/en.json`, same keys (tested). The choice
  lives in the `atesta_locale` cookie; the export is prerendered in Spanish.
- Design tokens: `src/styles/tokens.css` is the only file with color, font or radius values
  (tested). Neutral until the owner picks a brand identity.
- Frontend skills: `.claude/skills/frontend-design` and `.claude/skills/react-best-practices`.

## e2e

Playwright against the static export, the real API and Postgres, and the fake Cognito. Needs a
Postgres superuser URL; it recreates the database `atesta_e2e`.

```bash
pnpm build
ATESTA_E2E_ADMIN_URL=postgresql+psycopg://postgres@localhost:5432/postgres pnpm exec playwright test
```

`tests/e2e/serve.mjs` stands in for CloudFront: it serves `out/`, routes `/api` and `/auth` to the
API on :8000, and adds the security headers, including the CSP from `csp-policy.json`.
