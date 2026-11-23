# Prowler coverage for Microsoft 365 and Google Workspace

A scanner note, not a spec. It records, for the pinned engine, where each check lands in the
common controls, how Prowler's own compliance mappings compare with Atesta's, and what the
PowerShell-backed M365 checks need. The rules live in the
[scanner-connectors spec](../specs/scanner-connectors.md) (D1, D3, D6) and in
`atesta_core.exclusions`; this note does not change them.

State as of #242 (issues #233 and #234). Written 2026-11-23.

## Sources

- **Engine:** Prowler `5.49.0` (`scanner/requirements.in`), cloned at that tag (commit
  `9cd1a8ee450049195b1484e274fa626b72bd26e7`) as a read-only reference. Nothing was run against a
  tenant.
- **Check lists:** `scanner/expected/5.49.0/{m365,googleworkspace,m365-powershell}.json`
  (see [its README](../../scanner/expected/README.md) for hashes). Severity and service come from
  each check's `*.metadata.json` at the tag.
- **Prowler compliance files:** `prowler/compliance/` at `5.49.0`, and
  `prowler/compliance/m365/ens_rd2022_m365.json` at `5.52.0` (added in `5.51.0`).
- **ENS ground truth:** CCN-STIC 808 (April 2026 edition) and the 885A, 885B, 885C, 885D and
  888A configuration guides, cited by section and page. No guide text is reproduced.
- **ISO/IEC 27001 and CIS:** identifiers only; no text from those standards.

## The 214 checks

| Status | M365 | Google | Total |
|---|---:|---:|---:|
| Run today | 92 | 60 | 152 |
| Wait for PowerShell (D1, `not_granted` until PR 10) | 54 | 0 | 54 |
| Never run (D3 `not_granted`, D6 `excluded`) | 3 | 5 | 8 |
| **Listed by the pinned engine** | **149** | **65** | **214** |

Severity across the 214: 12 critical, 65 high, 125 medium, 12 low.

The 206 checks that run today or after PR 10 each feed exactly one control.
`apps/api/tests/test_catalog_checks.py` asserts it, together with two more rules. No control lists
a check that never runs. And a control with a PowerShell-backed check holds only such checks,
because one `not_evaluated` check keeps a control from passing (`atesta_core.controls`).

### By service

| Provider | Service | Checks | Critical / high / medium / low | PowerShell | Never run | Controls |
|---|---|---:|---|---:|---:|---|
| Google | additionalservices | 1 | 0 / 0 / 1 / 0 | 0 | 0 | `workspace_collaboration` |
| Google | calendar | 3 | 0 / 0 / 3 / 0 | 0 | 0 | `workspace_collaboration` |
| Google | chat | 6 | 0 / 0 / 5 / 1 | 0 | 0 | `app_governance`, `workspace_collaboration` |
| Google | directory | 2 | 0 / 2 / 0 / 0 | 0 | 0 | `privileged_accounts` |
| Google | drive | 11 | 0 / 0 / 11 / 0 | 0 | 3 | `device_management`, `workspace_collaboration`, `workspace_sharing` |
| Google | gmail | 17 | 0 / 0 / 17 / 0 | 0 | 0 | `app_governance`, `email_protection`, `workspace_collaboration` |
| Google | groups | 3 | 0 / 0 / 3 / 0 | 0 | 0 | `workspace_collaboration` |
| Google | marketplace | 1 | 0 / 0 / 1 / 0 | 0 | 0 | `app_governance` |
| Google | rules | 8 | 0 / 2 / 4 / 2 | 0 | 0 | `workspace_security_alerts` |
| Google | security | 12 | 0 / 5 / 7 / 0 | 0 | 2 | `app_governance`, `password_and_recovery`, `privileged_accounts`, `user_authentication`, `workspace_mfa` |
| Google | sites | 1 | 0 / 0 / 1 / 0 | 0 | 0 | `workspace_collaboration` |
| M365 | admincenter | 7 | 0 / 3 / 4 / 0 | 3 | 0 | `exchange_access_hardening`, `m365_external_sharing`, `password_and_recovery`, `privileged_accounts`, `teams_external_access` |
| M365 | defender | 18 | 1 / 3 / 11 / 3 | 17 | 0 | `email_protection`, `m365_mail_threat_policies` |
| M365 | defenderidentity | 1 | 0 / 0 / 1 / 0 | 0 | 0 | `hybrid_identity` |
| M365 | defenderxdr | 2 | 1 / 0 / 1 / 0 | 0 | 2 | none |
| M365 | entra | 81 | 5 / 26 / 45 / 5 | 0 | 1 | `admin_mfa`, `app_governance`, `application_consent`, `conditional_access_coverage`, `device_management`, `directory_governance`, `hybrid_identity`, `legacy_authentication`, `m365_external_sharing`, `password_and_recovery`, `privileged_accounts`, `sign_in_controls`, `user_authentication` |
| M365 | exchange | 17 | 1 / 8 / 7 / 1 | 17 | 0 | `exchange_access_hardening`, `m365_audit_logging`, `m365_mail_threat_policies`, `mailbox_audit_bypass` |
| M365 | intune | 1 | 0 / 1 / 0 / 0 | 0 | 0 | `device_management` |
| M365 | purview | 1 | 1 / 0 / 0 / 0 | 1 | 0 | `m365_audit_logging` |
| M365 | sharepoint | 5 | 0 / 5 / 0 / 0 | 0 | 0 | `app_governance`, `device_management`, `m365_external_sharing` |
| M365 | teams | 16 | 3 / 10 / 3 / 0 | 16 | 0 | `teams_external_access` |

