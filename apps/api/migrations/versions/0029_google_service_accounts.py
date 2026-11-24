"""Google service account ids and the verification start (scanner-connectors spec, issue 398).

`google_unique_id` and `google_verifier_unique_id` are the org's two service accounts' IAM
`uniqueId`s: the verifier matches admin role assignments against them, since IAM documents them
apart from the OAuth client ids. `verifying_since` bounds Google's 24 h propagation retry. Ids
are numeric and belong to Google rows only; an active Google connection has all four ids.

Revision ID: 0029
Revises: 0028
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_IDS = (
    "google_client_id",
    "google_verifier_client_id",
    "google_unique_id",
    "google_verifier_unique_id",
)


def upgrade() -> None:
    op.add_column("connections", sa.Column("google_unique_id", sa.Text(), nullable=True))
    op.add_column("connections", sa.Column("google_verifier_unique_id", sa.Text(), nullable=True))
    op.add_column(
        "connections", sa.Column("verifying_since", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_connections_google_ids_numeric"),
        "connections",
        " AND ".join(f"({c} IS NULL OR {c} ~ '^[0-9]{{6,30}}$')" for c in _IDS),
    )
    op.create_check_constraint(
        op.f("ck_connections_m365_no_google"),
        "connections",
        "provider <> 'm365' OR num_nonnulls(" + ", ".join(_IDS) + ", google_subject_email) = 0",
    )
    op.drop_constraint(op.f("ck_connections_active_google_complete"), "connections", type_="check")
    op.create_check_constraint(
        op.f("ck_connections_active_google_complete"),
        "connections",
        "provider <> 'google_workspace' OR status <> 'active' OR num_nulls(credential_ref,"
        " verifier_credential_ref, " + ", ".join(_IDS) + ", google_subject_email) = 0",
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
