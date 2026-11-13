# Spec: Cookie and browser storage information

Status: implementation slice of the approved landing-legal specification, 2026-11-13.
Depends on: organization-shell-design (#55). Independent of scanner ingestion (#56).

## Scope and verified inventory

Implement `/cookies` in Spanish and English, linked from the public and authenticated footer.
Use the approved light public theme, existing fonts and semantic tokens. A readable document
with an in-page index and separated inventory rows fits the content; no cards or banner.

| Storage | Purpose | Lifetime in the current implementation |
| --- | --- | --- |
| `atesta_locale` cookie | Explicit language choice | 365 days from the last choice; not set by merely visiting |
| `atesta_auth` cookie | Protect the pending sign-in | 600 seconds; cleared by a successful callback |
| `atesta_at` cookie | Authenticated API access | 43200 seconds from the last update; cleared at sign-out |
| `atesta_rt` cookie | Renew authenticated access | 43200 seconds from the last update; cleared at sign-out |
| `atesta_invite:v1` session storage | Keep an invitation through sign-in | Tab session; removed after successful acceptance |

Sources: `src/i18n/locale.ts`, `src/lib/invite.ts`, and the API identity `bff.py`.
Cookie expiry is not the access-token expiry or a promise that a session cannot end earlier.
The sign-in page is a separate Amazon Cognito surface: describe it separately and link to its
official documentation, without inventing a provider cookie inventory or claiming a live audit.

## Acceptance

- Explain each storage item's purpose, trigger and retention in plain language. Do not read,
  display or log stored values. Inventory rows expose machine-readable durations using `time`.
- Visiting public pages sets no cookie and requests no third-party resource. Changing language
  stores only the selected preference. Signing in creates the documented authentication cookies.
- Explain browser deletion/blocking controls and their consequences; no fake consent controls.
  Do not change cookie behavior or claim legal approval. Current code has no analytics or ads.
- All text is localized, including the index, footer and accessible labels. The page remains
  light in either system theme; fits 375/768/1280px; keyboard navigation and axe checks pass.
- Footer links are reachable from public pages and the workspace. Browser back navigation still
  returns to the previously viewed workspace route without changing the selected organization.

## Evidence and release boundary

Browser tests compare actual cookie names, attributes and expiry to the rendered inventory,
check creation/removal through the fake-Cognito flow, and verify ES/EN, network requests,
responsive layout and accessibility. Existing invitation tests cover session storage cleanup.
Capture red/green and clean-copy verification with REA; run the full existing checks.

Integration baseline: scanner PRs #56 through #62 are merged into main. The native macOS
suite exposed a scanner-test portability issue: Python adds `__CF_USER_TEXT_ENCODING` even
when the supplied subprocess environment omits it. Ignore only that runtime-added key on
Darwin in the existing assertion; retain the exact environment check for all other keys and
platforms. No scanner runtime changes. REA's minimal-process reproduction confirms the cause.

This increment does not complete aviso legal, privacy information or lawyer review. Existing
public-release gates remain applicable. Deployment still requires the real legal identity,
recorded product views and review of legal text and actual Cognito storage configuration.

Official references checked on 2026-11-13:
- [LSSI, article 22.2](https://www.boe.es/buscar/act.php?id=BOE-A-2002-13758#a22).
- [AEPD cookie guide, May 2024](https://www.aepd.es/guias/guia-cookies.pdf), sections 1 and 2.1.2.
- [Cognito managed login](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html).
- [Cognito session management update](https://aws.amazon.com/about-aws/whats-new/2026/11/amazon-cognito-session-management/).
  This recent change reinforces why the provider duration must be checked against the deployed
  configuration instead of assuming the old one-hour default is universal.
