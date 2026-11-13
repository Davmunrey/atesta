"""Frozen queue grants, version 1 (ADR-012 amendment 2, scanner-connectors spec).

Never edit after merge. Table grants go through rls_v1.grant(); this module holds only what
rls_v1 cannot express for Procrastinate 3.10.0: USAGE on its sequences, and EXECUTE on its
functions moved from PUBLIC to atesta_app.
"""

TABLES = (
    "procrastinate_jobs",
    "procrastinate_events",
    "procrastinate_periodic_defers",
    "procrastinate_workers",
)

SEQUENCES = (
    "GRANT USAGE ON SEQUENCE procrastinate_jobs_id_seq, procrastinate_events_id_seq,"
    " procrastinate_periodic_defers_id_seq, procrastinate_workers_id_seq TO atesta_app"
)

FUNCTIONS = (
    "DO $$ DECLARE f regprocedure; BEGIN"
    " FOR f IN SELECT p.oid::regprocedure FROM pg_proc p"
    " WHERE p.pronamespace = 'public'::regnamespace AND p.proname LIKE 'procrastinate\\_%'"
    " LOOP"
    " EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);"
    " EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO atesta_app', f);"
    " END LOOP; END $$"
)
