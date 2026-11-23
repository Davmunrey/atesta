# Governance

How decisions about Atesta are made, recorded and enforced.

## Who decides

- **The owner** (GitHub `Davmunrey`) decides product direction, accepts ADRs, releases catalog
  packs, changes repository settings, applies infrastructure and speaks for Atesta to customers,
  auditors and anyone outside the project. The closed list is in AGENTS.md, "Owner decisions".
- **Agents and contributors** propose. They open issues, write specs and ADRs as *proposed*, and
  open pull requests. An agent merges its own pull requests only when the owner has said so, once
  CI is green (AGENTS.md, "How a pull request lands").
- **Qualified reviewers** sign off framework packs and mappings before release. **Legal
  reviewers** sign off terms, the DPA and employee notices (ROADMAP, "Only a human can do").

## Where decisions live

| Kind | Where | Changed by |
| --- | --- | --- |
| Rules every change follows | `AGENTS.md` (imported by `CLAUDE.md`) | a pull request the owner merges |
| Architecture | `docs/adr/`, numbered, statuses *proposed* or *accepted* | proposed by anyone; accepted by the owner |
| Features | `docs/specs/`, written before code (rule 7) | the feature's pull request |
| Order of work and gates | `ROADMAP.md` | the owner, or a pull request that records progress |
| What changed, for users and auditors | `changes/` fragments, folded into `CHANGELOG.md` at release | every pull request; the release by the owner |
| Framework content and provenance | `catalog/`, each pack's `SOURCES.md` and `coverage.yaml` | pull requests; release by the owner after qualified review |

## How a decision is enforced

The rules are enforced by checks, not by memory:

- **CI jobs:**
  - `python`: tests, lint, types and module boundaries;
  - `web`: types, lint, tests, build and licences;
  - `e2e`: browser tests;
  - `security`: dependency audits and semgrep;
  - `secrets`: gitleaks;
  - `changes`: changelog fragments;
  - `scanner` and `infra`.
- **The `main` ruleset** requires a pull request, squash merge and every job green, with no bypass.
- **Code owners:** `.github/CODEOWNERS` assigns every path to the owner and marks where a review must slow down.

## Releases

1. The owner chooses a version (`vYYYY.MM.N`).
2. `uv run python -m apps.api.devtools.changes release --version vYYYY.MM.N` folds the pending
   fragments into `CHANGELOG.md` and deletes them.
3. The release pull request's body carries `Release: vYYYY.MM.N`, so the `changes` job lets it
   edit `CHANGELOG.md`. The owner merges it and tags the commit.

## Changing this file

Through a pull request the owner merges. If this file and AGENTS.md disagree, AGENTS.md wins
until both are fixed.
