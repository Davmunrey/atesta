# Spec: the organization dashboard as a readiness cockpit

- Issue: #161. Builds on `dashboard-overview.md`, `requirement-register.md`, `insights.md`, `rbac.md`.
- Status: draft

In the first viewport, the dashboard answers three questions: how are we doing, what needs
attention now, and who has to do what. Every figure comes from recorded rows: the organization's
own self-assessment and its recorded scan results. Nothing is a compliance score (claims-honesty
spec, ADR-005).

## API

`GET /api/v1/orgs/{org}/readiness` is open to every role, auditors included; they read counts
only. It returns one entry per framework that the organization may see and that has requirements.
Each entry carries:

- **Identity and size:** `key`, `name` and `total`, the requirements in the current catalog.
- **Assessment counts:** `assessed`, `implemented`, `partial`, `not_implemented` and
  `not_applicable`.
  - **Latest assessment wins:** these come from the latest assessment of each requirement.
  - **One state per requirement:** a requirement counts in exactly one state; `not_applicable`
    excludes the implementation states.
- **Scope:** `has_axes` and `scope_defined`.
- **Review:** `review_on`, the date of the latest security officer review, or null.
- **Overdue:** `overdue`, assigned measures past their due date that are neither implemented nor
  not applicable.
- **Unowned:** `unowned_open`, measures not done and with no owner.
- **By owner:** `open_by_owner`, the measures not done per owner's user id.
- **Last activity:** `last_assessed_at`.

Atesta computes nothing beyond these counts.

## Dashboard

- **Summary sentence.** Under the organization's name, one sentence per framework in progress:
  "ENS · RD 311/2022: 44 de 73 medidas evaluadas, 30 implantadas". It closes with how many items
  need attention, or with "Nada urgente". A brand-new organization still sees *Primeros pasos*
  instead.
- **Now ("Ahora").** A ruled list, most urgent first. Each item carries a text label (*Vencido*,
  *Falta*, *Pendiente*), never colour alone, and links to where the item is solved. The items:
  - measures past their due date, per framework;
  - frameworks in progress with no security officer review;
  - applicable measures with no owner;
  - frameworks with selection levels whose scope is not set;
  - for owners and admins, auditor access ending within 14 days.

  When the list is empty, it names the next useful step.
- **Framework ledger.**
  - **Order:** frameworks in progress come first, then frameworks with requirements, then
    templates without requirements, folded under one disclosure.
  - **Each row** shows a thin distribution bar of the self-assessment, with these segments:
    - implemented (success);
    - partial (warning);
    - not implemented (danger);
    - not applicable (neutral rule);
    - not assessed (empty).

    Under the bar, the same counts appear as text.
  - **Right side:** the recorded scan score when one exists, otherwise "44 / 73".
  - **Next step**, one link:
    - "Define el alcance";
    - "Evalúa N medidas pendientes";
    - "Registra la revisión";
    - "Exporta la declaración de aplicabilidad".
  - Recorded scan results keep their existing disclosure, provenance and wording.
- **Supporting column**, from 75rem beside the ledger, below it on smaller screens:
  - **Your work:** the next three measures assigned to the signed-in person, overdue first, with a
    link to *Mi trabajo*. Hidden for auditors.
  - **Team:** open measures per person, as ranked bars. Hidden for auditors, who do not see the
    people list.
  - **Recent activity:** the last five audit events, for admins and owners.
  - **Collections and evidence:** the existing summary, when there are any.

## Acceptance criteria

- [ ] **API counts:** the readiness API returns the counts above on real Postgres, under RLS.
  - Another organization's rows never count.
  - A framework without requirements is absent.
  - An auditor may read it.
- [ ] **Ledger from the self-assessment:** the dashboard never shows "Sin evaluar" for a
  framework with assessments, and the ledger order follows the rules above.
- [ ] **Attention list:** "Ahora" lists only true items, each with a link and a text label. With
  no items, it shows the next step.
- [ ] **Bar:** the distribution bar is decorative (`aria-hidden`); the same numbers are present as
  text.
- [ ] **Languages:** ES and EN, with plural forms.
- [ ] **Verified:** at 1280 and 375 pixels, light and dark, with axe clean.

## Out of scope

- A single score across frameworks.
- Notifications and email digests.
- Trend charts, which stay on each framework's page.

## Getting started (#196)

- [ ] **Who and where:** admins see a "Puesta en marcha" checklist on the overview until every step is
  done or they hide it (hidden per organization in the browser).
- [ ] **Steps.** Each is marked done from the organization's own records, never from a click:
  1. define the scope of the lead framework (the one with selection axes, else the largest);
  2. assess the first 10 measures;
  3. invite the team (more than one member);
  4. approve a policy;
  5. run an access review or a training;
  6. connect a tool (an API token exists);
  7. record the security officer review, which leads to the dossier.
- [ ] **Not listed until it works:** connecting Microsoft 365 or Google Workspace, because scanning
  needs the hosted environment.
