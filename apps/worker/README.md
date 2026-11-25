# apps/worker

Background jobs on Procrastinate 3.11.0 (Postgres-backed queue, ADR-003): scan scheduling, OCSF
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

## Jobs

| Job | Queue | Retry | Effect |
|---|---|---|---|
| `retry_stalled_jobs` | maintenance | n/a (every 5 min) | Retries jobs whose worker stopped sending heartbeats |
| `snapshot_scores` | scans | 3, transient database errors only | One score snapshot per scoreable framework, at REPEATABLE READ; deferred by ingest in its own transaction |
| `poll_file_scans` | files | n/a (every minute) | Drains GuardDuty's malware scan results from `ATESTA_FILE_SCAN_QUEUE_URL` and records each in its organization's context; on malware, queues `notify_event` for owners and admins. Unset: does nothing (evidence-malware-scanning spec) |
| `send_service_notices` | notifications | n/a (every minute) | Sends the service notice outbox (ADR-012 amendment 12): each pending notice in its organization's context, once per person, then marks it sent. An unsent notice stays for the next run |

## One synthetic scan, end to end (dev only)

`atesta-dev-scan` loads the synthetic catalog (`apps/api/tests/fixtures/catalog/`) as
`atesta_owner`, replays the synthetic M365 OCSF fixture in a fixed dev org, ingests it against
`scanner/expected/` and scores it with drafts included. No Docker, network or credentials. It
fails unless every synthetic framework gets a snapshot; a rerun changes nothing.

```bash
ATESTA_ENV=dev ATESTA_DB_SSLMODE=disable \
ATESTA_MIGRATION_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres \
ATESTA_DATABASE_URL=postgresql+psycopg://atesta_app:local-only@localhost:5432/postgres \
uv run atesta-dev-scan
```

Outputs go to `.atesta-dev/scans/` (git-ignored) unless `ATESTA_DEV_SCAN_DIR` is set.
