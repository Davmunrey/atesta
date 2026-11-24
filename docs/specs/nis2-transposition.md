# Spec: national transposition record for an EU directive pack (NIS2 first)

- Issue: #437. Builds on `content-model-v2.md` and `framework-catalog-preview.md` (ADR-011, rules 9 and 10).
- Status: draft

## Problem

A directive binds Member States, not companies. A company learns its duties from the national
law that transposes it. The NIS2 pack imports the Directive's own text (Articles 20, 21(1)-(4)
and 23(1)-(4)). It says nothing about national law beyond "the Spanish transposing law is
missing; confirm it with your reviewer".

A Spanish SME, its consultant and the assistant all ask the same first question: "what has my
country passed?". Today they answer it from news, which is often wrong or out of date. Atesta
must answer from the official record, with its date, and say nothing it cannot source.

## What the layer is

- **One record per directive pack:** `catalog/frameworks/<pack>/transposition.yaml`, optional,
  read and validated by the catalog loader like `coverage.yaml`. Catalog content only: no table,
  no code path for any framework (rule 9).
- **Exactly the 27 Member States.** For each one, the national measures it has notified to the
  Commission for the directive, as the EU Publications Office lists them, or none.
- **Per measure:**
  - its CELEX number;
  - its official title, in the national language as published;
  - its type and national reference when published;
  - its date;
  - its notification date;
  - an HTTPS link: the national website the Member State gave, or the measure's Publications
    Office record;
  - the notification's declaration code when one is published, kept as the code. Atesta does
    not interpret it.
- **National context, optional, per country:** what an official national source says, checked
  on a stated date:
  - the sources searched;
  - an authored summary in Spanish and English;
  - the national texts that cite the directive, each with an official quote;
  - competent authorities and CSIRTs, only when an official national or EU source names them.
    Otherwise the list is empty and the summary says so.
- **Where it shows:** as context in the framework view and to the assistant (follow-up issue),
  next to the EU pack. Never as requirements, never in a score.

## What it is not

- **Not national requirement text.** No national article becomes a requirement until a national
  law exists, is captured from its official publication and is reviewed (rule 10).
- **Not "transposed".** A notified measure means a Member State told the Commission that the
  measure implements the directive. It does not mean transposition is complete or correct. The
  record says "notified", never "transposed".
- **Not legal advice,** and not a decision that an entity is essential or important (ADR-005).
- **Not from news or memory.** "No measure notified as of <date>" is a valid, sourced value.
  "Partial" appears only where the source says so; the Publications Office data has no such flag.

## Data model (catalog content)

```yaml
act: 32022L2555                     # CELEX of the directive; the pack's source names it
source: https://publications.europa.eu/webapi/rdf/sparql
listing: https://eur-lex.europa.eu/legal-content/EN/NIM/?uri=CELEX:32022L2555
relation: http://publications.europa.eu/ontology/cdm#measure_national_implementing_implements_resource_legal
pulled_on: 2026-11-24
reviewed_by: null                   # the owner's signature: both or neither
reviewed_on: null
member_states:
- country: AUT                      # ISO 3166-1 alpha-3, as the Publications Office uses
  status: notified                  # notified | none_notified
  measures:
  - celex: 72022L2555AUT_202500243
    title: Bundesgesetz zur Gewährleistung eines hohen Sicherheitsniveaus von Netz- und
      Informationssystemen (Netz- und Informationssystemsicherheitsgesetz – NISG)
    date: 2018-12-28                # the measure's own date, as published
    notified_on: 2025-01-13
    url: https://publications.europa.eu/resource/celex/72022L2555AUT_202500243
    act_type: Bundesgesetz          # optional
    reference: null                 # optional
    declaration: null               # the published code, verbatim, when there is one
- country: ESP
  status: none_notified
  measures: []
national_context:
- country: ESP
  checked_on: 2026-11-24
  sources: [<the BOE open data search URL>]
  summary_es: ...
  summary_en: ...
  references:
  - id: BOE-A-2024-8715
    title: <official title, from the BOE>
    url: https://www.boe.es/buscar/act.php?id=BOE-A-2024-8715
    section: <the block heading, from the BOE>
    quote_es: <one paragraph, verbatim from the BOE>
  authorities: []
```

