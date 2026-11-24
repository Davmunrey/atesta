# Spec: shared UI package (`@atesta/ui`)

- Issues: #440 (the package); #441 (the component stylesheets, section below).
- Status: approved (2026-11-24, ADR-017 accepted in #405).
- ADRs: ADR-017 ("How the UI code is shared", "Design system"), ADR-006, ADR-013.
- Build order: step 1 of the operator portal (`operator-portal.md`, "Design notes").

## Problem

The operator portal (`apps/operator-web`) must look and behave like the console: same tokens,
fonts, components, i18n conventions and error envelope. The owner's rule is one design system,
never copied components. Today the shared set lives inside `apps/web`, so a second app could only
copy it.

## Acceptance criteria

- [ ] **One pnpm workspace at the root.** `pnpm-workspace.yaml` and the only `pnpm-lock.yaml` sit
  at the repository root and list `apps/web` and `packages/ui`. `minimumReleaseAge: 10080` and
  `ignoredBuiltDependencies` are kept. `blockExoticSubdeps: true` and `trustPolicy: no-downgrade`
  are added: semgrep's pnpm rules require them once the workspace file lists packages, and the
  lock already resolves every package from the registry. No dependency is added and no version changes: the lock's
  `packages` and `snapshots` sections are unchanged; only `importers` changes.
- [ ] **The package.** `packages/ui` is `@atesta/ui`, private, shipped as TypeScript source and
  compiled by each app (`transpilePackages`). It exports, one entry each:

  | Entry | What |
  |---|---|
  | `styles/tokens.css`, `styles/base.css`, `fonts` | tokens, base element styles, the three self-hosted faces (`styles/fonts/`) |
  | `styles/components.css` | the shared component styles (#441, below) |
  | `page-frame` | `PageHeader`, `Breadcrumbs`, `Panel`, `Loading`, `LoadError`, `Empty` |
  | `badge`, `severity`, `deadline`, `icons` | `Badge`, `ClockBadge`, the severity mapping, the countdown, the icon set |
  | `error-message`, `api-error` | `ErrorMessage`; `ApiError`, `errorCode`, `unwrap`, `expectOk`, `messageKey` |
  | `locale-switcher`, `i18n/locale`, `i18n/provider` | the switcher, the locale cookie rules, `I18nProvider` (each app passes its own messages) |
  | `format` | `percent`, `fileSize` |
  | `csp` | the CSP build step, run from the app's directory after `next build` |

- [ ] **Imported, never copied.** `apps/web` imports these only as `@atesta/ui/<entry>`. A test
  fails when a file in `apps/web` exports a name the package exports, imports the package by
  path, or imports an entry the package does not export.
- [ ] **One direction.** The package imports nothing from an app: only its peers (`next`,
  `next-intl`, `react`), `node:` built-ins and its own files (tested).
- [ ] **Each app keeps its own contract.** Messages, `error-codes.json` and the OpenAPI client
  stay per app. `ErrorMessage` shows `errors.<code>` when the app's messages hold a text for the
  code and `errors.unknown` otherwise; a test keeps the texts under `errors` equal to the API's
  codes plus `unknown`, so the console shows exactly what it showed before.
- [ ] **No visual or behavioural change.** Against the build of `main` before the move:
  - the same 37 HTML routes and the same non-static files;
  - the same markup on every route once scripts are removed;
  - 0 CSP script hashes and the same policy;
  - the same CSS byte for byte, apart from the class names `next/font` derives from its module path;
  - screenshots of `/`, `/ens`, `/app` and a measure at 1440 px match;
  - the existing unit tests and e2e pass with only their import paths and file paths changed.
- [ ] **Tooling follows.** CI and deploy read the root `package.json` and lockfile; Dependabot's
  npm entry points at `/`; `pnpm lint` in `apps/web` also lints `packages/ui`; the token, contrast
  and i18n guards also scan the package.
- [ ] **DESIGN.md** says the shared set lives in `packages/ui` and new shared components go there.

## Not in this change

- **Component stylesheets** (#441): the rules for buttons, fields, data tables, panels, the page
  header, badges and states stayed in `apps/web/src/styles` in #440. They were interleaved with
  console-only rules, so moving them reorders rules inside the components layer, which cannot keep
  the CSS byte-identical. They move in #441 (next section), with a computed-style comparison.
- **Product components** (`MeasureSheet`, `FrameworkMapping`, `ConsoleShell`, the views): they
  stay in `apps/web`. One moves only when a second app needs it.
- **Package tests:** the package's tests stay in `apps/web/tests` for now; they move with the first
  second consumer.

## Component stylesheets (#441)

Step 4.1 of the operator portal's build order: the portal must not copy the console's component
styles. They move from `apps/web/src/styles` into `packages/ui/src/styles/components.css`.

### Acceptance criteria

- [ ] **One components stylesheet in the package** with the rules of the shared components and of
  the shared patterns the portal needs: buttons (`dashboard-button`, `button-primary`,
  `button-danger`), the field (`field`), the page header and breadcrumbs (`page-title`,
  `page-header*`, `page-description`, `page-actions`, `breadcrumbs`), panels (`panel*`,
  `panel-flow`, `panel-grid*`, tables in panels), badges (`badge`, every severity, the running
  clock), data tables (`table-region`, the stacked layout below 36rem, `row-detail`, the
  returned-to row, print), the compact locale switcher (`topbar-locale`), the loading, error and
  empty states (`state-*`), and the phone and touch sizes of inputs, selects, buttons, summaries,
  checkboxes and breadcrumbs. Layered rules stay in `@layer components`; unlayered rules stay
  unlayered.
- [ ] **The app keeps only its own rules.** `globals.css` imports
  `@atesta/ui/styles/components.css` right after the tokens, before the app's stylesheets, so an
  app rule of the same specificity wins over a shared one. Where one selector served both, the
  shared component gets its own rule and the app keeps its selector: `.field` in the package and
  `.routine-form :is(input, textarea, select)` in the console, with the same declarations (a test
  keeps them equal); the phone sizes of the top bar's own controls stay in the console. The badge's
  `span[data-severity="clock"]` and `span[data-severity="overdue"]` become
  `.badge[data-severity="clock"]` (only badges carried them; the overdue one repeated
  `.badge[data-severity="overdue"]`).
- [ ] **Guard.** A test fails when a stylesheet in `apps/web` has a rule whose selector names only
  package classes or repeats a package selector, or when the package stylesheet is imported after
  the app's (`ui-package.test.ts`, shown to fail on planted rules). Rules that adjust a shared
  component in an app context (`.record-summary .badge`, `.panel.danger-zone`) stay allowed.
- [ ] **Tests read the moved rules from the package** (`consistency.test.tsx`,
  `ui-polish.test.tsx`).
- [ ] **No visual change.** Checked against the build of `main` before the move:
  - every pair of rules whose order changes, in the same layer with the same specificity,
    pseudo-element and an overlapping property, is listed from the built CSS, and every page of the
    comparison is searched for an element that matches both;
  - each such pair either sets the same value or is resolved in the app rule (table below);
  - the computed style of every element and its `::before`, `::after` and `::marker` (all
    properties) matches on every exported route (console routes with demo data), at 1440, 390 and
    375 px, light and dark; screenshots of the representative routes match;
  - 0 CSP script hashes and the same policy; the existing unit tests and e2e pass.
- [ ] **DESIGN.md** says where the component styles live and that an app never defines them.

### Reordered rules that met an element

Moving the shared rules ahead of the app's reverses their order against some app rules. From the
built CSS, these pairs have the same layer, specificity and pseudo-element, overlapping
properties and an element that matches both:

| App rule | Shared rule | Where | Outcome |
|---|---|---|---|
| `.ens-table table { min-width: 42rem }` | `.table-region table { min-width: 34rem }` | `/ens` | The 42rem never applied (the shared rule came later); removed, so the table keeps 34rem. |
| `.policy-copy :is(th, td) { padding }` | `.table-region th, .table-region td { padding-block: 1rem }` | `/docs/api`, `/docs/mcp` | The app rule becomes `.policy-copy :where(th, td)`, so the region's row padding still wins. |
| `.activity-table th, td { padding: 0.375rem 0.5rem }` | the same `.table-region` rule | `/app/activity` | The block padding never applied there; the app rule sets `padding-inline` only. |
| `.dossier th, .dossier td { padding }` (unlayered) | stacked `.table-region td { padding }` | `/app/dossier`, `/app/report` | The app rule becomes `.dossier :where(th, td)`, so the stacked cell padding still wins on phones. |
| `.framework-section { min-width: 0 }` | `.panel { min-width: 0 }` | `/app/frameworks` | Same value: no change. |
| `.attention-tag` (font size and weight) | `.badge` | `/app/org` | Same values: no change. |
| `[data-severity=…] .attention-tag { color }` (overdue, missing, pending) | `.badge[data-severity=…] { color }` | `/app/org` | The item and its badge carry the same severity, so the colour is the same. |

## Design notes

- The package has no build step and no toolchain of its own: `apps/web` type-checks it as part of
  its program, and the root `eslint.config.mjs` lints it with the console's rules.
- The package's peers resolve to the same installed copies as the app's (one React, one
  `next-intl`, one `next`), so context providers are shared.
- `base.css` declares `@source "../../"`, so Tailwind scans the package's files for utility
  classes as it scanned them inside `apps/web`.
- The fonts are declared in the package (`next/font/local` needs paths relative to the module), so
  `<html>` takes `fontVariables` from `@atesta/ui/fonts`.

## Test plan

- Unit: `apps/web/tests/unit/ui-package.test.ts` (copies, imports by path, unknown entries, the
  package reaching into an app, the workspace layout), each shown to fail on a planted violation;
  `errors.test.ts` (error texts equal the API's codes plus `unknown`); `next-config.test.ts`
  (`transpilePackages`); `apps/api/tests/test_ci_workflow.py` (Dependabot and pnpm setup at the
  root).
- Build comparison against `main`: route list, markup without scripts, CSS, CSP; screenshots.
- e2e: the existing Playwright suite against the new export.
- #441: `ui-package.test.ts` (no shared component defined in the app, import order),
  `consistency.test.tsx` (`.field` and the console form controls carry the same declarations);
  the reordered-rule listing and the computed-style comparison above, run against `main`'s build.
