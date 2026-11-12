# ADR-011: Framework-agnostic control model; frameworks are content packs

- Status: accepted (2026-11-12)

## Context
Atesta is a multi-framework platform (ENS, NIS2, ISO 27001, RGPD art. 32, DORA, SOC 2...). ENS
is the go-to-market wedge, not the limit.

## Decision
Checks feed common, Atesta-owned controls. Each framework is a versioned YAML pack whose
requirements map many-to-many to those controls. Scores are computed per framework from the same
control results (`atesta_core.frameworks`). No framework-specific tables or code paths.

## Consequences
- "Test once, comply with many": one scan and one piece of evidence serve every framework.
- Adding a framework is content work (mappings + review), not engineering.
- A pack ships only when 3+ customers or deals ask for it and >= 60% of its requirements map to
  existing controls.
- Every mapping records its source and reviewer (MF-06).
