# Spec: Public landing and legal pages

- Requirement ids: none yet (owner request, 13/11/2026)
- Status: draft
- ADRs: ADR-005 (AI never decides pass/fail), ADR-007 (EU only), ADR-012 (tenant isolation)
- Depends on: web-shell (static export, i18n, CSP, tokens)

## Problem

A security lead or owner of a Spanish SME that sells to the public sector lands on the site from
a referral or a search. In under ten seconds they need to know what the product does (evidence
for ENS and NIS2 audits), whether it is for a company like theirs, why they can trust it with
read-only access to Microsoft 365 or Google Workspace, and how to talk to someone. Today the
public page is a placeholder with a sign-in button. Spanish law also requires an aviso legal,
the information on how personal data is processed, and information on cookies before the site
goes public.

## Acceptance criteria

Visual system

- [ ] The layout system is adapted from the MongoDB design analysis in VoltAgent
      awesome-design-md (`design-md/mongodb/DESIGN.md`, MIT; "Not affiliated with or endorsed by
      MongoDB"). Its structure is reused: a dark hero band over light documentation surfaces,
      one bright CTA colour, pill CTAs, hairline borders, large medium-weight display type and a
      generous type scale. Its identity is not: no MongoDB green `#00ED64` or teal `#001E2B`, no
      leaf, no name, and not Euclid Circular A (a commercial typeface).
- [ ] Colours come from the palette the owner picks (Design notes, Palettes), as tokens in
      `src/styles/tokens.css`. No other colour literals in components.
- [ ] The typefaces are SIL OFL families, self-hosted with `next/font` at build time: Bricolage
      Grotesque (variable: optical size, width, weight) for display type, Plus Jakarta Sans for
      text, JetBrains Mono for codes and hashes. The browser makes no request to Google Fonts or
      any other third party.
- [ ] Every text and background pair used meets WCAG 2.2 AA (4.5:1 body, 3:1 large text and
      UI); the pairs are listed in a test with their computed ratio. Text never fades below that
      ratio as part of an animation; a decorative fade uses shapes, not text.

Motion

- [ ] CSS only: keyframes, transitions and scroll-driven animations (`animation-timeline:
      view()` and `scroll()`). No animation library and no animation script, so the CSP hash list
      does not grow.
- [ ] Progressive enhancement: every element's resting style is its final, readable state.
      Browsers without scroll-driven animations show the page complete and static.
- [ ] Only `transform`, `opacity`, `filter` and `background-size` are animated. Layout never
      moves after load (CLS under 0.1); the hero headline is the LCP element and paints without
      waiting for any animation (LCP under 2.5 s on the CI e2e profile).
- [ ] `prefers-reduced-motion: reduce` stops every animation and transition, and the hero
      product view is shown flat.
- [ ] A pause button in the header stops every animation, for anything that moves for more than
      five seconds (WCAG 2.2.2). It is a real `<button>` with `aria-pressed`.
- [ ] Motion tokens in `tokens.css`: ease-out `cubic-bezier(.215, .61, .355, 1)`, standard
      `cubic-bezier(.4, 0, .6, 1)`; 200 to 320 ms for hover and UI, 600 to 900 ms for entrances;
      entrance distance 24 px.

Content

- [ ] No price anywhere on the site (owner decision, 13/11/2026).
- [ ] The hero is a claim the visitor can check. The product view under it is labelled
      "ejemplo ilustrativo" until real screens exist, and it shows a "no evaluado" row, never only
      passes. No floating chat, no superlatives, no customer logos or figures that are not real
      and dated (market analysis rules, 13/11/2026).
- [ ] Every figure shows its official source in the same block. Figures checked on 13/11/2026:
      73 security measures in the ENS (RD 311/2022, anexo II, BOE-A-2022-7191, counted by measure
      code); 10 minimum risk-management elements in NIS2 (Directive (EU) 2022/2555, art. 21.2,
      letters a to j); 24 hours for the early warning of a significant incident (art. 23.4 a).
      The ENS measure names in the example (op.acc.6, op.exp.8, op.mon.3, mp.s.1, mp.info.6) are
      copied from anexo II.
- [ ] Every product statement is true on the day it is published. What is not built yet is
      labelled as such (for example, connectors "en desarrollo"). A reviewer checks each claim
      against the code or an ADR before release.
- [ ] Sections: hero with the illustrative scan; a marquee band of frameworks and sources (no
      customer logos); the problem (ENS and NIS2 for SMEs that sell to the public sector); the
      rule in three figures, with frameworks (ENS by category, NIS2); how it works, as three
      stacked cards (read-only connectors, scan once for every framework, evidence for the
      auditor); trust bento (read-only, data in the EU, AI cites and never decides pass or fail,
      tenant isolation, "no evaluado" is never a pass); questions; closing CTA; footer with the
      legal links.
- [ ] Main CTA: "Hablar con nosotros" (`mailto:` to the contact address). Secondary: "Entrar"
      (sign-in) for existing users. No form until a form spec exists.
- [ ] The product name is one message key (`brand.name`), so a rename is a one-line change.
      Internal identifiers (`atesta_api`, cookie names) do not change with the brand.
- [ ] ES first, EN second (rule 11); `lang` set on `<html>`; the existing locale switcher.

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
- [ ] The legal identity (name, NIF, address, registry, email) lives in one file. A release gate
      (`pnpm check-legal`, run by the deploy job) fails while any field is empty. CI does not
      run it, so drafts can merge.
- [ ] The legal texts are reviewed by a lawyer before the site is public. This spec does not
      replace legal advice.

## Out of scope

- Terms of service and the processor agreement (DPA, RGPD art. 28) for customers: separate
  documents, needed before the first contract.
- Contact form, newsletter, analytics, blog, pricing page.
- Trademark clearance of the product name (see the trademark report; owner decision pending).

## Design notes

Palettes (WCAG contrast computed 13/11/2026; market territories from the market analysis):

| Option | Hero band | CTA | Surfaces | Key pairs | Market |
|---|---|---|---|---|---|
| A, Tinta y amarillo (recommended) | `#111111` | `#FFD23F`, text `#111111` | `#FFFFFF`, `#FFF6E0` | 13.08:1 CTA; 17.54:1 cream on ink; 8.86:1 `#4A4A4A` on white | Yellow is unclaimed; only Vanta (`#FFBE0F`) and Workiva (`#FBAD17`) use it as a minor accent |
| B, Pino y ocre | `#0F2A22` | `#D9A441`, text `#0F2A22` | `#FFFFFF`, `#F7F1E6` | 6.79:1 CTA; 13.59:1 cream on pine | Deep green sits close to ServiceNow (`#032D42`, `#0A7B66`) |
| C, Lacre | `#1C1A17` | `#7A1E25`, text white | `#FFFFFF`, `#F4EEE2` | 10.29:1 CTA; 1.69:1 CTA on the band, so the hero CTA is inverted (`#7A1E25` on `#F4EEE2`, 8.91:1) | Red is also the "no conforme" state colour in a compliance UI |

MongoDB's own pair (`#00ED64` on `#001E2B`) is ruled out: neon green is a category cliché (five
competitor sites) and ServiceNow already uses dark teal with bright green.

