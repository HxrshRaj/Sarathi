from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.errors import NotFound
from app.models.enums import EvaluationStatus
from app.models.evaluation import Evaluation
from app.ratelimit import enforce
from app.schemas.evaluation import EvaluationOut, EvaluationRunIn
from app.services.queue import TASK_EVALUATION, dispatch

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/run", response_model=EvaluationOut, status_code=202)
async def run_evaluation(body: EvaluationRunIn, db: DbSession, user: CurrentUser) -> EvaluationOut:
    await enforce("evaluation_run", str(user.id))
    ev = Evaluation(
        benchmark_set=body.benchmark_set,
        model=body.model or get_settings().llm_default_model,
        prompt_bundle=body.prompt_bundle,
        comparison_group=body.comparison_group,
        baseline_evaluation_id=body.baseline_evaluation_id,
        status=EvaluationStatus.QUEUED,
    )
    db.add(ev)
    await db.flush()
    await db.commit()
    dispatch(TASK_EVALUATION, evaluation_id=str(ev.id))
    return EvaluationOut.model_validate(ev)


@router.get("", response_model=list[EvaluationOut])
async def list_evaluations(
    db: DbSession, _user: CurrentUser, limit: int = Query(50, le=200)
) -> list[EvaluationOut]:
    rows = (
        await db.scalars(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(limit))
    ).all()
    return [EvaluationOut.model_validate(r) for r in rows]


@router.get("/compare", response_model=list[EvaluationOut])
async def compare(db: DbSession, _user: CurrentUser, ids: str = Query(...)) -> list[EvaluationOut]:
    id_list = [uuid.UUID(x) for x in ids.split(",") if x.strip()]
    rows = (
        await db.scalars(
            select(Evaluation)
            .where(Evaluation.id.in_(id_list))
            .options(selectinload(Evaluation.results))
        )
    ).all()
    return [EvaluationOut.model_validate(r) for r in rows]


@router.get("/{evaluation_id}", response_model=EvaluationOut)
async def get_evaluation(
    evaluation_id: uuid.UUID, db: DbSession, _user: CurrentUser
) -> EvaluationOut:
    ev = await db.scalar(
        select(Evaluation)
        .where(Evaluation.id == evaluation_id)
        .options(selectinload(Evaluation.results))
    )
    if ev is None:
        raise NotFound("Evaluation")
    return EvaluationOut.model_validate(ev)
