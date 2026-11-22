"""Requirement register: scopes, self-assessments and their review (requirement-register spec).

Revision ID: 0014
Revises: 0013
"""

from typing import Any

import rls_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _tenant(table: str) -> list[Any]:
    return [
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f(f"fk_{table}_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    ]


def _recorded(column: str) -> "sa.Column[Any]":
    return sa.Column(
        column, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _finish(table: str, latest: list[str]) -> None:
    op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
    op.create_index(f"ix_{table}_latest", table, ["organization_id", *latest])
    for statement in rls_v1.tenant_rls(table):
        op.execute(statement)
    op.execute(rls_v1.grant(table, "SELECT", "INSERT"))  # append-only


def upgrade() -> None:
    op.create_table(
        "framework_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("axis_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        _recorded("decided_at"),
        *_tenant("framework_scopes"),
    )
    _finish("framework_scopes", ["framework_key", "decided_at"])

    op.create_table(
        "requirement_assessments",
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
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        _recorded("recorded_at"),
        sa.CheckConstraint(
            "applicability IN ('applies', 'not_applicable')",
            name=op.f("ck_requirement_assessments_applicability"),
        ),
        sa.CheckConstraint(
            "implementation IN ('not_implemented', 'partially_implemented', 'implemented')",
            name=op.f("ck_requirement_assessments_implementation"),
        ),
        sa.CheckConstraint(
            "char_length(justification) <= 2000",
            name=op.f("ck_requirement_assessments_justification_length"),
        ),
        sa.CheckConstraint(
            "char_length(performed_by) <= 200",
            name=op.f("ck_requirement_assessments_performed_by_length"),
        ),
        sa.CheckConstraint(
            "char_length(notes) <= 2000", name=op.f("ck_requirement_assessments_notes_length")
        ),
        sa.CheckConstraint(
            "cardinality(evidence_statement_ids) <= 50",
            name=op.f("ck_requirement_assessments_evidence_count"),
        ),
        *_tenant("requirement_assessments"),
    )
    _finish("requirement_assessments", ["framework_key", "requirement_code", "recorded_at"])

    op.create_table(
        "assessment_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("reviewer_name", sa.Text(), nullable=False),
        sa.Column("reviewer_role", sa.Text(), nullable=False),
        sa.Column("reviewed_on", sa.Date(), nullable=False),
        sa.Column("conclusions", sa.Text(), nullable=False),
        sa.Column("corrective_actions", sa.Text(), server_default="", nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        _recorded("recorded_at"),
        sa.CheckConstraint(
            "char_length(reviewer_name) BETWEEN 1 AND 200",
            name=op.f("ck_assessment_reviews_reviewer_name"),
        ),
        sa.CheckConstraint(
            "char_length(reviewer_role) BETWEEN 1 AND 200",
            name=op.f("ck_assessment_reviews_reviewer_role"),
        ),
        sa.CheckConstraint(
            "char_length(conclusions) BETWEEN 1 AND 4000",
            name=op.f("ck_assessment_reviews_conclusions"),
        ),
        sa.CheckConstraint(
            "char_length(corrective_actions) <= 4000",
            name=op.f("ck_assessment_reviews_corrective_actions"),
        ),
        *_tenant("assessment_reviews"),
    )
    _finish("assessment_reviews", ["framework_key", "recorded_at"])


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
