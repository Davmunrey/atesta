# Spec: Public landing and legal pages

- Requirement ids: none yet (owner request, 13/11/2026)
- Status: approved (the owner delegated design and product decisions on 13/11/2026: "Tú decides
  siempre")
- ADRs: ADR-005 (AI never decides pass/fail), ADR-007 (EU only), ADR-011 (common controls),
  ADR-012 (tenant isolation)
- Depends on: web-shell (static export, i18n, CSP, tokens); scanner-connectors (real product
  views)

## Problem

A security lead or owner of a Spanish SME that sells to the public sector lands on the site. The
page has to show, without explaining, that the product is powerful: one screen with the ENS and
NIS2 position of their organization, built from their own systems. Today the public page is a
placeholder with a sign-in button. Spanish law also requires an aviso legal, the information on
how personal data is processed, and information on cookies before the site goes public.

## Decisions (13/11/2026, delegated by the owner)

| Id | Decision | Reason |
|---|---|---|
| L1 | The landing is product-led: the product views are the argument. No explanatory or trust copy on the landing (read-only access, EU hosting and the AI rules live in the legal pages and in sales material) | Owner direction: "quiero que el producto hable por sí solo" |
| L2 | The first real product screen is the overview with per-framework scores | It runs the whole pipeline (connector, scanner, common controls, framework scores); the evidence pack builds on the same data |
| L3 | The landing is not deployed publicly until every product view on it is rendered from data recorded from the real product against a test tenant | Showing a product that does not exist yet as if it did may be a misleading commercial practice (Ley 3/1991 de Competencia Desleal, art. 5; candidate, to be confirmed by the lawyer review) |
| L4 | Palette A on paper: ink `#141414`, paper `#F4F1EA`, highlighter `#FFE58A` in the product, yellow `#FFD23F` on ink for the closing CTA, stamp blue `#23389A`. Public pages are light only (`color-scheme: light`) | Design canvas version 6; market analysis (yellow is unclaimed in the category) |
| L5 | Typefaces: Newsreader for display, IBM Plex Sans for text and product UI, IBM Plex Mono for codes and hashes. All SIL OFL | Editorial, non-generic display type; Plex is legible at UI sizes |
| L6 | Positioning (owner, 23/11/2026, relayed by the coordinator; #308): one product and one brand, sold as plans and modules. The lead message is the ENS: prepare and keep it without a full-time consultant, for SMEs that sell to the public sector. NIS2, RGPD, LOPDGDD and DORA appear only as "también cubre", by plan. Consultancies get at most one short secondary line, never a second hero. No prices | The ENS is what the first buyers must show to public-sector clients; the other frameworks are add-ons, not separate products |
| L7 | The product moments show only what the console ships (#313): the official text and self-assessment of one ENS measure, the records an auditor asks for, and the dossier ready to sign. The scan across frameworks and the assistant join the page when they ship | L3 applies to each view, not only to the fixture's origin: the web app has no connector flow and the AI module no endpoint yet |

## Acceptance criteria

Visual system

- [ ] Colours come from `src/styles/tokens.css` (L4). No other colour literals in components.
- [ ] The three typefaces (L5) are self-hosted. The browser makes no request to Google Fonts or
      any other third party.
- [ ] Every text and background pair used meets WCAG 2.2 AA (4.5:1 body, 3:1 large text and UI);
      the pairs are listed in a test with their computed ratio. Text never animates below that
      ratio.

Content

- [ ] Sections, in order: header (wordmark, language switcher, "Entrar", "Solicitar acceso");
      hero (one ENS headline per L6, the CTA, the overview screen), then a "también cubre" line
      naming NIS2, RGPD, LOPDGDD and DORA and one short line for consultancies (#308); three product moments (L7), each a headline of at most six words
      next to a product view (the official text and self-assessment of one ENS measure, the
      records an auditor asks for, the dossier ready to sign); closing headline with the CTA; footer
      with the legal links.
- [ ] Copy budget: at most 60 words of marketing copy on the page, product views and footer
      excluded. No subtitles, eyebrow labels, section paragraphs or taglines.
- [ ] No price, no customer logos, no testimonials, and no figures outside the product views.
- [ ] Product views are React components fed by one fixture, `src/content/landing-fixture.json`.
      The fixture has an `origin` field: `illustrative` until L3 is met, then `recorded` with the
      scan id and date of the test-tenant run it was exported from. It holds no customer data.
- [ ] ENS measure codes and names shown in the product views are copied from RD 311/2022,
      anexo II (BOE-A-2022-7191).
- [ ] Main CTA "Solicitar acceso": `mailto:` to the contact address in `src/content/legal-entity.ts`.
      Until the owner sets it, the address is a marked placeholder on the reserved `.invalid`
      domain, and `check-legal` blocks any placeholder value (owner, 23/11/2026). Secondary:
      "Entrar" (sign-in). No form until a form spec exists.
- [ ] The product name is one message key (`brand.name`). Internal identifiers (`atesta_api`,
      cookie names) do not change with the brand.
- [ ] ES first, EN second (rule 11); `lang` set on `<html>`; the existing locale switcher.

Motion

- [ ] CSS only: keyframes, transitions and scroll-driven animations (`animation-timeline:
      view()` and `scroll()`). No animation library and no animation script, so the CSP hash list
      does not grow.
- [ ] Motion comes from the product itself: score rings fill, counters count, matrix cells mark,
      timeline entries arrive, the export bar completes and the stamp lands. Nothing loops, so
      nothing moves for more than five seconds on its own (WCAG 2.2.2 does not apply).
- [ ] Every element's resting style is its final, readable state. Browsers without scroll-driven
      animations show the page complete and static.
- [ ] Only `transform`, `translate`, `scale`, `opacity`, `stroke-dashoffset` and registered
      custom properties are animated. CLS under 0.1; the hero headline is the LCP element and
      paints without waiting for any animation (LCP under 2.5 s on the CI e2e profile).
- [ ] `prefers-reduced-motion: reduce` stops every animation and transition.
- [ ] Motion tokens in `tokens.css`: ease-out `cubic-bezier(.215, .61, .355, 1)`; 200 ms for
      hover, 700 to 1400 ms for entrances; entrance distance 24 to 28 px.

Legal pages (Spanish is the binding version)

- [ ] `/aviso-legal` shows the information in LSSI art. 10.1 a), b), e) and g): name or company
      name, address, email and another direct contact channel, registry details (if a company),
      NIF, codes of conduct (none). 10.1 f) does not apply while no price is shown.
