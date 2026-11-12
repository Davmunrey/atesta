# ADR-010: RAG with citations and guardrails; no fine-tuning

- Status: accepted (2026-11-12)

## Decision
AI answers only from retrieved passages: base corpus (RD 311/2022 Annex II, CCN-STIC guides
subject to reuse terms, Atesta catalog) and, from v2, tenant documents filtered by
organization_id. pgvector in the main Postgres, hybrid search (full-text + vectors) with
reranking. Claude generates structured JSON validated with Pydantic.

## Guardrails
- Every claim cites a retrieved chunk id; invalid citations reject the response.
- Below the relevance threshold: "insufficient basis", never a guess.
- Customer documents are untrusted data; injection filtered; personal data redacted before
  embedding.
- Outputs are drafts until approved; prompt version, model and chunks logged per response.

## Evaluation
Golden set of 100 auditor-validated questions in CI: citation validity 100%, faithfulness >= 90%.

## Consequences
Auditable, citable AI. More engineering than a plain LLM call; corpus must be reindexed on each
catalog release.
