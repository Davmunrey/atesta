# ADR-009: Single entitlements service gates plans and add-ons

- Status: accepted (2026-11-12)

## Decision
`billing.api.has_feature` and `connector_limit` are the only access checks for plans and
add-ons, used by API and UI. Add-ons are modules or features switched on by entitlements, never
separate services.

## Consequences
New add-ons are configuration, not refactors. No hard-coded plan checks anywhere else.

## Amendment 1 (accepted 2026-11-13): framework grants are data
`billing.api.has_framework(plan, framework_key, applies_to=None, addons)` joins `has_feature`
and `connector_limit` as an access check. Plan and add-on grants for framework packs live in
`catalog/plans.yaml`, validated against the pack ids in `catalog/frameworks/`. `Feature` keeps
only framework-agnostic features. Selling a new pack or level is a YAML change (MF-03, rule 9).
