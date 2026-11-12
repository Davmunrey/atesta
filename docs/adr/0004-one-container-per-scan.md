# ADR-004: One ephemeral Fargate task per scan

- Status: accepted (2026-11-12)

## Decision
Each scan runs in its own container with short-lived tenant credentials and a task role scoped
to that tenant's S3 prefix. No shared disk.

## Consequences
Strong tenant isolation and crash containment. Cold start of ~1 min per scan, acceptable for
daily scans.