- [ ] `/privacidad` gives the information in RGPD art. 13.1 and 13.2 for each processing:
      controller and contact; DPO (only if appointed); purposes and legal basis; legitimate
      interests where art. 6.1 f) is the basis; recipients (processors such as AWS in
      eu-south-2); international transfers (none intended outside the EU/EEA; state the
      safeguards if a processor's contract allows one); retention; rights under arts. 15 to 22;
      complaint to the AEPD; whether giving the data is required; automated decisions (none:
      ADR-005). The first layer next to any data collection follows LOPDGDD art. 11.2.
- [ ] `/cookies` lists every cookie the site and app set, with purpose and duration: the
      language preference (chosen by the user) and the sign-in session cookies (strictly
      necessary). Both are exempt from consent under LSSI art. 22.2 as read by the AEPD guide
      (May 2024, "cookies de preferencias o personalización" chosen by the user, and cookies
      needed to provide a service the user requested). With no analytics or third-party
      cookies there is no consent banner. Adding any non-exempt cookie requires this spec to
      change first.

Release gates (run by the deploy job, not by CI, so drafts can merge)

- [ ] `pnpm check-legal` fails while any field of the legal identity file (name, NIF, address,
      registry, email) is empty.
- [ ] `pnpm check-landing` fails while the landing fixture's `origin` is not `recorded` (L3).
- [ ] The legal texts are reviewed by a lawyer before the site is public. This spec does not
      replace legal advice.

### Release gate input contract

`pnpm check-legal` reads the named `legalEntity` export from
`src/content/legal-entity.ts`. It must be an object with non-blank string fields `name`,
`nif`, `address`, `registry` and `email`. `pnpm check-landing` reads
`src/content/landing-fixture.json`: `origin` must equal `recorded`, `scan_id` must be a
UUID and `scan_date` a real calendar date in `YYYY-MM-DD` form. These metadata checks
do not authenticate the recorded run or replace the lawyer's review.

Both commands accept one optional input file path for isolated verification. Defaults resolve
relative to the web package, regardless of the caller's working directory. Missing, unreadable,
malformed or incomplete input exits with code 1 and field names only, never the input values.
Unexpected arguments also fail closed. Run both commands before uploading a public release;
keep them separate from `build` and CI so drafts can still merge. No deploy job exists yet.
Until the landing implementation supplies these files, both gates intentionally block release.

## Out of scope

- Terms of service and the processor agreement (DPA, RGPD art. 28) for customers: separate
  documents, needed before the first contract.
- A trust or security page (read-only access, EU hosting, AI rules): separate spec if sales
  needs one.
- Contact form, newsletter, analytics, blog, pricing page.
- Trademark clearance of the product name (see the trademark report).

## Design notes

Design canvas: the owner's Claude design artifact, boards "Landing · el producto" (version 6),
"Paletas" and "Legal". Earlier directions were rejected by the owner on 13/11/2026: a dark SaaS
landing with bento grid, marquee and trust claims ("AI slop"), then an "expediente" page built on
stamps and trust claims ("no quiero dar explicaciones").

Tokens (L4; WCAG ratios computed 13/11/2026):

| Pair | Ratio |
|---|---|
| ink `#141414` on paper `#F4F1EA` | 16.33:1 |
| muted `#55514A` on paper | 6.99:1 |
| muted on white | 7.89:1 |
| ok `#1A6B43` on `#E4F3E8` | 5.66:1 |
| bad `#A3241C` on `#FBE8E5` | 6.29:1 |
| not evaluated `#55514A` on `#EEEBE4` | 6.63:1 |
| ink on highlighter `#FFE58A` | 14.76:1 |
| yellow `#FFD23F` on ink | 12.76:1 |
| stamp `#23389A` on paper | 8.85:1 |

Motion references (owner request, 13/11/2026: "efecto wow" like Clay, Vanta, Revolut, Nike and
Apple). Measured on 13/11/2026 with headless Chromium at 1440 x 900, by sampling computed styles
while scrolling. These are techniques to borrow, not designs to copy:

| Site | Stack | Measured | Taken for Atestas |
|---|---|---|---|
| clay.com | Webflow, GSAP + ScrollTrigger, 10 videos, 5 sticky elements | `cubic-bezier(.215, .61, .355, 1)` at 0.3 s; continuous logo marquee; scroll-scrubbed scale | Ease-out token; scroll-scrubbed scale of the overview screen |
| vanta.com | Webflow, GSAP + ScrollTrigger | Cards rise 24 px with opacity 0 to 1; real product UI fragments | 24 px entrance; real product UI as the argument |
| apple.com/es | No animation library | `cubic-bezier(.4, 0, .6, 1)` at 0.32 s; one product per screen | One product view per section, generous whitespace |
| nike.com/es | No animation library | Full-bleed media, very large headlines | Very large display headlines |
| revolut.com | Not measured | The site served a bot check to the headless browser; it was not bypassed | Nothing |

Files: `src/app/(public)/page.tsx`; `src/components/landing/` (overview, framework matrix, change
timeline, pack export, assistant); `src/content/landing-fixture.json`;
`src/content/legal-entity.ts`; `src/app/(public)/aviso-legal/`, `privacidad/`, `cookies/`;
`scripts/check-legal.ts`, `scripts/check-landing.ts`; messages in `messages/{es,en}.json`;
tokens in `src/styles/tokens.css`. The CSP hash list grows only with a new inline script
(budget: 1,783 characters, CloudFront limit).

Sources (official texts saved 13/11/2026):

- LSSI-CE, Ley 34/2002, arts. 10 and 22: BOE consolidated text, BOE-A-2002-13758, via the BOE
  open-data API.
- LOPDGDD, LO 3/2018, art. 11: BOE-A-2018-16673, via the BOE open-data API.
- RGPD, Reglamento (UE) 2016/679, art. 13: DOUE-L-2016-80807 (BOE copy of the DOUE).
- AEPD, "Guía sobre el uso de las cookies", updated May 2024:
  https://www.aepd.es/guias/guia-cookies.pdf
- ENS, Real Decreto 311/2022, anexo II: BOE-A-2022-7191, block `ai-2`, via the BOE open-data API.

## Test plan

| Test | Proves |
|---|---|
| Unit: every message key exists in ES and EN; `brand.name` used, no literal name in components | i18n, one-line rename |
| Unit: contrast table for every token pair used | WCAG AA |
| Unit: no colour literal outside `tokens.css` | Tokens only |
| Unit: marketing copy on the landing is at most 60 words | Copy budget |
| Unit: every ENS code in the fixture exists in the catalog with the same name | Official names |
| Unit: `check-legal` and `check-landing` fail on an incomplete input and pass on a full one | Release gates |
| e2e (Playwright + axe): landing, aviso legal, privacidad, cookies in ES and EN, no violations | Accessibility |
| e2e: the page loads with no request to a third-party host and sets no cookie before the user acts | No banner needed |
| e2e: CSP blocks an injected inline script on the landing | Security headers |
| e2e: with `prefers-reduced-motion: reduce`, `document.getAnimations()` has no running animation | Reduced motion |
| e2e: five seconds after load, no animation is still running | No looping motion |
| e2e: CLS under 0.1 and LCP under 2.5 s on the landing (Performance API) | Performance |
