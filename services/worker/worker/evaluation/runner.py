"""Evaluation runner: execute the full orchestrator against each benchmark, then
grade with deterministic gates + invariants + an advisory LLM judge.

A benchmark repo is a real local git repo, so the ordinary pipeline (clone →
index → analyse → plan → code → test → security → review) runs unmodified.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.db import SyncSessionLocal
from app.logging import get_logger
from app.models.enums import (
    AutonomyLevel,
    EvaluationStatus,
    IndexStatus,
    RunStatus,
    Severity,
    TaskStatus,
)
from app.models.evaluation import Evaluation, EvaluationResult
from app.models.repository import Repository, RepositoryVersion
from app.models.run import AgentRun, FileChange, SecurityFinding
from app.models.task import Task
from app.models.user import User

from worker.codeintel.ingest import index_repository_version
from worker.evaluation.benchmarks import Benchmark, load_benchmarks
from worker.orchestrator import Orchestrator
from worker.sandbox import SandboxConfig, SandboxError, SandboxRunner

log = get_logger("evaluation")
_EVAL_USER_GH_ID = -1


def run_evaluation(evaluation_id: str) -> dict:
    with SyncSessionLocal() as db:
        ev = db.get(Evaluation, uuid.UUID(evaluation_id))
        assert ev
        ev.status = EvaluationStatus.RUNNING
        ev.started_at = datetime.now(UTC)
        db.commit()
        benchmarks = load_benchmarks(ev.benchmark_set)
        model = ev.model

    if not benchmarks:
        with SyncSessionLocal() as db:
            ev = db.get(Evaluation, uuid.UUID(evaluation_id))
            ev.status = EvaluationStatus.FAILED
            ev.finished_at = datetime.now(UTC)
            db.commit()
        return {"error": "no benchmarks found", "benchmark_set": ev.benchmark_set}

    results: list[dict] = []
    for bench in benchmarks:
        started = time.perf_counter()
        try:
            row = _run_one(evaluation_id, bench, model)
        except Exception as exc:  # noqa: BLE001
            log.exception("benchmark_crash", benchmark=bench.id)
            row = {
                "benchmark_id": bench.id,
                "passed": False,
                "build_ok": False,
                "lint_ok": False,
                "tests_ok": False,
                "security_ok": False,
                "regression": False,
                "repair_iterations": 0,
                "tool_failures": 0,
                "judge_score": None,
                "detail": {"error": str(exc)[:500]},
            }
        row["latency_s"] = round(time.perf_counter() - started, 2)
        results.append(row)
        _persist_result(evaluation_id, row)

    return _aggregate(evaluation_id, results)


# ── one benchmark ─────────────────────────────────────────────────────────────
def _run_one(evaluation_id: str, bench: Benchmark, model: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"cp-bench-{bench.id}-"))
    origin = tmp / "origin"
    try:
        _init_git_repo(bench.repo_dir, origin)

        with SyncSessionLocal() as db:
            user = _eval_user(db)
            repo = Repository(
                user_id=user.id,
                github_repo_id=abs(hash(bench.id)) % 1_000_000,
                full_name=f"benchmarks/{bench.id}",
                default_branch="main",
                private=True,
                clone_url=str(origin),
            )
            db.add(repo)
            db.flush()
            head = subprocess.run(  # noqa: S603
                ["git", "rev-parse", "HEAD"], cwd=origin, capture_output=True, text=True
            ).stdout.strip()
            version = RepositoryVersion(
                repository_id=repo.id, branch="main", commit_sha=head, status=IndexStatus.PENDING
            )
            db.add(version)
            db.flush()
            task = Task(
                user_id=user.id,
                repository_id=repo.id,
                repository_version_id=version.id,
                branch="main",
                title=f"[eval] {bench.id}",
                description=bench.task,
                autonomy=AutonomyLevel(bench.autonomy),
                model=model,
                max_iterations=bench.max_iterations,
                run_evaluation=False,
                auto_create_pr=False,
                status=TaskStatus.QUEUED,
            )
            db.add(task)
            db.flush()
            run = AgentRun(
                task_id=task.id,
                status=RunStatus.RUNNING,
                autonomy=task.autonomy,
                model=model,
                correlation_id=f"eval-{bench.id}-{str(run_uuid := uuid.uuid4())[:8]}",
            )
            run.id = run_uuid
            db.add(run)
            db.commit()
            task_id, run_id, version_id = str(task.id), str(run.id), str(version.id)

        index_repository_version(version_id)
        asyncio.run(Orchestrator(task_id, run_id).run())

        with SyncSessionLocal() as db:
            run = db.get(AgentRun, uuid.UUID(run_id))
            changes = db.query(FileChange).filter_by(agent_run_id=run.id).all()
            high_sec = (
                db.query(SecurityFinding)
                .filter(
                    SecurityFinding.agent_run_id == run.id,
                    SecurityFinding.severity.in_([Severity.HIGH, Severity.CRITICAL]),
                )
                .count()
            )
            workspace = Path(run.workspace_path) if run.workspace_path else None
            repair_iters = _extract_repair_iters(db, run.id)
            run_cost = float(run.total_cost_usd)
            run_status = run.status.value

        gates = _grade(bench, workspace)
        invariants_ok, invariant_detail = _check_invariants(bench, workspace, changes)
        judge = _judge(bench, workspace, model)

        criteria = bench.criteria
        passed = (
            run_status == "succeeded"
            and (gates["build_ok"] or criteria.get("build_ok") != "required")
            and (gates["lint_ok"] or criteria.get("lint_ok") != "required")
            and (gates["hidden_tests_ok"] or criteria.get("hidden_tests_pass") != "required")
            and (gates["regression_ok"] or criteria.get("regression_suite_pass") != "required")
            and (high_sec == 0 or criteria.get("no_new_high_security") != "required")
            and invariants_ok
        )
        return {
            "benchmark_id": bench.id,
            "passed": bool(passed),
            "build_ok": gates["build_ok"],
            "lint_ok": gates["lint_ok"],
            "tests_ok": gates["hidden_tests_ok"] and gates["regression_ok"],
            "security_ok": high_sec == 0,
            "regression": not gates["regression_ok"],
            "repair_iterations": repair_iters,
            "tool_failures": 0,
            "judge_score": judge,
            "cost_usd": run_cost,
            "detail": {
                "run_status": run_status,
                "changed_files": [c.path for c in changes],
                "gates": gates,
                "invariants": invariant_detail,
                "high_security_findings": high_sec,
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── helpers ───────────────────────────────────────────────────────────────────
def _init_git_repo(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest)
    env = {
        "GIT_AUTHOR_NAME": "bench",
        "GIT_AUTHOR_EMAIL": "bench@codepilot.local",
        "GIT_COMMITTER_NAME": "bench",
        "GIT_COMMITTER_EMAIL": "bench@codepilot.local",
    }
    for args in (
        ["init", "-b", "main"],
        ["add", "-A"],
        ["commit", "-m", "benchmark: initial state"],
    ):
        subprocess.run(
            ["git", *args], cwd=dest, check=True, capture_output=True, env={**env, "PATH": _path()}
        )  # noqa: S603


def _path() -> str:
    import os

    return os.environ.get("PATH", "")


def _eval_user(db) -> User:  # noqa: ANN001
    from sqlalchemy import select

    u = db.scalar(select(User).where(User.github_user_id == _EVAL_USER_GH_ID))
    if u is None:
        u = User(github_user_id=_EVAL_USER_GH_ID, login="evaluation", name="Evaluation Harness")
        db.add(u)
        db.flush()
    return u


def _sandbox_or_none(language: str) -> SandboxRunner | None:
    try:
        return SandboxRunner(SandboxConfig.for_language(language))
    except SandboxError:
        return None


def _grade(bench: Benchmark, workspace: Path | None) -> dict:
    out = {"build_ok": False, "lint_ok": False, "hidden_tests_ok": False, "regression_ok": False}
    if workspace is None or not workspace.exists():
        return out
    runner = _sandbox_or_none("python")
    if runner is None:
        out["_note"] = "sandbox unavailable — gates skipped (blocked)"
        return out

    graded = workspace
    if bench.hidden_tests_dir.exists():
        dest = workspace / "_hidden_tests"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(bench.hidden_tests_dir, dest)

    def _run(cmd: list[str]) -> int:
        try:
            return runner.run(
                workspace_dir=graded, command=cmd, language="python", timeout_s=120
            ).exit_code
        except SandboxError:
            return 1

    out["build_ok"] = (
        _run(
            [
                "python",
                "-c",
                "import compileall,sys; sys.exit(0 if compileall.compile_dir('.', quiet=1) else 1)",
            ]
        )
        == 0
    )
    out["lint_ok"] = (
        _run(["ruff", "check", "."]) == 0 or _run(["python", "-m", "pyflakes", "."]) == 0
    )
    out["regression_ok"] = (
        _run(["pytest", "-q", "--deselect", "_hidden_tests"]) == 0
        if (workspace / "tests").exists()
        else True
    )
    out["hidden_tests_ok"] = (
        _run(["pytest", "-q", "_hidden_tests"]) == 0 if bench.hidden_tests_dir.exists() else True
    )
    return out


def _check_invariants(bench: Benchmark, workspace: Path | None, changes) -> tuple[bool, dict]:  # noqa: ANN001
    inv = bench.invariants or {}
    detail: dict = {}
    ok = True
    changed = {c.path for c in changes}
    for path in inv.get("files_changed", []):
        hit = path in changed
        detail[f"files_changed:{path}"] = hit
        ok = ok and hit
    for path in inv.get("files_not_changed", []):
        hit = path not in changed
        detail[f"files_not_changed:{path}"] = hit
        ok = ok and hit
    if workspace:
        for spec in inv.get("file_contains", []):
            p = workspace / spec["path"]
            hit = p.exists() and spec["text"] in p.read_text("utf-8", errors="ignore")
            detail[f"file_contains:{spec['path']}"] = hit
            ok = ok and hit
    return ok, detail


def _judge(bench: Benchmark, workspace: Path | None, model: str) -> int | None:
    if not bench.rubric or workspace is None:
        return None
    try:
        from worker.git_ops import _run as git_run

        diff = git_run(["diff", "HEAD~1", "HEAD"], cwd=workspace)[:12000]
    except Exception:  # noqa: BLE001
        return None
    try:
        from worker.llm import get_llm
        from worker.llm.base import LLMMessage
        from worker.prompts import get_prompt

        prompt = get_prompt("judge")
        res = asyncio.run(
            get_llm().complete(
                model=model,
                system=prompt.render_system(),
                messages=[
                    LLMMessage(
                        role="user",
                        content=f"# Rubric\n{bench.rubric}\n\n# Diff\n{diff}\n\nScore 0-100 then justify.",
                    )
                ],
                max_tokens=400,
            )
        )
        import re

        m = re.search(r"\b(\d{1,3})\b", res.text)
        return max(0, min(100, int(m.group(1)))) if m else None
    except Exception:  # noqa: BLE001
        return None


def _extract_repair_iters(db, run_id) -> int:  # noqa: ANN001
    from app.models.run import TestRun

    phases = db.query(TestRun.phase).filter(TestRun.agent_run_id == run_id).all()
    return sum(1 for (p,) in phases if p.startswith("repair_"))


def _persist_result(evaluation_id: str, row: dict) -> None:
    with SyncSessionLocal() as db:
        db.add(
            EvaluationResult(
                evaluation_id=uuid.UUID(evaluation_id),
                benchmark_id=row["benchmark_id"],
                passed=row["passed"],
                build_ok=row["build_ok"],
                lint_ok=row["lint_ok"],
                tests_ok=row["tests_ok"],
                security_ok=row["security_ok"],
                regression=row["regression"],
                repair_iterations=row["repair_iterations"],
                tool_failures=row["tool_failures"],
                latency_s=row.get("latency_s", 0),
                cost_usd=row.get("cost_usd", 0),
                judge_score=row.get("judge_score"),
                detail_json=row.get("detail", {}),
            )
        )
        db.commit()


def _aggregate(evaluation_id: str, results: list[dict]) -> dict:
    n = len(results) or 1
    with SyncSessionLocal() as db:
        ev = db.get(Evaluation, uuid.UUID(evaluation_id))
        ev.task_success_rate = sum(r["passed"] for r in results) / n
        ev.test_pass_rate = sum(r["tests_ok"] for r in results) / n
        ev.regression_rate = sum(r["regression"] for r in results) / n
        ev.security_violation_rate = sum(not r["security_ok"] for r in results) / n
        ev.avg_latency_s = sum(r.get("latency_s", 0) for r in results) / n
        ev.avg_cost_usd = sum(r.get("cost_usd", 0) for r in results) / n
        ev.status = EvaluationStatus.COMPLETED
        ev.finished_at = datetime.now(UTC)

        if ev.baseline_evaluation_id:
            base = db.get(Evaluation, ev.baseline_evaluation_id)
            if base:
                ev.has_regression = _is_regression(base, ev)
        db.commit()
        summary = {
            "task_success_rate": float(ev.task_success_rate),
            "test_pass_rate": float(ev.test_pass_rate),
            "regression_rate": float(ev.regression_rate),
            "security_violation_rate": float(ev.security_violation_rate),
            "has_regression": ev.has_regression,
            "benchmarks": n,
        }
    return summary


def _is_regression(base: Evaluation, cur: Evaluation) -> bool:
    def f(x) -> float:  # noqa: ANN001
        return float(x or 0)

    return (
        f(cur.task_success_rate) < f(base.task_success_rate) - 0.02
        or f(cur.test_pass_rate) < f(base.test_pass_rate) - 0.02
        or f(cur.security_violation_rate) > f(base.security_violation_rate) + 0.001
        or f(cur.avg_latency_s) > f(base.avg_latency_s) * 1.5
        or f(cur.avg_cost_usd) > f(base.avg_cost_usd) * 1.5
    )