## Acceptance criteria

**Schema (generic, `catalog_schema.py`)**
- [ ] A pack may carry `transposition.yaml`; the loader validates it and the preview import
  stores it with the framework attributes, like the coverage ledger.
- [ ] **The catalog refuses:**
  - a record without exactly the 27 Member States, or with a country twice;
  - `notified` without measures, or `none_notified` with measures;
  - a measure without an HTTPS link, a date or a notification date;
  - a measure notified after the pull date;
  - national context for a country outside the list, twice for one country, or without a
    source;
  - an authority without its official source;
  - a reviewer without a review date, or a date without a reviewer;
  - a record whose act is not the CELEX in the pack's source link.
- [ ] No code names a framework (the rule 9 guard stays green).

**Content (`catalog/frameworks/nis2/transposition.yaml`)**
- [ ] Generated by `apps/api/devtools/eu_nim.py` from one SPARQL pull, with the pull date and
  the response hash in the pack's SOURCES.md.
- [ ] Spain's national context is checked on the BOE consolidated legislation open data API.
  It quotes every consolidated text that cites the Directive, verbatim.
- [ ] Unsigned: `reviewed_by` and `reviewed_on` are null. Only the owner signs, in session.
  An agent never sets `reviewed_by`.

**Display strings (for the follow-up UI; ES first)**

| Key | ES | EN |
| --- | --- | --- |
| heading | Transposición nacional | National transposition |
| notified | {count, plural, one {# medida nacional notificada} other {# medidas nacionales notificadas}} a la Comisión | {count, plural, one {# national measure} other {# national measures}} notified to the Commission |
| none_notified | Ninguna medida nacional notificada en EUR-Lex a {date} | No national measure notified in EUR-Lex as of {date} |
| caveat | Una medida notificada no indica que la transposición esté completa. No es asesoramiento jurídico ni decide si tu entidad es esencial o importante. | A notified measure does not mean transposition is complete. This is not legal advice and does not decide whether your entity is essential or important. |
| unreviewed | Pendiente de revisión | Awaiting review |
| source | Fuente: Oficina de Publicaciones de la UE, consultada el {date} | Source: EU Publications Office, checked on {date} |

Measure titles are official texts in the national language and are shown as published, with
their `lang` attribute; they are never translated.

## Refresh procedure

1. `uv run python -m apps.api.devtools.eu_nim 32022L2555 > /tmp/members.yaml` (outside CI;
   it queries the Publications Office). It prints `member_states` for all 27 and, on stderr,
   the SHA-256 of the SPARQL response.
2. Replace `member_states` and `pulled_on` in `transposition.yaml`; keep `national_context`.
3. Re-check each national context on its official source and update `checked_on`. A new
   national law is captured as its own pack or pack revision, with its own SOURCES.md, before
   any of its text appears in Atesta.
4. Record the pull date and hash in SOURCES.md; clear `reviewed_by` and `reviewed_on`, because
   the content changed.
5. Run the gates and the catalog preview import.

Refresh at least monthly while Member States are still notifying, and before any release that
shows the record.

## Out of scope

- The console view and the assistant's use of the record (#438).
- National requirement texts, mappings and scoring.
- Infringement procedures and Commission assessments of conformity.

## Test plan

- **Unit, schema:** each refusal above, on a synthetic record.
- **Unit, devtool:** bindings from a synthetic SPARQL response become sorted measures, with the
  national link preferred and countries without measures as `none_notified`.
- **Catalog:** the NIS2 record lists exactly the 27, every measure has a link and both dates,
  the pull date is set, the record is unsigned, and Spain's context quotes the BOE verbatim.
