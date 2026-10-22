"""work tasks, earnings ledger, work log, reconciliation runs

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# Tables nobody may update or delete from (trigger plus revoked grants).
APPEND_ONLY = ("earnings_ledger", "work_log", "reconciliation_runs", "task_submissions")
ALL_APPEND_ONLY = ("audit_log", "config_versions", "trust_ledger", "out_of_cell_log", *APPEND_ONLY)
TASK_KINDS = "('transcription_public_domain', 'captioning', 'labeling_non_personal')"


def upgrade() -> None:
    op.create_table(
        "job_partners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.add_column("job_listings", sa.Column("partner_id", sa.Integer(), nullable=True))
    op.add_column(
        "job_listings",
        sa.Column("pay_per_task_cents", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_foreign_key(
        "fk_listing_partner", "job_listings", "job_partners", ["partner_id"], ["id"]
    )

    op.create_table(
        "job_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("claimed_by", sa.Integer(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["job_listings.id"]),
        sa.ForeignKeyConstraint(["claimed_by"], ["residents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", "external_id", name="uq_task_external"),
        sa.CheckConstraint(f"kind IN {TASK_KINDS}", name="ck_task_kind"),
        sa.CheckConstraint(
            "status IN ('open', 'claimed', 'accepted', 'rejected')", name="ck_task_status"
        ),
    )
    op.create_index(op.f("ix_job_tasks_listing_id"), "job_tasks", ["listing_id"])

    op.create_table(
        "task_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("review_reason", sa.String(32), nullable=False),
        sa.Column("pay_cents", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["job_tasks.id"]),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["job_listings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index(op.f("ix_task_submissions_resident_id"), "task_submissions", ["resident_id"])

    op.create_table(
        "earnings_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(8), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=True),
        sa.Column("gross_cents", sa.Integer(), nullable=False),
        sa.Column("resident_cents", sa.Integer(), nullable=False),
        sa.Column("facility_cents", sa.Integer(), nullable=False),
        sa.Column("deductions_cents", sa.Integer(), nullable=False),
        sa.Column("split", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trust_ledger_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["task_submissions.id"]),
        sa.ForeignKeyConstraint(["trust_ledger_id"], ["trust_ledger.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id"),
        sa.UniqueConstraint("trust_ledger_id"),
        sa.CheckConstraint("entry_type IN ('earned', 'payout')", name="ck_earn_type"),
        sa.CheckConstraint(
            "entry_type <> 'earned' OR (gross_cents > 0 AND resident_cents >= 0"
            " AND facility_cents >= 0 AND deductions_cents >= 0"
            " AND gross_cents = resident_cents + facility_cents + deductions_cents"
            " AND submission_id IS NOT NULL AND trust_ledger_id IS NULL)",
            name="ck_earn_earned_adds_up",
        ),
        sa.CheckConstraint(
            "entry_type <> 'payout' OR (resident_cents < 0 AND gross_cents = 0"
            " AND facility_cents = 0 AND deductions_cents = 0"
            " AND trust_ledger_id IS NOT NULL AND submission_id IS NULL)",
            name="ck_earn_payout_shape",
        ),
    )
    op.create_index(op.f("ix_earnings_ledger_resident_id"), "earnings_ledger", ["resident_id"])

    op.create_table(
        "work_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["job_listings.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["job_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "event IN ('joined', 'left', 'task_accepted', 'task_rejected')", name="ck_worklog_event"
        ),
    )
    op.create_index(op.f("ix_work_log_resident_id"), "work_log", ["resident_id"])

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("checked", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("problems", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.drop_constraint("ck_ledger_type", "trust_ledger", type_="check")
    op.create_check_constraint(
        "ck_ledger_type",
        "trust_ledger",
        "entry_type IN ('deposit', 'purchase', 'refund', 'adjustment', 'job_payout')",
    )

    for table in APPEND_ONLY:
        op.execute(f"""
            CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
        """)
        op.execute(f"""
            CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
        """)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO isd_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO isd_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON {", ".join(ALL_APPEND_ONLY)} FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    for table in reversed(APPEND_ONLY):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table}")
    op.drop_constraint("ck_ledger_type", "trust_ledger", type_="check")
    op.create_check_constraint(
        "ck_ledger_type",
        "trust_ledger",
        "entry_type IN ('deposit', 'purchase', 'refund', 'adjustment')",
    )
    op.drop_table("reconciliation_runs")
    op.drop_index(op.f("ix_work_log_resident_id"), table_name="work_log")
    op.drop_table("work_log")
    op.drop_index(op.f("ix_earnings_ledger_resident_id"), table_name="earnings_ledger")
    op.drop_table("earnings_ledger")
    op.drop_index(op.f("ix_task_submissions_resident_id"), table_name="task_submissions")
    op.drop_table("task_submissions")
    op.drop_index(op.f("ix_job_tasks_listing_id"), table_name="job_tasks")
    op.drop_table("job_tasks")
    op.drop_constraint("fk_listing_partner", "job_listings", type_="foreignkey")
    op.drop_column("job_listings", "pay_per_task_cents")
    op.drop_column("job_listings", "partner_id")
    op.drop_table("job_partners")
