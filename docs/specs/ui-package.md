# Spec: shared UI package (`@atesta/ui`)

- Issue: #440. Follow-up: #441 (component stylesheets).
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
  `ignoredBuiltDependencies` are kept. No dependency is added and no version changes: the lock's
  `packages` and `snapshots` sections are unchanged; only `importers` changes.
- [ ] **The package.** `packages/ui` is `@atesta/ui`, private, shipped as TypeScript source and
  compiled by each app (`transpilePackages`). It exports, one entry each:

  | Entry | What |
  |---|---|
  | `styles/tokens.css`, `styles/base.css`, `fonts` | tokens, base element styles, the three self-hosted faces (`styles/fonts/`) |
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
  header, badges and states stay in `apps/web/src/styles` for now. They are interleaved with
  console-only rules, so moving them reorders rules inside the components layer, which cannot keep
  the CSS byte-identical. They move, with a computed-style comparison of every route, before the
  first `apps/operator-web` screen.
- **Product components** (`MeasureSheet`, `FrameworkMapping`, `ConsoleShell`, the views): they
  stay in `apps/web`. One moves only when a second app needs it.
- **Package tests:** the package's tests stay in `apps/web/tests` for now; they move with the first
  second consumer.

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
