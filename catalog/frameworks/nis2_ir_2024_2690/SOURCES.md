# NIS2 Implementing Regulation (EU) 2024/2690: source and mapping review record

Status: draft. Prepared on 2026-11-23; qualified normative and mapping review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- **Act:** Commission Implementing Regulation (EU) 2024/2690 of 17 October 2024, OJ L, 2024/2690, 18.10.2024, CELEX `32024R2690`.
- **Captured** on 2026-11-23 from the EU Publications Office repository, because EUR-Lex HTML answers automated clients with a challenge:
  - `http://publications.europa.eu/resource/celex/32024R2690`, with `Accept: application/xhtml+xml`;
  - `Accept-Language: spa` resolved to manifestation `28f15de8-8ce9-11ef-a130-01aa75ed71a1.0007.03`, SHA-256 `65a0fc429b7f6597185b8bbc476a44a9afde374e1add8bb34327aab99459cf6f`;
  - `Accept-Language: eng` resolved to manifestation `28f15de8-8ce9-11ef-a130-01aa75ed71a1.0006.03`, SHA-256 `1d10f42c31a2b3c6b929b4696a04093ee1d84a298c0c0437a22f8718a9ffb3cd`.

  These hashes identify the retrieved files, not future responses.
- **Extraction:** `apps/api/devtools/eu_act.py` reads both captures:
  - articles with the default reader;
  - the Annex with `--annex`.

  Normalization is whitespace only.
- **The Annex reader:**
  - It keeps each numbered heading ("1.", "1.1.") and each numbered point ("1.1.1.") with its paragraphs in document order.
  - Lettered and numbered sub-points keep their label ("a) …", "(a) …", "i) …"); nested ones are indented under their parent.
  - Points 5.2 and 12.5 have no number of their own in the Journal: the text follows its subsection heading. Each is imported under the subsection's number.
- **Completeness check (both languages):** the extracted text matches the Annex text character for character, whitespace aside. Two differences remain, and both are accounted for:
  - the Annex title, which is not imported;
  - the labels "5.2." and "12.5." added to the two unnumbered points.

  The Spanish and English extractions have the same 161 points in the same order, with the same number of paragraphs in each.
- **Imported:** Article 2 and the 161 points of the Annex, 162 requirements in total.
- **Requirement text and hash:**
  - `official_text_es` and `official_text_en` keep each paragraph;
  - the SHA-256 per requirement hashes `{"id", "paragraphs_es", "paragraphs_en"}` as UTF-8 JSON with sorted keys and `ensure_ascii=False`, as for NIS2.
- **Titles:** the official heading of the point's subsection (or of its section, where points hang directly off it), plus "· punto 1.1.1" / "· point 1.1.1". Group headings are the official subsection and section headings, in Spanish and English.
- **Scope and applicability text:** the pack quotes the list of relevant entities of Article 1 verbatim. Its applicability note follows Article 2(2), including the three phrases quoted from the English text.
- **Coverage:** `coverage.yaml` lists all 16 articles and the Annex. Each unit is either covered by named requirements or excluded with its reason in Spanish and English.
- **Reuse:** EU documents may be reused under Commission Decision 2011/833/EU, © European Union. Legislative text is reproduced as published.

## Corrigenda check (2026-11-23)

- **Source of the list:** the Publications Office SPARQL endpoint (`https://publications.europa.eu/webapi/rdf/sparql`, `cdm:resource_legal_corrects_resource_legal`) lists four corrigenda, `32024R2690R(01)` to `R(04)`.
- **Languages:** they cover Polish (R(01)), Swedish (R(02)) and Dutch (R(03), R(04)). None covers Spanish or English, so the imported texts are unaffected.

## Candidate mappings

- **162 candidate mappings,** one per requirement, to the documentary guide of the requirement's Annex section. For example:
  - 1 and 7 → `ctl.security_governance`;
  - 2 and Article 2 → `ctl.risk_analysis`;
  - 3 → `ctl.incident_response`;
  - 11 → `ctl.access_review`;
  - 13 → `ctl.physical_security`.
- **No automated control is mapped yet.** The scanner's controls can be added point by point once a reviewer agrees on them.
- **No reviewer identity is invented;** every `reviewed_by` is null. Mappings are preparation aids, not equivalence claims.
