# ADR-015: The repository is public

- Status: proposed (2026-11-23); the owner accepts it. The owner made the repository public on
  2026-11-22 ("He hecho la app pública para tener minutos de CI").
- Related: SECURITY.md, AGENTS.md ("Owner decisions"), ADR-013.

## Context

The repository started private. To get CI minutes, the owner made it public on 2026-11-22. Its
code, specs, ADRs and catalog are now readable by anyone. The licence stays proprietary
(`LICENSE`: all rights reserved), so public does not mean open source.

## Decision

- **What never enters the repository:**
  - pricing, competitor analysis, prospects, customer names and the business plan, which lives
    outside the repository;
  - customer data, secrets, tokens and real tenant identifiers (CLAUDE.md rule 2, enforced by
    gitleaks in CI and GitHub push protection).
- **Settings that hold the decision,** read from the GitHub API on 2026-11-23:
  - **Code security:** secret scanning and push protection on; Dependabot security updates on;
    private vulnerability reporting on.
  - **Workflow token:** the default workflow token is read-only, and workflows cannot approve pull
    requests.
  - **Fork pull requests:** workflows from every external contributor need approval before they
    run.
  - **Actions pinning:** actions must be pinned to a full commit SHA.
  - **The `main` ruleset (id 27855446, active):** a pull request, squash merge and every CI job
    green (`.github/rulesets/main-branch.json`).
- **Vulnerabilities** are reported privately (SECURITY.md), never in public issues. Issue forms
  require a "no private data" confirmation.
- **Security through obscurity is not a control.** Everything public must be safe to be public.
  Tenant isolation, read-only connectors and the absence of secrets hold because of tests, not
  because nobody reads the code.

## Consequences

- Attackers can read the code, so the controls in SECURITY.md must hold on their own. The
  independent penetration test (ROADMAP Gate A) assumes full source access.
- Anyone can see the catalog's official texts and Atesta-authored guides. The licence still
  forbids reuse without agreement.
- Business material needs a private place. The owner keeps the plan outside the repository.
- Making the repository private again is an owner decision. It would cost CI minutes, and it
  would not undo what has already been public.
