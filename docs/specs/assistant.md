# Spec: assistant without an AI model

- Requirement ids: none yet (owner request, 23/11/2026, #357; engine #359)
- Status: approved (owner decisions of 23/11/2026, relayed by the coordinator)
- ADRs: ADR-010 amendment 2 (proposed: v1 uses no generative model), ADR-005 (nothing here
  decides pass or fail), ADR-011 (frameworks are content packs), ADR-013 (interface work)
- Depends on: landing-legal (static export, CSP, claims honesty, copy budget), claims-honesty,
  i18n-complete, requirement-register (808 evidence, 890C profiles, 803 valuation steps)

## Problem

An SME preparing for the ENS has small, precise questions: what does op.acc.6 ask, what evidence
does an auditor expect for it, which category is our system, does the essential profile fit us,
how long do we have to report an incident. Today the answers are spread over the BOE, the
Directive and three CCN-STIC guides. A chatbot that writes its own answers would be quicker but
could invent a deadline or a requirement, and nobody could check where an answer came from.

## Decisions (owner, 23/11/2026)

| Id | Decision |
|---|---|
| D1 | Two assistants: a public one on the landing and a signed-in one in the app. |
| D2 | No AI model at all. Retrieval and guided flows only; nothing is generated. |
| D3 | Catalog content only, plus a product FAQ that the owner reviews. No customer data. |
| D4 | Spec and build now. |

## What the assistant answers with

Every answer is a card that quotes catalog content verbatim and names its source. The cards are:

| Card | Content (verbatim) | Citation |
|---|---|---|
| Official text | A requirement's official text, ES and, where published, EN | Framework, requirement code, section, source URL (BOE or EUR-Lex) |
| Expected evidence | The CCN-STIC 808 items the owner signed for an ENS measure | Guide, edition, section, page |
| Profile | A CCN-STIC 890C profile: its summary and each measure's value | Guide, edition, section, page |
| Valuation | A CCN-STIC 803 valuation question or note | Guide, edition, section, page |
| Reporting clock | A pack's reporting clock (duration) with the official text it comes from | Framework, requirement code, source URL |
| FAQ | An entry of the product FAQ, in our own words | "Preguntas frecuentes de Atesta", entry id, review state |

The index holds only content that is public or signed:

- official texts (`official_text_es`, `official_text_en`) of the packs in the v1 corpus;
- catalog blocks whose `reviewed_by` is set (808 expected evidence, 890C profiles, 803 scope
  guide); a block without a signature is left out;
- reporting clocks and incident criteria, which point at official texts;
- the product FAQ, whose cards say "Pendiente de revisión" until the owner signs it.

Mappings, control guides, pack summaries and anything else still a candidate stay out.

**v1 corpus:** ENS (RD 311/2022), NIS2 (Directive 2022/2555, Articles 20, 21 and 23), GDPR
Articles 32 to 34 and the LOPDGDD articles in the catalog. DORA, its RTS and the NIS2
Implementing Regulation (about 140 KB gzipped together) join when the budget allows.

## Acceptance criteria

Content and honesty

- [ ] No generative model, no remote call: the engine runs in the browser over a static JSON
      index. A query never leaves the browser, so nothing about it is logged or stored.
- [ ] Every card carries at least one citation. A card without one is dropped at index build and
      again at render.
- [ ] Official text published only in Spanish is shown as is and marked `lang="es"` in the
      English interface; it is never translated.
- [ ] When the best match scores below the threshold, the assistant says it found no answer in
      the catalog and offers the contact address (`legalEntity.email`). It never improvises.
- [ ] The FAQ lives in `apps/web/src/content/assistant-faq.json` (ES and EN), in our own words.
      Until `reviewed_by` is set, each FAQ card says "Pendiente de revisión"; agents never set it.
- [ ] The FAQ passes claims honesty: `test_claims.py` scans it. No "certificado", no "cumple",
      nothing beyond shipped features; the scan of connected systems stays "Próximamente".
- [ ] The guided flows decide nothing about the customer's compliance (ADR-005). The category
      flow applies the CCN-STIC 803 rule the catalog records (the category follows the highest
      level) to the levels the person picks, says the result is a guide, and stores nothing.

Search

- [ ] Normalisation: lower case, accents folded, punctuation dropped, a light ES and EN plural
      and vowel stemmer, ES and EN stop words.
- [ ] Measure codes are one token whatever their spelling: `op.acc.6`, `OP.ACC.6`, `op acc 6`,
      `op-acc-6` and `opacc6` all find op.acc.6.
- [ ] Curated synonyms (`apps/web/src/content/assistant-synonyms.json`) expand the query, for
      example "backup" to "copias de seguridad" and "MFA" to "autenticación".
- [ ] Ranking is BM25 over weighted fields (code, title, keywords, text). An exact code match
      ranks first. At most five cards; no card under the threshold.
- [ ] Golden queries return the expected first card: "op.acc.6" (op.acc.6), "copias de
      seguridad" (mp.info.6), "plazo NIS2 24 horas" (NIS2 early warning, Article 23(4)(a)),
      "categoría MEDIA" (CCN-STIC 803, section 4.1), and nonsense returns no answer.

Guided flows

- [ ] "¿Qué categoría ENS tengo?": the five 803 questions (C, I, T, A for information, D for the
      service), each quoted with its citation; the person picks a level for each; the result is the
      category the catalog's 803 table gives for the highest level, with the 803 notes it rests on.
- [ ] "¿Qué evidencias pide una medida?": pick an ENS measure; the signed 808 items, each cited.
- [ ] "¿Me aplica el perfil esencial (890C)?": two questions (all dimensions low; IT or IT/OT/IoT
      scope). Not all low: the profile does not fit (890C §2). Otherwise the matching profile card,
      whose quoted summary states the NIS2 condition, and each measure's value with its 890C
      criterion section.
- [ ] "¿Qué plazos tengo ante un incidente?": pick NIS2 (significant incident) or GDPR (personal
      data breach); the pack's clocks with their official text, and the incident criteria.
- [ ] "¿Qué cubre Atesta?": the FAQ entries.

Surfaces

- [ ] Landing: a launcher button fixed at the bottom right opens the panel. The index and the
      engine load on first open only (dynamic import and `fetch`), never with the page.
- [ ] App: the same launcher, engine and index in the signed-in console. A card about a
      requirement also links to that requirement in the current organization's framework page
      (`/app/framework?org=…&framework=…#req-<code>`).
- [ ] The index is a static asset, `/assistant/index.json`, written by `scripts/assistant-index.ts`
      before `next build`. Budget: 250 KB gzipped; the build fails above it. CSP stays `'self'`
      with 0 script hashes: no inline script, no new origin.
- [ ] Assistant strings live in the `assistant` message namespace (ES first, EN second). They are
      a product surface, so the landing copy budget (amendment A1) does not count them.

Accessibility

- [ ] The panel is a non-modal `<dialog popover="auto">` (modern-web-guidance, dialog rule 2): the
      page stays usable, Esc closes it, a visible close button closes it, focus moves to the search
      field on open (or to "Volver" when a flow is open, since reopening keeps the flow) and back to
      the launcher on close.
- [ ] Results are announced through one `role="status"` live region ("3 respuestas", "Sin
      respuesta"); the cards themselves are not live.
- [ ] Everything works with the keyboard alone. axe reports no violations at 375 and 1280 px, in
      light and (in the app) dark mode.

## Out of scope

- Any generative model, embeddings or server-side search (ADR-010 v2 work).
- Customer data in the index, and answers about a specific organization's state.
- Saving conversations, analytics of queries, or a feedback button.
- DORA, its RTS and the NIS2 Implementing Regulation in the v1 corpus.

## Design notes

- Engine, pure TypeScript in `apps/web/src/lib/assistant/`: `normalize.ts` (tokens, codes, stems,
  synonyms), `search.ts` (BM25F scorer, threshold), `flows.ts` (decision trees over the index),
  `types.ts`. No search library: about 150 lines of our own beat a dependency here.
- Index builder `apps/web/scripts/assistant-index.ts` reads `catalog/frameworks/*` with `js-yaml`
  (MIT, already in the lockfile, now pinned as a dev dependency) and the FAQ, keeps the public or
  signed content listed above, and writes `public/assistant/index.json` (git-ignored).
- UI: `components/assistant/launcher.tsx` (button and empty dialog, in every page bundle, small)
  and `components/assistant/panel.tsx` (lazy). Reuses DESIGN.md tokens, the search field, the
  primary button and ruled rows. DESIGN reviews the launcher's placement against the landing work.
- Security: no `dangerouslySetInnerHTML`; catalog text renders as text. Links are the catalog's
  own `https://` sources, opened with `rel="noopener noreferrer"`.

## Test plan

| Test | Proves |
|---|---|
| Unit: normalisation (accents, plurals, codes in five spellings, stop words, synonyms) | Search input |
| Unit: BM25 ranks an exact code first; field weights; threshold returns nothing for nonsense | Scoring |
| Unit: golden queries on the real index built from the catalog | Answers |
| Unit: every document in the built index carries a citation; unsigned blocks are absent | Citation rule |
| Unit: index under 250 KB gzipped | Budget |
| Unit: flows (category from levels, 890C branches, clocks) and the panel's cards render citations | Flows |
| Python: `test_claims.py` scans the FAQ | Claims honesty |
| e2e landing: open with keyboard, search, cards with citations, no answer offers contact, Esc closes and focus returns; axe at 375 and 1280 | Public surface |
| e2e app: the same in the console, with the link to the organization's measure; axe light and dark | Signed-in surface |
