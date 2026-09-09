"""Task orchestrator — the agent state machine.

queued → analyzing → planning → retrieving → [coding → applying → testing ⇄
debugging(≤N) → security → reviewing] → awaiting_approval | completed | failed.

Between every step: budget check, cancellation check, agent_steps write, event
emit. The whole run is reconstructable from agent_steps + tool_calls +
file_changes + test_runs + security_findings + model_usage.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.db import SyncSessionLocal
from app.logging import get_logger
from app.models.enums import (
    AgentName,
    AutonomyLevel,
    ChangeType,
    IndexStatus,
    RunStatus,
    SecuritySource,
    Severity,
    StepStatus,
    TaskStatus,
)
from app.models.repository import Repository, RepositoryVersion
from app.models.run import (
    AgentRun,
    AgentStep,
    FileChange,
    Review,
    SecurityFinding,
    TestRun,
)
from app.models.task import Task
from app.models.user import GithubIdentity
from app.security.crypto import decrypt
from sqlalchemy.orm import Session

from worker.agents import (
    coder,
    debugger,
    planner,
    repo_analyzer,
    retriever,
    reviewer,
    security,
    tester,
)
from worker.agents.base import AgentError
from worker.git_ops import clone_at, init_work_branch
from worker.git_ops import commit as git_commit
from worker.llm import get_llm
from worker.runtime.budget import BudgetExceeded, Cancelled, RunBudget
from worker.runtime.context import RunContext
from worker.runtime.events import EventEmitter
from worker.runtime.schemas import RepoAnalysis
from worker.runtime.toolset import Toolset, build_toolset

log = get_logger("orchestrator")

_STEP_ORDER = [
    AgentName.REPO_ANALYZER,
    AgentName.PLANNER,
    AgentName.RETRIEVER,
    AgentName.CODER,
    AgentName.TESTER,
    AgentName.SECURITY,
    AgentName.REVIEWER,
]


class Orchestrator:
    def __init__(self, task_id: str, run_id: str) -> None:
        self.task_id = uuid.UUID(task_id)
        self.run_id = uuid.UUID(run_id)
        self.settings = get_settings()
        self._seq = 0

    # ── public entrypoint ───────────────────────────────────────────────────
    async def run(self) -> None:
        db = SyncSessionLocal()
        try:
            await self._run(db)
        finally:
            db.close()

    async def _run(self, db: Session) -> None:
        run = db.get(AgentRun, self.run_id)
        task = db.get(Task, self.task_id)
        assert run and task
        emitter = EventEmitter(str(self.run_id), str(self.task_id))

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        task.status = TaskStatus.RUNNING
        db.commit()
        emitter.emit("run.started", {"task_title": task.title, "autonomy": task.autonomy.value})

        try:
            workspace, repo_version_id = self._prepare_workspace(db, task, run)
            budget = RunBudget(
                max_tokens=self.settings.max_tokens,
                max_cost_usd=min(
                    self.settings.max_cost_usd, float(task.max_iterations) * 1.0 + 2.0
                ),
                max_iterations=max(self.settings.max_iterations, task.max_iterations * 4),
                max_runtime_s=self.settings.max_runtime_s,
                model=task.model,
            )
            ctx = RunContext(
                db=db,
                run_id=self.run_id,
                task_id=self.task_id,
                correlation_id=run.correlation_id,
                workspace=workspace,
                repo_version_id=repo_version_id,
                llm=get_llm(),
                model=task.model,
                budget=budget,
                emitter=emitter,
                autonomy=task.autonomy.value,
                task_description=task.description,
            )

            analysis = await self._step(ctx, AgentName.REPO_ANALYZER, self._analyze)
            plan = await self._step(ctx, AgentName.PLANNER, lambda c: self._plan(c, analysis))
            bundle = await self._step(ctx, AgentName.RETRIEVER, lambda c: self._retrieve(c, plan))

            if task.autonomy == AutonomyLevel.ASSIST:
                self._finalize_assist(db, run, task, plan, bundle, emitter)
                return

            allow_mut = True
            toolset = build_toolset(ctx, analysis, allow_mutations=allow_mut)

            coder_out = await self._step(
                ctx, AgentName.CODER, lambda c: self._code(c, plan, bundle, toolset)
            )
            await self._step(
                ctx, AgentName.TESTER, lambda c: self._test(c, plan, coder_out, toolset)
            )
            self._persist_changes(db, toolset)

            test_summary, gates_ok = await self._testing_phase(ctx, toolset)
            findings = await self._step(
                ctx, AgentName.SECURITY, lambda c: self._security(c, toolset)
            )
            self._persist_findings(db, findings)

            review, review_meta = await self._step(
                ctx,
                AgentName.REVIEWER,
                lambda c: self._review(c, toolset, test_summary, findings, gates_ok),
            )
            self._persist_review(db, review, review_meta)
            self._commit_workspace(db, task, workspace)
            self._finalize_success(db, run, task, review, review_meta, coder_out, emitter)

        except (AgentError, BudgetExceeded, Cancelled) as exc:
            self._finalize_failure(db, run, task, exc, emitter)
        except Exception as exc:  # noqa: BLE001
            log.exception("orchestrator_crash", run_id=str(self.run_id))
            self._finalize_failure(db, run, task, exc, emitter)

    # ── workspace ───────────────────────────────────────────────────────────
    def _prepare_workspace(
        self, db: Session, task: Task, run: AgentRun
    ) -> tuple[Path, uuid.UUID | None]:
        repo = db.get(Repository, task.repository_id)
        assert repo
        identity = db.query(GithubIdentity).filter_by(user_id=repo.user_id).one_or_none()
        token = decrypt(identity.access_token_encrypted) if identity else None

        version = None
        if task.repository_version_id:
            version = db.get(RepositoryVersion, task.repository_version_id)
        if version is None:
            version = (
                db.query(RepositoryVersion)
                .filter_by(repository_id=repo.id, branch=task.branch, status=IndexStatus.READY)
                .order_by(RepositoryVersion.created_at.desc())
                .first()
            )
        ref = version.commit_sha if version else task.branch

        root = Path(self.settings.run_workspace_root) / str(self.run_id)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        repo_dir = root / "repo"
        clone_at(repo.clone_url, repo_dir, ref=ref, token=token)
        init_work_branch(repo_dir, f"sarathi/run-{str(self.run_id)[:8]}")

        run.workspace_path = str(repo_dir)
        db.commit()
        return repo_dir, (version.id if version and version.status == IndexStatus.READY else None)

    def _commit_workspace(self, db: Session, task: Task, workspace: Path) -> None:
        try:
            from worker.git_ops import stage_all

            stage_all(workspace)
            sha = git_commit(
                workspace,
                f"Sarathi: {task.title}",
                author_name="Sarathi Runner",
                author_email="runner@sarathi.local",
            )
            log.info("workspace_committed", sha=sha)
        except Exception as exc:  # noqa: BLE001 - nothing to commit is fine
            log.info("workspace_commit_skipped", reason=str(exc)[:200])

    # ── step wrapper ────────────────────────────────────────────────────────
    async def _step(self, ctx: RunContext, agent: AgentName, fn):  # noqa: ANN001
        ctx.budget.check()
        if ctx.emitter.cancelled():
            raise Cancelled(f"cancelled before {agent.value}")
        self._seq += 1
        seq = self._seq
        step = AgentStep(
            agent_run_id=self.run_id,
            seq=seq,
            agent=agent,
            status=StepStatus.RUNNING,
            started_at=datetime.now(UTC),
            input_json={},
            prompt_version=None,
        )
        ctx.db.add(step)
        ctx.db.flush()
        ctx._current_step_id = step.id
        ctx.emitter.emit("step.started", {"agent": agent.value}, agent=agent.value, step_seq=seq)
        try:
            result = await fn(ctx)
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = f"{type(exc).__name__}: {exc}"
            step.finished_at = datetime.now(UTC)
            ctx.db.commit()
            ctx.emitter.emit(
                "step.finished",
                {"agent": agent.value, "status": "failed", "error": step.error},
                agent=agent.value,
                step_seq=seq,
            )
            raise
        step.status = StepStatus.SUCCEEDED
        step.finished_at = datetime.now(UTC)
        step.output_json = _jsonable(result)
        ctx.db.commit()
        ctx.emitter.emit(
            "step.finished",
            {"agent": agent.value, "status": "succeeded", "budget": ctx.budget.snapshot()},
            agent=agent.value,
            step_seq=seq,
        )
        ctx._current_step_id = None
        return result

    # ── step bodies ─────────────────────────────────────────────────────────
    async def _analyze(self, ctx: RunContext) -> RepoAnalysis:
        analysis = await repo_analyzer.analyze(ctx)
        ctx.analysis = analysis.model_dump()
        return analysis

    async def _plan(self, ctx: RunContext, analysis: RepoAnalysis):
        return await planner.make_plan(ctx, analysis)

    async def _retrieve(self, ctx: RunContext, plan):  # noqa: ANN001
        return await retriever.retrieve_for_plan(ctx, plan)

    async def _code(self, ctx: RunContext, plan, bundle, toolset: Toolset):  # noqa: ANN001
        return await coder.implement(ctx, plan, bundle.context_block, toolset)

    async def _test(self, ctx: RunContext, plan, coder_out, toolset: Toolset):  # noqa: ANN001
        return await tester.author_tests(ctx, plan, coder_out.final_text, toolset)

    async def _security(self, ctx: RunContext, toolset: Toolset) -> list[dict]:
        diff = _diff(toolset)
        return await security.review_security(ctx, diff, toolset)

    async def _review(self, ctx: RunContext, toolset, test_summary, findings, gates_ok):  # noqa: ANN001
        return await reviewer.review_change(
            ctx,
            diff=_diff(toolset),
            test_summary=test_summary,
            security_findings=findings,
            deterministic_gates_pass=gates_ok,
        )

    # ── testing + repair loop ───────────────────────────────────────────────
    async def _testing_phase(self, ctx: RunContext, toolset: Toolset) -> tuple[dict, bool]:
        self._seq += 1
        seq = self._seq
        step = AgentStep(
            agent_run_id=self.run_id,
            seq=seq,
            agent=AgentName.DEBUGGER,
            status=StepStatus.RUNNING,
            started_at=datetime.now(UTC),
            input_json={},
        )
        ctx.db.add(step)
        ctx.db.flush()
        ctx._current_step_id = step.id
        ctx.emitter.emit("step.started", {"agent": "testing"}, agent="tester", step_seq=seq)

        max_repairs = min(self.settings.max_repair_iterations, 3)
        phase = "post_change"
        summary: dict = {}
        gates_ok = False

        for iteration in range(max_repairs + 1):
            if not toolset.registry.has("run_tests"):
                summary = {"blocked": True, "reason": "no test command"}
                break
            res = toolset.registry.invoke("run_tests", {})
            data = res.data
            self._record_test_run(ctx.db, phase, data)
            ctx.emitter.emit(
                "test.run",
                {
                    "phase": phase,
                    "exit_code": data.get("exit_code"),
                    "passed": data.get("passed"),
                    "failed": data.get("failed"),
                    "blocked": data.get("blocked", False),
                },
                agent="tester",
                step_seq=seq,
            )
            if data.get("blocked"):
                summary = {"blocked": True, "reason": res.error}
                break
            summary = {
                "exit_code": data.get("exit_code"),
                "passed": data.get("passed", 0),
                "failed": data.get("failed", 0),
                "errors": data.get("errors", 0),
                "iterations": iteration,
            }
            if data.get("exit_code") == 0:
                gates_ok = True
                break
            if iteration >= max_repairs:
                summary["gave_up"] = True
                break
            ctx.emitter.emit(
                "step.progress", {"repair_iteration": iteration + 1}, agent="debugger", step_seq=seq
            )
            await debugger.attempt_fix(ctx, data, _diff(toolset), toolset, iteration + 1)
            self._persist_changes(ctx.db, toolset)
            phase = f"repair_{iteration + 1}"

        step.status = StepStatus.SUCCEEDED if gates_ok else StepStatus.FAILED
        step.finished_at = datetime.now(UTC)
        step.output_json = summary
        ctx.db.commit()
        ctx.emitter.emit(
            "step.finished",
            {"agent": "testing", "status": step.status.value, "summary": summary},
            agent="tester",
            step_seq=seq,
        )
        ctx._current_step_id = None
        return summary, gates_ok

    # ── persistence helpers ─────────────────────────────────────────────────
    def _persist_changes(self, db: Session, toolset: Toolset) -> None:
        db.query(FileChange).filter_by(agent_run_id=self.run_id).delete()
        for rec in toolset.fs.changes.values():
            db.add(
                FileChange(
                    agent_run_id=self.run_id,
                    path=rec.path,
                    change_type=ChangeType(rec.change_type),
                    before_content=rec.before_content,
                    after_content=rec.after_content,
                    diff=rec.diff,
                    lines_added=rec.lines_added,
                    lines_removed=rec.lines_removed,
                    applied=True,
                )
            )
        db.commit()

    def _record_test_run(self, db: Session, phase: str, data: dict) -> None:
        db.add(
            TestRun(
                agent_run_id=self.run_id,
                phase=phase,
                command=" ".join(data.get("command", []) or []),
                framework=data.get("framework"),
                exit_code=int(data.get("exit_code", 0) or 0),
                passed=int(data.get("passed", 0) or 0),
                failed=int(data.get("failed", 0) or 0),
                errors=int(data.get("errors", 0) or 0),
                duration_ms=int(data.get("duration_ms", 0) or 0),
                stdout=(data.get("stdout") or "")[:20000],
                stderr=(data.get("stderr") or "")[:20000],
            )
        )
        db.commit()

    def _persist_findings(self, db: Session, findings: list[dict]) -> None:
        db.query(SecurityFinding).filter_by(agent_run_id=self.run_id).delete()
        for f in findings:
            db.add(
                SecurityFinding(
                    agent_run_id=self.run_id,
                    source=SecuritySource(f["source"]),
                    severity=Severity(f["severity"]),
                    rule_id=f.get("rule_id"),
                    path=f.get("path"),
                    line=f.get("line"),
                    message=f["message"][:2000],
                    deterministic=f.get("deterministic", True),
                )
            )
        db.commit()

    def _persist_review(self, db: Session, review, meta: dict) -> None:  # noqa: ANN001
        db.query(Review).filter_by(agent_run_id=self.run_id).delete()
        db.add(
            Review(
                agent_run_id=self.run_id,
                overall_score=review.overall_score,
                correctness=review.correctness,
                security=review.security,
                maintainability=review.maintainability,
                testing=review.testing,
                performance=review.performance,
                blocking_issues=review.blocking_issues,
                warnings=review.warnings,
                suggestions=review.suggestions,
                production_ready=meta["production_ready"],
                escalated_to_human=meta["escalated_to_human"],
                escalation_reason=meta["escalation_reason"],
            )
        )
        db.commit()

    # ── finalizers ──────────────────────────────────────────────────────────
    def _finalize_assist(self, db, run, task, plan, bundle, emitter) -> None:  # noqa: ANN001
        run.status = RunStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.confidence = "medium"
        run.summary = f"Assist mode: produced a plan ({len(plan.implementation_plan)} steps) and retrieved context. No files were modified."
        run.total_input_tokens = run.total_input_tokens
        task.status = TaskStatus.AWAITING_APPROVAL
        db.commit()
        self._sync_run_totals(db)
        emitter.emit(
            "run.finished", {"mode": "assist", "plan_steps": len(plan.implementation_plan)}
        )

    def _finalize_success(self, db, run, task, review, meta, coder_out, emitter) -> None:  # noqa: ANN001
        has_changes = db.query(FileChange).filter_by(agent_run_id=self.run_id).count() > 0
        run.status = RunStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.confidence = review.confidence
        run.summary = coder_out.final_text[:2000] if has_changes else "No changes were required."
        self._sync_run_totals(db)

        if not has_changes:
            task.status = TaskStatus.COMPLETED
        elif (
            task.autonomy == AutonomyLevel.CONTROLLED
            and task.auto_create_pr
            and meta["production_ready"]
        ):
            task.status = (
                TaskStatus.AWAITING_APPROVAL
            )  # PR creation still recorded via approve/dispatch
        else:
            task.status = TaskStatus.AWAITING_APPROVAL
        db.commit()

        emitter.emit(
            "review.completed",
            {
                "overall_score": review.overall_score,
                "production_ready": meta["production_ready"],
                "escalated_to_human": meta["escalated_to_human"],
                "reason": meta["escalation_reason"],
            },
        )
        emitter.emit(
            "awaiting_approval" if task.status == TaskStatus.AWAITING_APPROVAL else "run.finished",
            {"confidence": review.confidence},
        )
        emitter.emit("run.finished", {"status": "succeeded"})

    def _finalize_failure(self, db, run, task, exc, emitter) -> None:  # noqa: ANN001
        category = getattr(exc, "category", None) or (
            "limit_exceeded"
            if isinstance(exc, BudgetExceeded)
            else "cancelled"
            if isinstance(exc, Cancelled)
            else "agent"
        )
        run.status = RunStatus.CANCELLED if isinstance(exc, Cancelled) else RunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_category = category
        run.error_message = str(exc)[:2000]
        self._sync_run_totals(db)
        task.status = TaskStatus.CANCELLED if isinstance(exc, Cancelled) else TaskStatus.FAILED
        db.commit()
        emitter.emit(
            "run.cancelled" if isinstance(exc, Cancelled) else "run.failed",
            {"category": category, "message": str(exc)[:500]},
        )

    def _sync_run_totals(self, db: Session) -> None:
        from app.models.telemetry import ModelUsage
        from sqlalchemy import func

        run = db.get(AgentRun, self.run_id)
        row = (
            db.query(
                func.coalesce(func.sum(ModelUsage.input_tokens), 0),
                func.coalesce(func.sum(ModelUsage.output_tokens), 0),
            )
            .filter(ModelUsage.agent_run_id == self.run_id)
            .one()
        )
        run.total_input_tokens, run.total_output_tokens = int(row[0]), int(row[1])
        from worker.llm.base import Usage
        from worker.llm.pricing import estimate_cost

        run.total_cost_usd = estimate_cost(run.model, Usage(int(row[0]), int(row[1])))
        db.commit()


def _diff(toolset: Toolset) -> str:
    return "\n".join(rec.diff for rec in toolset.fs.changes.values())


def _jsonable(obj) -> dict:  # noqa: ANN001
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}
