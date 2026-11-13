# apps/worker

Background jobs on Procrastinate 3.10.0 (Postgres-backed queue, ADR-003): scan scheduling, OCSF
ingest, score snapshots, regression alerts, report builds.

- Jobs call module `api.py` functions only (import-linter contract, rule 8).
- Job arguments are ids only (`<name>_id: str`); the worker refuses to start otherwise, because
  the queue tables carry no RLS (ADR-012 amendment 2).
- A job that touches tenant data opens `context.org_session(organization_id)`: one transaction,
  org context entered with reason `job`.

Run locally against the migrated database, as `atesta_app`:

```bash
ATESTA_DATABASE_URL=postgresql+psycopg://atesta_app:...@localhost:5432/atesta \
ATESTA_DB_SSLMODE=disable uv run atesta-worker
```
