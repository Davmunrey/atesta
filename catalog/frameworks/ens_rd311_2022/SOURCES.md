# ENS source and mapping review record

Status: draft. Prepared on 2026-11-13; qualified normative/mapping review is pending.
This pack cannot be scored, including when development draft visibility is enabled.

## Source boundary

- [Official publication](https://www.boe.es/diario_boe/txt.php?id=BOE-A-2022-7191):
  RD 311/2022, BOE 106, 2022-05-04, pages 61715–61804.
- [Current consolidated reference](https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191):
  last published update shown as 2024-11-06 when retrieved. Consolidated BOE text is
  informative; the original official publication remains the legal source.
- All 73 Annex II measure headings, paragraphs and selection tables match between the two
  captured documents after HTML entity decoding and whitespace normalization. Preserve
  source spelling, including typographical inconsistencies; do not silently correct law.
- `official_text_es` retains measure/reinforcement paragraphs. `applicability_es` retains
  the application clauses, including alternatives. `selection_rules` retains each table
  cell. `selection_basis` distinguishes category from dimension level. `applies_to` stays
  empty: the existing flat tag filter cannot decide ENS applicability correctly.
- Source section and SHA-256 accompany each measure. Hash input is the normalized source
  record with keys `id`, `title_es`, `section`, `paragraphs`, `tables`, serialized as UTF-8
  JSON with sorted keys, ensure_ascii=False and default Python JSON separators.
- Diagrams and figures are not reproduced; consult BOE. Articles, Annex I categorization,
  Annex III audit, other annexes, technical instructions and applicable profiles are not
  separate assessed requirements in this first pack. The pack is therefore partial even
  though every Annex II measure has been imported.

Captured original HTML SHA-256:
`6249bcb304bd17439c767cf2bd025df9a307c2781cf32c3154cdfe026a07f135`.
Captured consolidated HTML SHA-256:
`78164a180f744a3071c02b4030bc45bcce6f3f852e107d81e6780bef9dd55bf8`.
These identify the retrieved pages, not future BOE responses or only the annex.
REA capture: `ev_812795b24763887230a2edbeeb5ccbbbc46674b9f822a6a75374de5750c90597`.

Legislative text is excluded from copyright under
[Article 13 of RDL 1/1996](https://www.boe.es/buscar/act.php?id=BOE-A-1996-8930#a13).
No copyrighted CCN-STIC guide, ISO standard or AICPA criteria are reproduced. The
[CCN update notice dated 2026-06-02](https://www.ccn-cert.cni.es/es/seguridad-al-dia/novedades-ccn-cert/13155-el-ccn-actualiza-cuatro-guias-ccn-stic-de-su-serie-800-sobre-el-esquema-nacional-de-seguridad.html)
is a review pointer, not a claim that those guides are incorporated into the pack.

## Candidate mappings and configuration guidance

Twenty common documentary controls provide an initial review route for all 73 measures.
Their groupings are preparation aids, not equivalence claims. Each measure and applicable
reinforcement still needs its own evidence and qualified review. No reviewer identity is
invented; every `reviewed_by` is null.

Five additional technical mappings support three measures: administrator MFA, legacy
authentication and Workspace 2SV support `op.acc.6`; application consent supports `op.acc.4`;
mailbox bypass observation supports `op.exp.8`. Every such measure retains a documentary
control, so passing all automated checks alone leaves all 73 requirements manual.

All six configured check identifiers exist in Prowler 5.49.0's committed inventories.
The sixth, Drive allowlisted-domain sharing, is preparation-only with no normative mapping:
its exact-match criterion can fail when external sharing is completely disabled. Never
weaken a configuration just to make a scanner result pass. The six guide files link both
current vendor documentation and the pinned check implementation reviewed on 2026-11-13.

The MFA/legacy checks reject report-only policies. Stronger authentication methods and
excluded populations still require manual review. Workspace checks have domain-policy and
override limits. Mailbox bypass needs PowerShell, currently excluded by the scanner contract;
its absence must remain unassessed. An enabled consent workflow does not validate existing
application grants. None of these checks demonstrates the full legal measure.

## Release work remaining

1. Qualified review of source text, applicability, every candidate mapping and vendor guidance.
2. System scope, asset/dimension/category decisions and a reviewed declaration of applicability.
3. Review current technical instructions, CCN profiles/guides and applicable audit requirements.
4. Real tenant evidence, complete collection coverage and a documentary review workflow.
5. Production catalog release/version migration and the repository's demand/reuse gates.

No customer configuration, production data, assessment or certification is changed by this pack.

## Group headings

`pack.yaml` `groups_es` copies, in the source's order, the Annex II section headings from the consolidated BOE text
(https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191), read on 2026-11-22: "3. Marco
organizativo [ORG]", "4. Marco operacional [op]", "4.1 Planificación [op.pl]" through
"4.7 Monitorización del sistema [op.mon]", "5. Medidas de protección [mp]", and
"5.1 Protección de las instalaciones e infraestructuras [mp.if]" through
"5.8 Protección de los servicios [mp.s]". Only the heading words are kept; numbering and brackets
are dropped.

## Scope profiles (draft8, issue 227)

- **Guides:** CCN-STIC 890, "Guía de Adecuación al ENS conforme al Perfil de Cumplimiento
  Específico de Requisitos Fundamentales de Seguridad", and CCN-STIC 890C, "Perfil de
  Cumplimiento Específico de Requisitos Fundamentales de Seguridad (Entidades de menor tamaño)",
  both November 2026 editions. Read on 2026-11-23 from the owner's copies (SHA-256 890
  `919c17143bfdfcf884104cd11d12d60a91847d7c7d6cb6883026ba383d81dc42`, 890C
  `1d2ea1ba450dfb6dff747c520efd71cc719d63d7b1e9dd0f059df8863a097f17`). Printed page numbers
  equal the PDF page index in both.
- **What is taken:** for each of the 73 measures, the value of the two columns of 890C section 4
  (pages 8 to 10): "Aplicación IT" and "Aplicación IT/OT/IoT". A category or level is kept as
  the term; "N/A" and "N/A (*)" become `n.a.`. The "Ref" column becomes `criteria`, citing the
  section 5 subsection and its page (5.1 and 5.2 on page 12, 5.3 to 5.8 on 13, 5.9 to 5.11 on
  14, 5.12 and 5.13 on 15). No sentence of either guide is reproduced; titles and summaries are
  Atesta's own wording.
- **Extraction:** text extracted with pypdf 5.4.0 and parsed per table row. The op.acc.6 row
  wraps, and its "5.2" reference was taken by reading the extracted text. The counts match the
  guide's own totals in section 4.1 (page 10): 38 measures apply for IT, 42 for IT/OT/IoT. The
  rendered table was not compared cell by cell: that is part of the owner's review.
- **Not taken:** the reinforcement columns (CAT B/M/A) stay with the BOE selection rules; the
  conditions in section 5 apply only by reference; CCN-STIC 890A (local entities) is not
  imported.
- **Review:** both profiles carry `reviewed_by: null`. They are candidates until the owner signs.

## Scope guide (draft8, issue 225)

- **Guide:** CCN-STIC 803, "ENS. Valoración de los sistemas", June 2025 edition (NIPO
  083-25-216-7). Read on 2026-11-23 from the owner's copy (SHA-256
  `274f34fa4e064978c54a7de28773c854302f32bc53dcbaae75503f3a26c84f56`, 17 pages; printed page
  numbers equal the PDF page index).
- **What is taken:** the valuation order (section 1.2, page 5: information for C, I, T and A,
  then services for D), one question per dimension (sections 3.1 to 3.5, page 9), and notes on
  the common criteria (2.1, page 7), the recovery time objective (2.2.2, page 8), personal data
  (3.6, page 9), the result (4.1, page 12) and documentation (4.5, page 15). Every question and
  note is Atesta's own wording; no sentence and no table (Tables 1 and 2) of the guide is
  reproduced. `category_by_level` follows RD 311/2022 Annex I section 4, which the guide quotes
  on page 4.
- **Review:** `reviewed_by: null`; a candidate until the owner signs.
