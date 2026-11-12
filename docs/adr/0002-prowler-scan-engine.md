# ADR-002: Prowler as scan engine, pinned, wrapped not forked

- Status: accepted (2026-11-12)

## Context
Prowler (Apache-2.0) already runs hundreds of read-only checks and ships ENS RD2022 mappings for
AWS and GCP, with providers for M365 and Google Workspace.

## Decision
Use Prowler as a pinned dependency inside the scanner image. Do not fork. Atesta builds its own
ENS mappings for M365 and Google Workspace and its own catalog on top.

## Consequences
Months of check development saved. Atesta's value moves to catalog, organizational measures,
evidence pack and UX. Prowler Cloud is also a competitor; monitor it. Version bumps require a
golden-test run.
