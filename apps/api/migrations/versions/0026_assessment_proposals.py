"""Self-assessment proposals from API keys (mcp-server spec, #339; ADR-005, ADR-016).

A key with assessment:propose stores a pending proposal; a person confirms or rejects it. Only a
confirmation writes requirement_assessments, as that person's. A tenant table with the standard
policy (ADR-012 amendment 6): SELECT, INSERT, and UPDATE only to record the decision. At most one
pending proposal per measure. Free text is customer content (rule 2).

Revision ID: 0026
Revises: 0025
"""

import rls_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("requirement_code", sa.Text(), nullable=False),
        sa.Column("applicability", sa.Text(), nullable=False),
        sa.Column("implementation", sa.Text(), nullable=False),
        sa.Column("regularly_reviewed", sa.Boolean(), nullable=False),
        sa.Column("justification", sa.Text(), server_default="", nullable=False),
        sa.Column("performed_by", sa.Text(), server_default="", nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=True),
        sa.Column(
            "evidence_statement_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "applicability IN ('applies', 'not_applicable')",
            name=op.f("ck_assessment_proposals_applicability"),
        ),
        sa.CheckConstraint(
            "implementation IN ('not_implemented', 'partially_implemented', 'implemented')",
            name=op.f("ck_assessment_proposals_implementation"),
        ),
        sa.CheckConstraint(
            "char_length(justification) <= 2000",
            name=op.f("ck_assessment_proposals_justification_length"),
        ),
        sa.CheckConstraint(
            "char_length(performed_by) <= 200",
            name=op.f("ck_assessment_proposals_performed_by_length"),
        ),
        sa.CheckConstraint(
            "char_length(notes) <= 2000", name=op.f("ck_assessment_proposals_notes_length")
        ),
        sa.CheckConstraint(
            "char_length(btrim(rationale)) BETWEEN 1 AND 2000",
            name=op.f("ck_assessment_proposals_rationale_length"),
        ),
        sa.CheckConstraint(
            "cardinality(evidence_statement_ids) <= 50",
            name=op.f("ck_assessment_proposals_evidence_count"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name=op.f("ck_assessment_proposals_status"),
        ),
        sa.CheckConstraint(
            "(status = 'pending') = (decided_by IS NULL)"
            " AND (status = 'pending') = (decided_at IS NULL)",
            name=op.f("ck_assessment_proposals_decided_together"),
        ),
        sa.CheckConstraint(
            "(status = 'confirmed') = (assessment_id IS NOT NULL)",
            name=op.f("ck_assessment_proposals_confirmed_names_assessment"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["requirement_assessments.organization_id", "requirement_assessments.id"],
            name=op.f(
                "fk_assessment_proposals_organization_id_assessment_id_requirement_assessments"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_assessment_proposals_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_proposals")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_assessment_proposals_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_assessment_proposals_organization_id"),
        "assessment_proposals",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_assessment_proposals_one_pending",
        "assessment_proposals",
        ["organization_id", "framework_key", "requirement_code"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    for statement in rls_v1.tenant_rls("assessment_proposals"):
        op.execute(statement)
    op.execute(rls_v1.grant("assessment_proposals", "SELECT", "INSERT", "UPDATE"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
