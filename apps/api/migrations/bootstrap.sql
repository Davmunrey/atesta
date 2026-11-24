-- Roles and schema grants (tenant-data-layer spec). Idempotent; no passwords.
-- Run as superuser (tests) or as the RDS master user (infra). LOGIN is set by the caller.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atesta_owner') THEN
    CREATE ROLE atesta_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atesta_app') THEN
    CREATE ROLE atesta_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
  -- Operator portal (ADR-017, ADR-012 amendment 8): reads metadata columns only, never content.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atesta_operator') THEN
    CREATE ROLE atesta_operator NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO atesta_owner;
GRANT USAGE ON SCHEMA public TO atesta_app;
GRANT USAGE ON SCHEMA public TO atesta_operator;
