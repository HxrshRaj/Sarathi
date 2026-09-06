from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.db import SyncSessionLocal
from app.logging import correlation_id_var, get_logger
from app.models.enums import PRState, TaskStatus
from app.models.pr import PullRequest
from app.models.repository import Repository
from app.models.run import AgentRun, FileChange
from app.models.task import Task
from app.models.telemetry import AuditLog
from app.models.user import GithubIdentity
from app.security.crypto import decrypt
from app.services.github import GithubClient

from worker.celery_app import celery
from worker.codeintel.ingest import index_repository_version as _index_impl
from worker.git_ops import GitError, push_branch
from worker.llm import get_llm
from worker.llm.base import LLMMessage
from worker.prompts import get_prompt
from worker.runtime.schemas import PRArtifacts

log = get_logger("tasks")


@celery.task(name="worker.run_agent_task", bind=True, max_retries=0)
def run_agent_task(self, task_id: str, run_id: str) -> dict:  # noqa: ANN001, ARG001
    from worker.orchestrator import Orchestrator

    correlation_id_var.set(f"run-{run_id[:8]}")
    log.info("run_agent_task_start", task_id=task_id, run_id=run_id)
    asyncio.run(Orchestrator(task_id, run_id).run())
    with SyncSessionLocal() as db:
        run = db.get(AgentRun, uuid.UUID(run_id))
        return {"run_id": run_id, "status": run.status.value if run else "unknown"}


@celery.task(name="worker.index_repository_version", bind=True, max_retries=0)
def index_repository_version(self, repository_version_id: str) -> dict:  # noqa: ANN001, ARG001
    log.info("index_start", repository_version_id=repository_version_id)
    return _index_impl(repository_version_id)


@celery.task(name="worker.run_evaluation", bind=True, max_retries=0)
def run_evaluation(self, evaluation_id: str) -> dict:  # noqa: ANN001, ARG001
    from worker.evaluation.runner import run_evaluation as _run_eval

    log.info("evaluation_start", evaluation_id=evaluation_id)
    return _run_eval(evaluation_id)


@celery.task(name="worker.create_pull_request", bind=True, max_retries=0)
def create_pull_request(self, task_id: str, run_id: str) -> dict:  # noqa: ANN001, ARG001
    return asyncio.run(_create_pr(task_id, run_id))


async def _create_pr(task_id: str, run_id: str) -> dict:
    with SyncSessionLocal() as db:
        task = db.get(Task, uuid.UUID(task_id))
        run = db.get(AgentRun, uuid.UUID(run_id))
        assert task and run
        repo = db.get(Repository, task.repository_id)
        identity = db.query(GithubIdentity).filter_by(user_id=repo.user_id).one_or_none()
        if identity is None:
            raise RuntimeError("No GitHub identity to push with")
        token = decrypt(identity.access_token_encrypted)
        changes = db.query(FileChange).filter_by(agent_run_id=run.id).all()
        diff_stat = "\n".join(f"{c.path}  +{c.lines_added}/-{c.lines_removed}" for c in changes)
        full_diff = "\n".join(c.diff for c in changes)
        workspace = Path(run.workspace_path) if run.workspace_path else None

        prompt = get_prompt("pr_writer")
        artifacts, _usage = await get_llm().structured(
            model=task.model,
            system=prompt.render_system(),
            messages=[
                LLMMessage(
                    role="user",
                    content=f"# Task\n{task.description}\n\n# Diff stat\n{diff_stat}\n\n# Diff\n{full_diff[:12000]}",
                )
            ],
            output_model=PRArtifacts,
            max_tokens=prompt.model_config.get("max_tokens", 1500),
        )

        branch = (
            artifacts.branch_name
            if artifacts.branch_name.startswith("codepilot/")
            else f"codepilot/{artifacts.branch_name.strip('/')}"
        )

        pr_row = PullRequest(
            task_id=task.id,
            agent_run_id=run.id,
            branch=branch,
            base=task.branch,
            title=artifacts.pr_title,
            body=artifacts.pr_body,
            state=PRState.CREATING,
            commit_sha=None,
        )
        db.add(pr_row)
        db.add(
            AuditLog(
                user_id=repo.user_id,
                actor="worker",
                action="pr.create.start",
                target_type="task",
                target_id=str(task.id),
                correlation_id=run.correlation_id,
                metadata_json={"branch": branch},
            )
        )
        db.commit()

        try:
            if workspace and workspace.exists():
                from worker.git_ops import _run

                _run(["branch", "-M", branch], cwd=workspace)
                push_branch(workspace, repo.clone_url, branch, token)
            else:
                raise RuntimeError("run workspace no longer available to push")

            gh = GithubClient(token)
            pr = await gh.create_pull_request(
                repo.full_name,
                head=branch,
                base=task.branch,
                title=artifacts.pr_title,
                body=artifacts.pr_body,
                draft=False,
            )
            pr_row.github_pr_number = pr["number"]
            pr_row.github_pr_url = pr["html_url"]
            pr_row.state = PRState.OPEN
            task.status = TaskStatus.COMPLETED
            db.add(
                AuditLog(
                    user_id=repo.user_id,
                    actor="worker",
                    action="pr.create.ok",
                    target_type="pull_request",
                    target_id=str(pr_row.id),
                    correlation_id=run.correlation_id,
                    metadata_json={"url": pr["html_url"], "number": pr["number"]},
                )
            )
            db.commit()
            return {"pull_request_url": pr["html_url"], "number": pr["number"]}
        except (GitError, Exception) as exc:  # noqa: BLE001
            pr_row.state = PRState.FAILED
            pr_row.body = (pr_row.body or "") + f"\n\n<!-- push/create failed: {exc} -->"
            db.add(
                AuditLog(
                    user_id=repo.user_id,
                    actor="worker",
                    action="pr.create.fail",
                    target_type="task",
                    target_id=str(task.id),
                    correlation_id=run.correlation_id,
                    metadata_json={"error": str(exc)[:500]},
                )
            )
            db.commit()
            log.error("pr_create_failed", error=str(exc))
            raise


@celery.task(name="worker.gc_workspaces")
def gc_workspaces() -> dict:
    """Delete run workspaces older than WORKSPACE_TTL_H. Wire to celery-beat in prod."""
    from app.config import get_settings

    settings = get_settings()
    root = Path(settings.run_workspace_root)
    if not root.exists():
        return {"removed": 0}
    cutoff = datetime.now(UTC).timestamp() - settings.workspace_ttl_h * 3600
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                import shutil

                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return {"removed": removed}
