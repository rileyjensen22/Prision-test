"""phase 20: facility model (site, hub, line, floor, rec area), cells on floors, per-floor blocks

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
    )
    op.create_table(
        "hubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
    )
    op.create_index("ix_hubs_site_id", "hubs", ["site_id"])
    op.create_table(
        "lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hub_id", sa.Integer(), sa.ForeignKey("hubs.id"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
    )
    op.create_index("ix_lines_hub_id", "lines", ["hub_id"])
    op.create_table(
        "floors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.UniqueConstraint("line_id", "level", name="uq_floor_level"),
    )
    op.create_index("ix_floors_line_id", "floors", ["line_id"])
    op.create_table(
        "rec_areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("lines.id"), nullable=False),
        sa.Column("code", sa.String(24), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.CheckConstraint("kind IN ('indoor', 'outdoor')", name="ck_rec_area_kind"),
    )
    op.create_index("ix_rec_areas_line_id", "rec_areas", ["line_id"])
    op.add_column("cells", sa.Column("floor_id", sa.Integer(), sa.ForeignKey("floors.id")))
    op.create_index("ix_cells_floor_id", "cells", ["floor_id"])
    op.add_column(
        "schedule_blocks",
        sa.Column("floor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "schedule_blocks", sa.Column("rec_area_id", sa.Integer(), sa.ForeignKey("rec_areas.id"))
    )
    op.drop_constraint("uq_schedule_block", "schedule_blocks", type_="unique")
    op.create_unique_constraint(
        "uq_schedule_block", "schedule_blocks", ["unit", "day", "kind", "start", "floor"]
    )
    # Dashboard and roster filters group by these.
    op.create_index(
        "ix_device_assignments_open",
        "device_assignments",
        ["resident_id"],
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO isd_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO isd_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON
              audit_log, config_versions, trust_ledger, out_of_cell_log, earnings_ledger,
              work_log, reconciliation_runs, task_submissions, out_of_cell_events,
              certificates, reentry_events, outcome_records, outcome_import_batches,
              chess_moves FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_index("ix_device_assignments_open", table_name="device_assignments")
    op.drop_constraint("uq_schedule_block", "schedule_blocks", type_="unique")
    op.create_unique_constraint(
        "uq_schedule_block", "schedule_blocks", ["unit", "day", "kind", "start"]
    )
    op.drop_column("schedule_blocks", "rec_area_id")
    op.drop_column("schedule_blocks", "floor")
    op.drop_index("ix_cells_floor_id", table_name="cells")
    op.drop_column("cells", "floor_id")
    for t in ("rec_areas", "floors", "lines", "hubs", "sites"):
        op.drop_table(t)
