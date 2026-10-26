"""phase 18: resident lifecycle, staff MFA, shared rate limits, encryption at rest

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _encrypt_existing(
    table: str, column: str, purpose: str, hash_column: str | None = None
) -> None:
    """Encrypts values written before encryption existed (the app reads either form)."""
    from isd.crypto import blind_index, encrypt, is_encrypted

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")  # noqa: S608
    ).all()
    for row_id, value in rows:
        if is_encrypted(value):
            continue
        params = {"v": encrypt(value, purpose), "id": row_id}
        extra = ""
        if hash_column:
            extra = f", {hash_column} = :h"
            params["h"] = blind_index(value)
        conn.execute(
            sa.text(f"UPDATE {table} SET {column} = :v{extra} WHERE id = :id"),  # noqa: S608
            params,
        )


def upgrade() -> None:
    # resident lifecycle
    op.add_column("residents", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))

    # staff sign-in security
    op.add_column("staff", sa.Column("mfa_secret", sa.Text(), nullable=True))
    op.add_column(
        "staff", sa.Column("mfa_enabled", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "staff",
        sa.Column("mfa_recovery_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("staff", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    op.add_column(
        "staff",
        sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "staff", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # shared rate-limit store: counters live in Postgres so several API processes agree
    op.execute("""
        CREATE UNLOGGED TABLE rate_limit_hits (
            id BIGSERIAL PRIMARY KEY,
            bucket VARCHAR(32) NOT NULL,
            key VARCHAR(128) NOT NULL,
            hit_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("CREATE INDEX ix_rate_limit_hits ON rate_limit_hits (bucket, key, hit_at)")

    # encryption at rest
    op.alter_column("contacts", "phone_ref", type_=sa.Text(), existing_nullable=True)
    op.add_column("contacts", sa.Column("phone_hash", sa.String(64), nullable=True))
    op.create_index("ix_contacts_phone_hash", "contacts", ["phone_hash"])
    op.alter_column("call_records", "provider_ref", type_=sa.Text(), existing_nullable=False)
    op.alter_column("call_records", "monitor_ref", type_=sa.Text(), existing_nullable=True)
    _encrypt_existing("contacts", "phone_ref", "contacts.phone_ref", "phone_hash")
    _encrypt_existing("messages", "body", "messages.body")
    _encrypt_existing("call_records", "provider_ref", "call_records.provider_ref")
    _encrypt_existing("call_records", "monitor_ref", "call_records.monitor_ref")

    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'isd_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO isd_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO isd_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON
              audit_log, config_versions, trust_ledger, out_of_cell_log, earnings_ledger,
              work_log, reconciliation_runs, task_submissions, out_of_cell_events,
              certificates, reentry_events, outcome_records FROM isd_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    raise NotImplementedError("encrypted values are not decrypted back; restore from a backup")
