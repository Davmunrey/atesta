# ADR-008: Modular monolith with enforced boundaries

- Status: accepted (2026-11-12)

## Decision
One deployable backend with modules: identity, connections, scanning, compliance, evidence, ai,
billing. Modules interact only through `api.py`. `lint-imports` enforces it in CI. No
cross-module database joins.

## Extraction triggers
- > 200 scans/day or ingest slows the API: extract the ingest worker.
- AI cost/latency hurts UX: ai module behind its own queue.
- Enterprise isolation demand: dedicated tenant (separate account), not microservices.

## Consequences
One deploy, cheap refactors, clean due diligence. Requires discipline on boundaries.
