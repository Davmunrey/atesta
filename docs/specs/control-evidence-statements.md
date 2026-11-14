# Spec: declared evidence per common control

- Requirements: FR-07, FR-13, MF-02, NFR-05; ADR-005, ADR-008, ADR-012
- Status: implementation

Members can record a named statement and optional HTTPS document reference against a visible
common control, and read existing collected evidence. Evidence remains shared across all
frameworks mapped to that control. This complements the manual review workflow in #79;
it does not duplicate its review model or scoring, change a decision, or certify compliance.

## Acceptance criteria

1. Statements extend existing evidence with a tenant-bound, append-only table, forced RLS,
   composite foreign key, and a per-organization submission identifier. Existing scan evidence
   remains readable as safe metadata, without storage keys or downloads.
2. Authenticated members can read and submit. Controls must be active and reachable through
   visible framework mappings or preparation metadata. Foreign organizations return the same
   not-found response as missing organizations. Hidden controls cannot receive submissions.
3. Titles (1–200), statements (1–10000) and HTTPS references (at most 2048 characters) are
   trimmed and validated. References cannot include credentials or control characters and are
   never fetched by the server. A reference whose query or fragment carries a signature or token
   parameter (Azure SAS `sig`, S3 `X-Amz-Signature`/`X-Amz-Credential`, GCS `X-Goog-Signature`,
   `token`, `access_token`, `code`, `key` and similar) is refused: statements are append-only, so
   a link that is itself a credential could never be purged (rule 2). Links whose path is the
   capability ("anyone with the link") cannot be told apart and remain a documented limit. Text renders as text. Cookie writes retain same-origin CSRF.
4. Identical retries return the original evidence. Reusing a submission identifier for a
   different payload, author or control returns a conflict, including concurrent requests.
   Evidence, its control association and its audit event commit atomically. Audit metadata
   contains identifiers only, never titles, statements or references.
5. The framework register and preparation guides expose evidence on demand next to each
   control, with paginated history, author/date, an explicit empty state, a working form,
   loading/error/retry/success states and ES/EN copy. Closed disclosures do not fetch evidence.
   Keyboard operation, dark/light themes and 375/768/1280px layouts remain usable.
6. Real PostgreSQL tests cover validation, isolation, idempotency, concurrency, audit privacy,
   append-only permissions and unchanged scores. REA records a clean checkout verification
   and browser checks. The local demo uses synthetic statements only.

## Boundaries and coordination

No binary upload, remote retrieval, document parsing or automatic approval. A recorded
statement is declared evidence, not a verified document. #79 owns manual review and rescoring;
this increment displays no invented linkage between its decisions and these statements.
Pinning a decision to selected evidence and invalidating it on new evidence remain explicit
follow-up work. #80 owns hardening and #81 owns scan endpoints.

The abandoned local review prototype is archived outside the repository. Migration 0013
follows #79's 0012; dependent PRs target that branch until it is ready to merge. Apply the
schema only to disposable tests and the synthetic local demo, never production databases.
