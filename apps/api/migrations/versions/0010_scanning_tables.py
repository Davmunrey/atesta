"""Scanning tables: scans, scan_check_results, findings (scanner-connectors spec, PR 2).

Scans change status but are never deleted; check results and findings are append-only.
One queued or running scan per connection (partial unique index).

Revision ID: 0010
Revises: 0009
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("image_digest", sa.Text(), nullable=True),
        sa.Column("output_prefix", sa.Text(), nullable=True),
        sa.Column("manifest_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("expected_checks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evaluated_checks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("engine = 'prowler'", name=op.f("ck_scans_engine")),
        sa.CheckConstraint(
            "manifest_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_scans_manifest_sha256_format")
        ),
        sa.CheckConstraint(
            "output_prefix IS NULL OR output_prefix ~ ('^' || organization_id::text || '/scans/'"
            " || id::text || '/attempt-[1-9][0-9]*/out/$')",
            name=op.f("ck_scans_output_prefix_in_tenant"),
        ),
        sa.CheckConstraint(
            "provider IN ('m365', 'google_workspace')", name=op.f("ck_scans_provider")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'collected', 'succeeded', 'partial', 'failed',"
            " 'blocked')",
            name=op.f("ck_scans_status"),
        ),
        sa.CheckConstraint(
            "trigger IN ('schedule', 'user', 'activation')", name=op.f("ck_scans_trigger")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_scans_attempts_non_negative")),
        sa.CheckConstraint(
            "evaluated_checks BETWEEN 0 AND expected_checks", name=op.f("ck_scans_coverage_bounded")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_scans_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scans")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_scans_organization_id_id")),
    )
    op.create_index(op.f("ix_scans_organization_id"), "scans", ["organization_id"], unique=False)
    op.create_index(
        "uq_scans_one_active_per_connection",
        "scans",
        ["organization_id", "connection_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("muted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_uid", sa.Text(), nullable=False),
        sa.Column("resource_name", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("engine = 'prowler'", name=op.f("ck_findings_engine")),
        sa.CheckConstraint("status IN ('pass', 'fail', 'manual')", name=op.f("ck_findings_status")),
        sa.ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["scans.organization_id", "scans.id"],
            name=op.f("fk_findings_organization_id_scan_id_scans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_findings_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_findings_organization_id_id")),
    )
    op.create_index(
        op.f("ix_findings_organization_id"), "findings", ["organization_id"], unique=False
    )
    op.create_index(
        op.f("ix_findings_organization_id_scan_id_check_id"),
        "findings",
        ["organization_id", "scan_id", "check_id"],
        unique=False,
    )
    op.create_table(
        "scan_check_results",
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("pass_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fail_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("manual_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(status = 'not_evaluated') = (reason IS NOT NULL)",
            name=op.f("ck_scan_check_results_reason_iff_not_evaluated"),
        ),
        sa.CheckConstraint("engine = 'prowler'", name=op.f("ck_scan_check_results_engine")),
        sa.CheckConstraint(
            "reason IN ('no_findings', 'excluded', 'not_granted')",
            name=op.f("ck_scan_check_results_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'manual', 'not_evaluated')",
            name=op.f("ck_scan_check_results_status"),
        ),
        sa.CheckConstraint(
            "pass_count >= 0 AND fail_count >= 0 AND manual_count >= 0",
            name=op.f("ck_scan_check_results_counts_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["scans.organization_id", "scans.id"],
            name=op.f("fk_scan_check_results_organization_id_scan_id_scans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_scan_check_results_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "scan_id", "engine", "check_id", name=op.f("pk_scan_check_results")
        ),
    )
    op.create_index(
        op.f("ix_scan_check_results_organization_id"),
        "scan_check_results",
        ["organization_id"],
        unique=False,
    )
    for table in ("scans", "scan_check_results", "findings"):
        for statement in rls_v1.tenant_rls(table):
            op.execute(statement)
    op.execute(rls_v1.grant("scans", "SELECT", "INSERT", "UPDATE"))
    for table in ("scan_check_results", "findings"):
        op.execute(rls_v1.grant(table, "SELECT", "INSERT"))  # append-only


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
