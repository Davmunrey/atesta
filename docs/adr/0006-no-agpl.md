# ADR-006: No AGPL/GPL dependencies in network-facing services

- Status: accepted (2026-11-12)

## Context
CISO Assistant Community is AGPL v3. Network use of AGPL code can force source disclosure and
weakens IP in an acquisition.

## Decision
No AGPL/GPL code in services exposed over the network. License checker in CI (Phase 2).

## Consequences
Some open-source GRC components cannot be reused; framework content is rebuilt from official
sources.
