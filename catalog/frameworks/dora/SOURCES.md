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

## Major incident criteria (draft5)

- **Act:** Commission Delegated Regulation (EU) 2024/1772 (RTS on the classification of ICT-related incidents and cyber threats), CELEX `32024R1772`.
- **Captured** on 2026-11-23 from the Publications Office (`http://publications.europa.eu/resource/celex/32024R1772`, `Accept: application/xhtml+xml`):
  - ES manifestation `fa35ec94-328d-11ef-a61b-01aa75ed71a1.0007.03`, SHA-256 `cec536d1de33db588b598124e0a9a509b91e3dd6ae069b6991864bada6fe3306`;
  - EN manifestation `…0006.03`, SHA-256 `ff97c2c669031563bfe256ae39a06f9d07b9136267577e447f1ac339265816c0`.

  Both have 13 articles with matching paragraph counts. The SPARQL endpoint lists no corrigenda.
- **Shown:** Articles 1 to 9 (classification criteria, major incidents and their materiality thresholds) are `incident_criteria` with `needs: significant`, extracted with `eu_act.py`. They carry the official ES and EN text and the usual per-text hash.
- **Not shown:**
  - Article 10 is about significant cyber threats, not incidents;
  - Articles 11 and 12 are addressed to competent authorities;
  - Article 13 is entry into force.
- **What the user sees:** the incident form shows the criteria next to the "significant" flag. Atesta shows the text; whether an incident is major is the financial entity's decision (ADR-005).
