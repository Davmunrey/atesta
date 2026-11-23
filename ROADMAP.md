# Roadmap

The engineering order of work, and what gates each step. Product context is in
[PRODUCT.md](PRODUCT.md); what exists today is in
[docs/status/dashboard-readiness.md](docs/status/dashboard-readiness.md). Every item becomes an
issue before work starts (AGENTS.md rule 12) and a spec before code (rule 7).

Two rules hold throughout: connectors stay read-only, and AI never decides pass or fail.

## Gate A: a hosted ENS workspace, safe to invoice

The first thing a customer uses has no connection to their tenant. They record their own ENS
self-assessment and keep it current.

1. **Honest copy.** No string, export or document claims that a customer complies (#130,
   `docs/specs/claims-honesty.md`).
2. **ENS register.** For the customer's category, per Annex II measure: state (implantada /
   sujeta a revisión regular), linked evidence statements, who performed it and when; the
   Annex III 2.1.b review by the security officer and the corrective actions.
3. **Declaración de Aplicabilidad export** (RD 311/2022 art. 28.2), with a signer field for
   the responsable de la seguridad.
4. **Applicability.** The reviewed ENS selection tables filter the measures by category, with
   a manual "No aplica" and its justification as the fallback.
5. **Production workspace in AWS eu-south-2.** Network, RDS, KMS, ECS for API and worker,
   ECR, secrets, SES, static web, monitoring, CloudTrail and GuardDuty; hosted sign-in with MFA;
   a deploy pipeline with migrations and manual approval. No scanner tasks yet.
6. **Public legal and trust pages.** Aviso legal, privacidad, cookies, `/seguridad`,
   `security@` and `/.well-known/security.txt`, from the real legal entity.
7. **Operations.** Restore drill with measured RTO and RPO; runbooks in ES and EN (onboarding,
   incident, deploy and rollback, offboarding); alarms and an external status page.
8. **Independent penetration test** of web, API, sessions and cross-tenant RLS, with critical
   and high findings fixed and retested.

Exit: every item above has evidence (a command, a test, a signed document or a URL).

## In parallel: preparation packs for the other frameworks

Content work that does not block Gate A. Each pack is labelled "preparation", carries no
score, and is released only after a qualified reviewer signs it off and the owner decides.

- **Content model v2 and coverage.** Every pack records every unit of its official source
  (each article, paragraph and annex point) as covered or excluded with a reason, so "all
  guides" is measured against the source, not against a list we chose.
- **NIS2** (Directive (EU) 2022/2555; Spanish transposition tracked with its date), **GDPR**
  security of processing (Art. 32 and linked duties, with LOPDGDD), **DORA**
  (Reg. (EU) 2022/2554 with its RTS and ITS): official ES and EN text from EUR-Lex and BOE.
- **Status (2026-11-23):**
  - Content model v2 and coverage ledgers are in (#148).
  - NIS2 Art. 20, 21 and 23 are in (#148), as are GDPR Art. 32 to 34 (#150) and DORA Chapters II to V (#152), in official ES and EN.
  - Qualified review, the Spanish NIS2 transposition, Implementing Regulation (EU) 2024/2690, the LOPDGDD and the DORA technical standards are still to come.
- **ISO/IEC 27001:2022 and SOC 2:** clause and control identifiers with Atesta-authored guides
  only; no ISO or AICPA text is stored.
- **ISO 27001 to ENS crosswalk** for organizations that already hold ISO 27001.

## Gate B: live, read-only tenant collection

Before any customer tenant is connected: the Fargate scan runner with deny-by-default egress,
the Microsoft 365 connector passing its live golden test on an Atesta-owned tenant, Microsoft
publisher verification, and a penetration-test extension to the scanner and the consent flows.
Automated coverage is always stated exactly, taken from the pack's mappings.

## Device agent: specification first

A read-only, on-device posture agent (disk encryption, screen lock, supported OS, updates,
firewall, platform integrity, malware protection) for macOS first. It never changes a setting,
runs a remote command or remediates. The ADR, the threat model, the data boundary and the
employee-notice templates come first; the build starts when customers ask for it.

## Later

Auditor evidence pack, the cited AI readiness assistant (ADR-010, EU-only), the Google Workspace
connector, binary evidence upload, the MSP console, and the remaining product screens.

## Only a human can do

Qualified review and sign-off of each framework pack; legal review of terms, the DPA and the
employee notices; creating cloud accounts and applying infrastructure; custody of signing keys;
releasing a pack (AGENTS.md, "Owner decisions").
