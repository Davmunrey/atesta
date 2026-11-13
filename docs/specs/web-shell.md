# Spec: Web shell, sign-in and organization screens

- Requirement ids: FR-01, NFR-03, NFR-10
- Status: draft
- ADRs: ADR-001, ADR-007, ADR-012, ADR-013
- Build order: after identity-auth (its endpoints are the only backend this needs)

## Problem

The identity backend works but nobody can use it: `apps/web` is empty. The security lead of an
SME must sign up with MFA, create the organization, invite colleagues and manage roles from a
browser, in Spanish first. The shell built here (auth, layout, API client, i18n) is what every
later screen (connections, scores, evidence) plugs into.

## Acceptance criteria

- [ ] Next.js (App Router) + TypeScript strict in `apps/web`, shadcn/ui components copied into
      the repo, Tailwind CSS, TanStack Query (Architecture tab). Node 22 LTS pinned in `.nvmrc`;
      pnpm with `minimumReleaseAge: 10080` (minutes, 7 days; same cooldown as uv; pnpm docs,
      dependency-resolution settings, checked 2026-11-13).
- [ ] Backend for frontend (BFF): the Next.js server runs Authorization Code + PKCE against
      Cognito managed login and keeps the tokens. The browser never sees an access, ID or refresh
      token: they live in encrypted, `HttpOnly`, `Secure`, `SameSite=Lax` cookies, one per
      token, each under 4 KB.
- [ ] `/auth/login` creates `state`, `nonce` and the PKCE verifier in a short-lived
      `HttpOnly` cookie and redirects to `/oauth2/authorize` with `lang=es` (default) or `lang=en`
      and scopes `openid email`. `/auth/callback` rejects a missing or mismatched `state`,
      exchanges the code, sets the session cookies and redirects to `/app`. `/auth/logout`
      clears them and calls the Cognito logout endpoint.
- [ ] API calls go through one proxy route, `/api/v1/*`, that adds the bearer token on the
      server, refreshes an expired access token once with the refresh token, and returns the
      API's status and stable error code. Mutating requests (POST, PATCH, DELETE) are rejected
      with 403 unless their `Origin` equals the web origin. The proxy never logs headers or
      bodies.
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
- [ ] Security headers on every response: nonce-based CSP with no `unsafe-inline` scripts,
      `frame-ancestors 'none'`, HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy:
      same-origin` (no-referrer on `/invite`).
- [ ] Accessibility: WCAG 2.1 AA for these screens (keyboard path, labels, focus, contrast),
      checked with axe in the e2e tests.
- [ ] Visual identity: design tokens (color, type, radius, spacing) as CSS variables in one
      file, from the brand identity the owner picks; neutral tokens until then. No brand value
      is hard-coded in components.
- [ ] Dependency licenses: CI fails on GPL or AGPL packages (ADR-006).

## Out of scope

- Compliance screens (connections, scores, evidence, AI): their own specs.
- Billing and plan screens (ADR-009 spec).
- Hosting: Fargate service, ALB, domain, certificates (infra spec, eu-south-2).
- Marketing site.
- Real Cognito in automated tests: e2e uses a fake OIDC provider; real login is a manual check
  in the dev pool (identity spec).

## Design notes

### Layout

```text
apps/web/
  src/app/(public)/          sign-in landing, /invite
  src/app/(app)/app/...      authenticated screens, server-side session check
  src/app/auth/{login,callback,logout}/route.ts
  src/app/api/v1/[...path]/route.ts   proxy
  src/lib/session.ts         cookie encryption (jose, A256GCM), refresh
  src/lib/api/               generated types + openapi-fetch client
  src/components/ui/         shadcn/ui copies
  messages/{es,en}.json
  tests/                     vitest (unit), playwright (e2e)
```

### Why a BFF

| Option | Token exposure | Cost |
|---|---|---|
| BFF, tokens in HttpOnly cookies (chosen) | Script injection cannot read tokens | One proxy route; cookies sized per token |
| SPA, tokens in memory | XSS reads and exfiltrates tokens | Simpler; silent refresh needs refresh tokens in JS |

RFC 10017 (OAuth 2.0 for Browser-Based Applications, draft-ietf-oauth-browser-based-apps-27,
section 6.1.4.3, checked 2026-11-13) ranks the BFF as the most secure pattern and "strongly
recommended for business applications, sensitive applications". Atesta stores customers' security
posture, so token theft by XSS is the risk to remove.

### Configuration

| Variable | Use |
|---|---|
| `ATESTA_API_URL` | API base for the proxy (server only) |
| `ATESTA_WEB_ORIGIN` | Origin check and redirect URIs |
| `ATESTA_COGNITO_DOMAIN`, `ATESTA_COGNITO_APP_CLIENT_ID` | Managed login |
| `ATESTA_SESSION_KEY` | 32-byte key for cookie encryption (Secrets Manager in AWS) |

### Libraries

| Library | License | Use |
|---|---|---|
| next, react | MIT | Framework |
| tailwindcss, shadcn/ui (copied) | MIT | Styling, components |
| @tanstack/react-query | MIT | Data fetching |
| next-intl | MIT | i18n |
| jose | MIT | Cookie encryption (JWE) |
| openapi-typescript, openapi-fetch | MIT | Typed API client |
| vitest, @playwright/test, @axe-core/playwright | MIT, Apache-2.0, MPL-2.0 | Tests (dev only) |

ADR-013: the vendored frontend skills (anthropics/skills frontend-design, vercel-labs React and
Next.js rules) are adopted in a separate PR before the first screen.

## Test plan

| Area | Cases |
|---|---|
| Auth routes (unit) | login sets an HttpOnly state cookie and redirects with PKCE S256 and `lang`; callback rejects missing or wrong `state`; callback sets one encrypted cookie per token with HttpOnly, Secure, SameSite=Lax; logout clears all |
| Proxy (unit) | adds bearer on the server; refreshes once on 401 then gives up; rejects cross-origin POST, PATCH, DELETE with 403; passes the API error code through; logs contain no token |
| Invite (unit) | fragment token moved to sessionStorage and removed from the URL; posted in the body; deleted after success |
| i18n | every error code in the backend specs has an ES and EN message (test reads the code list) |
| Contract | generated API types equal a fresh OpenAPI export |
| e2e (Playwright, fake OIDC, real API and Postgres) | sign in, create org, invite, accept as a second user, change role, remove; Spanish by default, English after switching; axe finds no serious violations |
| Headers | CSP, HSTS, frame-ancestors, referrer policies present on every route |
| Manual | sign-up with TOTP in the dev Cognito pool end to end |
