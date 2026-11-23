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
  dark-surface: "#22221f"
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

This record describes implemented styles, not the future landing composition. Source authority: `apps/web/src/styles/tokens.css`, `apps/web/src/app/globals.css` and `apps/web/src/styles/dashboard.css`; inherited identity: decisions L4/L5 in `docs/specs/landing-legal.md`. The dashboard composition and behavior remain in `docs/specs/dashboard-overview.md`.

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

Frontmatter `dark-*` entries record the existing dark-mode overrides of the corresponding CSS tokens, not additional application tokens. The authenticated workspace follows the operating system. Public surfaces explicitly retain the light palette. Accent and accent foreground remain unchanged in dark mode; focus changes from blue to the highlighter.

**The Paired State Rule.** Change foreground and background together; state changes must retain readable contrast.

## Typography

Self-hosted Newsreader supplies display type; IBM Plex Sans supplies text and controls; IBM Plex Mono supplies recorded catalog versions and other codes. Dashboard section headings remain sans serif so the organization title is the strongest typographic landmark.

The frontmatter records the reused hierarchy. Dashboard titles reduce to (2rem) at the small-screen breakpoint. Scores use (0.9375rem), result counts (1.375rem) and evidence totals (2rem); these are dashboard data roles, not a replacement display scale. Counts, percentages and dates use tabular numerals where specified. Supporting copy is bounded at (60ch) for empty states and (72ch) for the assessment note.

**The Identifier Rule.** Reserve monospace for identifiers; human-readable labels and numerical summaries retain Plex Sans.

## Layout

The application header and workspace share a centered maximum width of (80rem). Default horizontal padding is (2rem), reducing to (1.25rem) at widths up to (40rem). At (64rem), the organization context becomes a (14rem) left rail with a (3.5rem) gap and a vertical divider; below this, the selector and wrapping navigation sit above the page.

The dashboard starts as one column with a (2.5rem) section gap. At (75rem), the ledger and supporting summary use `minmax(0, 1.6fr) minmax(16rem, 1fr)` with a (2rem) gap. Result counts use two columns, expanding to four from (40rem). Names and provenance wrap rather than forcing the page wider. The toolbar keeps refresh beside its explanatory text.

The spacing vocabulary derives from the existing quarter-rem unit. Content establishes separation through padding and ruled rows; supporting content receives a tinted container. This composition belongs to the dashboard, not every future product surface.

## Elevation & Depth

The inspected application uses no shadows. Depth comes from paper against a slightly darker surface, one-pixel borders and whitespace. Focus is an outline (2px) with a (2px) offset, not elevation. The current implementation uses (180ms ease-out) for button opacity and disclosure rotation; reduced-motion preferences shorten transitions and animations to (0.01ms).

## Shapes

Controls and navigation use the small radius; shared primary actions and the collection summary use the medium radius. Ledger rows stay open and ruled, without individual rounded containers. The brand mark has a yellow underline (4px); it is the inherited wordmark treatment, not a general-purpose section ornament. Progress and result-distribution bars are thin (0.375rem), with square ends.

## Components

**Buttons.** Shared primary actions use highlighter fill, medium rounding and medium-weight text. Destructive actions use the danger pair. Dashboard refresh, retry and clear-search controls use a bordered paper surface, small rounding and a surface-colored hover. Buttons, inputs and selects have a minimum height of (2.75rem). Disabled buttons retain their label with (0.6) opacity and a non-interactive cursor. Primary hover underlines text; keyboard focus uses the shared outline.

**Fields.** Search and organization selection use a one-pixel border, paper background and small rounding. Labels remain visible above the field. Search spans its available width; its caret uses the link color. Shared administration inputs use medium rounding. Error messages use danger text and a danger border with an alert role.

**Navigation.** Organization links wrap horizontally on small screens and form a vertical rail on desktop. Current location uses the highlighter pair and medium weight, with `aria-current="page"`; hover uses the supporting surface. A visible-on-focus skip link reaches the main content.

**Framework ledger.** Native `details` and `summary` expose each recorded result in place; the first result starts expanded. Name, version and pending review text precede the right-aligned score and SVG chevron. Hover underlines the name; opening rotates the chevron. Expanded content contains labeled counts, a decorative distribution bar and readable scope/date/catalog provenance. Missing assessment and unavailable score remain explicit text states.

**Collection summary.** A single tinted container groups recent collections and evidence totals. Ruled rows preserve visible status labels, dates and coverage; native progress elements appear only when the expected count is known. Collection coverage and framework result distribution retain different meanings.

**Data tables.** Tables sit in a scroll region that is also a size container. Below 36rem of their own width they stack: one ruled block per row, the first cell as its title, every other cell preceded by its column name (`data-label`) in muted 13px text. The markup stays a semantic table and nothing scrolls sideways on a phone (ui-polish spec).

**Touch and text floors.** No interface text under 13px (0.8125rem), chart ticks included: charts draw at their measured width so SVG text never scales down. Below 40rem or on coarse pointers, buttons, fields, disclosure summaries, breadcrumbs and standalone action links (`.action-link`) are at least 44px tall, and fields use 16px text so phones do not zoom. The document scroll padding clears the sticky top bar so focus and anchors are never hidden.

**Loading, empty and error states.** Loading uses static surface-colored placeholders and status text. Empty states explain the absence; search can be cleared. Errors expose retry. Refresh temporarily disables its control and changes its label. Development data stays visibly labeled and synthetic framework results are not presented as ENS/NIS2 assessments.

## Do's and Don'ts

### Do:
- **Do** reuse semantic colors and their paired dark-mode overrides from the stylesheet.
- **Do** keep keyboard focus visible, labels explicit and reduced-motion behavior intact.
- **Do** preserve record provenance, text statuses and the distinction between missing results and zero values.
- **Do** let long names wrap and stack supporting dashboard content below the ledger on smaller screens.

### Don't:
- **Don't** nest panels, or turn each row inside a panel into its own card; rows inside a panel stay ruled (console-shell spec).
- **Don't** use status color alone to convey an outcome or replace recorded results with decorative scores.
- **Don't** promote future landing-only colors, entrance animations or product views into implemented tokens.

Documentation evidence: source files above; `framework-ledger.tsx`, `overview-dashboard.tsx`, `scan-history.tsx`, `organization-nav.tsx`, local-font declarations and shared control usages; final screenshots at 1440px light, 375px light, 1280px dark and 524px light. The independent finish review reported ship. No new design decisions or detector claims are introduced here.

Not canonized: landing-planned closing-CTA yellow and entrance motion are absent from the shipped styles; the declared but unused large radius is omitted from this reused-system record. No implementation repair was made during documentation. The optional design engine is unavailable; the sidecar follows the shipped schemaVersion 2 reference, without fabricated tonal ramps or runtime-validation claims.
