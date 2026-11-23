# Vendored agent skills (ADR-013)

Copied unmodified at a pinned commit, read in full before commit. Never auto-updated.

| Skill | Source | Commit | License | Read in full |
|---|---|---|---|---|
| test-driven-development | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development | 22f0b463e7a5e579904dd6211a520321035526f7 (2026-11-03) | MIT, see `LICENSE.superpowers` | 2026-11-13 |
| systematic-debugging | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging | same | MIT | 2026-11-13 |
| verification-before-completion | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion | same | MIT | 2026-11-13 |
| writing-plans | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/writing-plans | same | MIT, see `LICENSE.superpowers` | 2026-11-23 |
| executing-plans | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/executing-plans | same | MIT, see `LICENSE.superpowers` | 2026-11-23 |
| requesting-code-review | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/requesting-code-review | same | MIT, see `LICENSE.superpowers` | 2026-11-23 |
| receiving-code-review | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/receiving-code-review | same | MIT, see `LICENSE.superpowers` | 2026-11-23 |
| finishing-a-development-branch | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/finishing-a-development-branch | same | MIT, see `LICENSE.superpowers` | 2026-11-23 |
| brainstorming (text subset) | https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/brainstorming | same | MIT, see `LICENSE.superpowers` | 2026-11-23 |
| frontend-design | https://github.com/anthropics/skills/tree/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/frontend-design | 41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f (2026-09-03; identical at upstream HEAD 2c5958e) | Apache-2.0, see `frontend-design/LICENSE.txt` | 2026-11-13 |
| impeccable (text subset) | https://github.com/pbakaus/impeccable/tree/f56335bc9667f7c8ed6cde847742e5a61fc5f90a/.claude/skills/impeccable | f56335bc9667f7c8ed6cde847742e5a61fc5f90a (2026-11-14) | Apache-2.0, see `impeccable/LICENSE.txt` | `SKILL.md` 2026-11-22; references read before each use |
| modern-web-guidance (text subset) | https://github.com/GoogleChrome/modern-web-guidance/tree/4dd968349e54ca45a05dd5c818fb035c9054b022/skills/modern-web-guidance | 4dd968349e54ca45a05dd5c818fb035c9054b022 (2026-11-10) | Apache-2.0, see `modern-web-guidance/LICENSE.txt` | `SKILL.md` 2026-11-22; guides read before each use |
| react-best-practices (subset) | https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/skills/react-best-practices | 1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62 (2026-10-27) | MIT (declared upstream, no LICENSE file), see `LICENSE.vercel-agent-skills` | 2026-11-13 |
| taste-skill (text subset) | https://github.com/Leonxlnx/taste-skill/tree/f6b76575f949707b4e3c37cd86cb44b0b98643e8/skills/taste-skill | f6b76575f949707b4e3c37cd86cb44b0b98643e8 (2026-11-07) | MIT, see `taste-skill/LICENSE` | `SKILL.md` 2026-11-23; references read before each use. Landing page only (ADR-013) |
| i-have-adhd | https://github.com/ayghri/i-have-adhd/tree/1ecea1993b7fce257ffbd686c070948b5e07eda6/skills/i-have-adhd | 1ecea1993b7fce257ffbd686c070948b5e07eda6 (2026-10-11) | MIT, see `i-have-adhd/LICENSE` | 2026-11-23 |
| caveman | https://github.com/juliusbrussee/caveman/tree/b4ee71d557d96e3cbc14f88fa6e953a1362865f5/skills/caveman | b4ee71d557d96e3cbc14f88fa6e953a1362865f5 (2026-11-13) | Apache-2.0, see `caveman/LICENSE`, `caveman/NOTICE` and `caveman/LICENSE-MIT` | 2026-11-23 |
| ultracave | https://github.com/juliusbrussee/caveman/tree/b4ee71d557d96e3cbc14f88fa6e953a1362865f5/skills/ultracave | same as caveman | Apache-2.0, see `caveman/` | 2026-11-23 |
| megacave | https://github.com/juliusbrussee/caveman/tree/b4ee71d557d96e3cbc14f88fa6e953a1362865f5/skills/megacave | same as caveman | Apache-2.0, see `caveman/` | 2026-11-23 |

Upstream examples are TypeScript and npm based; in this repo read them as patterns for pytest
and uv. Project rules in AGENTS.md (imported by CLAUDE.md) win over any skill text.

## react-best-practices: what was left out

`SKILL.md` is unmodified, so it still lists files that are not here:

| Upstream file | Why left out |
|---|---|
| `rules/server-*.md` (10) | Server actions, `React.cache`, `after()`, RSC per-request data. The web app is a static export with no server runtime (web-shell spec). |
| `AGENTS.md` | Compiled copy of all rules, 108 KB. The rule files are the source. |
| `rules/_sections.md`, `rules/_template.md` | Inputs to the upstream build script. |

