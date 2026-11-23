# Spec: UI polish for phones, management and dark mode

- Issues: #238 (phones), #239 (readable activity, consistent panels), #240 (executive summaries),
  #276 (incident criteria on phones), #283 (loading, error and empty states),
  #287 (records at a glance on the overview), #295 (expected evidence polish),
  #301 (public pages).
- Builds on `console-shell.md`, `insights.md`, `recorded-routines.md` and DESIGN.md. Operate mode:
  refinement of the console, not a new visual world.
- Status: draft
- Evidence: the audit of 2026-11-23 covered 26 pages at 375 and 1280 px, light and dark, plus print,
  with axe on each. Its screenshots are kept outside the repository. The checks also draw on the
  vendored `impeccable` craft floor and `modern-web-guidance` (`responsive-table`), plus two
  published checklists used as reference only, neither of them vendored:
  - taste-skill (MIT): the 13 px floor, 44 px targets and at most two boxes deep;
  - ui-ux-pro-max (MIT): focus not obscured, 16 px inputs on phones, status never by colour alone.

## Phones (#238)

**Tables**
- [ ] **Stacked on narrow containers:** a `.table-region` is a size container. Below 36rem, its table becomes one block per row, and every cell except the first shows its column name before the value.
  - The column name comes from the cell's `data-label`; the hidden header row is not read twice.
  - The table keeps its semantic markup (`table`, `th`, `td`).
- [ ] **No sideways scroll:** nothing in the console scrolls sideways at 375 px.

**Charts**
- [ ] **Readable axes:** axis labels stay at 13 px at every width, rendered as HTML text beside the SVG. They do not scale down with the drawing.
- [ ] **Complete table view:** the table view names both columns.

**Targets and text**
- [ ] **44 px targets:** on coarse pointers, standalone links (outside running text), disclosure summaries and buttons are at least 44 px tall.
- [ ] **No text under 13 px:** this covers navigation group labels, search hints and chart ticks.
- [ ] **16 px inputs on phones:** inputs, selects and textareas are 16 px below 40rem, so iOS does not zoom.
- [ ] **Focus not obscured:** the document scroll padding clears the sticky top bar (WCAG 2.4.11), for focused controls and `#req-…` anchors alike.

## Readable activity and consistent panels (#239)

**Activity**
- [ ] **Every action has a label:** each audit action the API records has an ES and EN label. A test reads the actions from the API source.
- [ ] **Unknown actions:** an action with no label shows "Otra acción" / "Other action", never the code.
- [ ] **No UUIDs:** UUID targets are not shown. Readable targets, such as framework keys and requirement codes, stay as identifiers in mono.

**Accessible names**
- [ ] **Incident deadlines:** the "Marcar como enviado" button's accessible name starts with its visible text (WCAG 2.5.3).

**Dark mode**
- [ ] **Two distinct levels:** `surface` and `panel` differ in dark mode, so header rows, hovers and inline forms show inside panels.
- [ ] **Contrast:** muted text keeps at least 4.5:1 on both levels; the contrast test covers the pair.

**Panels**
- [ ] **No nesting on the overview:** evidence totals sit in the scans panel as a ruled row, not as a box inside it.
- [ ] **No repeated header:** the frameworks page's panel has no title of its own, because the page header already names it.
- [ ] **Spacing:** settings paragraphs and their actions keep the panel's spacing.
- [ ] **Requirement states:** every requirement state shows an icon with its label, using the badge vocabulary (done, partial, missing, not applicable, pending).
- [ ] **Print:** the page prints on white, and the console chrome stays hidden.

## Executive summary on records pages (#240)

**Every records page**

Policies, access reviews, training, incidents and integrations each open with:
- [ ] **A summary sentence:** management can read the state without scanning rows.
- [ ] **Key figures:** a KPI strip, with the state written as text with an icon, never colour alone.

**Content**
- [ ] **Policies:** total, approved and in date, review overdue, never approved.
- [ ] **Access reviews:** total, open, closed, and accounts still to decide in open reviews.
- [ ] **Training:** campaigns, open, and confirmations recorded.
- [ ] **Incidents:** open, closed, and deadlines still running.
- [ ] **Integrations:** active tokens, revoked or expired, and the most recent use.

**Data and order**
- [ ] **No new endpoint:** figures come from data the page already loads. While data loads, or when a load fails, no figures are shown.
- [ ] **Register first:** the register comes before the creation form.

**Strings**
- [ ] **i18n:** ES and EN strings with ICU plurals.

## Incident criteria on phones (#276)

The incident form shows the official text behind each flag (recorded-routines spec). With several
frameworks active, one flag can carry twenty or more criteria.

