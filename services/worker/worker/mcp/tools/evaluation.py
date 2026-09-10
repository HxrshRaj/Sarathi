"""`run_evaluation` + `get_evaluation_result` — enqueue and poll the real
evaluation harness (`worker.evaluation.runner.run_evaluation`, executed by the
Celery worker).

The harness runs the full orchestrator per benchmark (real model calls, real
sandbox containers) and takes minutes, so the tool enqueues rather than blocks.
"""

from __future__ import annotations

import uuid

import anyio
from app.config import get_settings
from app.db import SyncSessionLocal
from app.models.enums import EvaluationStatus
from app.models.evaluation import Evaluation, EvaluationResult
from app.services.queue import TASK_EVALUATION, dispatch
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from worker.mcp.models import (
    BenchmarkResult,
    EvaluationResultOut,
    RunEvaluationResult,
)


def _iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def _f(x) -> float | None:  # noqa: ANN001
    return float(x) if x is not None else None


def _enqueue_sync(
    benchmark_set: str, model: str | None, only: list[str] | None
) -> RunEvaluationResult:
    chosen_model = model or get_settings().llm_default_model
    with SyncSessionLocal() as db:
        ev = Evaluation(
            benchmark_set=benchmark_set,
            model=chosen_model,
            prompt_bundle="active",
            status=EvaluationStatus.QUEUED,
        )
        db.add(ev)
        db.commit()
        ev_id = str(ev.id)

    dispatch(TASK_EVALUATION, evaluation_id=ev_id, only=only)
    return RunEvaluationResult(
        evaluation_id=ev_id,
        status="queued",
        benchmark_set=benchmark_set,
        model=chosen_model,
        only=only,
        detail=(
            "Enqueued to the Celery worker. Poll get_evaluation_result with this "
            "evaluation_id. Needs the worker + Docker sandbox running; on a "
            "free-tier model key expect the daily request cap to bite for a full set."
        ),
    )


def _result_sync(evaluation_id: str) -> EvaluationResultOut:
    with SyncSessionLocal() as db:
        ev = db.get(Evaluation, uuid.UUID(evaluation_id))
        if ev is None:
            raise ValueError(f"No evaluation {evaluation_id}")
        rows = list(
            db.scalars(
                select(EvaluationResult)
                .where(EvaluationResult.evaluation_id == ev.id)
                .order_by(EvaluationResult.benchmark_id)
            ).all()
        )
        return EvaluationResultOut(
            evaluation_id=str(ev.id),
            status=ev.status.value,
            model=ev.model,
            benchmark_set=ev.benchmark_set,
            started_at=_iso(ev.started_at),
            finished_at=_iso(ev.finished_at),
            task_success_rate=_f(ev.task_success_rate),
            test_pass_rate=_f(ev.test_pass_rate),
            regression_rate=_f(ev.regression_rate),
            security_violation_rate=_f(ev.security_violation_rate),
            avg_latency_s=_f(ev.avg_latency_s),
            avg_cost_usd=_f(ev.avg_cost_usd),
            has_regression=ev.has_regression,
            results=[
                BenchmarkResult(
                    benchmark_id=r.benchmark_id,
                    passed=r.passed,
                    build_ok=r.build_ok,
                    lint_ok=r.lint_ok,
                    tests_ok=r.tests_ok,
                    security_ok=r.security_ok,
                    regression=r.regression,
                    repair_iterations=r.repair_iterations,
                    judge_score=r.judge_score,
                    latency_s=_f(r.latency_s) or 0.0,
                    cost_usd=_f(r.cost_usd) or 0.0,
                )
                for r in rows
            ],
        )


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="run_evaluation",
        description=(
            "Enqueue a Sarathi benchmark evaluation. The evaluation harness runs "
            "the full agent orchestrator against each benchmark and grades it with "
            "deterministic gates + invariants + an LLM judge. Long-running, so this "
            "returns an evaluation_id immediately; poll get_evaluation_result."
        ),
    )
    async def run_evaluation(
        benchmark_set: str = "v1",
        model: str | None = None,
        only: list[str] | None = None,
    ) -> RunEvaluationResult:
        """
        Args:
            benchmark_set: Benchmark set id (default 'v1').
            model: LLM model id to run the agent with (default: server LLM_DEFAULT_MODEL).
            only: Optional list of benchmark ids to run instead of the whole set.
        """
        return await anyio.to_thread.run_sync(_enqueue_sync, benchmark_set, model, only)

    @mcp.tool(
        name="get_evaluation_result",
        description=(
            "Read the current state and per-benchmark results of an evaluation "
            "previously started with run_evaluation. Aggregate rates are null until "
            "it finishes."
        ),
    )
    async def get_evaluation_result(evaluation_id: str) -> EvaluationResultOut:
        """Args: evaluation_id: id returned by run_evaluation."""
        return await anyio.to_thread.run_sync(_result_sync, evaluation_id)
