"""Hybrid retrieval: dense (pgvector) + lexical (tsvector) + symbol (trigram),
fused with Reciprocal Rank Fusion, packed to a token budget.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.config import get_settings
from app.models.code import CodeChunk, CodeFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from worker.codeintel.chunker import estimate_tokens
from worker.embeddings import get_embedder

_RRF_K = 60
_PER_MODALITY = 40


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    path: str
    symbol: str | None
    kind: str
    start_line: int
    end_line: int
    content: str
    tokens: int
    score: float
    modalities: list[str]


def _vector_hits(db: Session, version_id: uuid.UUID, query: str) -> list[uuid.UUID]:
    qvec = get_embedder().embed_one(query)
    stmt = (
        select(CodeChunk.id)
        .where(CodeChunk.repository_version_id == version_id, CodeChunk.embedding.isnot(None))
        .order_by(CodeChunk.embedding.cosine_distance(qvec))
        .limit(_PER_MODALITY)
    )
    return list(db.scalars(stmt).all())


def _keyword_hits(db: Session, version_id: uuid.UUID, query: str) -> list[uuid.UUID]:
    tsquery = func.websearch_to_tsquery("english", query)
    stmt = (
        select(CodeChunk.id)
        .where(
            CodeChunk.repository_version_id == version_id,
            CodeChunk.tsv.op("@@")(tsquery),
        )
        .order_by(func.ts_rank_cd(CodeChunk.tsv, tsquery).desc())
        .limit(_PER_MODALITY)
    )
    return list(db.scalars(stmt).all())


def _symbol_hits(db: Session, version_id: uuid.UUID, symbols: list[str]) -> list[uuid.UUID]:
    if not symbols:
        return []
    stmt = (
        select(CodeChunk.id)
        .where(
            CodeChunk.repository_version_id == version_id,
            CodeChunk.symbol.isnot(None),
        )
        .order_by(func.greatest(*[func.similarity(CodeChunk.symbol, s) for s in symbols]).desc())
        .limit(_PER_MODALITY)
    )
    return list(db.scalars(stmt).all())


def _rrf(ranked_lists: dict[str, list[uuid.UUID]]) -> dict[uuid.UUID, tuple[float, list[str]]]:
    scores: dict[uuid.UUID, tuple[float, list[str]]] = {}
    for modality, ids in ranked_lists.items():
        for rank, cid in enumerate(ids):
            prev_score, prev_mods = scores.get(cid, (0.0, []))
            scores[cid] = (prev_score + 1.0 / (_RRF_K + rank + 1), [*prev_mods, modality])
    return scores


def hybrid_search(
    db: Session,
    *,
    repository_version_id: uuid.UUID,
    query: str,
    symbol_hints: list[str] | None = None,
    token_budget: int | None = None,
) -> list[RetrievedChunk]:
    budget = token_budget or get_settings().retrieval_token_budget
    lists = {
        "vector": _vector_hits(db, repository_version_id, query),
        "keyword": _keyword_hits(db, repository_version_id, query),
        "symbol": _symbol_hits(db, repository_version_id, symbol_hints or []),
    }
    fused = _rrf(lists)
    if not fused:
        return []

    ordered_ids = [cid for cid, _ in sorted(fused.items(), key=lambda kv: kv[1][0], reverse=True)]
    rows = {
        c.id: (c, path)
        for c, path in db.execute(
            select(CodeChunk, CodeFile.path)
            .join(CodeFile, CodeFile.id == CodeChunk.code_file_id)
            .where(CodeChunk.id.in_(ordered_ids))
        ).all()
    }

    out: list[RetrievedChunk] = []
    used = 0
    for cid in ordered_ids:
        if cid not in rows:
            continue
        chunk, path = rows[cid]
        tokens = chunk.token_count or estimate_tokens(chunk.content)
        if used + tokens > budget and out:
            continue
        score, modalities = fused[cid]
        out.append(
            RetrievedChunk(
                chunk_id=cid,
                path=path,
                symbol=chunk.symbol,
                kind=chunk.kind,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                tokens=tokens,
                score=round(score, 6),
                modalities=modalities,
            )
        )
        used += tokens
        if used >= budget:
            break
    return out


def pack_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as delimited, clearly-untrusted context blocks."""
    parts = []
    for c in chunks:
        head = f'<repository_file path="{c.path}" lines="{c.start_line}-{c.end_line}"'
        if c.symbol:
            head += f' symbol="{c.symbol}"'
        head += ">"
        parts.append(f"{head}\n{c.content}\n</repository_file>")
    return "\n\n".join(parts)
