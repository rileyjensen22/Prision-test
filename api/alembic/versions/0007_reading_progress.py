"""reading progress, bookmarks and protected content sources

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approved_content_sources",
        sa.Column("protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_table(
        "reading_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resident_id", "item_id", name="uq_reading_progress"),
    )
    op.create_index(
        op.f("ix_reading_progress_resident_id"), "reading_progress", ["resident_id"], unique=False
    )
    op.create_table(
        "reading_bookmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resident_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resident_id", "item_id", "page", name="uq_reading_bookmark"),
    )
    op.create_index(
        op.f("ix_reading_bookmarks_resident_id"), "reading_bookmarks", ["resident_id"], unique=False
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
    op.drop_index(op.f("ix_reading_bookmarks_resident_id"), table_name="reading_bookmarks")
    op.drop_table("reading_bookmarks")
    op.drop_index(op.f("ix_reading_progress_resident_id"), table_name="reading_progress")
    op.drop_table("reading_progress")
    op.drop_column("approved_content_sources", "protected")
