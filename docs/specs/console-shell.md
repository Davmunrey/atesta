# Spec: console-style workspace

- Issue: #163. Builds on `readiness-cockpit.md`, `organization-shell-design.md`, `rbac.md`.
- Status: draft
- Owner decision (2026-11-23): "Algo estilo Microsoft, AWS, etc."; option chosen: console structure with
  Atesta's brand, for the whole authenticated app. DESIGN.md records the change.

The authenticated app reads like the cloud consoles that IT leads use every day. A fixed top bar
with global search, a grouped side navigation, breadcrumbs and a page header on every page, and
content in panels. Atesta keeps its own colours, type and voice; no Microsoft or AWS asset, name or
trademark is used.

## Shell

**Top bar**
- [ ] **Placement:** fixed at the top, full width.
- [ ] **Contents, left to right:**
  - the menu button;
  - "Atesta";
  - the current organization, as a switcher when the person belongs to several;
  - global search;
  - language;
  - the account menu.

**Side navigation**
- [ ] **Groups and order:**
  - *General*: Resumen, Mi trabajo and Marcos;
  - *Equipo*: Miembros and Invitaciones;
  - *Supervisión*: Actividad;
  - *Organización*: Ajustes.

  The RBAC visibility rules are unchanged.
- [ ] **Links:** each link has a drawn SVG icon with one stroke weight, plus its text. The current page uses the highlighter and `aria-current`.
- [ ] **Desktop collapse:** from 64rem, the menu button collapses the navigation to icons only. The labels stay as accessible names and tooltips, and the choice is remembered in `localStorage`.
- [ ] **Small screens:** below 64rem, the navigation is a drawer. The menu button opens it, with `aria-expanded`. Esc and choosing a link close it, and focus returns to the button.

**Page frame**
- [ ] **Every page** starts with breadcrumbs (organization › section › item) and a page header: an h1 in the display face, a one-line description, and actions on the right.

## Global search

- [ ] **API:** `GET /api/v1/orgs/{org}/search?q=` (members only) returns at most 12 requirements of frameworks the organization may see, matching code or title in Spanish or English (case- and accent-insensitive). Each result carries the framework key and name, the code and the titles. The query must be 2 to 100 characters, otherwise 422. Requirements are catalog content, so no tenant data is involved.
- [ ] **Combobox** (ARIA 1.2 pattern):
  - results grouped into pages, frameworks (from data already loaded) and measures (from the API);
  - arrow keys move, Enter opens, and Esc clears;
  - Ctrl+K or ⌘K focuses the search from anywhere;
  - a measure opens on its framework page at `#req-<code>`.

## Panels and pieces

- [ ] **Panel:** a bordered container on a lighter surface than the page, with a header (title, optional description and actions) and a body. Panels never nest.
- [ ] **KPI strip** on the overview, from the readiness counts:
  - frameworks in progress;
  - measures assessed out of the total;
  - implemented;
  - overdue;
  - without an owner.

  The overdue and without-owner figures carry their state as text, not only colour.
- [ ] **Status badge:** a small drawn icon plus text. Colour is never alone.
- [ ] **Tables:** a header row on the surface colour, ruled rows, a hover state, and tabular numerals.

## Pages

- [ ] **Resumen:** KPI strip, then panels:
  - Ahora, with Tu trabajo beside it;
  - Marcos;
  - Equipo, with Actividad reciente beside it;
  - collections and evidence, when present.
- [ ] **Marcos** (new, `/app/frameworks`): the framework ledger with search, in a panel.
- [ ] **Other pages:** Mi trabajo, Miembros, Invitaciones, Actividad, Ajustes and the framework page get the page frame, and their main sections become panels.

## Acceptance

- [ ] **States:** keyboard-only use reaches every control, and focus is visible.
- [ ] **Accessibility:** axe is clean at 375 and 1280 pixels, in light and dark.
- [ ] **Languages:** ES and EN.
- [ ] **CSP and colours:** the CSP still holds; no colour exists outside `tokens.css`.

## Out of scope

- Notifications, a help centre and a command palette for actions. Search only navigates.
- The public pages (landing, cookies).
