# Runbook: customer offboarding (export, closure, erasure)

- **When:** a customer ends its contract, or asks for its data to be deleted.
- **Spec:** `docs/specs/organization-closure.md`. ADR-012 amendment 3.
- **Who:** the customer's owner does steps 1 to 3 in the app; an Atesta operator does steps 4 to 6.
- **Legal basis:** as processor, Atesta deletes or returns all personal data at the end of the service, at the controller's choice (GDPR art. 28(3)(g)).

## Steps

1. **Written request.** Record the customer's request in the support ticket: who asked, their role, the date, and whether they want the data returned, deleted, or both. Only an owner can close an organization; if the requester is not the owner, ask the owner to act.
2. **Return (if asked).** The owner opens *Ajustes → Exportar los datos* and downloads the JSON export. It holds every row the organization recorded. Credential references and invitation token hashes are left out by design. Atesta staff never download it on the customer's behalf.
3. **Closure request.** The owner opens *Ajustes → Cerrar la organización* and types the organization's name. From then on every member sees the erase date, 30 days later. The owner can cancel until that date.
4. **Connected tenants.** Ask the customer to remove Atesta's application from their Microsoft Entra ID or Google Workspace admin console. Atesta's access is read-only, but removing the consent is the customer's own control. Note in the ticket when they confirm.
5. **Dry run, after the erase date.** An operator with the migration credentials runs:
   ```bash
   uv run python -m apps.api.devtools.erase_org --org <organization id> --note "<ticket reference>"
   ```
   The command refuses an organization without a closure request, or whose date has not passed. Read the row counts and paste them in the ticket.
6. **Erasure.** Run the same command with `--execute`. Every tenant row of the organization is deleted, then the users left without any organization. A receipt with the row counts and the note stays in `erasure_receipts`. Paste the output in the ticket and close it with the customer's confirmation.

## What erasure does not reach yet

- **Backups** age out under the backup retention policy stated in the DPA; they are not edited.
- **Binary evidence files** do not exist yet. When they do, this runbook gains a step.
- **Queue jobs** carry ids only and expire on their own.
- **Logs** never contain customer content (CLAUDE.md rule 2) and expire with their retention.
