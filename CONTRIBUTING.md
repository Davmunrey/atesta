# Contributing

Atesta is built by its owner (GitHub `Davmunrey`) and by coding agents (Claude Code, Codex)
working under the owner's direction. Outside contributions are not accepted.

The rules every change follows are in [AGENTS.md](AGENTS.md); `CLAUDE.md` imports the same
file. This document is the process around them: set up, check, propose, review, merge. Where
the two seem to differ, `AGENTS.md` wins.

## Set up

Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm 10 (`apps/web/.nvmrc`,
`apps/web/package.json`), Postgres 16 for database tests, Docker for the scanner image, and
OpenTofu for `infra/`.

```bash
uv sync --all-packages --locked
pnpm --dir apps/web install --frozen-lockfile
```

## Check before you push

Each block is one CI job in `.github/workflows/ci.yml`, with the same commands. A test keeps
this section and the workflow in step (`apps/api/tests/test_contributing.py`).

**python** (needs Postgres 16; any empty database the test user owns):

```bash
export ATESTA_TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m apps.api.devtools.preview_catalog
uv run lint-imports
uv run pytest -q
```

**web** (from `apps/web`):

```bash
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm check-licenses
```

**e2e** (from `apps/web`, after `pnpm build`; a Postgres superuser URL in
`ATESTA_E2E_ADMIN_URL`):

```bash
pnpm exec playwright test --trace off
```

**scanner** (from the repository root):

```bash
docker build -f scanner/Dockerfile -t atesta-scanner:ci .
scanner/golden.sh atesta-scanner:ci
```

**infra**:

```bash
tofu fmt -check -recursive infra
```

The **security** job (dependency audits and semgrep) runs pinned tools through `uvx` with a
7-day cooldown; read the exact commands in `ci.yml` rather than a copy here.

State what you ran and what you could not run. A check you could not run is "not run", never
"passed" (AGENTS.md, verification rules).

## From issue to merge

1. **Issue.** Every pull request resolves an issue (rule 12). Open it from the issue forms; a
   feature names its spec, a catalog change names its official source.
2. **Spec.** A feature starts with `docs/specs/<slug>.md`, from `docs/specs/_template.md`
   (rule 7). An architecture change adds or amends an ADR in `docs/adr/`.
3. **Branch.** From current `main`: `claude/<topic>` or `codex/<topic>`.
4. **Test first.** Write the failing test, then the code. A new guard is proven by planting
   the fault it catches and watching it fail; the pull request says what was planted.
5. **Pull request.** The template asks for `Fixes #n`, what changes, why, evidence and limits.
   Related issues may share one pull request, with one commit per issue, to save CI runs.
6. **Review.** The checklist below.
7. **Merge.** Squash, once every CI job is green; the `main` ruleset enforces both. The owner
   merges, or an agent the owner told to merge its own pull requests (AGENTS.md, "Owner
   decisions"). GitHub deletes the branch.

## Review checklist

Before reading for style, in this order:

1. Does it add a write scope, or log a secret, a token or customer content? (rules 1–2)
2. Tenant isolation: a new table without `organization_id` and an RLS policy, a query outside
   the tenant context, or a global table not listed in ADR-012? (rule 3)
3. A new dependency: licence (rule 4, ADR-006), pin, and the 7-day cooldown?
4. AI: can its output change a status, or is an uncited claim accepted? (rules 5–6, ADR-005)
5. Module boundaries: an import of another module's internals? (rule 8)
6. A framework-specific table or code path? (rule 9) Normative text without its official
   source? (rule 10)
7. User-visible action: an audit event, and strings in ES and EN?
8. Changes under `.github/`, `infra/`, `scanner/Dockerfile`, `scanner/requirements*.txt`,
   migrations, `modules/identity` or `modules/connections`: read those diffs first. Green CI
   reports only what the pull request's own workflows say about it.

## Where things are

[docs/README.md](docs/README.md) indexes the product, architecture, specs, status, catalog and
security documents.