## impeccable and modern-web-guidance: what was left out

Both `SKILL.md` files are unmodified and still name things that are not here.

| Upstream | Why left out |
|---|---|
| `impeccable/scripts/` (12 files, 1.7 MB) | The launcher downloads a binary on first run. ADR-013 allows no download at use time. The skill's own "Launcher unavailable" path applies: read PRODUCT.md, DESIGN.md and the references directly. |
| `npx -y modern-web-guidance@latest …` | Fetches the latest package at use time, past the 7-day cooldown and the pin. Read the guides in `modern-web-guidance/guides/` instead (the same content at the pinned commit), as Trazum does. |

## taste-skill: what was left out and what changed

Vendored on 2026-11-23 for the landing page (coordinator, relaying the owner): `SKILL.md`, the 22
files in `references/` and the licence.

| Upstream | Why left out or changed |
|---|---|
| `assets/` (1,594 files: images, CSS kit, components, effects), `scripts/` (12), `library/`, `examples/`, `install.sh` | Images and runnable code. ADR-013 vendors text only; the landing is built with this repo's tokens and components. The skill's own checks (`gate.mjs`, `copy-lint.mjs`, `consistency.mjs`) are not available; the Playwright e2e and the landing spec's unit tests stand in for them. |
| The `hooks.Stop` block in `SKILL.md`'s frontmatter | Removed; this is the only change to the file. On every stop it would `exec node` on a `gate.mjs` found under `$HOME/.claude/skills/…`, `$CLAUDE_PLUGIN_ROOT` or the project, which runs code from outside the repository. ADR-013 keeps the Stop hook out unless it is reviewed. Upstream `SKILL.md` SHA-256: `0c7a5852a5217be79cab422c6d58329b776f0c25bd6da8a7a01707ce75be6206`. |

## superpowers planning and review skills: what was left out

Vendored on 2026-11-23 at the owner's request (issue #350). The six `SKILL.md` files and the two
prompt templates (`requesting-code-review/code-reviewer.md`, `brainstorming/builder-check-prompt.md`)
are unmodified. `LICENSE.superpowers` is byte-identical to upstream `LICENSE` at this commit and
covers them, as it does the three skills vendored on 2026-11-13.

| Upstream | Why left out |
|---|---|
| `using-git-worktrees` | The owner's instruction. Worktrees are created and removed by whoever dispatched the work, never by the agent. `writing-plans` and `executing-plans` name it: work in the worktree you were given, never on `main`. |
| `subagent-driven-development` and its `scripts/` (`sdd-workspace`, `task-brief`, `review-package`) | Not requested, and scripts. `writing-plans` and `executing-plans` name them. Keep the ledger by hand in a scratch directory outside the repository, and review `git diff $(git merge-base origin/main HEAD)..HEAD`. |
| `executing-plans/scripts/task-start`, `task-done` | Bash scripts that call the scripts above; ADR-013 vendors text only. Do their work by hand: note BASE with `git rev-parse HEAD`, run the task's tests with the exit code captured (verification rules), then append the ledger line. |
| `brainstorming/scripts/` (`server.cjs`, `helper.js`, `start-server.sh`, `stop-server.sh`, `frame-template.html`) and `brainstorming/visual-companion.md` | A local Node web server and its browser client, and the guide to running them. Without the server the guide has no use. The visual companion is not available: sketch in text and do not offer it. |

## i-have-adhd and caveman: what was left out

