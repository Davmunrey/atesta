# Product context

Atesta helps security leads and owners of Spanish SMEs prepare continuously for audits.
It begins with ENS and NIS2. Read-only connectors feed common controls so the same evidence
can support multiple framework assessments. Atesta prepares evidence; it does not certify.

The current usable product covers sign-in, organizations, members, invitations and a dashboard
of recorded framework results, collection coverage and evidence counts. Framework detail adds
requirement states, configuration observations and available catalog guidance. An unreleased
ENS draft contains the 73 Annex II measures, candidate mappings and bilingual preparation
guides. NIS2, ISO/IEC 27001, GDPR Article 32, DORA and SOC 2 have scoped preparation templates,
not reviewed normative coverage. All six disable assessment; local recorded results remain
explicitly synthetic. Scope, missing work and official sources are available in each detail view. Current
capabilities and remaining work are recorded in `docs/status/dashboard-readiness.md`. Connector onboarding
and scanner execution remain a separate workstream. Show only implemented actions and recorded data: no
invented scores, scans or product states. Product views for the public landing must come from
a recorded test-tenant run before release.

Spanish is the default language, with complete English translations. Copy should describe
the user's task in direct, specific language. Respect role-based visibility and tenant
boundaries. Keep keyboard navigation, readable small-screen layouts and WCAG AA contrast.

The web is a static export. Browser requests stay on the same origin; self-host fonts and
assets. Preserve the strict CSP and reduced-motion preference. Approved visual decisions
live in `docs/specs/landing-legal.md`; durable architecture decisions live in `docs/adr/`.
