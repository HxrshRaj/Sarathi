"""Import all models so Alembic autogenerate and SQLAlchemy mappers see them."""

from app.models.base import Base
from app.models.code import CodeChunk, CodeFile
from app.models.evaluation import Evaluation, EvaluationResult
from app.models.pr import PullRequest
from app.models.repository import Repository, RepositoryVersion
from app.models.run import (
    AgentRun,
    AgentStep,
    FileChange,
    Review,
    SecurityFinding,
    TestRun,
    ToolCall,
)
from app.models.task import Task
from app.models.telemetry import AuditLog, ModelUsage, PromptVersion
from app.models.user import GithubIdentity, Session, User

__all__ = [
    "Base",
    "User",
    "GithubIdentity",
    "Session",
    "Repository",
    "RepositoryVersion",
    "CodeFile",
    "CodeChunk",
    "Task",
    "AgentRun",
    "AgentStep",
    "ToolCall",
    "FileChange",
    "TestRun",
    "SecurityFinding",
    "Review",
    "Evaluation",
    "EvaluationResult",
    "PullRequest",
    "ModelUsage",
    "PromptVersion",
    "AuditLog",
]
