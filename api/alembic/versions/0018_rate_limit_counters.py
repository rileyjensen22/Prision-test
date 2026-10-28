"""rate limits as sliding-window counters (one row per key and window) instead of one row per hit

A row per hit made the cost of each check grow with the traffic for a busy key (every request from
one address), and a per-key advisory lock serialised them. The load test at full facility size
showed it: the counters keep each check to one or two single-row statements.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rate_limit_hits")
    op.execute("""
        CREATE UNLOGGED TABLE rate_limit_counts (
            bucket text NOT NULL,
            key text NOT NULL,
            window_no bigint NOT NULL,
            n integer NOT NULL,
            start_s double precision NOT NULL,
            PRIMARY KEY (bucket, key, window_no)
        )
    """)
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_counts TO isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rate_limit_counts")
    op.execute("""
        CREATE UNLOGGED TABLE rate_limit_hits (
            id bigserial PRIMARY KEY,
            bucket varchar(32) NOT NULL,
            key varchar(128) NOT NULL,
            hit_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("CREATE INDEX ix_rate_limit_hits ON rate_limit_hits (bucket, key, hit_at)")
