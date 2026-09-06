// Wire contract for run events. MUST stay in sync with
// apps/api/app/schemas/events.py (RunEvent). tests/integration/test_event_schema_compat.py
// asserts the field names match.

export type RunEventType =
  | "run.started"
  | "run.finished"
  | "run.failed"
  | "run.cancelled"
  | "step.started"
  | "step.progress"
  | "step.finished"
  | "tool.called"
  | "tool.result"
  | "file.changed"
  | "test.run"
  | "security.finding"
  | "review.completed"
  | "budget.update"
  | "awaiting_approval";

export interface RunEvent {
  id: string;
  run_id: string;
  task_id: string;
  type: RunEventType;
  at: string;
  agent: string | null;
  step_seq: number | null;
  data: Record<string, unknown>;
}

export const RUN_EVENT_FIELDS = [
  "id",
  "run_id",
  "task_id",
  "type",
  "at",
  "agent",
  "step_seq",
  "data",
] as const;
