# apps/operator

The operator API (ADR-017, `docs/specs/operator-portal.md`): the service the Atesta team uses to
manage customer organizations from their metadata only. It is a third entrypoint of the same
codebase, next to the API and the worker, with its own database role (`atesta_operator`), its own
staff Cognito pool and, from build step 6, its own image.

- It calls modules only through their `api.py` and never sets a tenant context (import-linter).
- `atesta_operator.policy.POLICY` is the permissions matrix; every route is in it.
- Startup refuses any database role but `atesta_operator`, and a staff pool without required MFA.

Run locally against the migrated database, with the fake staff pool:

```bash
uv run python apps/api/devtools/fake_cognito.py --staff   # http://localhost:9001
ATESTA_ENV=local ATESTA_DB_SSLMODE=disable \
ATESTA_OPERATOR_DATABASE_URL=postgresql+psycopg://atesta_operator:...@localhost:5432/atesta \
ATESTA_STAFF_COGNITO_REGION=eu-south-2 ATESTA_STAFF_COGNITO_USER_POOL_ID=local-staff \
ATESTA_STAFF_COGNITO_APP_CLIENT_ID=local-operator ATESTA_STAFF_COGNITO_DOMAIN=localhost:9001 \
ATESTA_STAFF_COGNITO_ISSUER=http://localhost:9001 ATESTA_STAFF_COGNITO_BASE_URL=http://localhost:9001 \
uv run uvicorn atesta_operator.main:app --port 8001
```

A staff member needs a row in `operator_staff` with the `sub` of their staff-pool account (the
fake derives it from the email); creating it is a runbook step (build step 7).

Regenerate the portal's contract with
`ATESTA_UPDATE_API_CONTRACT=1 uv run pytest apps/operator/tests/test_contract.py`.
