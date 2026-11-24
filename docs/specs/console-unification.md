# Spec: console unification (2026-11-24)

- Issues: #409 (part 1, home and urgency), #410 (part 2, records pages, charts and nesting), #411
  (part 3, consistency and Spanish). Each part has its own pull request, stacked in that order.
- Builds on `console-shell.md`, `readiness-cockpit.md`, `ui-polish.md`, `insights.md`,
  `recorded-routines.md` and DESIGN.md.
- Status: draft
- Owner decisions, 2026-11-24:
  - top rule: "que la app no sea un frankenstein". The console is one product with one way of
    doing each thing;
  - scope "Unificación completa": all six findings of the critique (score 25/40);
  - home = "Lista de tareas";
  - form of address = "tú", everywhere in the app and on the web.
- Evidence: the impeccable critique of 2026-11-24, with findings verified by the coordinator.
  Screenshots are kept outside the repository.

DESIGN.md records the resulting rules as the single source: the home layout, the severity
mapping, the records-page pattern and the no-nested-panels rule.

## Part 1: home and urgency (#409)

### Home is a task list (P1)

Before, the home had nine panels of equal weight, and "Ahora" started about 1000 px down.

**Order of the page**
- [ ] **Header:** the organization name and the refresh action. No summary sentence that repeats the figures below.
- [ ] **Tasks first:** "Ahora" is the first full-width region. It merges what was "Ahora" and "Tu trabajo".
- [ ] **Frameworks next:** below the tasks, one line per framework with requirements. Each line has the framework's name as a link to it and its state:
  - the measures assessed and implemented;
  - otherwise, the recorded scan score;
  - otherwise, "Sin evaluar".

  Preparation templates (no requirements) are left out; the Marcos page lists them.
- [ ] **Records:** the "Registros" table stays below the frameworks.

**Order of tasks**

The list is sorted by group, then by deadline, soonest first:
1. running legal clocks (incident notifications), including those past due;
2. overdue items: overdue measures, policy reviews, access reviews, training, and my own overdue measures;
3. my measures due within the next 7 days;
4. everything else that needs someone: a review to sign, unowned measures, an undefined scope, an unapproved policy, an auditor's access ending.

**Contents of the task list**
- [ ] **My measures:** the person's own measures due later than this week are not listed. "Ver todo en Mi trabajo" links to them.
- [ ] **No double count:** when some of a framework's overdue measures are mine and already listed, the framework line counts only the others ("N medidas más con fecha límite vencida en …"). When all of them are mine, the line is not shown.
- [ ] **Nothing urgent:** the panel names the next step, as before.

**Removed from the home**

These pages already exist in the navigation:
- the KPI strip;
- "Equipo";
- "Actividad reciente";
- "Últimos análisis" with its evidence total.

**One figure, one place**
- [ ] **No repeats:** a figure appears at most once per screen.
- [ ] **Key figure:** the measures assessed of the lead framework, in its framework line, is the page's one key figure (DESIGN.md, brand in the console).

**Getting started**
- [ ] **Full list:** shown while fewer than 5 of the 7 steps are done.
- [ ] **One line from 5 of 7:** a single line, "6 de 7 · Invita a tu equipo →", linking to the first step not yet done.
- [ ] **Hidden at 7 of 7.** It can still be hidden by hand while it shows in full.

### Urgency (P1)

**A severity of its own**
- [ ] **Running clock:** a running regulatory clock has its own severity, `clock`. It shows a clock icon and a countdown, in danger colour: "Quedan 32 h", or "Quedan 3 días" from 72 h.
- [ ] **Past due:** a clock past its deadline reads "Vencido hace 5 h" (or "hace 2 días"), with the overdue icon.
- [ ] **Never like housekeeping:** a running clock is never a grey "Pendiente".

**Counting**
- [ ] **Countdown:** hours are rounded up while running and down once past due. Pure function, unit-tested.
- [ ] **Deadlines:** deadline computation is unchanged. The countdown reads `due_at` from the API.

**Records and lists**
- [ ] **Registros:** the incidents row never says "Al día" while an open incident has a clock running. It shows the clock severity with the countdown of the soonest deadline, and the lead sentence says a notification is due.
- [ ] **Incidents register:** an open incident's next deadline shows the same countdown badge.

**Incident detail**
- [ ] **Primary action:** "Marcar como enviado" is the primary action (`button-primary`), next to each running or overdue clock.
- [ ] **Closing:** "Cerrar el incidente" is a secondary action (`dashboard-button`).
- [ ] **Confirmation:** while any clock is not met, closing asks for confirmation first: "Quedan N avisos sin enviar. ¿Cerrar igualmente?", with "Cerrar" and "Cancelar". Without open clocks, it closes directly.

