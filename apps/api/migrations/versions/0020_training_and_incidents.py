"""Training acknowledgements and incidents (recorded-routines spec, part B).

Tenant tables with the standard RLS policy. training_campaigns also has the named read policy
training_token_read (ADR-012 amendment 4), and is updated once, to close it. The others are
append-only.

Revision ID: 0020
Revises: 0019
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

APPEND_ONLY = ("training_acknowledgements", "incidents", "incident_updates")
LINK_POLICY = (
    "CREATE POLICY training_token_read ON training_campaigns FOR SELECT"
    " USING (token_sha256 = app_setting_text('app.training_token_sha256'))"
)

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("aware_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("significant", sa.Boolean(), nullable=False),
        sa.Column("personal_data", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 200", name=op.f("ck_incidents_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_incidents_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_incidents_organization_id_id")),
    )
    op.create_index(
        op.f("ix_incidents_organization_id"), "incidents", ["organization_id"], unique=False
    )
    op.create_table(
        "training_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("material_url", sa.Text(), nullable=False),
        sa.Column("closes_on", sa.Date(), nullable=False),
        sa.Column("token_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "left(material_url, 8) = 'https://' AND length(material_url) <= 2000",
            name=op.f("ck_training_campaigns_material_https"),
        ),
        sa.CheckConstraint(
            "token_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_training_campaigns_token_format")
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL) = (closed_by IS NULL)",
            name=op.f("ck_training_campaigns_closed_together"),
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 200",
            name=op.f("ck_training_campaigns_title_length"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_training_campaigns_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_campaigns")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_training_campaigns_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_training_campaigns_organization_id"),
        "training_campaigns",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_training_campaigns_token_sha256"),
        "training_campaigns",
        ["token_sha256"],
        unique=False,
    )
    op.create_table(
        "incident_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("clock_ref", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(kind = 'clock') = (clock_ref IS NOT NULL)",
            name=op.f("ck_incident_updates_clock_ref_for_clocks"),
        ),
        sa.CheckConstraint(
            "kind IN ('note', 'clock', 'closed')", name=op.f("ck_incident_updates_kind")
        ),
        sa.CheckConstraint("length(note) <= 2000", name=op.f("ck_incident_updates_note_length")),
        sa.ForeignKeyConstraint(
            ["organization_id", "incident_id"],
            ["incidents.organization_id", "incidents.id"],
            name=op.f("fk_incident_updates_organization_id_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_incident_updates_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_updates")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_incident_updates_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_incident_updates_organization_id"),
        "incident_updates",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_incident_updates_clock",
        "incident_updates",
        ["organization_id", "incident_id", "clock_ref"],
        unique=True,
        postgresql_where=sa.text("clock_ref IS NOT NULL"),
    )
    op.create_index(
        "uq_incident_updates_closed",
        "incident_updates",
        ["organization_id", "incident_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'closed'"),
    )
    op.create_table(
        "training_acknowledgements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(full_name)) BETWEEN 1 AND 200",
            name=op.f("ck_training_acknowledgements_name_length"),
        ),
        sa.CheckConstraint(
            "length(email) BETWEEN 3 AND 320",
            name=op.f("ck_training_acknowledgements_email_length"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "campaign_id"],
            ["training_campaigns.organization_id", "training_campaigns.id"],
            name=op.f(
                "fk_training_acknowledgements_organization_id_campaign_id_training_campaigns"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_training_acknowledgements_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_acknowledgements")),
        sa.UniqueConstraint(
            "organization_id",
            "campaign_id",
            "email",
            name=op.f("uq_training_acknowledgements_organization_id_campaign_id_email"),
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_training_acknowledgements_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_training_acknowledgements_organization_id"),
        "training_acknowledgements",
        ["organization_id"],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("training_campaigns"):
        op.execute(statement)
    op.execute(LINK_POLICY)
    op.execute(rls_v1.grant("training_campaigns", "SELECT", "INSERT", "UPDATE"))  # closing only
    for table in APPEND_ONLY:
        for statement in rls_v1.tenant_rls(table):
            op.execute(statement)
        op.execute(rls_v1.grant(table, "SELECT", "INSERT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
