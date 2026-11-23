# DORA source and mapping review record

Status: draft. Prepared on 2026-11-23; qualified review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- **Act:** Regulation (EU) 2022/2554 (DORA), Official Journal L 333, 27.12.2022, p. 1, CELEX `32022R2554`.
- **Captured** on 2026-11-23 from the EU Publications Office repository (`http://publications.europa.eu/resource/celex/32022R2554`, `Accept: application/xhtml+xml`):
  - Spanish: manifestation `0caf473a-85bd-11ed-9887-01aa75ed71a1.0023.03`, SHA-256 `167638109bd5f962ed23e59d76d6e57ed727f68de821346c4d5e3a3efde700ab`;
  - English: manifestation `0caf473a-85bd-11ed-9887-01aa75ed71a1.0006.03`, SHA-256 `cf50d8f023d23b2a56f535aaee0760eba7f1925ef08a9858c5c31d43d414f46b`.
- **Corrigenda:**
  - The Publications Office SPARQL endpoint (`https://publications.europa.eu/webapi/rdf/sparql`, `cdm:resource_legal_corrects_resource_legal`) lists nine corrigenda, `32022R2554R(01)` to `R(09)`.
  - Their languages are BUL, DEU, EST, FRA, HRV, HUN, LAV, NLD, POL, POR, RON and SLV.
  - **None corrects the Spanish or English text.**
- **Extraction:**
  - **Extractor:** `apps/api/devtools/eu_act.py`; normalization is whitespace only.
  - **Pairing:** every article has the same number of paragraphs in both languages.
- **Granularity:** **one requirement per article.**
  - The title is the official article title.
  - The text holds every paragraph and point of the article.
  - The ID carries the chapter (`c2.art5`), so the register groups articles under the official chapter headings, in Spanish and English.
  - Each article mixes duties of different weight, and some paragraphs address authorities. A reviewer must read the whole article.
- **Source spelling is preserved.** Article 5(1) in Spanish reads "A fin lograr un nivel elevado…", without "de", as published.
- **Imported:**
  - Articles 5 to 14 and 16 (ICT risk management, including the simplified framework);
  - Articles 17 to 19 and 23 (incident management, classification and reporting);
  - Articles 24 to 27 (digital operational resilience testing);
  - Articles 28 to 30 (ICT third-party risk);
  - 22 requirements in total.
- **Coverage:** `coverage.yaml` accounts for all 64 articles; every article not imported carries its reason in Spanish and English.
- **Not imported:**
  - the delegated and implementing technical standards that detail the articles;
  - the oversight framework for critical ICT third-party providers (Articles 31 to 44).
- **Reuse:** under Commission Decision 2011/833/EU, © European Union.

## Candidate mappings

- 47 candidate mappings link the 22 articles to existing common guides.
- Each article keeps at least one documentary review.
- Technical observations (administrator MFA, Workspace 2-step verification, legacy authentication, mailbox audit bypass) support Articles 9 and 10 only partially.
- Every `reviewed_by` is null.
