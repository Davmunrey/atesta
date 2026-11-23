# ADR-014: A read-only device agent that reports posture and never acts

- Status: accepted by the owner (2026-11-23). Building
  waits for design partners to ask (owner decision, 2026-11-22: spec and ADR now).
- Spec: `docs/specs/device-agent.md`. Threat model: `docs/security/device-agent-threat-model.md`.

## Context

Customers preparing ENS, NIS2 or GDPR evidence need to show that the laptops their staff use are
encrypted, locked, updated and protected. Today Atesta reads cloud tenants only (ADR-002, ADR-011).

A device agent runs on an employee's computer, which raises two risks a cloud connector does not:
- **Workplace privacy:** Spanish law limits what an employer may look at on work devices. Under
  LOPDGDD art. 87.3, the employer must set criteria for device use, with workers' representatives
  taking part, and must inform workers of them.
- **Supply chain:** an agent that can execute commands becomes a supply-chain risk for every
  customer at once.

CLAUDE.md rule 1 already forbids write access to customer systems.

## Decision

- **Read-only, always.**
  - The agent reads configuration state only.
  - It never changes a setting, never installs or removes software, never runs a command it
    receives, and never remediates.
  - The server's replies carry no instructions. The client accepts only an acknowledgement and the
    next report time.
- **Minimal data,** defined in the spec as a closed list.
  - Each check sends a status (`pass`, `fail`, `unknown`) and at most one bounded value, such as
    the OS version.
  - It never sends file names or contents, application lists, browsing data, location, network
    names, processes, screenshots or keystrokes.
- **macOS first:**
  - written in Swift with the system frameworks and no third-party runtime dependencies (ADR-006);
  - signed with an Apple Developer ID and notarized;
  - distributed as a package that the customer deploys through MDM or installs by hand.
  - Signing keys stay with the owner ("Only a human can do" in ROADMAP.md).
- **Enrollment and transport:**
  - **Enrollment:** a one-time, organization-scoped enrollment token is exchanged for a
    per-device credential kept in the macOS Keychain. The API stores only a hash of each
    (identity-auth pattern for invitations).
  - **Transport:** TLS to the API in eu-south-2 (ADR-007).
  - **Storage:** device data is tenant data under RLS (ADR-012), in append-only reports.
- **The agent feeds the control model; it adds no new compliance path.**
  - Device results become check results on common controls (ADR-011).
  - Rule 9 holds: no framework-specific device logic.
  - AI does not judge devices (ADR-005).
- **Transparency:** the employee can see what the agent reports, on the device itself, and the
  customer receives a notice template to adapt with legal advice.

## Consequences

- No remote "fix it" or "lock it": the product stays an evidence tool, not endpoint management.
  Customers who need that keep their MDM.
- The data list is a contract. Adding a field needs a spec change and an update to the notice
  template.
- Apple developer enrollment, signing-key custody and notarization become owner tasks before the
  first build.
- Windows and Linux follow the same rules, with their own ADR amendment.
