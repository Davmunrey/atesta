# Local sign-in without AWS

Developer machines only (docs/specs/local-dev-auth.md). The fake mimics Cognito managed login;
the API runs the real token and BFF code against it.

```bash
docker compose up -d postgres
psql postgresql://postgres@localhost:5432/postgres -f apps/api/migrations/bootstrap.sql
ATESTA_MIGRATION_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres \
  ATESTA_MIGRATION_ROLE=atesta_owner ATESTA_DB_SSLMODE=disable \
  uv run alembic -c apps/api/alembic.ini upgrade head
psql postgresql://postgres@localhost:5432/postgres -c "ALTER ROLE atesta_app LOGIN PASSWORD 'local-only'"
uv run python apps/api/devtools/fake_cognito.py   # http://localhost:9000
set -a; . apps/api/.env.example; set +a
export ATESTA_SESSION_KEY="$(python3 -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')"
uv run uvicorn atesta_api.main:app --port 8000
```

Sign in at http://localhost:3000/auth/login once the web shell runs (its dev server rewrites
`/api` and `/auth` to port 8000). Any email and any 6 digits are accepted.
