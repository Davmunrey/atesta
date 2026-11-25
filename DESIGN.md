---
name: Atesta
description: Paper, ink and restrained highlighting for reviewing recorded audit evidence.
colors:
  bg: "#f4f1ea"
  surface: "#eeebe4"
  fg: "#141414"
  muted: "#55514a"
  border: "#888276"
  accent: "#ffe58a"
  accent-fg: "#141414"
  link: "#23389a"
  danger: "#a3241c"
  success: "#236044"
  warning: "#76520d"
  danger-fg: "#f4f1ea"
  focus: "#23389a"
  chart: "#3a55c9"
  dark-bg: "#171715"
  dark-surface: "#2d2c28"
  dark-fg: "#f4f1ea"
  dark-muted: "#c0baae"
  dark-border: "#817b70"
  dark-link: "#b9c5ff"
  dark-danger: "#ffaaa1"
  dark-success: "#a1d2b0"
  dark-warning: "#eec278"
  dark-danger-fg: "#171715"
  dark-focus: "#ffe58a"
  dark-chart: "#6f86ff"
typography:
  display:
    fontFamily: "Newsreader, serif"
    fontSize: "clamp(2rem, 4vw, 3rem)"
    fontWeight: 500
    lineHeight: 1.12
    letterSpacing: "-0.025em"
  dashboard-title:
    fontFamily: "Newsreader, serif"
    fontSize: "2.25rem"
    fontWeight: 500
    lineHeight: 1.12
    letterSpacing: "-0.025em"
  title:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 500
    lineHeight: 1.3
  body:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "0.875rem"
  metadata:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "0.8125rem"
  data:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
rounded:
  sm: "0.25rem"
  md: "0.375rem"
spacing:
  base: "0.25rem"
  "2": "0.5rem"
  "3": "0.75rem"
  "4": "1rem"
  "5": "1.25rem"
  "6": "1.5rem"
  "8": "2rem"
  "10": "2.5rem"
  "12": "3rem"
  "14": "3.5rem"
  "20": "5rem"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-fg}"
    rounded: "{rounded.md}"
    padding: "0.5rem 1rem"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.danger-fg}"
    rounded: "{rounded.md}"
    padding: "0.25rem 0.75rem"
  button-dashboard:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.fg}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.875rem"
  button-dashboard-hover:
    backgroundColor: "{colors.surface}"
  search:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.fg}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 0.75rem"
    width: "100%"
  navigation-current:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-fg}"
    rounded: "{rounded.sm}"
    padding: "0.625rem 0.75rem"
  collection-summary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
    rounded: "{rounded.md}"
    padding: "1.5rem"
---

# Design System: Atesta

