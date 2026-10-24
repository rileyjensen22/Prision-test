"""device health, pairing codes, device commands

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices", sa.Column("health", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("devices", sa.Column("health_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "device_pairings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_device_pairings_device_id", "device_pairings", ["device_id"])
    op.create_table(
        "device_commands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("issued_by", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["issued_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('lock', 'unlock', 'restart')", name="ck_device_command_kind"),
        sa.CheckConstraint("kind <> 'lock' OR ends_at IS NOT NULL", name="ck_lock_has_end"),
    )
    op.create_index("ix_device_commands_device_id", "device_commands", ["device_id"])
    op.create_table(
        "sweep_state",
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO isd_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO isd_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON
              audit_log, config_versions, trust_ledger, out_of_cell_log, earnings_ledger,
              work_log, reconciliation_runs, task_submissions, out_of_cell_events,
              certificates, reentry_events, outcome_records FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("sweep_state")
    op.drop_table("device_commands")
    op.drop_table("device_pairings")
    op.drop_column("devices", "health_at")
    op.drop_column("devices", "health")
