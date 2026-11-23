# NIS2 source and mapping review record

Status: draft. Prepared on 2026-11-23; qualified normative and mapping review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- **Act:** Directive (EU) 2022/2555 (NIS2), Official Journal L 333, 27.12.2022, p. 80, CELEX `32022L2555`.
- **Captured** on 2026-11-23 from the EU Publications Office repository, because EUR-Lex HTML answers automated clients with a challenge:
  - `http://publications.europa.eu/resource/celex/32022L2555`, with `Accept: application/xhtml+xml`;
  - `Accept-Language: spa` resolved to manifestation `9b84d482-85bd-11ed-9887-01aa75ed71a1.0023.03`, SHA-256 `9a9d3ac0a00dd900e61b2bf1c8d578c05cab508578d7bf0b9b7017e9ae8ffdaf`;
  - `Accept-Language: eng` resolved to manifestation `9b84d482-85bd-11ed-9887-01aa75ed71a1.0006.03`, SHA-256 `6ee66d5c419d9a056fb98d94083cacf9b818803bd6b416435718e0d4919cb589`.

  These hashes identify the retrieved files, not future responses.
- **Extraction:** `apps/api/devtools/eu_act.py` reads both captures.
  - **Normalization is whitespace only:** no-break spaces become spaces, and runs of whitespace collapse.
  - **Points:** lettered points keep their letter ("a) …", "(a) …").
  - **Pairing:** every article has the same number of paragraphs in both languages, so the Spanish and English texts pair one to one.
- **Imported:**
  - Article 20 (governance);
  - Article 21(1) to (4) (cybersecurity risk-management measures), with each point of 21(2) as its own requirement;
  - Article 23(1) to (4) (reporting obligations), with each point of 23(4) as its own requirement;
  - 23 requirements in total.
- **Requirement text and hash:**
  - `official_text_es` and `official_text_en` keep each paragraph;
  - a point of 21(2) or 23(4) carries its paragraph's lead-in;
  - 23(4)(b) also carries the paragraph's derogation for trust service providers;
  - 23(4)(d) carries its sub-points i) to iv);
  - the SHA-256 per requirement hashes `{"id", "paragraphs_es", "paragraphs_en"}` as UTF-8 JSON with sorted keys and `ensure_ascii=False`.
- **Titles:**
  - the points of 21(2) use their own text, without the letter and the closing punctuation, first letter capitalized;
  - every other requirement uses the official article title plus its reference ("Obligaciones de notificación · apartado 4, letra a)").
  - Group headings are the official article titles, in Spanish and English.
- **Source spelling is preserved.** The Spanish title of Article 33 is printed as "edidas de supervisión…" in the captured Journal text. It is only in the coverage ledger, not in a requirement, and is left as published.
- **Coverage:** `coverage.yaml` lists all 46 articles and the three annexes. Each unit is either covered by named requirements or excluded with its reason in Spanish and English.
- **Out of scope for now:**
  - Implementing Regulation (EU) 2024/2690 (CELEX `32024R2690`): imported as its own pack, `nis2_ir_2024_2690`, with its own record;
  - Article 27 (registry of entities);
  - the Spanish transposing law.

  None of these is imported or claimed.
- **Reuse:** EU documents may be reused under Commission Decision 2011/833/EU, © European Union. Legislative text is reproduced as published.

## Candidate mappings

- **37 candidate mappings** link the 23 requirements to existing common guides. Each requirement keeps at least one documentary review.
- **Technical observations** (administrator MFA, Workspace 2-step verification, legacy authentication) support Art. 21(2)(j) only partially.
- **No reviewer identity is invented;** every `reviewed_by` is null.
- **Mappings are preparation aids,** not equivalence claims. Each requirement still needs its own evidence, scoped to the entity and to the Spanish transposition.

## ENS coverage ledger

`catalog/frameworks/ens_rd311_2022/coverage.yaml` lists the units of RD 311/2022 from the consolidated BOE text retrieved on 2026-11-23 (`https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191&tn=0`, SHA-256 `04438f4eb7887e798f91e1f134815cd6bb52352beed407a28b88a143598ab1c4`):
- 41 articles;
- three additional provisions, the single transitional provision, the single repealing provision and three final provisions;
- Annexes I to IV.

Annex II is covered by the 73 imported measures. Every other unit is excluded with its reason.

## Corrigenda check (2026-11-23)

- **Source of the list:** the Publications Office SPARQL endpoint lists nine corrigenda to Directive (EU) 2022/2555, `32022L2555R(01)` to `R(09)`.
- **Spanish:** none corrects the Spanish text.
- **English:** only `R(04)` (OJ L, 2023/90206, 22.12.2023) covers English.
  - It corrects Article 19(1) alone ("on 17 January 2025" becomes "by 17 January 2025"); captured text SHA-256 `fa8913a509771efdab0418a38f7381f1d01b8340d9638ff004b7d2f418172c75`.
  - Article 19 is not imported, so the imported text is unaffected.

## Reporting clocks (draft2, recorded-routines spec)

- `early_warning`: 24 hours, from Article 23(4)(a) ("en el plazo de veinticuatro horas desde que se
  haya tenido constancia del incidente significativo" / "within 24 hours of becoming aware of the
  significant incident").
- `notification`: 72 hours, from Article 23(4)(b) ("en el plazo de setenta y dos horas" / "within
  72 hours of becoming aware").
- `final_report`: one month after the notification under (b), from Article 23(4)(d) ("a más
  tardar un mes después de presentar la notificación del incidente contemplada en la letra b)" /
  "not later than one month after the submission of the incident notification under point (b)").
- All three need the significant-incident flag. The quoted texts are the imported
  `official_text_es` and `official_text_en` of `art23.4a`, `art23.4b` and `art23.4d`.
- Not modelled:
  - the intermediate report (23(4)(c)), which is due only on request;
  - the case of an incident still ongoing at the final report (23(4)(e)): a progress report then,
    and a final report within one month of handling the incident. That month starts from an
    event Atesta does not record. Notes cover it for now.
