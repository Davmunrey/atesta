# Spec: Web shell, sign-in and organization screens

- Requirement ids: FR-01, NFR-03, NFR-10
- Status: draft
- ADRs: ADR-001, ADR-007, ADR-012, ADR-013
- Build order: after identity-auth (its endpoints are the only backend this needs)
- Revised 2026-11-13: BFF moved into the API so the web stays a static export (Infrastructure tab)
- Revised 2026-11-13: CSP is one header with every page's script hashes; `pnpm build` fails if it
  exceeds CloudFront's 1,783-character limit (AWS CloudFront quotas, checked 2026-11-13). e2e
  serves the export through a CloudFront stand-in (`tests/e2e/serve.mjs`) that adds the headers.

## Problem

The identity backend works but nobody can use it: `apps/web` is empty. The security lead of an
SME must sign up with MFA, create the organization, invite colleagues and manage roles from a
browser, in Spanish first. The shell built here (auth, layout, API client, i18n) is what every
later screen (connections, scores, evidence) plugs into.

## Acceptance criteria

- [ ] Next.js (App Router, `output: "export"`) + TypeScript strict in `apps/web`, shadcn/ui
      components copied into the repo, Tailwind CSS, TanStack Query (Architecture tab). Served as
      static files from S3 + CloudFront (Infrastructure tab); no Node server in production.
      CloudFront routes `/api/*` and `/auth/*` to the ALB, so web and API share one origin.
      Node 22 LTS pinned in `.nvmrc`;
      pnpm with `minimumReleaseAge: 10080` (minutes, 7 days; same cooldown as uv; pnpm docs,
      dependency-resolution settings, checked 2026-11-13).
- [ ] Backend for frontend (BFF) in the API (identity module, FastAPI): it runs Authorization
      Code + PKCE against Cognito managed login and keeps the tokens. The browser never sees an
      access, ID or refresh token: they live in AES-GCM encrypted, `HttpOnly`, `Secure`,
      `SameSite=Lax`, `Path=/` cookies on the shared origin, one per token, each under 4 KB.
      The API's auth dependency accepts this session cookie (browser) or a bearer token
      (tests, future CLI); both go through the same token verifier.
- [ ] `/auth/login` creates `state`, `nonce` and the PKCE verifier in a short-lived
      `HttpOnly` cookie and redirects to `/oauth2/authorize` with `lang=es` (default) or `lang=en`
      and scopes `openid email`. `/auth/callback` rejects a missing or mismatched `state`,
      exchanges the code, sets the session cookies and redirects to `/app`. `/auth/logout`
      clears them and calls the Cognito logout endpoint.
- [ ] API routes move from `/v1` to `/api/v1` (one router prefix), so CloudFront can route by
      path without rewriting.
