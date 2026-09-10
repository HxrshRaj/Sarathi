"""resize code_chunks.embedding to the configured EMBEDDING_DIM

The default embedding provider is now Gemini (`text-embedding-004`, 768 dims),
up from the local `fastembed` default (384). Embeddings are a rebuildable cache,
so this truncates the code tables, swaps the vector column to the configured
dimension, rebuilds the IVFFlat index, and marks every repository_version for
re-indexing.

Revision ID: 0002_embedding_dim
Revises: 0001_initial
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.config import get_settings

revision: str = "0002_embedding_dim"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DIM = get_settings().embedding_dim
_PREV_DIM = 384


def _retype(dim: int) -> None:
    op.execute("TRUNCATE TABLE code_chunks, code_files RESTART IDENTITY CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_code_chunks_embedding")
    op.execute("ALTER TABLE code_chunks DROP COLUMN IF EXISTS embedding")
    op.execute(f"ALTER TABLE code_chunks ADD COLUMN embedding vector({dim})")
    op.execute(
        "CREATE INDEX ix_code_chunks_embedding ON code_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    # 'pending' == IndexStatus.PENDING.value; literal here so the migration stays
    # self-contained and free of an app-enum import.
    op.execute("UPDATE repository_versions SET status = 'pending', chunk_count = 0, file_count = 0")


def upgrade() -> None:
    _retype(_DIM)


def downgrade() -> None:
    _retype(_PREV_DIM)
