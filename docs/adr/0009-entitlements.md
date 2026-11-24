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

## Amendment 2 (proposed 2026-11-23): entitlements are enforced, and the plan is stored
Status: proposed. The owner decided the substance on 2026-11-23, relayed by the coordinator.
Accepting the amendment is the owner's call.

- **Storage:** an organization's plan lives in billing's tenant table `subscriptions`, one row per
  organization. The app only reads it; the operator writes it.
- **Default:** an organization with no row has `billing.api.DEFAULT_PLAN`, `business`.
- **Enforcement:** routes enforce plans only through `billing.api.require_connector_slot`,
  `require_feature` and `require_framework`. A refusal is 403 `billing.plan_limit`.
- **Grants:** a plan in `catalog/plans.yaml` may be `all`, every framework.

See `docs/specs/billing-entitlements.md`.

## Amendment 3 (accepted 2026-11-24, #394): no payment gateway, customers are invoiced
Status: accepted. The owner decided on 2026-11-24 ("No va a haber pasarela de pago, va a ser todo
facturación"), relayed by the coordinator.

- **No gateway:** Atesta integrates no payment gateway or card processor (no Stripe). The app
  never collects or stores payment details.
- **Invoicing:** customers are invoiced outside the app, by the legal entity, under its own
  invoicing obligations. Prices stay out of the public repository.
- **Plans:** the operator sets an organization's plan in `subscriptions` (amendment 2) once the
  contract is agreed. The app only reads it, and every access check still goes through the
  entitlements service.
- **Consequence:** no payment provider joins the subprocessor list, and no billing webhook or
  public billing endpoint exists.
