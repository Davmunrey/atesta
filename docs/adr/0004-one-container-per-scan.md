# ADR-004: One ephemeral Fargate task per scan

- Status: accepted (2026-11-12)

## Decision
Each scan runs in its own container with short-lived tenant credentials and a task role scoped
to that tenant's S3 prefix. No shared disk.

## Consequences
Strong tenant isolation and crash containment. Cold start of ~1 min per scan, acceptable for
daily scans.

## Amendment 1 (accepted 2026-11-13, scanner-connectors spec)
- The scan task fetches the connector credential at start with its per-org, per-provider task role
  and holds it only for the task's lifetime. Prowler 5.49.0 takes no pre-issued token for M365 or
  Google, so "short-lived tenant credentials" becomes "credentials held only for the task's
  lifetime".
- The M365 certificate is one Atesta credential for all consenting M365 tenants (spec D5).
- Scan outputs are write-once; egress is deny-by-default; the image entrypoint is the Atesta
  wrapper `atesta-scan`, not `prowler`.
