# Spec: device agent (macOS), read-only posture reporting

- Issue: #154. Decision: ADR-014. Threat model: `docs/security/device-agent-threat-model.md`.
- Status: draft. **Build gate:** at least one design partner asks for device evidence, and the
  owner approves the start. Until then nothing below is built.

## Goal

An organization can show, with evidence, that the Macs its people use meet a small set of
security settings. Each person can see exactly what their Mac reports. Nothing on the Mac is ever
changed by Atesta.

## Checks (v1)

Every source command below is a **candidate**. Before the build, verify each one against Apple's
documentation for the supported macOS versions, as a standard user and without root. Replace it if
it needs privileges or a configuration profile.

| Check | Status rule | Value sent | Candidate source |
| --- | --- | --- | --- |
| Disk encryption | `pass` when FileVault is on | none | `fdesetup status` |
| Supported OS | `pass` when the version receives security updates | macOS version, such as `15.2` | `sw_vers`, compared with Apple's security releases page |
| Automatic security updates | `pass` when automatic security responses and system files install automatically | none | `softwareupdate` preferences |
| Firewall | `pass` when the application firewall is on | none | `socketfilterfw --getglobalstate` |
| System Integrity Protection | `pass` when enabled | none | `csrutil status` |
| Gatekeeper | `pass` when assessments are enabled | none | `spctl --status` |
| Screen lock | `pass` when a password is required within 5 minutes of sleep or screen saver | the delay in seconds | to be verified; may need an MDM profile |
| Malware protection | `pass` when XProtect is present and updated in the last 30 days | days since update | XProtect bundle version and date |

A check that cannot be read reports `unknown` with a reason code (`needs_privileges`,
`unsupported_version`, `not_found`), never a guess.

## Data boundary

- **What a report contains, and nothing else:**
  - the agent version;
  - a random device ID created at enrollment;
  - the device label;
  - the macOS version;
  - the time the checks ran;
  - for each check above, its key, status, reason code and the single value listed.
- **The device label** defaults to the Mac model plus the last four characters of the device ID,
  for example "MacBook Pro · 3f9a". It is not the hostname, which often contains a person's name.
  An administrator may rename it.
- **Assignment** to a person is optional. An administrator sets it in Atesta; the agent never
  reads the logged-in user.
- **Never collected:** file names or contents, installed applications, browsing history, location,
  Wi-Fi names, IP addresses beyond what the TLS connection shows the server, processes,
  screenshots, keystrokes, the serial number and the hostname.
- **Retention:** reports are kept for the organization's evidence period (default 24 months),
  then deleted by the retention job. Removing a device deletes its credential at once; its past
  reports stay as evidence until retention ends.

## Enrollment and transport

1. **Token:** an administrator creates an enrollment token in Atesta, valid for 7 days and a set
   number of devices. It is shown once; the API stores only its SHA-256.
2. **Delivery:** the token reaches the device through an MDM configuration, or the person pastes
   it into the agent.
3. **Exchange:** the agent exchanges it for a per-device credential, stored in the Keychain. The
   API stores only its hash.
4. **Reporting:** the agent reports once a day and when the person clicks "Check now". The request
   is `POST /api/v1/device-reports`, authenticated with the device credential, over TLS.
5. **Reply:** the server answers with `{"next_report_after": <seconds>}` only. The client ignores
   any other field.
6. **Updates:** a new agent version is a new signed, notarized package, deployed by the customer.
   There is no self-update channel in v1.

## Server side (sketch, for the build)

- **Tables,** all carrying `organization_id` and RLS (ADR-012):
  - `devices`: label, assigned member, enrolled and removed time, credential hash;
  - `device_enrollment_tokens`: hash, expiry, remaining uses;
  - `device_reports`: append-only, with the report body as JSON validated against the closed
    schema above.
- **Common control:** `ctl.endpoint_posture` (documentary plus technical). Each check becomes a
  check result `atesta-agent:<check>`, so framework packs map it like any other check (rule 9).
