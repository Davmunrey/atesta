# Runbook: plans and trials

- **When:** a customer signs a contract, changes plan or add-ons, or its trial ends.
- **Specs:** `docs/specs/operator-portal.md`, `docs/specs/billing-entitlements.md`. ADR-009
  amendments 2 and 3 (no payment gateway: customers are invoiced).
- **Who:** an operator portal admin or billing member. The owner's invoicing system issues the
  invoices; Atesta stores only the billing details used on them.

## How a customer starts

Customers onboard themselves (ADR-017, owner decision 3). Their organization starts a 14-day
trial with full access. When it ends with no plan set, the organization becomes read-only:
members can still read and export, and every write gets `billing.trial_ended`. The trial end date
is in the portal, in the organization's detail.

## After a contract is signed and invoiced

1. **Find the organization:** *Organizaciones*, search by name. Check the name and the creation
   date with the customer's contact, so you do not change the wrong one. The search is recorded
   in the operator trail.
2. **Billing details:** *Datos de facturación → Datos para las facturas*: legal name, NIF, address,
   province or region, country (two letters, for example `ES`) and billing email. Copy them from
   the signed order form, never from an email alone. The internal reason names the contract or
   ticket. The customer sees in its Activity that the billing details changed (field names only).
3. **Plan:** *Plan → Cambiar el plan*. Choose the plan and the add-ons in the contract. *Qué cambia*
   shows the connection limit and the features gained or lost. The optional plan note is the
   customer's own row: put nothing internal there. The internal reason names the contract.
4. **Check:** the detail shows the plan with *Fijado el* (today) and no trial notice. The
   customer's Activity shows "Equipo de Atesta" changed the plan.
5. **Invoice** from the invoicing system, with the details from step 2.

Setting a plan ends the read-only state of an ended trial at once: no deploy, no other step.

## Trials

- **Following up:** filter *Plan: Por defecto (sin plan fijado)* to see organizations still on the
  trial or past it, and *Sin datos de facturación* for those missing billing details.
- **A trial that ended:** the organization is read-only, and nothing is deleted. Contact the owner.
  If they sign, follow the section above. If they do not, leave it read-only, or start the
  offboarding (`offboarding.md`) when the owner asks for it.
- **Extending a trial:** not possible in the portal. No role but the migration role writes
  `trial_ends_at` (spec, "Database layer"), and the portal cannot remove a plan once set. If the
  owner of Atesta agrees to more time, set the plan the customer is testing, with the reason
  "trial extension until <date>, <ticket>". If they do not sign by that date, suspend the
  organization with *Contrato finalizado* (below) instead of leaving the plan on.

## Non-payment

1. Confirm the unpaid invoice in the invoicing system, and that the customer was reminded.
2. An admin suspends the organization: *Suspensión → Suspender la organización*, with the reason
   *Pago pendiente*, the typed name and the internal reason. Suspending needs a sign-in in the
   last 15 minutes. If the portal asks, choose *Volver a iniciar sesión*.
3. Members then see the suspension page. Owners can still export, close the organization and
   read the billing details. Owners and admins receive a service notice. Nothing is deleted.
4. When it is settled: *Reactivar la organización*. Every row is as it was.

## When the portal is not available

The SQL in `billing-entitlements.md` ("Plan setting") stays the fallback only while the portal is
not deployed (ADR-017, "Set the plan and add-ons"). It needs the migration credential, which can
read every customer's content, and it writes neither trail: the customer's Activity shows nothing.
Record who ran it, when and why in the ticket, and set the same plan again in the portal once it
is up, so both trails hold it.
