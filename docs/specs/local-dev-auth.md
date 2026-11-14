# Spec: Local sign-in without AWS

- Requirement ids: FR-01
- Status: approved (owner chose "postpone AWS, simulate Cognito locally", 2026-11-13)
- ADRs: ADR-012
- Build order: after the BFF (web-shell spec)

## Problem

AWS is postponed, so there is no Cognito pool. The BFF, the web shell and the week-1 demo still
need a working sign-in locally, through the same code paths production will use.

## Acceptance criteria

- [ ] `apps/api/devtools/fake_cognito.py`: a small FastAPI app that mimics the Cognito endpoints
      the API and BFF call: `/.well-known/jwks.json`, `/oauth2/authorize` (HTML form: email and a
      6-digit code standing in for TOTP), `/oauth2/token` (authorization_code with PKCE S256
      check, refresh_token), `/oauth2/userInfo`, `/logout`.
- [ ] Tokens are RS256 with Cognito's claim shapes: access (`token_use=access`, `client_id`,
      `scope="openid email"`), ID (`aud`, `nonce`, `email`, `email_verified`). `sub` is stable
      per email.
- [ ] The API reaches it only through two overrides, `ATESTA_COGNITO_ISSUER` and
      `ATESTA_COGNITO_BASE_URL`. Startup fails closed: either override is refused unless
      `ATESTA_ENV` is `local`, `dev` or `test` (unset, `prod` or any other value refuses).
- [ ] It lives outside the `atesta_api` package, so no production import can reach it.
- [ ] One test drives the real `CognitoOAuth`, `TokenVerifier` and `CognitoUserInfo` through a
      full sign-in, refresh and userInfo against the fake.

## Out of scope

- Real MFA. The code field only proves the screen exists; any 6 digits pass.
- Running the fake anywhere but a developer machine.
