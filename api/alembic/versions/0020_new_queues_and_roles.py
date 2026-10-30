"""New queues (health requests, grievances, attorney calls, deposits, library, reentry)
and expanded staff roles (health_staff, legal_liaison, commissary_clerk).

Revision ID: 0020
Revises: 0019
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand the staff role check constraint
    op.drop_constraint("ck_staff_role", "staff", type_="check")
    op.create_check_constraint(
        "ck_staff_role",
        "staff",
        "role IN ('officer','supervisor','admin','auditor','health_staff','legal_liaison','commissary_clerk')",
    )

    # Alter commissary_orders: add status, staff_id, refund_reason, updated_at
    op.add_column("commissary_orders", sa.Column("status", sa.String(20), nullable=False, server_default="new"))
    op.add_column("commissary_orders", sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True))
    op.add_column("commissary_orders", sa.Column("refund_reason", sa.Text(), nullable=False, server_default=""))
    op.add_column("commissary_orders", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_co_status", "commissary_orders",
        "status IN ('new','packed','delivered','refunded')"
    )

    # New tables
    op.create_table(
        "health_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resident_id", sa.Integer(), sa.ForeignKey("residents.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("staff_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('medical','mental_health')", name="ck_hr_kind"),
        sa.CheckConstraint("status IN ('open','triaged','scheduled','seen','closed')", name="ck_hr_status"),
    )

    op.create_table(
        "grievances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resident_id", sa.Integer(), sa.ForeignKey("residents.id"), nullable=False, index=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("response", sa.Text(), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open','under_review','resolved','closed')", name="ck_griev_status"),
    )

    op.create_table(
        "attorney_call_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resident_id", sa.Integer(), sa.ForeignKey("residents.id"), nullable=False, index=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("attorney_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("attorney_phone", sa.String(30), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("staff_note", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('pending','approved','scheduled','completed','denied')",
            name="ck_acr_status",
        ),
    )

    op.create_table(
        "deposit_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("imported_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','applied','rejected')", name="ck_di_status"),
    )

    op.create_table(
        "library_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("author", sa.String(200), nullable=False, server_default=""),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("reading_level", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "reentry_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("address", sa.String(500), nullable=False, server_default=""),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reentry_resources")
    op.drop_table("library_items")
    op.drop_table("deposit_imports")
    op.drop_table("attorney_call_requests")
    op.drop_table("grievances")
    op.drop_table("health_requests")

    op.drop_constraint("ck_co_status", "commissary_orders", type_="check")
    op.drop_column("commissary_orders", "updated_at")
    op.drop_column("commissary_orders", "refund_reason")
    op.drop_column("commissary_orders", "staff_id")
    op.drop_column("commissary_orders", "status")

    op.drop_constraint("ck_staff_role", "staff", type_="check")
    op.create_check_constraint(
        "ck_staff_role", "staff",
        "role IN ('officer','supervisor','admin','auditor')",
    )
