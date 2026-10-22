"""schedule blocks, out-of-cell events, stored welfare flags

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

KINDS = "('indoor', 'outdoor', 'program', 'visit')"
ALL_APPEND_ONLY = (
    "audit_log",
    "config_versions",
    "trust_ledger",
    "out_of_cell_log",
    "earnings_ledger",
    "work_log",
    "reconciliation_runs",
    "task_submissions",
    "out_of_cell_events",
)


def upgrade() -> None:
    op.add_column("cells", sa.Column("unit", sa.String(16), server_default="A", nullable=False))

    op.create_table(
        "schedule_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("start", sa.String(5), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(128), nullable=True),
        sa.Column("required_feature", sa.String(32), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit", "day", "kind", "start", name="uq_schedule_block"),
        sa.CheckConstraint(f"kind IN {KINDS}", name="ck_block_kind"),
        sa.CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_block_status"),
        sa.CheckConstraint("minutes > 0 AND capacity > 0", name="ck_block_positive"),
    )
    op.create_index(op.f("ix_schedule_blocks_unit"), "schedule_blocks", ["unit"])
    op.create_index(op.f("ix_schedule_blocks_day"), "schedule_blocks", ["day"])

    op.add_column("rec_bookings", sa.Column("block_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_rec_booking_block", "rec_bookings", "schedule_blocks", ["block_id"], ["id"]
    )
    op.create_index(op.f("ix_rec_bookings_block_id"), "rec_bookings", ["block_id"])
    op.drop_constraint("ck_rec_kind", "rec_bookings", type_="check")
    op.create_check_constraint("ck_rec_kind", "rec_bookings", f"kind IN {KINDS}")

    op.create_table(
        "out_of_cell_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(3), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity", sa.String(8), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=True),
        sa.Column("entered_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["block_id"], ["schedule_blocks.id"]),
        sa.ForeignKeyConstraint(["entered_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("event IN ('out', 'in')", name="ck_ooce_event"),
        sa.CheckConstraint(
            "activity IN ('indoor', 'outdoor', 'program', 'visit', 'other')",
            name="ck_ooce_activity",
        ),
    )
    op.create_index(
        op.f("ix_out_of_cell_events_resident_id"), "out_of_cell_events", ["resident_id"]
    )
    op.execute("""
        CREATE TRIGGER out_of_cell_events_no_update_delete BEFORE UPDATE OR DELETE
        ON out_of_cell_events FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
    """)
    op.execute("""
        CREATE TRIGGER out_of_cell_events_no_truncate BEFORE TRUNCATE ON out_of_cell_events
        FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
    """)

    op.create_table(
        "welfare_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("flag_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'cleared')", name="ck_wflag_status"),
    )
    op.create_index(op.f("ix_welfare_flags_resident_id"), "welfare_flags", ["resident_id"])
    op.add_column(
        "welfare_acks",
        sa.Column("action", sa.String(32), server_default="checked_in", nullable=False),
    )
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
    op.drop_column("welfare_acks", "action")
    op.drop_index(op.f("ix_welfare_flags_resident_id"), table_name="welfare_flags")
    op.drop_table("welfare_flags")
    op.execute("DROP TRIGGER IF EXISTS out_of_cell_events_no_truncate ON out_of_cell_events")
    op.execute("DROP TRIGGER IF EXISTS out_of_cell_events_no_update_delete ON out_of_cell_events")
    op.drop_index(op.f("ix_out_of_cell_events_resident_id"), table_name="out_of_cell_events")
    op.drop_table("out_of_cell_events")
    op.drop_constraint("ck_rec_kind", "rec_bookings", type_="check")
    op.create_check_constraint("ck_rec_kind", "rec_bookings", "kind IN ('indoor', 'outdoor')")
    op.drop_index(op.f("ix_rec_bookings_block_id"), table_name="rec_bookings")
    op.drop_constraint("fk_rec_booking_block", "rec_bookings", type_="foreignkey")
    op.drop_column("rec_bookings", "block_id")
    op.drop_index(op.f("ix_schedule_blocks_day"), table_name="schedule_blocks")
    op.drop_index(op.f("ix_schedule_blocks_unit"), table_name="schedule_blocks")
    op.drop_table("schedule_blocks")
    op.drop_column("cells", "unit")
