# Spec: content model v2 and source coverage

- Issue: #148. Builds on `framework-catalog-preview.md` (ADR-011, rule 10).
- Status: draft

Every framework pack shows how much of its official source it covers, measured against the
source itself. Acts that are official in Spanish and English carry both texts.

## Acceptance criteria

**Content model**
- [ ] A requirement's selection basis and rules are optional, but always appear together. Its application clause is optional.
- [ ] `official_text_en` holds the official English text when the act is official in English.
- [ ] Group headings may carry `title_en`, the official English heading.

**Coverage ledger**
- [ ] **Required:** every pack with requirements has `coverage.yaml`. It lists every unit of its source (article, provision, annex, or a range of paragraphs inside one) exactly once.
- [ ] **Two statuses:** a unit is either covered by named requirements, or excluded with a reason in Spanish and English.
- [ ] **What the catalog refuses:**
  - a missing ledger;
  - a duplicate unit;
  - a covered unit that names an unknown requirement;
  - a requirement that is in no covered unit;
  - an excluded unit without both reasons.
- [ ] **Delivery:** the import stores the ledger with the framework, and the framework detail API returns it.

**NIS2**
- [ ] **What is imported:** Articles 20, 21(1)-(4) and 23(1)-(4) of Directive (EU) 2022/2555, 23 requirements.
- [ ] **Source and wording:** copied verbatim in Spanish and English from the captured Official Journal text. Provenance, capture hashes, normalization rules and limits are in `catalog/frameworks/nis2/SOURCES.md`.
- [ ] **Coverage:** the ledger accounts for all 46 articles and the three annexes.
- [ ] **Mappings and scoring:** candidate mappings keep a documentary review for every requirement and have no reviewer. Scoring stays disabled.
- [ ] **No claims:** the pack claims nothing about the Spanish transposition or Implementing Regulation (EU) 2024/2690.

**ENS**
- [ ] The ENS ledger accounts for its 41 articles, its eight additional, transitional, repealing and final provisions, and Annexes I to IV, from the BOE text.

**Web**
- [ ] The official text shows in the reader's language when the act is official in it. Otherwise it shows in Spanish, marked `lang="es"`.
- [ ] Group headings use the official English heading in English.
- [ ] "Coverage of the official source" lists each unit with its requirements or its reason.
- [ ] Selection tables appear only when a requirement has them.

## Out of scope

- **Other packs and laws:** GDPR, DORA and the other packs; Implementing Regulation (EU) 2024/2690; the Spanish NIS2 transposition.
- **Release:** qualified review, and releasing or scoring any pack.

## Test plan

- **Unit, extractor:** the extractor keeps wording, points and order on synthetic XHTML.
- **Catalog:**
  - each ledger failure is refused;
  - both packs account for every unit of their source;
  - NIS2 keeps verbatim ES and EN quotes from the captured text;
  - no NIS2 mapping is reviewed, and each requirement keeps a documentary review.
- **Web unit:**
  - official text in each language and the fallback;
  - no selection table without rules;
  - the coverage list and its plurals.
- **Real app:** the NIS2 page in ES and EN, at 1280 and 375 pixels.
