# Spec: roles and access (RBAC)

- Issue: #144. Builds on `identity-auth.md` and `insights.md` (owners).
- Status: built (2026-11-23: every acceptance criterion is implemented and covered by the tests its test plan names)

## Roles

| Role (stored) | Shown as | Can |
| --- | --- | --- |
| `owner` | Propietario / Owner | Everything, including roles and removing members |
| `admin` | Administrador / Administrator | Everything except changing roles |
| `member` | Colaborador / Contributor | Read everything a member reads. Record the assessment of measures **assigned to them**. Record evidence statements. |
| `auditor` | Auditor externo / External auditor | Read the workspace and export the statement of applicability, until an access end date. No writes, and no view of members, invitations or activity. |

The stored `member` value is unchanged, so no data migration is needed; only its label changes.

## Acceptance criteria

**Auditor access**
- [ ] **No writes, enforced in one place:** an auditor's write (POST, PUT, PATCH, DELETE) is refused (403) in `require_member`, whatever the endpoint. An endpoint added later cannot forget the check.
- [ ] **End date required:** every auditor membership has `access_expires_at`, held by a database CHECK. Once past, every request returns 403 `identity.access_expired`.
- [ ] **How an auditor is added:** an auditor invitation needs `access_expires_on`, from tomorrow to 365 days ahead; accepting it carries the date into the membership. Changing a member to auditor needs the same date; leaving the role clears it.

**Visibility**
- [ ] The members list needs `member` or above; auditors get 403. Invitations and activity stay admin-only.

**Contributor**
- [ ] A contributor records an assessment only for a measure whose current owner they are (403 `compliance.not_owner` otherwise).
- [ ] Admins still record any assessment. Scope, review and assignment stay admin-only.

**Web**
- [ ] **Labels and controls:** the new role labels in ES and EN. Invite and role-change forms ask for the end date when the role is auditor.
- [ ] **Navigation by role:** an auditor sees no Miembros, Invitaciones or Actividad, and sees a notice "Acceso de auditor hasta {date}". A contributor sees the assessment form only on their own measures.
- [ ] **Mi trabajo** (contributors and above) lists every measure assigned to the signed-in person across frameworks: framework, measure, due date, state, an overdue flag, and a link to the measure.

## Out of scope

- Per-framework roles, custom roles, SSO group mapping.
- Auditor-specific evidence packs, which wait for the auditor pack spec.

## Test plan

- **Postgres:**
  - an auditor reads the overview, the register and the export;
  - an auditor gets 403 on every write tried, and 403 on members;
  - an expired auditor gets 403 on reads;
  - an auditor invitation without a date returns 422, and one more than 365 days ahead returns 422;
  - accept carries the date;
  - role change to auditor needs a date, and from auditor clears it;
  - the CHECK refuses an auditor row without a date;
  - a contributor assesses their own measure (201) and not another's (403).
- **Web unit:** permissions, navigation per role, the auditor notice, Mi trabajo listing and the overdue flag, the date field shown for auditor invitations.
