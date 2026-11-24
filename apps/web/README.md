# apps/web

Next.js static export (App Router, TypeScript strict, Tailwind CSS). Spec:
`docs/specs/web-shell.md`. No Node server in production: CloudFront serves `out/` and routes
`/api/*` and `/auth/*` to the API.

```bash
pnpm install          # pnpm 10, minimumReleaseAge 7 days (root pnpm-workspace.yaml)
pnpm dev              # http://localhost:3000; /api and /auth rewritten to ATESTA_API_URL (default :8000)
pnpm test             # vitest unit tests
pnpm typecheck && pnpm lint
pnpm build            # static export to out/; inline scripts move to files, CSP to csp-policy.json
pnpm check-licenses   # fails on GPL, AGPL or undeclared licenses
```

## Public release gates

Before uploading a public release, run `pnpm check-legal && pnpm check-landing`.
These commands are separate from the build and CI: drafts may build and merge while public
release stays blocked. They currently fail because the landing content is not implemented.

- `check-legal` requires `src/content/legal-entity.ts` to export `legalEntity` with non-blank
  string fields `name`, `nif`, `address`, `registry` and `email`.
- `check-landing` requires `src/content/landing-fixture.json` with `origin: "recorded"`, a UUID
  `scan_id` and a real `scan_date` in `YYYY-MM-DD` form.

Each command accepts one optional file path for isolated checks. Missing or malformed files
block release; diagnostics name fields without printing their values. These checks establish
metadata completeness, not the authenticity of a scan or legal approval. The lawyer review and
recorded-product requirement in `docs/specs/landing-legal.md` remain release requirements.
The future deploy job must run both gates before publishing; there is no deploy job yet.

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
- Design tokens: `packages/ui/src/styles/tokens.css` is the only file with color, font or radius
  values (tested).
- Shared UI (ADR-017, `docs/specs/ui-package.md`): tokens, fonts, base styles, page frame, badges,
  icons, the error message, the locale switcher, `format`, the API error envelope and the CSP
  script come from `@atesta/ui` (`packages/ui`). A component another app could need goes there,
  never into a copy here (tested).
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
