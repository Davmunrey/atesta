# GDPR (Articles 32 to 34) source and mapping review record

Status: draft. Prepared on 2026-11-23; qualified review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- **Act:** Regulation (EU) 2016/679 (GDPR), Official Journal L 119, 4.5.2016, p. 1, CELEX `32016R0679`.
- **Captured** on 2026-11-23 from the EU Publications Office repository (`http://publications.europa.eu/resource/celex/32016R0679`, `Accept: application/xhtml+xml`):
  - Spanish: manifestation `3e485e15-11bd-11e6-ba9a-01aa75ed71a1.0023.03`, SHA-256 `7e6f4309e448e2532be3fd9464f3de7929a0e25b5c4c53239b320669b9bce33b`;
  - English: manifestation `3e485e15-11bd-11e6-ba9a-01aa75ed71a1.0006.03`, SHA-256 `962539af03738bf552319ff4ce42d69e5f95a576307c4dfed7bf87e81b646b9d`.
- **Corrigenda:**
  - The consolidated version `02016R0679-20160504` (Spanish SHA-256 `a23521b339f218febb2d6d0c1c5178433b4f3aad13c7cc3a8ad89df881ff3d40`, English SHA-256 `a681ff22f32f125749af6e96947224369efc132edb8a95b12637e357df1056de`) lists the corrigenda OJ L 127, 23.5.2018 (both languages) and OJ L 74, 4.3.2021 (Spanish).
  - No correction marker falls inside Articles 32 to 34.
  - Their consolidated wording is identical to the original apart from whitespace, in both languages.
- **Extraction and titles:**
  - **Extractor:** `apps/api/devtools/eu_act.py`; normalization is whitespace only.
  - **Pairing:** every article has the same number of paragraphs in Spanish and English.
  - **Titles:** the points of Article 32(1) use their own text, without the letter and the closing punctuation, first letter capitalized. Every other requirement uses the official article title plus its reference.
  - **Lead-ins:** each point of 32(1) carries the paragraph's lead-in; 33(3) and 34(3) carry their points.
  - **Hashes:** the hash per requirement follows the NIS2 rule (`catalog/frameworks/nis2/SOURCES.md`).
- **Imported:**
  - Article 32(1), with each point (a) to (d) as its own requirement, and Article 32(2) and (4);
  - Article 33(1) to (5);
  - Article 34(1) to (3);
  - 14 requirements in total.
- **Excluded:**
  - Article 32(3) is excluded: adherence to a code of conduct or certification is an element to demonstrate compliance, not a duty.
  - Article 34(4) is a power of the supervisory authority.
  - `coverage.yaml` accounts for all 99 articles; every unit not imported carries its reason in Spanish and English.
- **Not imported:** the Spanish Organic Law 3/2018 (LOPDGDD). A reviewer must check national specifications.
- **Reuse:** under Commission Decision 2011/833/EU, © European Union.

## Candidate mappings

- 26 candidate mappings link the 14 requirements to existing common guides.
- Each requirement keeps at least one documentary review.
- Technical observations (administrator MFA, Workspace 2-step verification, Workspace sharing) support Article 32(1)(b) only partially.
- Every `reviewed_by` is null.
- Mappings are preparation aids, not equivalence claims.

The Publications Office SPARQL endpoint lists three corrigenda, `32016R0679R(01)` to `R(03)`.
The consolidated version above incorporates the ones in Spanish and English.

## Reporting clock (draft2, recorded-routines spec)

- `breach_notification`: 72 hours, from Article 33(1) ("a más tardar 72 horas después de que haya
  tenido constancia de ella" / "not later than 72 hours after having become aware of it"). It
  needs the personal-data flag. The quoted texts are the imported `official_text_es` and
  `official_text_en` of `art33.1`.
- Article 33(1) applies "where feasible" and not when the breach is unlikely to result in a risk;
  Atesta shows the clock and leaves that judgement to the organization (ADR-005).
