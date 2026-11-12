# ADR-003: Postgres-backed job queue

- Status: accepted (2026-11-12)

## Decision
Procrastinate on the existing Postgres instead of Redis or SQS.

## Consequences
One less service to run and secure; transactional enqueue with business data. Revisit above
~200 scans/day (see ADR-008 triggers).