Motion references (owner request, 13/11/2026: "efecto wow" like Clay, Vanta, Revolut, Nike and
Apple). Measured on 13/11/2026 with headless Chromium at 1440 x 900, by sampling computed styles
while scrolling. These are techniques to borrow, not designs to copy:

| Site | Stack | Measured | Taken for Atestas |
|---|---|---|---|
| clay.com | Webflow, GSAP + ScrollTrigger, 10 videos, 5 sticky elements | `cubic-bezier(.215, .61, .355, 1)` at 0.3 s; continuous logo marquee; scroll-scrubbed scale; stacked sticky cards | Ease-out token, marquee band (frameworks, not logos), stacked "how it works" cards |
| vanta.com | Webflow, GSAP + ScrollTrigger | Cards rise 24 px with opacity 0 to 1; hover 0.2 s ease; dot-grid hero; product UI fragments | 24 px entrance, dot grid, real product UI in the hero |
| apple.com/es | No animation library | `cubic-bezier(.4, 0, .6, 1)` at 0.32 s; subhead cross-fades; bento tiles; blurred sticky nav | Standard ease token, bento trust grid, blurred sticky header |
| nike.com/es | No animation library | Full-bleed media, giant condensed uppercase headlines, image fade-ins | Giant condensed statement ("Evidencias, no capturas") |
| revolut.com | Not measured | The site served a bot check to the headless browser; it was not bypassed | Nothing |

Design canvas with the three boards (landing, palettes, legal): owner's Claude design artifact.

Files: `src/app/(public)/page.tsx`, `src/app/(public)/aviso-legal/`, `privacidad/`, `cookies/`,
`src/content/legal-entity.ts`, messages in `messages/{es,en}.json`, tokens in
`src/styles/tokens.css`. The CSP hash list grows with any new inline script (budget: 1,783
characters, CloudFront limit).

Sources (official texts saved 13/11/2026):

- LSSI-CE, Ley 34/2002, arts. 10 and 22: BOE consolidated text, BOE-A-2002-13758, via the BOE
  open-data API.
- LOPDGDD, LO 3/2018, art. 11: BOE-A-2018-16673, via the BOE open-data API.
- RGPD, Reglamento (UE) 2016/679, art. 13: DOUE-L-2016-80807 (BOE copy of the DOUE).
- AEPD, "Guía sobre el uso de las cookies", updated May 2024:
  https://www.aepd.es/guias/guia-cookies.pdf
- ENS, Real Decreto 311/2022, anexo II: BOE-A-2022-7191, block `ai-2`, via the BOE open-data API.
- NIS2, Directiva (UE) 2022/2555, arts. 21.2 and 23.4: DOUE-L-2022-81963 (BOE copy of the DOUE).

## Test plan

| Test | Proves |
|---|---|
| Unit: every message key exists in ES and EN; `brand.name` used, no literal name in components | i18n, one-line rename |
| Unit: contrast table for every token pair used | WCAG AA |
| Unit: no colour literal outside `tokens.css` | Tokens only |
| Unit: `check-legal` fails on an empty legal field and passes on a full one | Release gate |
| e2e (Playwright + axe): landing, aviso legal, privacidad, cookies in ES and EN, no violations | Accessibility |
| e2e: the page loads with no request to a third-party host and sets no cookie before the user acts | No banner needed |
| e2e: CSP blocks an injected inline script on the landing | Security headers |
| e2e: with `prefers-reduced-motion: reduce`, `document.getAnimations()` has no running animation | Reduced motion |
| e2e: the header pause button sets `aria-pressed="true"` and leaves no running animation | WCAG 2.2.2 |
| e2e: with scroll-driven animations disabled, every section is visible and readable | Progressive enhancement |
| e2e: CLS under 0.1 and LCP under 2.5 s on the landing (Performance API) | No layout shift |
| Unit: every figure on the landing has a source string next to it | Sourced figures |
