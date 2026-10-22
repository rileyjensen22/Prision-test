"""quiz sessions, certificates, course resume

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("course_progress", sa.Column("last_lesson", sa.String(40), nullable=True))
    op.add_column(
        "course_progress", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("course_code", sa.String(32), nullable=False),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('open', 'submitted', 'expired')", name="ck_quiz_status"),
    )
    op.create_index(op.f("ix_quiz_sessions_resident_id"), "quiz_sessions", ["resident_id"])
    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("serial", sa.String(32), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("course_code", sa.String(32), nullable=False),
        sa.Column("title", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial"),
        sa.UniqueConstraint("resident_id", "course_code", name="uq_certificate"),
    )
    op.create_index(op.f("ix_certificates_resident_id"), "certificates", ["resident_id"])
    # certificates are never edited or deleted
    op.execute("""
        CREATE TRIGGER certificates_no_update_delete BEFORE UPDATE OR DELETE ON certificates
        FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
    """)
    op.execute("""
        CREATE TRIGGER certificates_no_truncate BEFORE TRUNCATE ON certificates
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
              certificates FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS certificates_no_truncate ON certificates")
    op.execute("DROP TRIGGER IF EXISTS certificates_no_update_delete ON certificates")
    op.drop_index(op.f("ix_certificates_resident_id"), table_name="certificates")
    op.drop_table("certificates")
    op.drop_index(op.f("ix_quiz_sessions_resident_id"), table_name="quiz_sessions")
    op.drop_table("quiz_sessions")
    op.drop_column("course_progress", "updated_at")
    op.drop_column("course_progress", "last_lesson")
