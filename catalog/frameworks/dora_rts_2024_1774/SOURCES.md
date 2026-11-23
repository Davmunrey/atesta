# DORA RTS (EU) 2024/1774: source and mapping review record

Status: draft. Prepared on 2026-11-23; qualified normative and mapping review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- **Act:** Commission Delegated Regulation (EU) 2024/1774 of 13 March 2024, regulatory technical standards specifying ICT risk management tools, methods, processes and policies and the simplified ICT risk management framework. OJ L, 2024/1774, 25.6.2024, CELEX `32024R1774`.
- **Captured** on 2026-11-23 from the EU Publications Office repository (`http://publications.europa.eu/resource/celex/32024R1774`, `Accept: application/xhtml+xml`):
  - `Accept-Language: spa` resolved to manifestation `dc25b21e-328d-11ef-a61b-01aa75ed71a1.0007.03`, SHA-256 `6461b7b71f7e3d5fa37041dceaa7cc8dc43abb2278eecd5cb95924d7b3aa52bb`;
  - `Accept-Language: eng` resolved to manifestation `dc25b21e-328d-11ef-a61b-01aa75ed71a1.0006.03`, SHA-256 `3fbf45496164c4951eb66c56de0f08c3b8c9749a00532fd6f1ee7a831f037920`.
- **Extraction:** `apps/api/devtools/eu_act.py`, whitespace normalization only.
  - Both languages have 42 articles with the same paragraph count in each.
  - One requirement per article for Articles 1 to 41, ids `<title><chapter>.art<n>` (for example `t2c3.art22`). The web groups requirements by Title and Chapter.
- **Group headings:** the official Title and Chapter headings joined with " · ", exactly as published. For example, the Spanish edition prints "Capítulo II" in mixed case where the other chapters are upper case.
- **Hash:** the SHA-256 per requirement hashes `{"id", "paragraphs_es", "paragraphs_en"}` as for the other EU packs, after the corrigendum below.
- **Coverage:** Articles 1 to 41 are covered; Article 42 (entry into force) is excluded with its reason.

## Corrigenda check (2026-11-23)

- **Source of the list:** the Publications Office SPARQL endpoint lists two corrigenda:
  - `32024R1774R(01)`, Croatian only;
  - `32024R1774R(02)` (OJ L 2025/90420, 15.5.2025), in every language including Spanish and English.
- **R(02) corrects Article 22, first subparagraph, point (d):** the cross-reference to Delegated Regulation (EU) 2024/1772 becomes "Article 8(2)" / "artículo 8, apartado 2", instead of "Article 15" / "[artículo [15]".
  - Both corrigendum texts were captured: ES SHA-256 `5470ddd55b83808403665e542dbce707645d2276dbdb5cac081c40b81cd08a5a`, EN `7d372558c4b301e53fa52e086b19392469564de8a9eca1bd2d6d501088f3ff02`.
  - The generator checks that the captured text contains the corrigendum's "for" / "donde dice" wording exactly once, then replaces it with the "read" / "debe decir" wording.
  - The imported Article 22 is the corrected text.

## Candidate mappings

- **41 candidate mappings,** one per article, to the documentary guide of its subject. For example:
  - Articles 4, 5 and 30 → asset inventory;
  - Article 12 → activity logging review;
  - Articles 24 to 26, 39 and 40 → continuity and restore.
- **No reviewer identity is invented;** every `reviewed_by` is null. Mappings are preparation aids, not equivalence claims.
