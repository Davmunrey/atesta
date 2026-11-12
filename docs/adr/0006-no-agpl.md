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

## Amendment 1 (proposed 2026-11-12): LGPL libraries
LGPL-licensed libraries are allowed when used unmodified as installed dependencies (dynamic
linking, no copied or patched source). LGPL has no network-use clause. Trigger: psycopg 3
(LGPL-3.0) is required by Procrastinate (ADR-003) and serves as the SQLAlchemy driver. AGPL and
GPL stay banned. Any patch to an LGPL library must be published, so patches need an ADR first.