> **Owner decision, 2026-11-23 (#163):** the authenticated app adopts a console structure, "estilo Microsoft, AWS",
> with Atesta's brand: an ink top bar with global search, grouped side navigation with drawn icons,
> breadcrumbs and page headers, content in panels, a KPI strip and status badges. Panels replace the
> earlier "ruled ledger, no cards" rule *inside the app only*; panels never nest, rows inside them stay
> ruled. Colours and type are unchanged; new tokens: `page`, `panel`, `border-subtle` and `topbar-*`
> (tokens.css). The public pages keep the paper-and-ink composition below. Spec: `docs/specs/console-shell.md`.

## Overview

**Creative North Star: "Paper and ink"**

The approved identity uses warm paper, dark ink, editorial headings and a yellow highlighter. The dashboard extends this identity into a working review surface: readable rows, explicit labels and recorded provenance. It does not introduce a replacement visual world.

This record describes implemented styles, not the future landing composition. Source authority: `packages/ui/src/styles/tokens.css`, `packages/ui/src/styles/base.css`, `packages/ui/src/styles/components.css`, `apps/web/src/app/globals.css` and `apps/web/src/styles/dashboard.css`; inherited identity: decisions L4/L5 in `docs/specs/landing-legal.md`. The dashboard composition and behavior remain in `docs/specs/dashboard-overview.md`.

**Key Characteristics:**
- Newsreader page titles paired with IBM Plex Sans interface text and IBM Plex Mono identifiers.
- Flat paper surfaces, fine rules and restrained rounding.
- Yellow selection; text labels accompany semantic result colors.
- A ruled framework ledger with disclosure in place and a quieter collection summary.

## Colors

Warm neutrals establish the reading surface; the highlighter marks location and primary actions.

### Primary

`accent` is the highlighter, paired with `accent-fg` for selected navigation and primary actions. `link` supplies functional blue, including collection progress and the input caret. These are distinct roles, not interchangeable decoration.

### Charts

`chart` is the one hue for single-series data marks (lines, bars, columns), distinct from `link`
so data never reads as a link. It passed the dataviz palette validator on both surfaces (lightness
band, chroma floor, contrast ≥ 3:1): `#3a55c9` on `bg` and `#6f86ff` on `dark-bg`. Charts stay
single-series; counts that compete for colour become figures instead (insights spec).

### Neutral

`bg` is the page; `surface` groups supporting content; `fg` carries primary text; `muted` carries explanations and metadata; `border` separates rows and defines controls. `success`, `danger` and `warning` encode recorded outcomes. Neutral borders represent not-applicable distribution segments. Danger actions pair `danger` with `danger-fg`.

Inside console panels, `surface` is the second level (table header rows, row hover, inline forms) and `panel` the first; they must differ in both themes. Dark `surface` is `#2d2c28` (ui-polish spec, 2026-11-23), one step above the dark panel `#22221f`; muted text keeps 7.2:1 on it. Print forces the light palette on white paper whatever the screen's scheme.

Frontmatter `dark-*` entries record the existing dark-mode overrides of the corresponding CSS tokens, not additional application tokens. The authenticated workspace follows the operating system. Public surfaces explicitly retain the light palette. Accent and accent foreground remain unchanged in dark mode; focus changes from blue to the highlighter.

**The Paired State Rule.** Change foreground and background together; state changes must retain readable contrast.

## Typography

Self-hosted Newsreader supplies display type; IBM Plex Sans supplies text and controls; IBM Plex Mono supplies recorded catalog versions and other codes. Dashboard section headings remain sans serif so the organization title is the strongest typographic landmark.

The frontmatter records the reused hierarchy. Dashboard titles reduce to (2rem) at the small-screen breakpoint. Scores use (0.9375rem), result counts (1.375rem) and evidence totals (2rem); these are dashboard data roles, not a replacement display scale. Counts, percentages and dates use tabular numerals where specified. Supporting copy is bounded at (60ch) for empty states and (72ch) for the assessment note.

**The Identifier Rule.** Reserve monospace for identifiers; human-readable labels and numerical summaries retain Plex Sans.

## Layout

Every console page, the portfolio (`/app`) and `/app/new` included, is the page header followed by panels on the page grid (console-unification spec). Page descriptions are bounded at 72ch, like other supporting copy. The assistant launcher keeps its bottom-right corner: the console keeps a bottom scroll padding so focus clears it, pads the page end on phones, and phone row actions keep their own width instead of running under it. The application header and workspace share a centered maximum width of (80rem). Default horizontal padding is (2rem), reducing to (1.25rem) at widths up to (40rem). At (64rem), the organization context becomes a (14rem) left rail with a (3.5rem) gap and a vertical divider; below this, the selector and wrapping navigation sit above the page.

The dashboard starts as one column with a (2.5rem) section gap. At (75rem), the ledger and supporting summary use `minmax(0, 1.6fr) minmax(16rem, 1fr)` with a (2rem) gap. Result counts use two columns, expanding to four from (40rem). Names and provenance wrap rather than forcing the page wider. The toolbar keeps refresh beside its explanatory text.

The spacing vocabulary derives from the existing quarter-rem unit. Content establishes separation through padding and ruled rows; supporting content receives a tinted container. This composition belongs to the dashboard, not every future product surface.

## Elevation & Depth

The inspected application uses no shadows. Depth comes from paper against a slightly darker surface, one-pixel borders and whitespace. Focus is an outline (2px) with a (2px) offset, not elevation. The current implementation uses (180ms ease-out) for button opacity and disclosure rotation; reduced-motion preferences shorten transitions and animations to (0.01ms).

## Shapes

Controls and navigation use the small radius; shared primary actions and the collection summary use the medium radius. Ledger rows stay open and ruled, without individual rounded containers. The brand mark has a yellow underline (4px); it is the inherited wordmark treatment, not a general-purpose section ornament. Progress and result-distribution bars are thin (0.375rem), with square ends.

## Components

**One shared set (ADR-017, `docs/specs/ui-package.md`).** Every Atesta web app (the console in `apps/web`, the operator portal in `apps/operator-web`) takes the design system from one package, `@atesta/ui` in `packages/ui`: the tokens, the self-hosted fonts and the base styles, the page frame (`PageHeader`, `Panel`, `Breadcrumbs`, `Loading`, `LoadError`, `Empty`), the app shell (`AppShell`, `AccountMenu`, `Notice`, `BrandMark`; #486), `Badge` and `ClockBadge` with the severity mapping, the icon set, `ErrorMessage` with the API error envelope, the locale switcher and its provider, the number formats and the CSP build step. A component a second app needs moves into the package and is documented here in the same pull request; it is never copied into an app (tests in `apps/web/tests/unit/ui-package.test.ts`). The component styles live with the components, in `packages/ui/src/styles/components.css` (#441): buttons (`dashboard-button`, `button-primary`, `button-danger`), the field (`field`), the inline confirmation (`confirm-row`) and form actions (`form-actions`), the page header and breadcrumbs, panels and panel grids, badges, data tables (`table-region`, the stacked phone layout, `row-detail` and the returned-to row), the compact locale switcher, the loading, error and empty states, and the phone and touch sizes of controls. Each app imports that file before its own stylesheets, so an app rule of the same specificity wins over it. An app's stylesheets hold only rules for its own screens; they may adjust a shared component in their own context (`.record-summary .badge`, `.panel.danger-zone`), but never define one, and a new shared component's styles go into the package with it (tested in `ui-package.test.ts`).

**App shell (`AppShell`, #486).** Every signed-in app has one frame: the ink top bar (a menu button when there is navigation, the lockup linking home, the app's own top-bar content, then the locale switcher and the account menu), the grouped side navigation (a 15rem rail on desktop that collapses to 4rem and remembers it, a drawer below 64rem closed by Esc or the scrim), the notices row and the page (at most 90rem). The console puts its organization switcher and search in the bar. Another app names itself beside the lockup (`label`, its short form on phones): the operator portal reads "Portal de operaciones" ("Operaciones" on a phone), so staff never mistake it for the console (ADR-017). `AccountMenu` is the quiet initial with the signed-in email, the app's own links and "Cerrar sesión". `Notice` is the one-line notice row: icon plus text, `overdue` in the danger pair for what blocks.

**Buttons.** Shared primary actions use highlighter fill, medium rounding and medium-weight text. Destructive actions use the danger pair (`.button-danger`), and the control that asks for one ("Quitar", "Cerrar el incidente" with notices unsent) is a bordered `dashboard-button` followed by an inline confirmation (`.confirm-row`): the question, the danger action, then "Cancelar". Dashboard refresh, retry and clear-search controls use a bordered paper surface, small rounding and a surface-colored hover. Buttons, inputs and selects have a minimum height of (2.75rem). Disabled buttons retain their label with (0.6) opacity and a non-interactive cursor. Primary hover underlines text; keyboard focus uses the shared outline.

**Fields.** Search and organization selection use a one-pixel border, paper background and small rounding. Labels remain visible above the field. Search spans its available width; its caret uses the link color. Fields in console forms, selects included, share one style (`.field` in the package; `.routine-form` fields in the console carry the same declarations, kept equal by a test): one-pixel border, paper background, small rounding, link-coloured caret. A select is never left with the browser's default look. Placeholders inside the page use `muted` (7.0:1 on light `bg`, 9.3:1 on dark). Month pickers are selects labelled in the interface language, not `<input type="month">`, which follows the browser's language. Error messages use danger text and a danger border with an alert role.

**Navigation.** Organization links wrap horizontally on small screens and form a vertical rail on desktop. Current location uses the highlighter pair and medium weight, with `aria-current="page"`; hover uses the supporting surface. A visible-on-focus skip link reaches the main content.

**Framework ledger.** Native `details` and `summary` expose each recorded result in place; the first result starts expanded. Name, version and pending review text precede the right-aligned score and SVG chevron. Hover underlines the name; opening rotates the chevron. Expanded content contains labeled counts, a decorative distribution bar and readable scope/date/catalog provenance. Missing assessment and unavailable score remain explicit text states.

**Collection summary.** A single tinted container groups recent collections and evidence totals. Ruled rows preserve visible status labels, dates and coverage; native progress elements appear only when the expected count is known. Collection coverage and framework result distribution retain different meanings.

**Charts earn their place (console-unification spec).** A chart is drawn only when it says more than its figures:
- a trend needs at least 7 distinct days on which the value changed;
- actions per day need activity on at least 7 days;
- ranked bars need at least 2 people.

Otherwise a muted sentence or the table stands in for it.

**Data tables.** Tables sit in a scroll region that is also a size container. Below 36rem of their own width they stack: one ruled block per row, the first cell as its title, every other cell preceded by its column name (`data-label`) in muted 13px text. The markup stays a semantic table and nothing scrolls sideways on a phone (ui-polish spec).

**Touch and text floors.** No interface text under 13px (0.8125rem), chart ticks included: charts draw at their measured width so SVG text never scales down. Below 40rem or on coarse pointers, buttons, fields, disclosure summaries, breadcrumbs and standalone action links (`.action-link`) are at least 44px tall, and fields use 16px text so phones do not zoom. The document scroll padding clears the sticky top bar so focus and anchors are never hidden.

**State badges.** Every recorded state shows a drawn icon beside its label: done (circle check), partial (half-ruled circle), missing (triangle), not applicable (slashed circle), pending (clock). Colour reinforces, never carries, the state.

**Severity mapping (console-unification spec, 2026-11-24).** This table is the one source for how urgent a state looks. `Badge` and `ClockBadge` (`@atesta/ui/badge`) draw it from the state names in `@atesta/ui/severity` (`policyUnapproved`, `reviewLate`, `tokenRevoked`…); no console page sets a badge's colour or icon by hand, and a test fails if one does.

| Severity | Icon | Colour | Label | Used for |
|---|---|---|---|---|
| `clock` | clock | danger, semibold | the countdown: "Quedan 32 h", "Quedan 3 días" | a running regulatory clock (incident notifications) |
| `overdue` | circle with a bar | danger | "Vencido", or "Vencido hace 5 h" for a clock | anything past its date |
| `missing` | triangle | warning | "Falta" or the state, such as "Sin aprobar" | something never recorded that should be |
| `pending` | clock | muted | "Pendiente", a date, or the state | housekeeping, not late |
| `done` | circle check | success | "Hecho", "Al día" or the state | recorded and current |

A running clock is never `pending`, and nothing that has a running clock reads "Al día". Countdowns
read the deadline the API computed; hours below 72 h, days from there.

An uploaded evidence file's malware scan uses the same table (evidence-malware-scanning spec):
- being scanned: `pending` ("En análisis");
- blocked as possible malware: `overdue`;
- could not be scanned: `missing`;
- no threats found: `done`.
Only `done` and the development store's "Sin analizar" offer "Descargar".

**Records-page pattern (console-unification spec, replaces the record summary of #240).** Policies, access reviews, training, incidents and integrations share one pattern, drawn by `RecordSummary` (`components/record-summary.tsx`) and nothing else:
- **Sentence:** one line, led by the register's state badge ("Requiere acción", a clock's countdown, or "Al día"). It names only the figures that need action, inline: "1 política con la revisión vencida y 1 política sin aprobar."
- **Nothing to do:** the sentence says why, with no figure.
- **No tiles:** no figure tiles, zeros or totals.
- **Order:** the register panel follows the sentence and is the page; creation forms come last. No sentence while the list loads, fails or is empty.

The home's "Registros" reads each register with the same function (`useRecordStates`), so its badge and sentence match the page's.

**Home (console-unification spec, owner decision 2026-11-24: "Lista de tareas").** The organization's home answers "what do I do now":
1. the page header, with the organization name and the refresh action, and no summary sentence;
2. "Ahora", the one task list and the first full-width region. Legal clocks come first, then overdue items, then my measures due this week, then the rest; within each group, soonest first;
3. getting started: the full checklist below 5 of 7 steps, one line ("6 de 7 · Invita a tu equipo →") from 5, nothing at 7;
4. "Marcos": one ruled line per framework, its name as a link and its state. The lead framework's measures assessed is the key figure;
5. "Registros".

No KPI strip, team chart, activity feed or scan list: their pages are in the navigation. A figure appears once per screen.

**Records at a glance.** When work is underway, the overview has a "Registros" table, in the fixed order policies, access reviews, training, incidents. Each row links to its page, writes its state as a badge ("Requiere acción", "Al día" or "Sin registros") and repeats the lead sentence of that page's record summary. While an incident's notification clock runs, the incidents row shows the `clock` severity with its countdown, never "Al día". A row that is loading or failed says so and claims no state.

**Landing (landing-legal A4, #393).** The public landing is light only, on the public content column (73.5rem plus 1.25rem gutters, which the header and footer share). It tells the story once:
- **Hero:** the ENS headline in the display face up to 5rem (it never moves, because it is the LCP; only its highlighter stroke draws), one line and the request. Below it, one ENS measure in a product frame, as the measure sheet.
- **Then:** the problem; "Cómo funciona" on ink (assess, records, incidents, dossier, then connect tagged "Próximamente", with no frame); the other frameworks as one mapping table; the consultancy line; the closing ink band, with a hairline seam above the ink footer.
- **Sample data:** one "Datos de ejemplo" per section, never one per frame. The official text is not sample data.
- **Motion:** CSS only. The frame rises once, then the clause is highlighted; everything rests by about 2 s. No shadows, no stock imagery, no eyebrow labels, no tabs, no marquee.

**Measure sheet (shared, `components/measure-sheet.tsx`).** The one view of a measure in the product (console-unification part 4). One anatomy: the code and title with the state, then two columns that sit side by side from 48rem of the sheet's own width, the record (the organization's own assessment, then the guide's expected evidence) beside the law (the official text as a ruled quotation with `lang`, then its source link). Two modes, never a third:

- *Sample* (no `row`): an open, static `article` for public pages (the landing's hero, `/producto`), inside a product frame, so its section labels are not headings. The record is sample data and names the Atesta team, never a person; the official text is an excerpt from the catalog at build time (`lib/catalog/landing.ts`), its last paragraph highlighted.
- *Console* (`row`): the register's disclosure row (`details.requirement-row`, `id="req-<code>"`, opened by a `#req-<code>` link). The record holds the inline self-assessment form (owner and due date, an agent's proposal, the form or the recorded fields); the law holds the official selection table, the applicability and the full official text behind a disclosure. The configurations, with the evidence panel and the manual review, sit below both columns as one disclosure; recorded results (meaning and next step) sit with them when the register leads.

Its parts are shared too, so no other component draws them: the state badge (`AssessmentState`), "Tu autoevaluación" with the proposal from the official tables (`AssessmentIntro`), the recorded fields (`AssessmentFields`, also used by an agent's proposal) and the official text (`OfficialText`). The expected evidence (`expected-evidence.tsx`) has three variants: a disclosure in the console, open in the sample, and print in the dossier.

**Mapping table (shared, `components/framework-mapping.tsx`).** One common control and the requirement it answers in each framework, from signed mappings only, the reviewer's name omitted. A `table-region` data table with the `public-table` look (the portfolio sample uses it too): it stacks by its own width on a phone. References link to the official source and stay in the source's language.

**Activity.** Audit actions read as sentences in ES and EN; an action without a label reads "Otra acción", database ids are never shown, readable targets (framework keys, requirement codes) stay in mono.

**Loading, empty and error states.** Every page load and records list uses the shared `Loading`, `LoadError` and `Empty` components. Loading is muted status text, never an empty status region; the overview alone adds static surface-coloured placeholders. A failed load shows the error and "Reintentar", which refetches. The page header and breadcrumbs stay in place while a page loads or fails. A 4xx answer is not retried, and a server or network failure is retried once, so errors show within seconds. Empty states explain the absence; search can be cleared. Refresh temporarily disables its control and changes its label. Development data stays visibly labeled and synthetic framework results are not presented as ENS/NIS2 assessments.

## Brand system

Introduced with the landing (#323, landing-legal amendment A1, accepted by the owner on 2026-11-23) and adopted by the
console (#330).

**Mark.** A double seal ring around three ledger lines, with the middle line on the highlighter: a
record that has been attested. Original work, geometry only, in `apps/web/public/brand/atesta-mark.svg`
(fixed colours, for use outside the app) and `components/brand-mark.tsx` (`currentColor` plus the
highlighter token, for use inside it). It is also the favicon (`app/icon.svg`).
- **Size:** at least 1rem.
- **Colour:** ink on paper, paper on ink. The highlighter line stays yellow on both grounds.
- **Treatment:** never recoloured, rotated, outlined or set inside another shape.

**Lockup.** The mark (2rem) beside the live wordmark ("Atesta" in Newsreader 600, 1.75rem, tracking
-0.04em), with a 0.625rem gap. The lockup links home; the mark is decorative, and the link's name
carries the brand. No SVG wordmark exists, because the wordmark is set live in the self-hosted
face.

**Signature motif: the highlighter stroke.** One motif, used in four places only:
- the key phrase of the hero headline, as a band behind the lower half of the letters;
- the clause of the hero's measure sheet that the section is about (A4), and the overview's lead figure (measures assessed);
- the 3rem × 4px tab on every section divider;
- the 3rem × 3px tab under the ink bar of every product frame.

It never marks state; status keeps its icon and label. On load it draws once, left to right; reduced
motion shows it drawn.

**Ink band.** One full-bleed ink section per page ("Cómo funciona" on the landing), besides the closing band: paper text, yellow step numbers (`--color-cta`), muted text in `--color-on-ink-muted`, focus rings in the CTA yellow. The closing band ends on a hairline in `--color-on-ink-muted`, so it never merges with the ink footer. The assistant launcher keeps a 2px paper keyline, so it stays visible on ink.

**Type scale (public pages).**

| Role | Face | Size |
|---|---|---|
| Hero headline | Newsreader 500 | up to 5rem, tracking -0.04em, at most 16ch |
| Section titles | Newsreader 500 | up to 4.5rem, at most 16ch |
| Statements | Newsreader 400 | up to 1.75rem, at most 44ch |
| Text and UI | IBM Plex Sans | 1rem, 1.25rem for step titles |
| Codes and step numbers | IBM Plex Mono | 0.875rem |

The floor stays 13px.

**Colour roles.**

| Role | Token | Value |
|---|---|---|
| Paper, the ground | `--color-bg` | #f4f1ea |
| Panels and frames | `--color-panel` | #faf8f3 |
| Ink, text and the closing band | `--color-fg` / `--color-ink` | #141414 |
| Muted text | `--color-muted` | #55514a |
| Highlighter, motif and primary buttons | `--color-accent` | #ffe58a |
| Yellow on ink, the closing CTA | `--color-cta` | #ffd23f |
| Stamp blue, links and focus | `--color-link` | #23389a |
| Muted text on ink | `--color-on-ink-muted` | #c0baae |

Every pair is checked by `tests/unit/contrast.test.ts`.

**In the console (#330).** The motif is used sparingly:
- **Top bar:** the lockup on ink (mark at 1.5rem, wordmark Newsreader 600).
- **Page titles:** the highlighter tab under every page title.
- **Key figure:** one per page, the home's measures assessed (on the lead framework's line). In light mode it gets the band behind ink. In dark mode it is set in the accent yellow with no band, because light text on yellow fails contrast. In print it is plain.

**Scrollytelling (#356, landing-legal amendment A2).** On wide screens with motion allowed:
- **Pinned steps:** "Cómo funciona" pins one product frame beside the steps. The frame shows the stage of the step in view (IntersectionObserver, no scroll-jacking); the active step's rule turns yellow. No counter and no progress bar (A4). Stages crossfade. Inactive step titles dim by colour, never by opacity, so contrast holds.
- **Reveals:** headlines reveal with CSS view timelines, using only clip-path and transform. Without view timelines, the page rests complete.
- **Count-up:** the overview's figures count up once; the document holds the final numbers. KPI suffixes ("de 73") are small through `.lv-of`, never by shrinking the figure.
- **Phones and reduced motion:** a static page, one step per row, each with its own frame (beside it from 64rem). On public pages body text never breaks inside a word (`overflow-wrap: break-word`; the console keeps `anywhere` so long names can shrink their cell), and paragraphs use `text-wrap: pretty`.
- **Free corner:** the bottom-right corner stays free for the assistant launcher. On phones it is the seal alone, and on the landing it stays faded (still focusable, shown on focus) until the hero has scrolled away, where scroll timelines and motion are available.
- **Removed in A4:** the hero tabs, "Un año de ENS", the frameworks marquee and ring diagram, the stage counter.

**Product frames.** Every product view on public pages sits in a frame: an ink bar carrying the mark,
the context and a "Datos de ejemplo" label while the fixture is illustrative.

## Public site (#371, landing-legal amendment A3, accepted 2026-11-23)

The product is the proof. Every public page shows Atesta at work in paper, ink and the
highlighter, with one motion language. Honest facts replace logos and testimonials.

**Chrome**
- **Header:** the lockup, then the menus. Producto and Docs open panels of links with a one-line
  description each; ENS, Seguridad and Consultoras are plain links once their pages exist. Then
  the language switcher, Entrar and Solicitar acceso.
  - It is sticky on paper with a hairline. It hides on scroll down and returns on scroll up,
    never under reduced motion.
  - Panels are disclosure buttons with `aria-expanded`; Esc and an outside click close them.
- **Footer:** an ink band with the lockup, "Preparación de auditorías. No certifica
  cumplimiento.", four columns (Producto, Recursos, Empresa, Legal). No proof strip (owner, 24/11/2026).
- **Links:** public pages link with plain anchors, so each navigation is a document load. That
  lets cross-document View Transitions morph the lockup and the page title. Reduced motion or no
  support: a normal load.

**Honest proof**
- **No proof strip:** the owner removed it on 24/11/2026 (landing-legal amendment A5). Facts
  stay where they belong: the BOE text on the landing and /ens, read-only access, hosting and the
  AI rule on /seguridad. No person's name appears on a public page; the reviewer is "el equipo de
  Atesta".
- **Customer logos:** a data file (`content/customers.json`) whose entries need a written-permission
  reference. The section does not render while the file is empty.

**Motion tokens**
- **Easings:** `--ease-decisive` (in-out) for entrances and stage changes, `--ease-soft` (out) for
  hovers, `--ease-entrance` (out) for figures and bars. Nothing overshoots (A4): the spring token is gone.
- **Durations:** 180 ms hover, 600 ms stage, 900–1400 ms entrances.

## Voice

Console and public copy address the reader as "tú", never "vosotros" or "usted" (owner decision 2026-11-24). Plain statements over slogans and triads. "Responsable de medidas" names whoever owns a measure; "encargado" stays reserved for the GDPR processor. Policies, access reviews, training and incidents are "registros periódicos" (EN "recurring records"), never "rutinas" or "routines" (#423); API identifiers such as `routines:write` keep their names.

## Do's and Don'ts

### Do:
- **Do** reuse semantic colors and their paired dark-mode overrides from the stylesheet.
- **Do** keep keyboard focus visible, labels explicit and reduced-motion behavior intact.
- **Do** preserve record provenance, text statuses and the distinction between missing results and zero values.
- **Do** let long names wrap and stack supporting dashboard content below the ledger on smaller screens.

### Don't:
- **Don't** nest panels, or turn each row inside a panel into its own card; rows inside a panel stay ruled (console-shell spec). Inside a panel, figures are a ruled definition list (`.stat-tiles`), never a bordered or filled box; the only filled areas inside a panel are the `surface` level (table headers, hover, inline forms) and notices.
- **Don't** use status color alone to convey an outcome or replace recorded results with decorative scores.
- **Don't** promote future landing-only colors, entrance animations or product views into implemented tokens.

Documentation evidence: source files above; `framework-ledger.tsx`, `overview-dashboard.tsx`, `scan-history.tsx`, `organization-nav.tsx`, local-font declarations and shared control usages; final screenshots at 1440px light, 375px light, 1280px dark and 524px light. The independent finish review reported ship. No new design decisions or detector claims are introduced here.

Not canonized: landing-planned closing-CTA yellow and entrance motion are absent from the shipped styles; the declared but unused large radius is omitted from this reused-system record. No implementation repair was made during documentation. The optional design engine is unavailable; the sidecar follows the shipped schemaVersion 2 reference, without fabricated tonal ramps or runtime-validation claims.
