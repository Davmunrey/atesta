# Product context

Atesta helps security leads and owners of Spanish SMEs prepare continuously for audits. It
begins with ENS and NIS2. Read-only connectors feed common controls, so the same evidence
supports several frameworks. Atesta prepares evidence; it does not certify.

What exists today is listed in `docs/status/dashboard-readiness.md`, row by row, with the spec
and the test behind each row. Read it before describing the product. In short:

- **The working product is the organization's own record.** An organization sets its ENS scope,
  assesses each measure itself, records evidence statements and files, manual reviews, access
  reviews, policies, training and incidents, and prints a statement of applicability, an auditor
  dossier and a monthly report. Roles are owner, admin, member and a time-boxed external auditor.
- **Automation is partial and says so.** Scans feed technical observations on common controls.
  Every ENS measure keeps a documentary control, so a scan alone never makes a measure pass, and
  a person approves every manual review (ADR-005). No generative AI model is called; the
  assistant answers from the catalog and cites it.
- **Every framework pack is a draft.** ENS, NIS2 with its Implementing Regulation, GDPR Articles
  32 to 34, the LOPDGDD and DORA with one of its technical standards hold official text and
  candidate mappings; few mappings are reviewed. ISO/IEC 27001 and SOC 2 are templates with no
  licensed text. No pack is released.
- **Integrations.** API keys with scopes, an evidence ingestion API and a local MCP server let a
  customer's tools and AI agents record evidence and propose assessments; a person confirms a
  proposal. Microsoft 365 can be connected from the web, on the local stack only.
- **Not there yet.** Nothing is deployed to AWS. No customer tenant has been scanned. There is no
  payment provider, no operator portal, no device agent and no hosted MCP server. Evidence files
  are not scanned for malware.

Show only implemented actions and recorded data: no invented scores, scans or product states.
Never say that a customer satisfies a framework: states read Superado / No superado and
Implantado / No implantado (`docs/specs/claims-honesty.md`). Product views for the public
landing must come from a recorded test-tenant run before release.

One product, one look. Every screen uses the tokens, typography and components that DESIGN.md
and the shared components define; a new screen refines what exists and never brings its own
styles (AGENTS.md, "Interface work"; owner rule of 2026-11-24).

Spanish is the default language, with complete English translations. Copy describes the user's
task in direct, specific language. Respect role-based visibility and tenant boundaries. Keep
keyboard navigation, readable small-screen layouts and WCAG AA contrast.

The web is a static export. Browser requests stay on the same origin; fonts and assets are
self-hosted. Preserve the strict CSP and the reduced-motion preference. Approved visual
decisions live in `docs/specs/landing-legal.md` and DESIGN.md; durable architecture decisions
live in `docs/adr/`.
