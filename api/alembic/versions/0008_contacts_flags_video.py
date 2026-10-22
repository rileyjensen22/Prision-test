"""contact requests, message delivery and flags, video bookings, recording purge

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("status", sa.String(10), server_default="approved", nullable=False),
    )
    op.add_column(
        "contacts",
        sa.Column("requested_by", sa.String(8), server_default="staff", nullable=False),
    )
    op.add_column("contacts", sa.Column("verification", sa.String(32), nullable=True))
    op.add_column("contacts", sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("contacts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("review_note", sa.Text(), nullable=True))
    op.create_foreign_key("fk_contacts_reviewed_by", "contacts", "staff", ["reviewed_by"], ["id"])
    op.execute("UPDATE contacts SET status = CASE WHEN approved THEN 'approved' ELSE 'pending' END")
    op.create_check_constraint(
        "ck_contact_status", "contacts", "status IN ('pending', 'approved', 'rejected')"
    )
    op.create_check_constraint(
        "ck_contact_approved_matches", "contacts", "approved = (status = 'approved')"
    )

    op.add_column(
        "messages", sa.Column("delivery", sa.String(10), server_default="delivered", nullable=False)
    )
    op.create_check_constraint(
        "ck_msg_delivery", "messages", "delivery IN ('queued', 'sent', 'delivered', 'failed')"
    )
    op.create_table(
        "message_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "rule_id", name="uq_flag_message_rule"),
        sa.CheckConstraint("status IN ('open', 'reviewed', 'referred')", name="ck_flag_status"),
    )
    op.create_index(op.f("ix_message_flags_message_id"), "message_flags", ["message_id"])

    op.create_table(
        "video_bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("call_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["call_id"], ["call_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('scheduled', 'started', 'cancelled', 'missed')", name="ck_booking_status"
        ),
        sa.CheckConstraint("minutes > 0", name="ck_booking_minutes"),
    )
    op.create_index(op.f("ix_video_bookings_resident_id"), "video_bookings", ["resident_id"])

    op.add_column(
        "call_records", sa.Column("recording_purged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO isd_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO isd_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON
              audit_log, config_versions, trust_ledger, out_of_cell_log FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("call_records", "recording_purged_at")
    op.drop_index(op.f("ix_video_bookings_resident_id"), table_name="video_bookings")
    op.drop_table("video_bookings")
    op.drop_index(op.f("ix_message_flags_message_id"), table_name="message_flags")
    op.drop_table("message_flags")
    op.drop_constraint("ck_msg_delivery", "messages", type_="check")
    op.drop_column("messages", "delivery")
    op.drop_constraint("ck_contact_approved_matches", "contacts", type_="check")
    op.drop_constraint("ck_contact_status", "contacts", type_="check")
    op.drop_constraint("fk_contacts_reviewed_by", "contacts", type_="foreignkey")
    for col in (
        "review_note",
        "reviewed_at",
        "reviewed_by",
        "requested_at",
        "verification",
        "requested_by",
        "status",
    ):
        op.drop_column("contacts", col)
