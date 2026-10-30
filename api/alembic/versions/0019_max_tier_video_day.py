"""Add max_tier_override to residents; no schema change needed for video_min_day (config only)

Revision ID: 0019
Revises: 0018
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "residents",
        sa.Column("max_tier_override", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("residents", "max_tier_override")
