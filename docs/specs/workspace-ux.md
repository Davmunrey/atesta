# Spec: customer journey: first steps and the self-assessment workspace

- Issue: #137. Builds on `docs/specs/requirement-register.md` (#133).
- Status: draft

## Problem

A new customer signs up and sees six frameworks, all "Sin evaluar · Borrador", with no next step.
The register the API records has no screen. The framework page is a single 10,700 px column. See #137.

## Acceptance criteria

- [ ] **Overview, framework order:** assessed frameworks first, then frameworks with requirements, then empty
      preparation templates. A template reads "En preparación: aún sin requisitos" instead of its version.
      No row opens by default unless it has a recorded result.
- [ ] **Overview, first steps:** the framework with the most requirements gets a "Primeros pasos" card.
      It has four steps, each with its real state (scope, measures assessed of total, reviewer sign-off,
      export), and one primary action.
- [ ] **Overview, refresh:** "Actualizar resultados" shows only when something has been recorded (a score or a scan).
- [ ] **Framework page, panel:** the self-assessment panel comes first, with the same four steps.
  - Scope: a select per declared level.
  - Progress: assessed, apply, implemented, partially implemented, do not apply.
  - Review: the customer's own security officer, with a note that Atesta only records it.
  - Export: a CSV download and a JSON view, stated not to be a certification.
- [ ] **Framework page, measures:** grouped by code prefix, each group with its progress.
  - Each row shows the person's decision, or "Pendiente" with the proposal.
  - Rows are closed by default.
  - Inside a row the assessment form leads, and the guide, the official text and the configuration fold away.
  - The form requires a justification when the decision is "does not apply" or differs from the proposal.
  - Filters: all, pending, apply, implemented, do not apply.
- [ ] **Framework page, members:** members read and never see edit controls (the API decides).
- [ ] **Copy:** "Puntuación automática desactivada…" replaces the message that said applicability is undetermined.
      Catalog version and hash move into "Detalles técnicos".
- [ ] **Links:** catalog links read `host · document id · section`. The full URL stays in the href and the title.
- [ ] **Backend:** the overview reports each framework's active requirement count.
- [ ] **Generic:** nothing in the web code names a framework (rule 9). Groups are code prefixes and axes come
      from the register.
- [ ] **Standards:** ES and EN strings; 2.75 rem targets; visible labels; no horizontal overflow at 375 px;
      DESIGN.md tokens only.

## Second pass: distill (owner, 2026-11-22: "no tenga más información de la cuenta, sino la necesaria")

Applied with the vendored impeccable references (Operate mode, `distill.md`, `craft-floor.md`) and
modern-web-guidance (`ui-components/menu.md`):

- [ ] The header shows the language and one account button. The signed-in email and sign-out live
      in a popover (`popover` and `popovertarget`, Baseline Widely available; light dismiss, Esc and
      focus return come from the platform; anchor positioning only under `@supports`).
- [ ] One organization shows its name, not a switcher; more than one keeps the switcher. The name
      hides below the rail breakpoint, where the page heading already says it.
- [ ] The overview drops the role line, the empty collection panel and the search below nine
      frameworks.
- [ ] "Not a certification" moves into the footer, once.
- [ ] On a framework with a register, the content-status block folds into "Sobre este contenido".
- [ ] Groups carry the pack's official headings (\`groups_es\`, copied from the BOE, an ordered list
      because JSONB loses object key order) in the source's order. Changing the pack bumps its
      version (\`2024-11-06.draft2\`), because imported drafts are immutable.
- [ ] Every value keeps to DESIGN.md: no shadows and no colour outside the tokens, both checked by tests.

## Out of scope

- Named group titles from the catalog (needs a pack field; the prefix is shown meanwhile).
- The landing page, which waits for the legal identity (`docs/specs/landing-legal.md`).
- Evidence upload and connectors.

## Test plan

- **Unit:** `apps/web/tests/unit/self-assessment.test.tsx` covers:
  - the panel first;
  - badges;
  - the scope POST body;
  - a justification required when the decision differs;
  - members read-only;
  - the export link;
  - grouping and progress;
  - ledger order;
  - first steps;
  - readable references.
- **Postgres:** `test_each_framework_reports_its_active_requirement_count`.
- **Live run:** the real stack (fake Cognito, API, web, Postgres), driven with Playwright: scope, assess
  org.1, review, CSV download, and the 375 px width.
