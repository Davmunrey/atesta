# Runbook: customer offboarding (export, closure, erasure)

- **When:** a customer ends its contract, or asks for its data to be deleted.
- **Specs:** `docs/specs/organization-closure.md`, `docs/specs/operator-portal.md` ("Erasure").
  ADR-012 amendment 3, ADR-017.
- **Who:** the customer's owner exports and may request the closure in the app. Operator portal
  admins ask for the export, start or follow the closure, and request and approve the erasure.
  The erasure runner executes it.
- **Legal basis:** as processor, Atesta deletes or returns all personal data at the end of the
  service, at the controller's choice (GDPR art. 28(3)(g)).

## Steps

1. **Written request.** Record the customer's request in the support ticket: who asked, their
   role, the date, and whether they want the data returned, deleted, or both. Only an owner
   closes an organization from the app. If the requester is not an owner, ask an owner to act.
2. **Return (if asked).** In the portal, *Exportación y cierre → Pedir a los propietarios que
   exporten* emails every owner and records the request in their Activity, as done by the Atesta
   team. The
   owner opens *Ajustes → Exportar los datos* and downloads the JSON export. Credential references
   and invitation token hashes are left out by design. **Atesta staff never download it on the
   customer's behalf**, and the portal has no way to.
3. **Closure.** Either:
   - the owner opens *Ajustes → Cerrar la organización* and types the name. Only the owner can
     cancel it; or
   - an admin, on the customer's written request, chooses *Iniciar el cierre* in the portal, with
     the typed name and a sign-in within the last 15 minutes. Only a portal admin can cancel it.

   Every member then sees the erase date, 30 days later, and owners get a service notice.
4. **Connected tenants.** Ask the customer to remove Atesta's application from their Microsoft
   Entra ID or Google Workspace admin console. Atesta's access is read-only, but removing the
   consent is the customer's own control. Note in the ticket when they confirm.
5. **Erasure request.** An admin chooses *Borrado → Pedir el borrado*, with the typed name and the
   ticket in the internal reason. The organization must already be closing. It can be done at any
   time during the 30 days; nothing is deleted before the erase date.
6. **Approval, two people.**
   - **Two or more admins:** a second admin opens the organization, checks the ticket, and
     chooses *Aprobar el borrado* with the typed name, within 7 days of the request. The requester
     cannot approve their own request.
   - **One admin:** the same admin approves only 72 hours after the request (owner answer 3).
   - **Expiry:** a request not approved within 7 days expires. Request it again.
   - **Cancel:** until it runs, any admin can choose *Cancelar la solicitud de borrado*.
7. **Execution.** The erasure runner starts every 6 hours. It erases each approved, uncancelled
   request whose erase date has passed. Every tenant row of the organization is deleted, then
   the users left without any organization. If the owner cancelled the closure, the runner refuses
   the request.
8. **Receipt.** *Organizaciones borradas* lists the receipt: the organization id, the closure and
   erase dates, and the rows deleted. It holds no names. The request shows *Ejecutada* with the
   receipt id, and *Registro de operaciones* shows "Se ejecutó el borrado". Paste the receipt id
   in the ticket and close it with the customer's confirmation.

## If the runner fails

The alarm `<env>-erasure-runner` emails the alerts address when a run fails or none finishes in a
day. Read the log group `/atesta/<env>/erasure`: each request has one line, and the last line has
the run's status. A refusal (`refused: …`) names the request and why. To run one request by hand,
first as a dry run, use the one-off task of `operator-staff.md`, "Running a staff command in
AWS":

```bash
run_ops atesta_api.ops.erase --request <request id>            # dry run: row counts only
run_ops atesta_api.ops.erase --request <request id> --execute
```

From a local checkout with the migration credential, `uv run python -m apps.api.devtools.erase_org`
takes the same arguments. Without an approved request, both refuse. There is no other way to erase.

## Billing details after erasure

`billing_profiles` is erased with the organization. Atesta's copy is a working copy. The invoices
and accounting records that tax and commercial law require keeping live in the owner's invoicing
system: RD 1619/2012 art. 19, and Código de Comercio art. 30 (six years). **Candidate, open for
the owner's tax adviser** (spec, "Owner answers" 4): if the adviser says Atesta itself must keep
them, the rows are blocked under LOPDGDD art. 32, readable by no role, and destroyed when the
period ends. Until the adviser answers, erasure deletes them.

## What erasure does not reach yet

- **Backups** age out under the backup retention policy stated in the DPA; they are not edited.
- **Evidence files and scan outputs** in the evidence bucket: erasure deletes database rows only.
  The objects stay under the bucket's one-year lock; their deletion and the lock's retention are
  an open decision (organization-closure spec, "Out of scope"). Note it in the ticket.
- **Queue jobs** carry ids only and expire on their own.
- **Logs** never contain customer content (AGENTS.md rule 2) and expire with their retention.
- **The operator trail** keeps the ids and actions of what staff did, and outlives erasure by
  design (ADR-017, "Audit").
