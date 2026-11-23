# Spec: billing entitlements are enforced

- Requirement ids: ADR-009 (and its amendment 1), MF-03, rule 9
- Status: approved (owner decisions relayed by the coordinator, 2026-11-23: enforce now; `subscriptions` table; default `business`; grants as in `catalog/plans.yaml`)

## Problem

`billing.api` defines what each plan allows (`has_feature`, `connector_limit`, `has_framework`),
but no endpoint asks it. Any organization can add any number of connectors, open every framework
and export every dossier, whatever it pays for. The owner decided on 2026-11-23 to enforce
entitlements now, during pilots too.

## What each plan allows

Plan contents live in one place each: features and connector limits in `billing.api`, framework
grants in `catalog/plans.yaml` (ADR-009 amendment 1). This table restates them; the code is the
source.

| Plan | Connectors | Features | Frameworks |
| --- | --- | --- | --- |
| `starter` | 1 | none | as granted in `catalog/plans.yaml` |
| `pro` | 3 | `daily_monitoring`, `evidence_export`, `policy_ai_review` | as granted |
| `business` | unlimited | every feature | as granted |

**Add-ons:**
- A feature add-on is a `Feature` value. It grants that feature on any plan.
- A framework add-on is a name under `addons:` in `catalog/plans.yaml`. It grants that entry's
  frameworks.

## Acceptance criteria

**Where an organization's plan lives**
- [ ] **Table:** `subscriptions`, a tenant table (ADR-012) with the standard RLS policy. It holds
  one row per organization, keyed by `organization_id`, with:
  - the plan (`starter`, `pro` or `business`, held by a CHECK);
  - add-ons (a text array);
  - a note from whoever set it;
  - when it was last set.
- [ ] **Set by the operator, never the app:** the app role may only read the table. The operator
  writes the row with the migration role (`ATESTA_MIGRATION_DATABASE_URL`), as for erasure
  (organization-closure spec):

  ```sql
  INSERT INTO subscriptions (organization_id, plan, addons, note)
  VALUES ('<org id>', 'pro', '{}', '<who and why>')
  ON CONFLICT (organization_id) DO UPDATE
    SET plan = EXCLUDED.plan, addons = EXCLUDED.addons, note = EXCLUDED.note,
        updated_at = now();
  ```
- [ ] **Default:** an organization with no row has the default plan, `business` (owner decision,
  2026-11-23). This covers every organization created before this change, so pilot
  organizations keep everything they use today.
- [ ] **Business opens every framework:** `catalog/plans.yaml` grants `business: all`, so a draft
  pack, a pack added later or a synthetic test pack never locks a business organization out.

**What the API refuses** (403, `{"code": "billing.plan_limit", "limit": <what>}`)
- [ ] **Connectors:** `POST /orgs/{org}/connections` when the organization already has as many
  connections as its plan allows (`limit: "connectors"`). Disconnected connections do not count.
  A downgrade never removes or stops a connection that already exists.
- [ ] **Evidence export:** `GET /orgs/{org}/frameworks/{key}/dossier` without
  `evidence_export` (`limit: "evidence_export"`).
- [ ] **Frameworks:** every route under `/orgs/{org}/frameworks/{key}`, read or write, when neither
  the plan nor an add-on grants that framework (`limit: "framework"`).
  - An unknown framework keeps its 404.
  - The plan check runs after the membership check, so a non-member still gets 404 and learns
    nothing about the plan.
- [ ] **Never gated:**
  - the organization export and closure (organization-closure spec, GDPR Art. 20);
  - members, invitations, activity and sign-in;
  - reading connections and scans already made.
- [ ] **Message:** the web shows `errors.billing.plan_limit` in ES and EN. It says the plan does
  not include this and names the next step. It never names a price.

**One place decides**
- [ ] Routes ask `billing.api` and nothing else (ADR-009, rule 8). No route compares plan names.

## Out of scope

- **Billing:** payments, invoices, prices and self-service plan changes.
- **Not built yet:** `daily_monitoring`, `policy_ai_review`, `questionnaire_autofill` and
  `trust_center` gate features that do not exist yet. Each one asks `has_feature` when it is
  built.
- **Levels within a framework:** a grant's `applies_to` list is not checked against a recorded
  scope. Only whole frameworks are gated.
- **Lists:** the overview, readiness and report still list every framework. Opening one the plan
  does not grant gets the message above.

## Design notes

- **Billing module:**
  - `models.py` holds `Subscription`.
  - `api.py` adds the following, all reading the row in the caller's RLS context:
    - `entitlements(session, org) -> Entitlements` (plan and add-ons, or the default);
    - `require_connector_slot(session, org, in_use)`;
    - `require_feature(session, org, feature)`;
    - `require_framework(session, org, framework_key)`.
  - `parse_grants` accepts `all` for a whole plan.
- **Compliance:** `plan_gate.framework_in_plan` is a dependency of every route under
  `/frameworks/{key}`. It runs after `require_member`, answers 404 for an unknown framework, then
  asks `billing.api`.
- **Connections:** the module counts its own non-disconnected connections and passes the count.
  Billing never reads another module's tables.
- **Migration** `0022_subscriptions`: the table, RLS, a SELECT grant for the app role and nothing
  more. Pilot organizations get no row, so the default applies to them.
- **Default:** the default plan is a constant in `billing.api`, `DEFAULT_PLAN`.
- **Known limit:** two connections created at the same instant could both pass the count. Plans
  are small and an admin creates connections by hand, so this is accepted for now.

## Test plan

- **Unit:**
  - plan contents (existing tests);
  - the default plan;
  - feature add-ons and framework add-ons;
  - `catalog/plans.yaml` opens every pack, and a synthetic one, to `business`; the ENS pack to
    `starter` and `pro`; NIS2 to neither.
- **Postgres:**
  - an organization with no row keeps working: a second connector, the dossier, a framework;
  - `starter`:
    - a second connector gets 403 `billing.plan_limit`;
    - a disconnected one frees the slot;
    - the dossier gets 403;
    - a framework the plan does not grant gets 403 on read and on write;
  - `pro` exports the dossier;
  - a non-member still gets 404;
  - another organization's plan never applies;
  - the app role cannot insert, update or delete a plan row;
  - the database refuses an unknown plan.
- **Contract and web:** `billing.plan_limit` is in the error-code list, with ES and EN messages.
