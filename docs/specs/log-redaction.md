# Spec: log redaction (rule 2)

- Issue: #269. Builds on rule 2, `hosted-environment.md` (`ecs`: logs carry no secrets or
  customer content) and `scanner-connectors.md` (Logs and personal data).
- Status: built (tests listed under Test plan)

## Problem

Rule 2 keeps secrets and customer content out of every log. Three paths broke it (#269, all
reproduced on 2026-11-23 with PostgreSQL 16.16, uvicorn 0.54 and Procrastinate 3.11):

- **Exception text.** uvicorn logs an unhandled API error with `exc_info`, and Procrastinate
  does the same for a failed job. A PostgreSQL error's text carries its `DETAIL` line: the
  duplicate key's value, or, for a check or not-null violation, the whole failing row.
  `hide_parameters=True` hides bound parameters in SQLAlchemy's message, but not in `DETAIL`.
- **Access-log query strings.** uvicorn's access log writes the path with its query string,
  so `/auth/callback?code=...` logs an OAuth authorization code and `search?q=...` logs what a
  person typed.
- **Scanner events.** The local runner forwarded every key of any `scan.*` JSON line from the
  container's stdout.

## Acceptance criteria

- [x] A log record that carries an exception keeps the traceback frames (file, line, function,
  source line) and, for each exception in the chain, its qualified type name, its SQLSTATE and
  its constraint, table and column names. It never keeps the exception's message.
- [x] An exception passed as a log argument (`log.error("failed: %s", exc)`) is logged as its
  qualified type name.
- [x] `uvicorn.access` records keep the path and replace the whole query string:
  `/auth/callback?[query omitted]`. Parameter names are dropped too, because a bare name can be
  a token (`/x?tok_live_...`).
- [x] The local runner forwards only `event` (`scan.` and lower-case letters or `_`),
  `scan_id` and `organization_id` (UUIDs), `attempt` and `exit_code` (integers). Any other key,
  and any value of the wrong shape, is dropped.
- [x] `create_app()` and the worker's `build_app()` install the redaction. Installing it twice
  wraps the record factory once.

## Out of scope

- Load balancer and CloudFront access logs, which also record query strings (infra lane,
  candidate).
- The Prowler log file, which the wrapper scrubs before it is stored (scanner-connectors spec).
- Client IP addresses in the access log.

## Design notes

- `atesta_api.platform.logs` wraps the process-wide log record factory
  (`logging.setLogRecordFactory`). Every record from every logger and handler passes through
  it, whatever the logging configuration: uvicorn configures its loggers before it imports the
  app, and Procrastinate logs through its own loggers.
- The record's `exc_info` is replaced with `exc_text`, the safe rendering, so no formatter or
  handler can render the message again.
- Database errors are described by psycopg's `sqlstate` and `diag` fields. Constraint, table
  and column names are schema identifiers, not data.
- A redacted traceback is harder to debug. The SQLSTATE and constraint name identify every
  integrity error, and the request or job id finds the row.

## Test plan

- `apps/api/tests/db/test_log_redaction.py`: real PostgreSQL unique, check and not-null
  violations are logged through the `uvicorn.error` and `procrastinate.worker` loggers. The output holds the SQLSTATE and
  constraint, and none of the values.
- `apps/api/tests/test_log_redaction.py`: exception chains and arguments, access-log query
  strings, idempotent installation, and installation by `create_app()`.
- `apps/worker/tests/test_app.py::test_build_app_installs_log_redaction`: the worker's app
  installs it, and a Procrastinate job-failure record loses its message.
- `apps/api/tests/test_local_docker_runner.py`: a forged event with extra keys and badly
  shaped values is forwarded with the allowed keys only.