- [ ] Local development keeps one origin too: the Next.js dev server rewrites `/api/*` and
      `/auth/*` to the API (`next.config` rewrites apply only to `next dev`; production routing is
      CloudFront's).
- [ ] The web calls the API directly at `/api/v1/*` with the cookie (same origin, no proxy).
      When the access token has expired, the API refreshes it once with the refresh token and
      rotates the cookies. Cookie-authenticated POST, PATCH and DELETE are rejected with 403
      `auth.bad_origin` unless `Origin` equals `ATESTA_WEB_ORIGIN`. Nothing logs cookies.
- [ ] Typed client generated from the FastAPI OpenAPI document (`openapi-typescript` +
      `openapi-fetch`). CI fails when the generated types differ from a fresh export.
- [ ] Screens, Spanish first with English: sign in, create organization (first login without
      memberships lands here), organization home (memberships switcher), members (list, change
      role, remove), invitations (create, show the copy-once link with a copy button and a
      warning that it is shown once, list pending, revoke), accept invitation (`/invite`).
      Buttons and routes the caller's role does not allow are hidden; the API stays the
      authority (403 shown as a message).
- [ ] `/invite` reads the token from the URL fragment, removes it with `history.replaceState`,
      keeps it in `sessionStorage` across the login redirect, posts it in the JSON body, then
      deletes it. The page sends `Referrer-Policy: no-referrer`.
- [ ] i18n with `next-intl`: `messages/es.json` and `messages/en.json`, ES default, the user's
      choice stored in a cookie. Every API error code maps to an ES and EN message; an unknown
      code shows a generic message, never the raw code.
- [ ] Security headers on every response, from a CloudFront response headers policy: CSP
      with script hashes computed at build time (static export has no per-request nonce) and no
      `unsafe-inline` scripts, `frame-ancestors 'none'`, HSTS, `X-Content-Type-Options:
      nosniff`, `Referrer-Policy: same-origin` (no-referrer on `/invite`). A build step writes
      the hashes; the infra spec applies them.
- [ ] Accessibility: WCAG 2.1 AA for these screens (keyboard path, labels, focus, contrast),
      checked with axe in the e2e tests.
- [ ] Visual identity: design tokens (color, type, radius, spacing) as CSS variables in one
      file, from the brand identity the owner picks; neutral tokens until then. No brand value
      is hard-coded in components.
- [ ] Dependency licenses: CI fails on GPL or AGPL packages (ADR-006).

## Out of scope

- Compliance screens (connections, scores, evidence, AI): their own specs.
- Billing and plan screens (ADR-009 spec).
- Hosting: S3 bucket, CloudFront distribution and path routing, domain, certificates (infra
  spec, eu-south-2).
- Marketing site.
- Real Cognito in automated tests: e2e uses a fake OIDC provider; real login is a manual check
  in the dev pool (identity spec).

## Design notes

### Layout

```text
apps/web/
  src/app/(public)/          landing with sign-in button, /invite
  src/app/(app)/app/...      authenticated screens; GET /api/v1/me decides signed-in state
  src/lib/api/               generated types + openapi-fetch client (credentials: same-origin)
  src/components/ui/         shadcn/ui copies
  messages/{es,en}.json
  tests/                     vitest (unit), playwright (e2e)
apps/api/.../identity/bff.py /auth/login, /auth/callback, /auth/logout, session cookies
```

### Why a BFF, and why in the API

| Option | Token exposure | Cost |
|---|---|---|
| BFF in the API, tokens in HttpOnly cookies (chosen) | Script injection cannot read tokens | Three routes in identity; CloudFront path routing |
| BFF in a Next.js server | Same | Extra always-on Node service, breaks the static-export decision |
| SPA, tokens in memory | XSS reads and exfiltrates tokens | Simplest; silent refresh needs refresh tokens in JS |

RFC 10017 (OAuth 2.0 for Browser-Based Applications, draft-ietf-oauth-browser-based-apps-27,
section 6.1.4.3, checked 2026-11-13) ranks the BFF as the most secure pattern and "strongly
recommended for business applications, sensitive applications". Atesta stores customers' security
posture, so token theft by XSS is the risk to remove. Putting the BFF in FastAPI keeps one
server-side language (ADR-001) and the static frontend (Infrastructure tab).

### Configuration

| Variable | Use |
|---|---|
| `ATESTA_WEB_ORIGIN` (API) | Origin check, redirect URIs, cookie scope |
| `ATESTA_SESSION_KEY` (API) | 32-byte AES-GCM key for the session cookies (Secrets Manager) |
| `NEXT_PUBLIC_*` (web) | None needed: the web only knows relative paths |

### Libraries

| Library | License | Use |
|---|---|---|
| next, react | MIT | Framework |
| tailwindcss, shadcn/ui (copied) | MIT | Styling, components |
| @tanstack/react-query | MIT | Data fetching |
| next-intl | MIT | i18n |
| openapi-typescript, openapi-fetch | MIT | Typed API client |
| vitest, @playwright/test, @axe-core/playwright | MIT, Apache-2.0, MPL-2.0 | Tests (dev only) |

ADR-013: the vendored frontend skills (anthropics/skills frontend-design, vercel-labs React and
Next.js rules) are adopted in a separate PR before the first screen.

## Test plan

| Area | Cases |
|---|---|
| BFF routes (pytest, API) | login sets an HttpOnly state cookie and redirects with PKCE S256 and `lang`; callback rejects missing or wrong `state`; callback sets one encrypted cookie per token with HttpOnly, Secure, SameSite=Lax; tampered cookie rejected; logout clears all |
| Cookie auth (pytest, API) | cookie and bearer reach the same user; expired access token refreshed once and cookies rotated; cross-origin POST, PATCH, DELETE with a cookie get 403 `auth.bad_origin`; logs contain no cookie or token |
| Invite (unit) | fragment token moved to sessionStorage and removed from the URL; posted in the body; deleted after success |
| i18n | every error code in the backend specs has an ES and EN message (test reads the code list) |
| Contract | generated API types equal a fresh OpenAPI export |
| e2e (Playwright, fake OIDC, real API and Postgres) | sign in, create org, invite, accept as a second user, change role, remove; Spanish by default, English after switching; axe finds no serious violations |
| Headers | the build writes CSP script hashes for every inline script; e2e checks the policy blocks an injected inline script |
| Manual | sign-up with TOTP in the dev Cognito pool end to end |