## Part 2: records pages, charts and nesting (#410)

### One records-page pattern (P2)

This replaces the KPI strip on records pages (ui-polish spec, #240). It applies to policies, access
reviews, training, incidents and integrations.

**The pattern**
- [ ] **One component:** `RecordSummary` is the one records-page header.
- [ ] **One sentence:** a single lead sentence. Only the figures that need action appear, inline in that sentence, with the severity icon. When nothing needs action, the sentence says so.
- [ ] **No tiles:** no figure tiles, no zero figures and no totals, such as "Cerrados 0" or "Último uso" as a headline figure.
- [ ] **The register is the page:** the register panel follows the sentence, and creation forms come after it.

**What needs action, per page**

| Page | Needs action when |
|---|---|
| Policies | a review is overdue, or a policy is unapproved |
| Access reviews | an open review is past its date; accounts still to decide in open reviews |
| Training | an open campaign is past its closing date |
| Incidents | a clock is overdue or running |
| Integrations | no key is active |

### Charts only when they say something (P2)
- [ ] **ENS "Evolución":** the implemented-over-time and score charts show only with at least 7 distinct days on which the value changed. Otherwise a muted line says when the chart will appear.
- [ ] **Activity "Acciones por día":** shows only with activity on at least 7 days. Otherwise the page is the table.
- [ ] **"Equipo" ranked bars:** show only when at least 2 people own measures. Otherwise one sentence names the owner, or says there is none.

### No nested panels (P2)
- [ ] **Insights:** the framework insights section is one panel. Its figures are a ruled definition list, not boxed tiles inside it (`.stat-tiles` loses its border and fill inside a panel).
- [ ] **Everywhere else:** no panel contains a bordered, filled box.

## Part 3: consistency and Spanish (#411)

### Consistency (P2)
- [ ] **Selects:** selects in forms (`.routine-form select`) use the shared field style: the border, radius, paper background and padding of inputs.
- [ ] **Severity mapping:** one mapping from state to severity in `lib/severity.ts`, used by every badge. "Sin aprobar" looks the same everywhere, `missing`.
- [ ] **Removing a member:** "Quitar" is a `dashboard-button`. The confirm is `button-danger`, as other destructive actions are.
- [ ] **No repeated titles:** a register panel does not repeat the page H1. It has no title on Incidentes, Revisiones de acceso and Formación.
- [ ] **Shell grid:** the portfolio (`/app`) and `/app/new` sit on the console page grid, with the page header and panels.
- [ ] **Line length:** `.page-description` is at most 72ch, like other supporting copy.
- [ ] **Placeholders:** input placeholders use the `muted` token, which passes AA on the field in both themes. The contrast test covers the pair.
- [ ] **Assistant launcher:** on phones, the console reserves bottom padding for the launcher, so it never covers a primary button such as "Registrar aprobación" at 390 px. The launcher does not move.

### Spanish (P3)
- [ ] **"Tú" everywhere:** every console string uses "tú": no "vosotros" forms (vuestro, tuvisteis, os…) and no "usted". Public and landing keys belong to another lane; the pull request lists their occurrences.
- [ ] **Terms and phrasing:**
  - "Encargados" becomes "Responsables de medidas", because in the GDPR an "encargado" is a processor;
  - no "de un vistazo";
  - no triads such as "Qué está comprobado, qué falta y cómo avanzar";
  - no slogans such as "Todo lo que pide el auditor en un solo documento"; the dossier intro says plainly what it contains;
  - "Conecta una herramienta para registrar evidencias solas" becomes plain Spanish.
- [ ] **Mi trabajo, empty:** an owner or admin sees a link to assign measures (the framework register), never "Un administrador puede asignártelas". Members keep a role-correct line.
- [ ] **Report month:** the month picker reads in the interface language, not "November 2026".
- [ ] **English:** EN strings stay complete and match.

## Tests

| Area | Cases |
|---|---|
| Unit | countdown hours and days, running and past due; task order (clock, overdue, my week, the rest), and my later measures left out; overdue not double counted; getting started full, one line from 5 of 7, hidden at 7 of 7; Registros incidents row with a running clock; incident close asks for confirmation with open clocks; the records sentence lists only figures that need action and no tiles; chart thresholds (7 days); the shared severity map; members "Quitar" is a button; no vosotros or usted in console strings; month input localised |
| e2e | home: the task list is the first region after the header at 390 and 1440; axe and no overflow as before |
