# Vendored agent skills (ADR-013)

Copied unmodified at a pinned commit, read in full before commit. Never auto-updated.

| Skill | Source | Commit | License | Read in full |
|---|---|---|---|---|
| test-driven-development | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development | 22f0b463e7a5e579904dd6211a520321035526f7 (2026-11-03) | MIT, see `LICENSE.superpowers` | 2026-11-13 |
| systematic-debugging | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging | same | MIT | 2026-11-13 |
| verification-before-completion | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion | same | MIT | 2026-11-13 |
| frontend-design | https://github.com/anthropics/skills/tree/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/frontend-design | 41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f (2026-09-03; identical at upstream HEAD 2c5958e) | Apache-2.0, see `frontend-design/LICENSE.txt` | 2026-11-13 |
| react-best-practices (subset) | https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/skills/react-best-practices | 1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62 (2026-10-27) | MIT (declared upstream, no LICENSE file), see `LICENSE.vercel-agent-skills` | 2026-11-13 |

Upstream examples are TypeScript and npm based; in this repo read them as patterns for pytest
and uv. Project rules in AGENTS.md (imported by CLAUDE.md) win over any skill text.

## react-best-practices: what was left out

`SKILL.md` is unmodified, so it still lists files that are not here:

| Upstream file | Why left out |
|---|---|
| `rules/server-*.md` (10) | Server actions, `React.cache`, `after()`, RSC per-request data. The web app is a static export with no server runtime (web-shell spec). |
| `AGENTS.md` | Compiled copy of all rules, 108 KB. The rule files are the source. |
| `rules/_sections.md`, `rules/_template.md` | Inputs to the upstream build script. |

## Where project rules override these skills

| Skill text | Project rule |
|---|---|
| `client-swr-dedup`, `client-event-listeners` use SWR | TanStack Query is the data layer (web-shell spec). Same goal: one request per key. |
| `async-api-routes`, server parts of `async-suspense-boundaries` | No API routes or request-time server components in the web app. The API is FastAPI. |
| `rendering-hydration-no-flicker` inline `<script>` | The CSP allows no `unsafe-inline`. Any inline script needs its hash written by the build (web-shell spec). |
| `js-cache-storage` cookie example, `js-cache-function-results` `isLoggedIn` example | Auth cookies are HttpOnly and never read from JS. Session state comes from `GET /api/v1/me`. |
| `client-localstorage-schema` | Never store tokens, customer data or PII in browser storage (CLAUDE.md rule 2). |
| `bundle-defer-third-party` analytics example | No third-party analytics or scripts without an ADR. |
| `frontend-design` "confirm with the client" | The client is the owner. Brand direction waits for the owner's choice of identity; until then the web shell uses neutral tokens. |

Every vendored file is pinned by SHA-256 in `VENDORED.sha256` and checked by
`apps/api/tests/test_vendored_skills.py`; regenerate the manifest only together with a review.
