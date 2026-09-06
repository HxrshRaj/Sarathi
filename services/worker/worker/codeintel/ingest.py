"""Repository indexing: workspace -> code_files + code_chunks (+ embeddings)."""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pathspec
from app.config import get_settings
from app.db import SyncSessionLocal
from app.logging import get_logger
from app.models.code import CodeChunk, CodeFile
from app.models.enums import IndexStatus
from app.models.repository import Repository, RepositoryVersion
from app.models.user import GithubIdentity
from app.security.crypto import decrypt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from worker.codeintel.chunker import chunk_file
from worker.codeintel.languages import detect_language
from worker.codeintel.secrets import redact
from worker.embeddings import get_embedder
from worker.git_ops import clone_at

log = get_logger("ingest")

_MAX_FILE_BYTES = 400_000
_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "vendor",
    "target",
}
_EMBED_BATCH = 128


def _iter_source_files(root: Path):
    ignore = pathspec.PathSpec.from_lines("gitwildmatch", _load_gitignore(root))
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        if ignore.match_file(rel):
            continue
        if detect_language(rel) is None:
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        yield rel, raw.decode("utf-8", errors="ignore")


def _load_gitignore(root: Path) -> list[str]:
    gi = root / ".gitignore"
    return gi.read_text("utf-8", errors="ignore").splitlines() if gi.exists() else []


def index_repository_version(version_id: str) -> dict:
    with SyncSessionLocal() as db:
        version = db.get(RepositoryVersion, uuid.UUID(version_id))
        if version is None:
            raise ValueError(f"RepositoryVersion {version_id} not found")
        repo = db.get(Repository, version.repository_id)
        assert repo is not None
        token = _repo_token(db, repo)

        version.status = IndexStatus.INDEXING
        version.index_error = None
        db.commit()

    try:
        with tempfile.TemporaryDirectory(prefix="cp-index-") as tmp:
            workdir = Path(tmp) / "repo"
            clone_at(repo.clone_url, workdir, ref=version.commit_sha, token=token)
            stats = _ingest_workspace(uuid.UUID(version_id), workdir)
    except Exception as exc:  # noqa: BLE001
        with SyncSessionLocal() as db:
            v = db.get(RepositoryVersion, uuid.UUID(version_id))
            if v:
                v.status = IndexStatus.FAILED
                v.index_error = str(exc)[:1000]
                db.commit()
        log.error("index_failed", version_id=version_id, error=str(exc))
        raise

    with SyncSessionLocal() as db:
        v = db.get(RepositoryVersion, uuid.UUID(version_id))
        assert v is not None
        v.status = IndexStatus.READY
        v.file_count = stats["files"]
        v.chunk_count = stats["chunks"]
        v.indexed_at = datetime.now(UTC)
        db.commit()
    log.info("index_complete", version_id=version_id, **stats)
    return stats


def _repo_token(db: Session, repo: Repository) -> str | None:
    identity = db.scalar(select(GithubIdentity).where(GithubIdentity.user_id == repo.user_id))
    return decrypt(identity.access_token_encrypted) if identity else None


def _ingest_workspace(version_id: uuid.UUID, workdir: Path) -> dict:
    embedder = get_embedder()
    settings = get_settings()

    with SyncSessionLocal() as db:
        db.execute(delete(CodeChunk).where(CodeChunk.repository_version_id == version_id))
        db.execute(delete(CodeFile).where(CodeFile.repository_version_id == version_id))
        db.commit()

    file_count = 0
    chunk_count = 0
    pending: list[tuple[CodeChunk, str]] = []

    def flush(force: bool = False) -> None:
        nonlocal chunk_count
        if not pending or (len(pending) < _EMBED_BATCH and not force):
            return
        texts = [f"{c.symbol or ''}\n{content}" for c, content in pending]
        vectors = embedder.embed(texts)
        with SyncSessionLocal() as db:
            for (chunk, _), vec in zip(pending, vectors, strict=True):
                chunk.embedding = vec
                db.add(chunk)
            db.commit()
        chunk_count += len(pending)
        pending.clear()

    for rel, source in _iter_source_files(workdir):
        redacted = redact(source)
        lang = detect_language(rel)
        file_id = uuid.uuid4()
        with SyncSessionLocal() as db:
            db.add(
                CodeFile(
                    id=file_id,
                    repository_version_id=version_id,
                    path=rel,
                    language=lang,
                    size_bytes=len(source.encode("utf-8")),
                    sha=hashlib.sha1(source.encode("utf-8"), usedforsecurity=False).hexdigest(),
                    symbol_count=0,
                )
            )
            db.commit()
        file_count += 1

        for ch in chunk_file(rel, redacted):
            if len(ch.content) > settings.retrieval_token_budget * 8:
                continue
            pending.append(
                (
                    CodeChunk(
                        repository_version_id=version_id,
                        code_file_id=file_id,
                        symbol=ch.symbol,
                        kind=ch.kind,
                        start_line=ch.start_line,
                        end_line=ch.end_line,
                        content=ch.content,
                        token_count=ch.token_estimate,
                    ),
                    ch.content,
                )
            )
            flush()

    flush(force=True)
    return {"files": file_count, "chunks": chunk_count}
