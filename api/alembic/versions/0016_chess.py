"""phase 19: human chess matches, staff switch, cell line code, append-only moves

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("chess_human", sa.Boolean(), nullable=True))
    op.add_column("cells", sa.Column("line_code", sa.String(16), nullable=True))
    op.add_column(
        "chess_games",
        sa.Column("black_resident_id", sa.Integer(), sa.ForeignKey("residents.id"), nullable=True),
    )
    op.create_index("ix_chess_games_black_resident_id", "chess_games", ["black_resident_id"])
    for name, kind in (
        ("level", sa.Integer()),
        ("white_handle", sa.String(32)),
        ("black_handle", sa.String(32)),
        ("fen", sa.String(100)),
        ("result", sa.String(8)),
        ("result_reason", sa.String(16)),
        ("draw_offer_by", sa.String(5)),
        ("wait_until", sa.DateTime(timezone=True)),
        ("updated_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("chess_games", sa.Column(name, kind, nullable=True))
    op.create_check_constraint(
        "ck_chess_result", "chess_games", "result IN ('white','black','draw')"
    )
    op.create_check_constraint(
        "ck_chess_draw_offer", "chess_games", "draw_offer_by IN ('white','black')"
    )
    op.execute("""
        CREATE TRIGGER chess_moves_no_update_delete BEFORE UPDATE OR DELETE ON chess_moves
        FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
    """)
    op.execute("""
        CREATE TRIGGER chess_moves_no_truncate BEFORE TRUNCATE ON chess_moves
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
              certificates, reentry_events, outcome_records, outcome_import_batches,
              chess_moves FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS chess_moves_no_truncate ON chess_moves")
    op.execute("DROP TRIGGER IF EXISTS chess_moves_no_update_delete ON chess_moves")
    op.drop_constraint("ck_chess_draw_offer", "chess_games")
    op.drop_constraint("ck_chess_result", "chess_games")
    for name in (
        "updated_at",
        "wait_until",
        "draw_offer_by",
        "result_reason",
        "result",
        "fen",
        "black_handle",
        "white_handle",
        "level",
    ):
        op.drop_column("chess_games", name)
    op.drop_index("ix_chess_games_black_resident_id", table_name="chess_games")
    op.drop_column("chess_games", "black_resident_id")
    op.drop_column("cells", "line_code")
    op.drop_column("residents", "chess_human")
