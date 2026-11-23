# Spec: claims honesty

Issue: #130. Status: built (2026-11-23: both test-plan items pass).

## Problem

Atesta prepares evidence for audits; it does not certify, and its checks cover a small part of
each framework (for ENS, partial automated evidence for 3 of the 73 Annex II measures). Copy that
says a customer "cumple" or "complies" tells a public-sector supplier something Atesta cannot
know, and is a misleading claim (Ley 3/1991, art. 5).

## Vocabulary

| Thing | ES | EN | Never |
| --- | --- | --- | --- |
| Automated check or requirement state from recorded results | Superado / No superado | Passed / Not passed | Cumple, No cumple, Meets, Compliant |
| Human manual review decision | Implantado / No implantado (RD 311/2022 Annex III) | Implemented / Not implemented | Cumple, Conforme, Certificado |
| The score | Porcentaje de requisitos superados en las comprobaciones registradas; no es una evaluación de conformidad | Share of requirements passed in the recorded checks; not a conformity assessment | Nivel de cumplimiento, compliance score |
| What Atesta is | Preparación de auditorías | Audit readiness | Certificación, cumplimiento garantizado |

## Forbidden patterns

Checked by `apps/api/tests/test_claims.py` in every message value of
`apps/web/messages/es.json` and `en.json`, and in `README.md` and `PRODUCT.md`:

- ES: the verb forms `cumple`, `cumplen`, `cumplís`, `cumplimos`; `cumplimiento garantizado`;
  `garantiza`/`garantizamos` followed by `cumplimiento` or `certificación`; `certificado por Atesta`.
- EN: `complies`, `comply`, `compliant`, `meets`, `guarantee`, `certified by Atesta`.

The noun `cumplimiento` and negations such as "No certifica cumplimiento" are allowed: they
describe the domain, not a result.

## Out of scope

Official framework texts in `catalog/frameworks/*/requirements.yaml` (they are the law's own
words), sales material outside the repository (reviewed by the lawyer), and the device agent.

## Test plan

- [ ] `test_claims.py` passes on the repository and fails on planted text for each pattern.
- [ ] Web unit and e2e tests use the new labels.
