# Spec: organization data export and closure

- Issue: #156. Builds on `identity-auth.md`, `rbac.md` and ADR-012 (amendment 3 below).
- Status: built (2026-11-23: every acceptance criterion is implemented and covered by the tests its test plan names)

At the end of a contract, the customer either takes their data or has it deleted. As a processor,
Atesta must, "at the choice of the controller, delete or return all the personal data … after
the end of the provision of services". That is GDPR art. 28(3)(g), Official Journal L 119,
4.5.2016, as captured in `catalog/frameworks/gdpr_art32/SOURCES.md`.

## Acceptance criteria

**Export** (owner only)
- [ ] **Endpoint and content:** `GET /api/v1/orgs/{org}/export` returns a JSON file (`attachment`) with:
  - `format`, which is `atesta-organization-export/1`;
  - `exported_at`;
  - the organization;
  - one list per tenant table, holding that organization's rows, read under its RLS context;
  - the members' email and display name.
- [ ] **Left out:** columns that only reference secrets (connection credential references) and the hashes of invitation tokens.
- [ ] **Other roles:** 403 for every role but owner.
- [ ] **Audit:** `organization.exported`, with the row count per table and no content.

**Closure request** (owner only)
- [ ] **Request:** `POST /api/v1/orgs/{org}/closure` with `{"confirm_name": "<exact name>"}` records who asked and when. It answers with the erase date, 30 days later. A wrong name returns 422 `identity.closure_name_mismatch`.
- [ ] **Cancel:** `DELETE /api/v1/orgs/{org}/closure` cancels before the erase date.
- [ ] **Audit:** both are audited (`organization.closure_requested`, `organization.closure_cancelled`).
- [ ] **Visibility:** `/me` memberships carry `closure_erase_after`, so every member sees a banner with the date. Nothing else changes until erasure: the organization keeps working, so the export is still possible.

**Erasure** (operator, never the app)
- [ ] **Command:** `python -m apps.api.devtools.erase_org --org <id>` runs as `atesta_owner` through `ATESTA_MIGRATION_DATABASE_URL`.
- [ ] **Dry run by default:** it prints the rows it would delete per table. `--execute` deletes them.
- [ ] **Refusals:** it refuses an organization with no closure request, or one whose erase date has not passed.
- [ ] **Order:** it deletes every tenant table's rows for that organization, children first (FK order from the metadata), then the organization row.
- [ ] **Users:** it then deletes users left with no membership in any organization. Users who belong to other organizations stay.
- [ ] **Isolation:** another organization's rows are untouched.
- [ ] **Receipt:** a row in `erasure_receipts` with organization id, requested at, erased at, the operator's note and row counts per table, and no names or content.
- [ ] **Receipt table:** the app role has no privilege on it (ADR-012 amendment 3).

**Web**
- [ ] **Settings page:** an "Ajustes de la organización" page for owners, reachable from the navigation, with two parts:
  - export, a download link;
  - closure, a danger zone that asks for the exact name, then shows the erase date and a cancel button.
- [ ] **Everyone:** members see the closure banner.
- [ ] **Languages:** strings in ES and EN.

## Out of scope

- Binary evidence objects: there are none yet. When they arrive, erasure must remove them too, and their Object Lock retention needs a decision.
- Queue jobs: they hold ids only and expire on their own.
- Backups: they age out under the retention policy, which the DPA states.
- Self-service erasure without an operator.

## Test plan

- **Postgres:**
  - the export holds only the organization's rows and leaves out secret references and token hashes;
  - non-owners get 403;
  - closure needs the exact name, can be cancelled, and is audited;
  - the erase command refuses early or unrequested erasure;
  - it deletes everything of one organization, keeps another organization and shared users, deletes orphaned users, and writes a receipt;
  - the app role cannot read receipts.
- **Web unit:**
  - the settings page is for owners only;
  - export link;
  - the closure form needs the exact name;
  - cancel;
  - the banner.