| Upstream | Why left out |
|---|---|
| i-have-adhd: everything but `skills/i-have-adhd/SKILL.md` and `LICENSE` (`agents/*.yaml`, `agents/*.toml`, `hooks/`, `extensions/`, `scripts/`, plugin manifests, `.opencode` JS) | The owner's instruction: the skill text only. |
| caveman: everything but the `caveman`, `ultracave` and `megacave` `SKILL.md` files and `LICENSE`, `NOTICE`, `LICENSE-MIT` (`hooks/` with `hooks.json` and `codex-sessionstart.js`, `proxy/`, `engine/`, `mcp/`, `scripts/`, packages, binaries, the skills' `README.md` files, every other skill) | The owner's instruction: the text of `caveman` and of the two skills it names as aliases (`/caveman ultra`, `/caveman wenyan`). Without the hook, `/caveman status` gives the skill's own no-hook answer, `(not tracked by this host)`. `/caveman-compress`, named in `ultracave` and `megacave`, is a script-backed skill and is not here. |

`caveman/NOTICE` is kept whole, as Apache-2.0 section 4(d) requires. Its third-party entries
(`engine/pixel/`, the fonts, `browse/`, the CLI) describe upstream code that is not vendored
here. `LICENSE-MIT` is kept because the NOTICE says contributions made before 3.0.0 stay under
MIT. "Caveman" is the upstream project's trademark and is used here only to name it.

`i-have-adhd`, `ultracave` and `megacave` declare `disable-model-invocation: true`, so the
Skill tool will not load them unprompted. When AGENTS.md says one applies, read its `SKILL.md`.

## Where project rules override these skills

| Skill text | Project rule |
|---|---|
| `client-swr-dedup`, `client-event-listeners` use SWR | TanStack Query is the data layer (web-shell spec). Same goal: one request per key. |
| `async-api-routes`, server parts of `async-suspense-boundaries` | No API routes or request-time server components in the web app. The API is FastAPI. |
| `rendering-hydration-no-flicker` inline `<script>` | The CSP allows no `unsafe-inline`. Any inline script needs its hash written by the build (web-shell spec). |
| `js-cache-storage` cookie example, `js-cache-function-results` `isLoggedIn` example | Auth cookies are HttpOnly and never read from JS. Session state comes from `GET /api/v1/me`. |
| `client-localstorage-schema` | Never store tokens, customer data or PII in browser storage (CLAUDE.md rule 2). |
| `bundle-defer-third-party` analytics example | No third-party analytics or scripts without an ADR. |
| impeccable "Redesign replaces" (choose a new visual world) | DESIGN.md "Paper and ink" is the approved identity (`docs/specs/landing-legal.md` L4/L5). App work is refinement in Operate mode, not a new world, unless the owner asks for one. |
| modern-web-guidance features not Baseline Widely available | Use only with the guide's fallback; the static export must keep working with the strict CSP. |
| taste-skill photographs, stand-in stock photographs, shader effects, scenes and dealt layouts | `docs/specs/landing-legal.md` wins: a product-led page whose argument is the product's own views, fed by one fixture. No stock photographs, no effects library, CSS-only motion. |
| taste-skill "60 to 80 words a screen" | The landing's copy budget is at most 60 words of marketing copy for the whole page (landing-legal spec). |
| taste-skill "one hard fact on the first screen", figures and claims | Claims honesty (`docs/specs/claims-honesty.md`): no "certificado", no "cumple", no figure outside the product views. |
| `frontend-design` "confirm with the client" | The client is the owner. Brand direction waits for the owner's choice of identity; until then the web shell uses neutral tokens. |
| `finishing-a-development-branch` option 1 (merge locally), `git branch -d` and `-D`, the discard path, `git worktree remove` and `git worktree prune` | Merging, closing and deleting branches are owner decisions, and work lands only by squash-merged pull request (AGENTS.md "Owner decisions", "How a pull request lands"). Take option 2: push, open the pull request with `Fixes #n` (rule 12), and stop. Never remove or prune a worktree and never delete a branch. |
| `finishing-a-development-branch` "force-push only on your human partner's explicit request" | Never force-push `main` or a branch that is not yours. Updating your own open pull request after a rebase on `origin/main` uses `git push --force-with-lease`. |
| `executing-plans` "four things stop you" (merge, push to a shared branch, publish) | Same list as AGENTS.md "Owner decisions", which is the full one: an owner decision stops you even when the skill would not. |
| `requesting-code-review` "Mandatory: before merge to main", `executing-plans` final review dispatch | Approval and merge belong to the owner (or the coordinator the owner names). A dispatched worker follows its dispatch on whether it may start subagents; without one, use the template as a self-review and say so. |
| `receiving-code-review` replies with `gh api …/replies` | Reply in threads on the project's own pull requests only. Answering a person outside the project is an owner decision. |
| `writing-plans` saves to `docs/superpowers/plans/`, `brainstorming` saves to `docs/superpowers/specs/` | Specs go in `docs/specs/` from `_template.md` (rule 7). Plans are working notes: keep them in the issue, the pull request body or a scratch directory outside the repository. |
| `writing-plans` execution handoff, `brainstorming` hard gate (wait for approval of the design) | An issue with acceptance criteria from the owner, or a dispatched task, is the approved request. Questions go to whoever gave the task; do not stall for a menu choice already made. |
| `i-have-adhd` "applies to every response for the rest of the session" | Only messages addressed to the owner (AGENTS.md). Commits, pull requests, issues, specs and docs keep the project's normal style. |
| `caveman` and `ultracave` persistence | Only agent-to-coordinator chat and status messages (AGENTS.md). `megacave` (Classical Chinese) is vendored as an alias and not used: project messages are in English or Spanish. |

Every vendored file is pinned by SHA-256 in `VENDORED.sha256` and checked by
`apps/api/tests/test_vendored_skills.py`; regenerate the manifest only together with a review.
