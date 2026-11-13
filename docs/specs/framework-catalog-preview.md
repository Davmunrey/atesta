# Spec: official framework content and preparation templates

- Requirement ids: MF-06, FR-08, ADR-011, rule 10
- Status: draft

## Problem

The requirement screen exists, but only synthetic catalog data can be loaded. Users need
to distinguish authoritative requirements from preparation topics, see applicability and
configuration guidance, and know exactly which content and assessments are missing.

## Acceptance criteria

- Load versioned framework-independent YAML packs and common controls through a validated,
  local-only preview command. Reject duplicate identities, dangling mappings, unknown pinned
  scanner checks, missing provenance, unsafe links and manual controls with automated checks.
- Import every Annex II measure of RD 311/2022 from the captured official BOE publication.
  Preserve Spanish wording, category/dimension distinction, alternative reinforcements and
  application clauses. Verify against the current consolidated text. Record source hashes,
  sections, retrieval date and review limitations. Do not infer customer applicability.
- Keep ENS as a draft pending qualified review. Disable scoring for preview packs even when
  development draft visibility is enabled. No synthetic scan may create an ENS assessment.
- Add preparation templates for NIS2, ISO/IEC 27001, GDPR Article 32, DORA and SOC 2, based on
  their official scope/source pages. State their distinct legal/certification/report nature.
  Empty requirement lists and unreviewed mappings cannot be presented as covered requirements.
  Do not reproduce licensed ISO/AICPA criteria or claim current national NIS2 transposition.
- Common-control guides explain prerequisites, expected settings, implementation, evidence,
  verification and limits in ES/EN. Technical mappings are partial candidates; mapped measures
  retain documentary review. Controls prepare multiple frameworks without invented equivalence.
- The detail screen exposes pack readiness, scope, applicability guidance, official requirement
  text and candidate preparation controls. Empty templates show missing content, never a score.
  Preserve the current visual system, safe links, accessibility and responsive behavior.
- Update the demo with draft catalog content only. Existing synthetic results remain separate.
  Record an explicit inventory of imported measures, candidate mappings, guides and pending work.

## Out of scope

Production release, certification, legal conclusions for a customer, tenant category selection,
automatic applicability/exemption decisions, editing customer configuration, documentary approval,
and the other session's connection endpoints/scanner runtime. Release demand/reuse and qualified
review gates still apply; user authorization covers preparation, not fabrication of those gates.

## Design notes

Use existing global catalog tables and their JSON attributes, not framework-specific tables.
The public API returns a typed allowlist of explanatory content, never arbitrary attributes or
reviewer identities. Preview import is transactional and content-addressed; it refuses to change
an existing pack under the same version and preserves history. No new dependencies or migrations.

## Test plan

REA-captured failing tests before implementation; independent literal applicability examples;
source comparison; malformed pack/check/reference rejection; real PostgreSQL import idempotency,
conflict rollback and production/scoring guards; API membership isolation; web empty/draft/official
text states and responsive browser checks. Fresh checkout/database verification before publication.
