# ADR-009: Single entitlements service gates plans and add-ons

- Status: accepted (2026-11-12)

## Decision
`billing.api.has_feature` and `connector_limit` are the only access checks for plans and
add-ons, used by API and UI. Add-ons are modules or features switched on by entitlements, never
separate services.

## Consequences
New add-ons are configuration, not refactors. No hard-coded plan checks anywhere else.
