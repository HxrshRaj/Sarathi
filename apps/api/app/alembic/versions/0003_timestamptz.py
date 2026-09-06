"""make every timestamp column timezone-aware (timestamptz)

`created_at` / `updated_at` were already `timestamptz`; the rest (session
expiry, run/step/eval start-finish, index time, token expiry) were naive.
App code writes tz-aware UTC datetimes and asyncpg rejects those against a
naive column, breaking the OAuth callback. Existing naive values are read as UTC.

Revision ID: 0003_timestamptz
Revises: 0002_embedding_dim
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_timestamptz"
down_revision: str | None = "0002_embedding_dim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: list[tuple[str, str]] = [
    ("sessions", "expires_at"),
    ("sessions", "revoked_at"),
    ("github_identities", "token_expires_at"),
    ("repository_versions", "indexed_at"),
    ("agent_runs", "started_at"),
    ("agent_runs", "finished_at"),
    ("agent_steps", "started_at"),
    ("agent_steps", "finished_at"),
    ("evaluations", "started_at"),
    ("evaluations", "finished_at"),
]


def upgrade() -> None:
    for table, col in _COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE timestamptz "
            f"USING {col} AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    for table, col in _COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE timestamp "
            f"USING {col} AT TIME ZONE 'UTC'"
        )
