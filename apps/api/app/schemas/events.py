"""Run-event contract. Shared by worker (producer), API SSE relay, and the web UI.

The TypeScript mirror lives in packages/shared/src/events.ts and is kept honest by
tests/integration/test_event_schema_compat.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "run.started",
    "run.finished",
    "run.failed",
    "run.cancelled",
    "step.started",
    "step.progress",
    "step.finished",
    "tool.called",
    "tool.result",
    "file.changed",
    "test.run",
    "security.finding",
    "review.completed",
    "budget.update",
    "awaiting_approval",
]


class RunEvent(BaseModel):
    id: str = Field(description="monotonic per-run id; usable as SSE Last-Event-ID")
    run_id: uuid.UUID
    task_id: uuid.UUID
    type: EventType
    at: datetime
    # step context (present for step.* / tool.* / file.* events)
    agent: str | None = None
    step_seq: int | None = None
    # free-form, event-type-specific, already redacted of secrets by the producer
    data: dict[str, Any] = {}
