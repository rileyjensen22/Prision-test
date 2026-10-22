"""keep-separate, release date, reentry checklist events, outcome records

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

APPEND_ONLY = ("reentry_events", "outcome_records")


def upgrade() -> None:
    op.add_column("residents", sa.Column("release_date", sa.Date(), nullable=True))
    op.create_table(
        "keep_separate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_a_id", sa.Integer(), nullable=False),
        sa.Column("resident_b_id", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["resident_a_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["resident_b_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["added_by"], ["staff.id"]),
        sa.ForeignKeyConstraint(["ended_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("resident_a_id < resident_b_id", name="ck_keep_separate_order"),
    )
    op.create_index("ix_keep_separate_resident_a_id", "keep_separate", ["resident_a_id"])
    op.create_index("ix_keep_separate_resident_b_id", "keep_separate", ["resident_b_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_keep_separate_open ON keep_separate (resident_a_id, resident_b_id)"
        " WHERE ended_at IS NULL"
    )
    op.create_table(
        "reentry_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reentry_events_resident_id", "reentry_events", ["resident_id"])
    op.create_table(
        "outcome_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("window_months", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("corrects_id", sa.Integer(), nullable=True),
        sa.Column("entered_by", sa.Integer(), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["corrects_id"], ["outcome_records.id"]),
        sa.ForeignKeyConstraint(["entered_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("window_months IN (6, 12, 24)", name="ck_outcome_window"),
        sa.CheckConstraint(
            "outcome IN ('no_return', 'returned', 'unknown')", name="ck_outcome_value"
        ),
    )
    op.create_index("ix_outcome_records_resident_id", "outcome_records", ["resident_id"])
    for table in APPEND_ONLY:
        op.execute(f"""
            CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
        """)
        op.execute(f"""
            CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
        """)
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
    for table in reversed(APPEND_ONLY):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table}")
    op.drop_table("outcome_records")
    op.drop_table("reentry_events")
    op.execute("DROP INDEX IF EXISTS uq_keep_separate_open")
    op.drop_table("keep_separate")
    op.drop_column("residents", "release_date")
