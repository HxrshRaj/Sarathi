"""Enums shared by models and API schemas. Values are the DB-native enum labels."""

from __future__ import annotations

from enum import StrEnum


class AutonomyLevel(StrEnum):
    ASSIST = "assist"  # L1 — suggest only
    SUPERVISED = "supervised"  # L2 — modify workspace + run checks, approval to push
    CONTROLLED = "controlled"  # L3 — may auto-open PR, still no merge/force/secrets


class IndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentName(StrEnum):
    REPO_ANALYZER = "repo_analyzer"
    PLANNER = "planner"
    RETRIEVER = "retriever"
    CODER = "coder"
    TESTER = "tester"
    DEBUGGER = "debugger"
    SECURITY = "security"
    REVIEWER = "reviewer"
    EVALUATION = "evaluation"


class StepStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChangeType(StrEnum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class ChunkKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"
    BLOCK = "block"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecuritySource(StrEnum):
    GITLEAKS = "gitleaks"
    DETECT_SECRETS = "detect_secrets"
    BANDIT = "bandit"
    SEMGREP = "semgrep"
    PIP_AUDIT = "pip_audit"
    NPM_AUDIT = "npm_audit"
    AI_REVIEW = "ai_review"


class PRState(StrEnum):
    DRAFT = "draft"
    CREATING = "creating"
    OPEN = "open"
    FAILED = "failed"


class EvaluationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