- [ ] **Grouped by framework:** under each flag, criteria are grouped by framework, in the order the API returns them.
- [ ] **One disclosure per framework:** a framework with several criteria shows a single disclosure, "Qué dice DORA (9 criterios)" / "What DORA says (9 criteria)". It opens onto one disclosure per criterion, titled by the criterion alone. A framework with one criterion keeps the single disclosure "Qué dice RGPD: …".
- [ ] **Official text unchanged:** text keeps `lang="es"` when no official English exists, and each criterion keeps its official source link.

## Loading, error and empty states (#283)

**Shared components**

`page-frame.tsx` exports three components, and every console page load and records list uses them:
- `Loading`: visible text inside a polite status region.
- `LoadError`: the error plus a "Reintentar" / "Try again" button that refetches.
- `Empty`: a muted line saying nothing is recorded yet.

**Acceptance criteria**
- [ ] **Header stays:** while loading and on error, the page header and breadcrumbs stay in place.
- [ ] **No silent status:** no status region is empty.
- [ ] **Fast failure:** queries never retry a 4xx answer. They retry a 5xx or network failure once, so a failing page shows its error within a few seconds instead of about seven.

## Records at a glance on the overview (#287)

Management reads the records an auditor asks for from the overview, without opening each page.

**The panel**
- [ ] **Rows:** when work is underway, the overview has a "Registros" / "Records" table with one row per record type, in a fixed order: policies, access reviews, training, incidents.
- [ ] **Cells:** each row has three cells:
  - the record type, linking to its page;
  - a state written as icon plus text: "Requiere acción", "Al día" or "Sin registros";
  - the summary sentence that the records page shows.

**Needs action when**
- [ ] **Policies:** a review is overdue or a policy is unapproved.
- [ ] **Access reviews:** an open review is past its due date.
- [ ] **Training:** an open campaign is past its closing date.
- [ ] **Incidents:** an open incident has an overdue deadline.

**Data**
- [ ] **No new endpoint:** figures come from the list endpoints the records pages use; the query cache is shared with them.
- [ ] **Honest rows:** a row that is loading or failed says so and claims no state.

## Expected evidence polish (#295)

Refines the expected-evidence disclosure from `requirement-register.md` and `auditor-dossier.md` (#226).

- [ ] **Reference once:** when every item of a requirement shares one guide reference, it is shown once under the status line ("Referencia: …" / "Reference: …"), and the items carry no reference of their own. When references differ, each item keeps its own.
- [ ] **Dossier for print:** in the dossier, the lists are closed on screen and open while printing, from the print button or the browser. A `beforeprint`/`afterprint` handler opens them and restores their state; it is Baseline widely available, and no inline script is added.
- [ ] **Register style:** in the register, the disclosure uses the requirement row's section style: one rule, no triangle, the same summary type as its siblings.

## Public pages (#301)

The public side (`/`, `/cookies`, `/invite`, `/training`, the 404 page) and the dossier print view
get the same quality bar as the console.

**Frame**
- [ ] **One frame:** every public page has the same header (skip link, wordmark linking home, language switcher) and the site footer.
- [ ] **Light only:** public pages are light only (landing-legal spec, L4) and render the light theme under dark emulation.

**Link states**
- [ ] **Heading and next step:** the invite and training link states (missing, invalid or expired) have an h1 and one sentence on what to do.
- [ ] **Training link refused:** when the API refuses a training link with a 4xx, the page says the link is not valid or no longer active, never a form-validation message. A 5xx keeps the generic error.

**Checks**
- [ ] **e2e:** a public-pages e2e spec runs axe, overflow, the 13 px floor and 44 px targets on these routes at 375 and 1280 px, in light and dark, and on the dossier print view.


## Polish from the #305 and #315 reviews (#345)

- [ ] **One control size:** radios and checkboxes in the manual review form are 1.125rem on fine pointers and 1.5rem on coarse ones.
- [ ] **Evidence labels:** evidence options read at regular weight, with their date muted.
- [ ] **Saved state:** after saving a review, the saved line is a `.notice` with an icon, and the cited list, the notice and the button keep the panel's spacing.
- [ ] **Classify input:** the classification time input names its help with `aria-describedby`, and its `min` is the incident's awareness time.
- [ ] **Print:** the incident page's classify and note forms do not print.


| Area | Cases |
|---|---|
| Unit | classify input min and description; expected evidence: shared reference once, per-item references otherwise, dossier lists open for print and restored after; overview records rows: order, states and links from fixtures; incident criteria grouped by framework, with counts; a failed list load offers a retry that refetches; members keeps its header while loading; no retry on 4xx; stacked tables carry a `data-label` per cell; every API audit action has ES and EN labels; unknown actions and UUIDs never show; incident button name; summaries count from fixtures; dark `surface`/`panel` differ and pass contrast |
| e2e | axe with no violations and no horizontal overflow at 375 and 1280 px on the pages above; CSP reports stay empty |
