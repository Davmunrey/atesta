# Threat model: device agent (macOS)

- **Scope:** the design in `docs/specs/device-agent.md` and ADR-014.
- **Status:** draft. Review it again before the build, and after every change to the data boundary.
- **Method:** STRIDE per component.

## Components and trust boundaries

1. **The agent** runs on the employee's Mac as the logged-in standard user. It is trusted to read
   configuration, and never trusted to decide anything on the server.
2. **The enrollment token** travels from an Atesta administrator to the device, through MDM or
   copy and paste.
3. **The device credential** is kept in the macOS Keychain, in the agent's access group.
4. **The report channel** is TLS from the agent to the API in eu-south-2.
5. **The API** authenticates the device, validates the report against the closed schema, and
   stores it under the organization's RLS context.
6. **Atesta's signing and notarization keys** are custodied by the owner.

## Threats and mitigations

| # | Component | STRIDE | Threat | Mitigation in the design |
| --- | --- | --- | --- | --- |
| T1 | API ↔ agent | Elevation / Tampering | A compromised or malicious Atesta server tells agents to run commands, fleet-wide. | No command channel exists: the client parses only `next_report_after` and ignores everything else (acceptance test with a malicious reply). The binary contains no code path that executes server-supplied content. |
| T2 | Distribution | Tampering | A modified agent package spreads through a customer's MDM. | Developer ID signing and notarization. `spctl --assess` in CI. Keys held by the owner, not in CI secrets, until a hardware-backed signing service is decided. |
| T3 | Agent | Information disclosure | The agent collects more than declared (files, apps, names), by bug or by design creep. | A closed report schema on both sides; the API refuses unknown fields (422). Adding a field needs a spec change, a notice update and review (ADR-014). The hostname, serial and user name are never read. |
| T4 | Enrollment token | Spoofing | A leaked token enrolls a rogue device that pollutes evidence. | Single display, 7-day expiry, a use limit and admin revocation. Every enrollment is audited and visible on the Devices page. Rogue reports are evidence noise, not access: a device credential reads nothing. |
| T5 | Device credential | Spoofing | A credential copied from a Keychain sends fake "pass" reports. | Reports are self-declared evidence and labelled as such. Removing a device revokes the credential, and the ledger shows the last report time. Candidate for the build: bind the credential to the Secure Enclave, so it cannot be exported. |
| T6 | Report | Repudiation | An organization disputes what a device reported. | Reports are append-only with server receive time; enrollment and removal are audit events. |
| T7 | API | Information disclosure (cross-tenant) | A device credential reads or writes another organization's data. | A credential maps to one organization. Writes run under that organization's RLS context; device tables join the RLS guard tests (ADR-012). The device endpoint has no read routes. |
| T8 | API | Denial of service | Many devices or a scripted client flood reports. | Per-credential rate limit (one report per 15 minutes accepted; extra requests are dropped with 429). Body size capped at 8 KiB. |
| T9 | Agent | Elevation (local) | The agent becomes a local privilege-escalation path. | It runs as the standard user and has no privileged helper or launch daemon running as root in v1. Checks that need root report `unknown` instead. |
| T10 | People | Privacy and labour law | Employees are monitored beyond what they were told, contrary to LOPDGDD art. 87. | Data boundary, an on-device transparency window and a notice template that refers to the employer's device-use criteria (art. 87.3). The customer's DPO decides whether a DPIA is needed. |

## Residual risks, accepted for v1

- Reports are self-declared by software the user controls. A determined local administrator can
  fake them. The product says "reported by the device", never "verified".
- Owner custody of the signing keys is a single point of failure. Moving to a hardware-backed
  signing service is a decision for before the first release.
