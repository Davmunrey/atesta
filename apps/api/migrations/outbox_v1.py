"""Frozen outbox grants, version 1 (ADR-012 amendment 12, operator-portal spec, #474).

Never edit after merge. The worker, as atesta_app, reads the service notice outbox and marks a
row sent; it changes no other column. rls_v1.grant() emits table-level grants only, so the
column-level UPDATE lives here, as operator_v1 holds atesta_app's column grant on organizations.
The operator role's insert comes from operator_v1.grant().
"""

APP_GRANTS = (
    "GRANT SELECT ON service_notices TO atesta_app",
    "GRANT UPDATE (sent_at) ON service_notices TO atesta_app",
)