### Checks in no control

The eight never-run checks, on purpose (#233):

| Check | Reason |
|---|---|
| `defenderxdr_critical_asset_management_pending_approvals` | D3: needs `ThreatHunting.Read.All`, never requested |
| `defenderxdr_endpoint_privileged_user_exposed_credentials` | D3 |
| `entra_app_registration_no_unused_privileged_permissions` | D3 |
| `drive_shared_drive_disable_download_print_copy` | D6: asks for an `apps.licensing` token, which has no read-only variant |
| `drive_shared_drive_managers_cannot_override` | D6 |
| `drive_shared_drive_members_only_access` | D6 |
| `security_dlp_drive_rules_configured` | D6 |
| `security_session_duration_limited` | D6 |

The guides of the controls that listed them say these aspects need documentary evidence.

## Coverage by control

All mappings are candidates (`reviewed_by: null`).

| Control | Provider | Checks | Run today | Wait for PowerShell | ENS | NIS2 | GDPR | DORA |
|---|---|---:|---:|---:|---|---|---|---|
| `ctl.admin_mfa` | M365 | 1 | 1 | 0 | op.acc.6 | art21.2j | art32.1b | c2.art9 |
| `ctl.app_governance` | Google + M365 | 15 | 15 | 0 | op.acc.4, op.acc.6, op.exp.3 | art21.2i | art32.1b | c2.art9 |
| `ctl.application_consent` | M365 | 1 | 1 | 0 | op.acc.4 | — | — | — |
| `ctl.conditional_access_coverage` | M365 | 17 | 17 | 0 | op.acc.6, op.exp.3 | art21.2i | art32.1b | c2.art9 |
| `ctl.device_management` | Google + M365 | 18 | 18 | 0 | mp.eq.3, op.exp.2 | art21.2i | art32.1b | c2.art9 |
| `ctl.directory_governance` | M365 | 8 | 8 | 0 | op.acc.3, op.acc.4 | art21.2i | art32.1b | c2.art9 |
| `ctl.email_protection` | Google + M365 | 14 | 14 | 0 | mp.s.1 | — | art32.1b | c2.art9 |
| `ctl.exchange_access_hardening` | M365 | 10 | 0 | 10 | op.acc.1, op.acc.6, op.exp.2 | art21.2j | — | c2.art9 |
| `ctl.hybrid_identity` | M365 | 5 | 5 | 0 | op.acc.6 | art21.2i | — | c2.art9 |
| `ctl.legacy_authentication` | M365 | 1 | 1 | 0 | op.acc.6 | art21.2j | — | c2.art9 |
| `ctl.m365_audit_logging` | M365 | 3 | 0 | 3 | op.exp.8 | — | — | c2.art10 |
| `ctl.m365_external_sharing` | M365 | 8 | 8 | 0 | op.acc.4 | art21.2i | art32.1b | — |
| `ctl.m365_mail_threat_policies` | M365 | 22 | 0 | 22 | mp.s.1, op.exp.6 | — | art32.1b | c2.art9 |
| `ctl.mailbox_audit_bypass` | M365 | 1 | 0 | 1 | op.exp.8 | — | — | c2.art10 |
| `ctl.password_and_recovery` | Google + M365 | 7 | 7 | 0 | op.acc.5, op.acc.6 | art21.2j | art32.1b | c2.art9 |
| `ctl.privileged_accounts` | Google + M365 | 12 | 12 | 0 | op.acc.4 | art21.2i | art32.1b | c2.art9 |
| `ctl.sign_in_controls` | M365 | 5 | 5 | 0 | op.acc.6 | art21.2i | art32.1b | c2.art9 |
| `ctl.teams_external_access` | M365 | 18 | 0 | 18 | op.acc.4, op.exp.2 | art21.2i | art32.1b | — |
| `ctl.user_authentication` | Google + M365 | 9 | 9 | 0 | op.acc.5, op.acc.6 | art21.2j | art32.1b | c2.art9 |
| `ctl.workspace_collaboration` | Google | 21 | 21 | 0 | op.acc.4 | art21.2i | art32.1b | c2.art9 |
| `ctl.workspace_mfa` | Google | 1 | 1 | 0 | op.acc.6 | art21.2j | art32.1b | c2.art9 |
| `ctl.workspace_security_alerts` | Google | 8 | 8 | 0 | op.mon.1 | art21.2b | — | c2.art10 |
| `ctl.workspace_sharing` | Google | 1 | 1 | 0 | — | — | art32.1b | — |

### Weak coverage

- **No result until PR 10.** Five controls hold only PowerShell-backed checks:
  `mailbox_audit_bypass`, `m365_mail_threat_policies`, `m365_audit_logging`,
  `exchange_access_hardening` and `teams_external_access`. Until the permission lands, ENS mp.s.1
  for M365 rests on one check (`defender_domain_dmarc_records_published` in `email_protection`),
  and op.exp.8 has no automated M365 evidence at all.
- **One check each:** `admin_mfa`, `application_consent`, `legacy_authentication`, `workspace_mfa`
  and `workspace_sharing`. One PASS says little about the measure.
- **Unmapped where you would expect a mapping:**
  - `workspace_sharing` has no ENS mapping, because 888A gives no Drive-sharing section to cite.
    It sits beside `workspace_collaboration`, which already reaches op.acc.4.
  - `email_protection` and `m365_mail_threat_policies` have no NIS2 mapping.
  - `application_consent` appears only in ENS.
- **Broad controls:** `workspace_collaboration` (21 checks across seven Google services) and
  `m365_mail_threat_policies` (22) fail as a whole if one check fails, so the finding detail is
  what tells the customer where to act.
- **Narrowed by #233:** `app_governance`, `directory_governance`, `privileged_accounts`,
  `sign_in_controls` and `workspace_collaboration` no longer claim the never-run aspects.
- **`no_findings`:** a check with no finding (for example, a tenant without the licence or the
  feature) is `not_evaluated`, so its control has no result. This is by design (ADR-005).

## Prowler's own compliance mappings

Prowler's mappings are a hint, not ground truth. None of them was copied into the catalog.

| File (at 5.49.0 unless noted) | Requirements | With M365 or Google checks | Distinct checks | Checks in an Atesta control |
|---|---:|---:|---:|---:|
| `m365/cis_7.0_m365.json` (also 4.0, 6.0) | 160 | 115 | 113 | 113 |
| `m365/iso27001_2022_m365.json` | 45 | 45 | 86 | 83 |
| `m365/prowler_threatscore_m365.json` | 64 | 64 | 68 | 66 |
| `googleworkspace/cis_1.4_googleworkspace.json` (also 1.3) | 86 | 64 | 63 | 58 |
| `googleworkspace/cisa_scuba_0.6_googleworkspace.json` | 133 | 50 | 50 | 47 |
| `cis_controls_8.1.json` (multi-provider) | 153 | 29 | 109 | 103 |
| `cmmc_2.0.json` (multi-provider) | 149 | 36 | 67 | 67 |
| `fedramp_20x_ksi_2026.json` (multi-provider) | 46 | 15 | 67 | 67 |
| `m365/ens_rd2022_m365.json` (5.51.0 and later) | 81 | 24 | 30 | 30 |

The checks missing from the last column are the eight never-run ones.

- **NIS2, GDPR, DORA.** Prowler maps these for AWS, Azure and GCP only. `dora_2022_2554.json`
  lists no M365 or Google check. Atesta's mappings for these packs are its own.
- **ENS for M365 (Prowler 5.51.0+).** Built from the 885A-D guides. Of its 30 mapped checks, 28
  land in Atesta on a control mapped to the same measure. The other two were reviewed and not
  adopted:
  - `entra_conditional_access_policy_mdm_compliant_device_required`: Prowler maps it to
    op.acc.6, reinforcement R9 (remote access). R9 asks for authorization, encryption and logging
    of remote access. Device compliance fits Atesta's `device_management` (mp.eq.3, op.exp.2)
    better.
  - `entra_policy_restricts_user_consent_for_apps`: Prowler maps it to op.exp.2. Atesta keeps it in
    `app_governance` (op.acc.4, op.exp.3). User consent is an access-rights decision, and
    op.exp.3 is the configuration management measure. A reviewer may add op.exp.2.

  Prowler's file also has 57 manual requirements without checks. Their descriptions follow the
  885 guides and could inform `manual: true` guides once reviewed.
- **ENS for Azure (5.49.0).** `azure/ens_rd2022_azure.json` uses Azure provider check ids,
  not M365 ones, and maps loosely (op.mon.1 to security defaults, for example). It was not used.
- **ISO/IEC 27001:2022.** Atesta's pack is a template, with no requirements until licensed text
  is available. Prowler's M365 file maps checks to 45 Annex A identifiers, many very broadly; it
  ties mail policies to A.5.2, for example. The useful part, as identifiers only:

  | Annex A | Atesta controls |
  |---|---|
  | A.5.15, A.5.17, A.8.2, A.8.5 | identity controls: `admin_mfa`, `user_authentication`, `conditional_access_coverage`, `privileged_accounts`, `legacy_authentication`, `hybrid_identity` |
  | A.5.14, A.5.33, A.6.7 | sharing controls: `m365_external_sharing`, `teams_external_access`, `exchange_access_hardening` |
  | A.8.7 | `m365_mail_threat_policies`, `teams_external_access` |
  | A.8.15, A.5.28 | `m365_audit_logging` |

  Treat the rest as noise until a reviewer maps the pack.
- **CIS.** CIS M365 7.0 references 113 of the M365 checks; all are in an Atesta control. CIS
  Google 1.4 references 63, 58 of them in a control. CIS benchmark text is licensed, so only
  identifiers would ever enter the catalog.

## PowerShell-backed M365 checks

The 54 checks in `m365-powershell.json`, found by `scanner/tools/powershell_checks.py`, read
data that Prowler collects only through two PowerShell sessions:

| Session | Services (checks) | Connect, certificate path |
|---|---|---|
| Exchange Online | exchange 17, defender 17, admincenter 3, purview 1 (38) | `Connect-ExchangeOnline -Certificate $certificate -AppId $clientID -Organization $tenantDomain` (`m365_powershell.py:234`) |
| Microsoft Teams | teams 16 | `Connect-MicrosoftTeams -Certificate $certificate -ApplicationId $clientID -TenantId $tenantID` (`m365_powershell.py:198`) |

### Cmdlets at 5.49.0

`prowler/providers/m365/lib/powershell/m365_powershell.py` calls only `Get-*` cmdlets to collect
data:

- **Exchange:** `Get-AdminAuditLogConfig`, `Get-AntiPhishPolicy`, `Get-AntiPhishRule`,
  `Get-ApplicationAccessPolicy`, `Get-AtpPolicyForO365`, `Get-ATPProtectionPolicyRule`,
  `Get-DkimSigningConfig`, `Get-EmailTenantSettings`, `Get-EOPProtectionPolicyRule`,
  `Get-EXOMailbox`, `Get-ExternalInOutlook`, `Get-HostedConnectionFilterPolicy`,
  `Get-HostedContentFilterPolicy`, `Get-HostedContentFilterRule`,
  `Get-HostedOutboundSpamFilterPolicy`, `Get-HostedOutboundSpamFilterRule`,
  `Get-MailboxAuditBypassAssociation`, `Get-MalwareFilterPolicy`, `Get-MalwareFilterRule`,
  `Get-OrganizationConfig`, `Get-OwaMailboxPolicy`, `Get-ReportSubmissionPolicy`,
  `Get-RoleAssignmentPolicy`, `Get-SafeAttachmentPolicy`, `Get-SafeAttachmentRule`,
  `Get-SafeLinksPolicy`, `Get-SafeLinksRule`, `Get-SharingPolicy`, `Get-TeamsProtectionPolicy`,
  `Get-TransportConfig`, `Get-TransportRule`, `Get-User`.
- **Teams:** `Get-CsTeamsClientConfiguration`, `Get-CsTeamsMeetingPolicy`,
  `Get-CsTeamsMessagingPolicy`, `Get-CsTenantFederationConfiguration`.

The other cmdlets in the file, and why Atesta never reaches them:

| Cmdlet | Where | Atesta |
|---|---|---|
| `Install-Module ... -Force` | `--init-modules` only (`m365_powershell.py:1162`) | Never passed. Modules are baked into the image; nothing installs at scan time (spec, Image) |
| `Invoke-RestMethod` (token endpoint), `Get-MsalToken` | Client-secret path (`m365_powershell.py:155`, `:180`, `:212`) | Not used: Atesta authenticates with a certificate (`--certificate-auth`, `scanner/atesta_scanner/invocation.py`) |
| `Set-OrganizationConfig` | The only M365 fixer, `exchange_organization_delicensing_resiliency_enabled_fixer.py` | Never run: the wrapper never passes `--fixer` (spec, Image) |

### Permissions and rule 1

- **Exchange session.** It needs the application permission `Exchange.ManageAsApp` on Office 365
  Exchange Online (admin consent), plus an Entra directory role assigned to the app. Prowler
  documents Global Reader
  (`docs/user-guide/providers/microsoft365/authentication.mdx`, "Grant PowerShell Module
  Permissions"). The permission name says "Manage", but the session's rights come from the role
  (spec, expected set v2). With Global Reader, every cmdlet above is a read.
- **Teams session.** It needs the same directory role. Prowler's docs also list
  `application_access` on the Skype and Teams Tenant Admin API. The spec never requests it,
  because the certificate path does not use it. That Global Reader suffices for the `Get-Cs*`
  cmdlets is still a candidate until the live golden in PR 10.
- **Verdict.** No PowerShell-backed check needs a write scope, and the code paths Atesta runs
  issue only reads. All 54 do need admin consent to an application permission and a directory
  role. Microsoft labels Global Reader privileged, and it carries two Service Health `allTasks`
  actions (spec, D1). So all 54 stay **excluded** (`not_granted`) until the owner decides D1 and
  counsel clears D11 (module licence terms). The alternative in D1, a custom Exchange role group,
  would cover the 38 Exchange-session checks without an Entra role. The 16 Teams checks would
  still need one.
- **Not verified.** Whether `Get-EXOMailbox` and `Get-User` return more fields than the checks
  need, for example mailbox metadata of every user, is a candidate for the PR 10 data-minimization
  review. Rule 2 applies to anything logged from them.

## Owner-pending conflicts (not resolved here)

| Topic | Checks (control) | Conflict |
|---|---|---|
| Password expiry | `admincenter_settings_password_never_expire` (`password_and_recovery`) | Prowler passes only when passwords never expire; CCN-STIC 808 checks password rules against the organization's own policy (op.acc.5 p. 37, op.acc.6 p. 41) |
| Lockout | `entra_password_protection_lockout_threshold_limited`, `entra_password_protection_lockout_duration_configured` (`password_and_recovery`) | Threshold and duration values to accept for ENS |
| SMS MFA | `entra_authentication_method_sms_voice_disabled` (`user_authentication`) | Whether SMS and voice are an acceptable factor at each ENS level |

## Newer Prowler releases

5.50.0, 5.51.0 and 5.52.0 add or remove no M365 or Google Workspace check. 5.51.0 adds the ENS
M365 compliance file used above. 5.52.0 fixes a `KeyError` in two Defender outbound-spam checks
(both PowerShell-backed). The upgrade is written up in #243; the pin is unchanged.

## Reproduce

```bash
git clone --depth 1 --branch 5.49.0 https://github.com/prowler-cloud/prowler.git <empty dir>
# Inventory: join scanner/expected/5.49.0/*.json with each check's *.metadata.json and with
# catalog/controls/*.yaml (prowler_checks); never run Prowler against a tenant for this.
uv run pytest -q apps/api/tests/test_catalog_checks.py
```
