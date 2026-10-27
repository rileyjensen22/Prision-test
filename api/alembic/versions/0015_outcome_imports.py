"""outcome CSV imports: an append-only batch table and a batch id on each imported outcome

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_new", sa.Integer(), nullable=False),
        sa.Column("rows_correcting", sa.Integer(), nullable=False),
        sa.Column("rows_unchanged", sa.Integer(), nullable=False),
        sa.Column("entered_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column(
            "entered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column(
        "outcome_records",
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("outcome_import_batches.id")),
    )
    op.create_index("ix_outcome_records_batch_id", "outcome_records", ["batch_id"])
    op.execute("""
        CREATE TRIGGER outcome_import_batches_no_update_delete
        BEFORE UPDATE OR DELETE ON outcome_import_batches
        FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
    """)
    op.execute("""
        CREATE TRIGGER outcome_import_batches_no_truncate BEFORE TRUNCATE ON outcome_import_batches
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
              certificates, reentry_events, outcome_records, outcome_import_batches FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS outcome_import_batches_no_truncate ON outcome_import_batches"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS outcome_import_batches_no_update_delete ON outcome_import_batches"
    )
    op.drop_index("ix_outcome_records_batch_id", table_name="outcome_records")
    op.drop_column("outcome_records", "batch_id")
    op.drop_table("outcome_import_batches")
