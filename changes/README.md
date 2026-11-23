# Pending changes

One file per change merged into `main` and not yet released. A release folds them into
[CHANGELOG.md](../CHANGELOG.md) under its version and deletes them.

## Add one

Name it `<issue>.<kind>.md`, where `<issue>` is the number in the pull request's `Fixes #n`.
A second entry for the same issue is `<issue>-2.<kind>.md`. `<kind>` is one of `added`,
`changed`, `deprecated`, `removed`, `fixed`, `security`; a release lists them in that order.

The body is the entry as it will read: one bold sentence that says what changed for someone
using or auditing Atesta, then `(#<issue>)`, then at most a few sentences more.

```markdown
**Connections are verified read-only before every scan.** (#91) A grant beyond the allowlist stops the scan.
```

## Cut a release

`uv run python -m apps.api.devtools.changes release --version vYYYY.MM.N` checks every fragment,
writes them into `CHANGELOG.md` under the version, grouped by kind, and deletes them. The owner
chooses the version and merges the release pull request (GOVERNANCE.md).

## Why a folder

Every pull request editing one `## Unreleased` section conflicts with every other open pull
request. A file per change cannot. It also gives each change a registered reference and a
written description, which is what change management asks for (ENS op.exp.5).

## The check

`uv run python -m apps.api.devtools.changes check --base origin/main --body <file>` runs in CI
on every pull request (`ci.yml`, job `changes`). It fails when the pull request adds no
fragment, when a fragment is misnamed or malformed, when a fragment's issue is not one the body
fixes, or when a pull request other than a release edits `CHANGELOG.md`. A release pull request carries
a `Release: vYYYY.MM.N` line in its body. Dependabot is exempt.
