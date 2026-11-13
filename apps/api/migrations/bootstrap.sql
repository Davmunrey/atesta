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
END
$$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO atesta_owner;
GRANT USAGE ON SCHEMA public TO atesta_app;
