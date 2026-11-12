# Control catalog

Atesta's core IP, framework-agnostic (ADR-011): common controls, framework packs, and the
many-to-many mappings between them. Versioned with the code; every catalog release re-indexes the
RAG corpus (ADR-010).

## Layout

```text
catalog/
  controls/                 Common Atesta controls, one YAML per control
  frameworks/<pack>/
    pack.yaml               Framework metadata and version
    requirements.yaml       Requirements copied from the official text
    mappings.yaml           Requirement -> control mappings
```

Pack order: ENS (wedge) -> NIS2 -> ISO 27001 -> RGPD art. 32 -> DORA -> SOC 2 and others on demand.

## Rules

- Requirement ids, titles and levels are copied from official sources and verified by a qualified
  reviewer before release. Never written from memory.
- Every mapping records `source` and `reviewed_by` (MF-06).
- Every `prowler_checks` id must exist in the pinned Prowler version (CI validation, Phase 2).
- `manual: true` controls are organizational: evidence comes from documents, not scans.
- A new pack ships only with 3+ customers/deals asking and >= 60% mapping to existing controls.
