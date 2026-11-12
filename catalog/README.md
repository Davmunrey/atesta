# Control catalog

Atesta's core IP: ENS (RD 311/2022) Annex II measures, levels per category, and mappings to
Prowler check ids and Atesta custom checks. Versioned with the code; every catalog release
re-indexes the RAG corpus (ADR-010).

## Layout

```text
catalog/
  ens/        One YAML file per ENS measure
  nis2/       Art. 21 measures, mapped to ENS controls (v2)
  iso27001/   Annex A cross-mapping (v3)
```

## Rules

- Measure codes, titles and levels are copied from the official RD 311/2022 text and verified by
  an ENS auditor before release. Never written from memory.
- Every `prowler_checks` id must exist in the pinned Prowler version (CI validation, Phase 2).
- `manual: true` measures are organizational: evidence comes from documents, not scans.
