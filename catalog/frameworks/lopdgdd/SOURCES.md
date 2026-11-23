# LOPDGDD (security of processing): source and mapping review record

Status: draft. Prepared on 2026-11-23; qualified normative and mapping review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- **Act:** Ley Orgánica 3/2018, de 5 de diciembre, de Protección de Datos Personales y garantía de los derechos digitales (BOE núm. 294, 6.12.2018, `BOE-A-2018-16673`), consolidated text.
- **Captured** on 2026-11-23 from the BOE open data API, `https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2018-16673/texto`, with `Accept: application/xml` (HTTP 200). SHA-256 `18144157087656060bd9210224675d22f3c77c3e180d57ea66436fc195ef54a7`. The hash identifies the retrieved file, not future responses.
- **Versions:** the API returns each provision with its versions. The pack uses the latest version of each.
  - All six imported provisions have a single version, in force since 2018-12-07.
  - Provisions that were amended (for example Articles 2, 23, 24 and 44) are not imported.
- **Extraction:**
  - each provision's first paragraph is its heading; the rest are its paragraphs, in order;
  - normalization is whitespace only (tabs, no-break spaces and runs of spaces become one space);
  - the SHA-256 per requirement hashes `{"id", "paragraphs_es", "paragraphs_en": []}` as for the EU packs.
- **Imported:**
  - Article 5 (duty of confidentiality);
  - Article 28 (general obligations of controller and processor);
  - Article 31 (record of processing activities);
  - Article 32 (blocking of data);
  - Article 33 (processor);
  - the first additional provision (security measures in the public sector, which points to the ENS).
- **No English:** there is no official English text. `title_en` and `official_text_en` are empty, never translated.
- **Coverage:** `coverage.yaml` lists all 144 provisions of the consolidated text:
  - 98 articles, including Article 53 bis;
  - 23 additional, 6 transitional, 1 repealing and 16 final provisions.

  Each is covered or excluded with its reason in Spanish and English.
- **Reuse:** legislative text is excluded from copyright under Article 13 of RDL 1/1996.

## Candidate mappings

- **Eight candidate mappings** to documentary guides:
  - information handling;
  - people awareness;
  - risk analysis;
  - supplier and cloud review;
  - security governance.
- **No reviewer identity is invented;** every `reviewed_by` is null. Mappings are preparation aids, not equivalence claims.