- **Audit events:** `device.enrolled`, `device.removed`, `device.renamed`,
  `device_token.created`, `device_token.revoked`.

## Product

- **Devices page** (admins, auditors read-only under the RBAC spec), with one row per device:
  - label, assigned person, last report and each check's state;
  - a filter for "needs attention";
  - an export of the device evidence.
- **Contributors** see only the devices assigned to them.
- **On the Mac:** a menu bar item opens "What Atesta sees on this Mac". It lists the exact report
  that was last sent, with a link to the organization's notice.

## Employee notice (template content)

The product will ship this template in Spanish and English through the i18n files, after legal
review. It is information for the customer to adapt, not legal advice. Its sections:

1. **Who is responsible.** The employer, as controller, and Atesta, as processor under the data
   processing agreement.
2. **Why.** To keep evidence that company devices meet the security measures required by
   [framework], and to protect the integrity of the devices.
3. **What is checked.** The list of checks and the exact fields in a report, copied from this
   spec.
4. **What is never collected.** The "never collected" list above, verbatim.
5. **What Atesta never does.** Atesta never changes a setting, never locks or erases the device,
   never runs commands and never reads files.
6. **Who sees it.** The organization's administrators, and external auditors with time-limited,
   read-only access.
7. **How long it is kept.** The retention period.
8. **How to see it.** The "What Atesta sees on this Mac" window.
9. **Your rights.** How to exercise your data protection rights, and who to contact.
10. **Device-use criteria.** Under LOPDGDD art. 87.3, the employer sets device-use criteria with
    workers' representatives taking part, and informs workers of them. This notice should be
    part of, or refer to, those criteria.

Legal source for item 10: Ley Orgánica 3/2018, art. 87, consolidated BOE text
(`https://www.boe.es/buscar/act.php?id=BOE-A-2018-16673`, captured 2026-11-23, SHA-256
`c35fac0414e15487baab959ddcaa548e71369fabd6184ea7cfa65ecc78ca8b02`).
- **Art. 87.3** requires the employer to set device-use criteria that respect minimum privacy
  standards, with workers' representatives taking part, and to inform workers of them.
- **Art. 87.2** limits the employer's access to content to controlling work obligations and
  ensuring device integrity. The agent reads no content.

Whether a data protection impact assessment (GDPR art. 35) is needed is for the customer's DPO to
decide. Atesta provides this spec and the threat model as input.

## Acceptance criteria (for the build)

- [ ] **Read-only:** every check runs as the logged-in standard user with read-only system calls.
  A test inventory proves that no call writes, launches, or changes settings.
- [ ] **Closed schema:**
  - a report with any field outside the closed schema is refused by the API (422) and never
    stored;
  - the client is unit-tested to build only that schema.
- [ ] **No remote instructions:** the client ignores every reply field except
  `next_report_after`. A test sends a malicious reply and observes no action.
- [ ] **Enrollment:**
  - tokens are single-display;
  - tokens and credentials are stored only as hashes;
  - an expired, used-up or revoked token is refused;
  - removing a device revokes its credential immediately.
- [ ] **Tenant isolation:** device tables pass the RLS guard tests. A device credential can write
  only its own organization's reports.
- [ ] **Transparency:** the "What Atesta sees on this Mac" window shows the last report
  byte-for-byte.
- [ ] **Signing:** packages are signed and notarized, verified with `spctl --assess` in CI on a
  macOS runner.
- [ ] **Languages and audit:** user-facing strings exist in ES and EN, and audit events are
  emitted.

## Out of scope

- Remediation, remote lock or wipe, and the software inventory.
- Windows and Linux.
- An auto-update channel.
- Continuous monitoring beyond the daily report.

## Test plan (for the build)

- **Swift unit tests** for each check parser, using recorded outputs from supported macOS
  versions.
- **A schema contract test** shared by the client and the API.
- **API tests** on real Postgres: enrollment, revocation, RLS and schema refusal.
- **A manual run** on a clean Mac with a standard user, recorded as evidence.
