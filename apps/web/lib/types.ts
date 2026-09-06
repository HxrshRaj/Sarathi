// Hand-maintained mirror of the API's response models. Kept small on purpose.
// The wire contract for run events also lives in packages/shared/src/events.ts.

export type Autonomy = "assist" | "supervised" | "controlled";
export type TaskStatus =
  | "draft"
  | "queued"
  | "running"
  | "awaiting_approval"
  | "approved"
  | "completed"
  | "failed"
  | "cancelled";
export type RunStatus = "running" | "succeeded" | "failed" | "cancelled";
export type IndexStatus = "pending" | "indexing" | "ready" | "failed";

export interface Me {
  id: string;
  login: string;
  name: string | null;
  avatar_url: string | null;
  default_autonomy: Autonomy;
  csrf_token: string;
  auth_mode: "github" | "dev";
}

export interface RepositoryVersion {
  id: string;
  branch: string;
  commit_sha: string;
  status: IndexStatus;
  file_count: number;
  chunk_count: number;
  index_error: string | null;
  indexed_at: string | null;
  created_at: string;
}

export interface Repository {
  id: string;
  github_repo_id: number;
  full_name: string;
  default_branch: string;
  private: boolean;
  created_at: string;
  latest_version: RepositoryVersion | null;
}

export interface RunSummary {
  id: string;
  status: RunStatus;
  confidence: string | null;
  summary: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  error_category: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface Task {
  id: string;
  repository_id: string;
  branch: string;
  title: string;
  description: string;
  autonomy: Autonomy;
  model: string;
  max_iterations: number;
  run_evaluation: boolean;
  auto_create_pr: boolean;
  status: TaskStatus;
  created_at: string;
  latest_run: RunSummary | null;
}

export interface FileChange {
  path: string;
  change_type: "create" | "modify" | "delete";
  diff: string;
  before_content: string | null;
  after_content: string | null;
  lines_added: number;
  lines_removed: number;
  applied: boolean;
}

export interface DiffResponse {
  run_id: string;
  files: FileChange[];
  total_added: number;
  total_removed: number;
}

export interface RunEvent {
  id: string;
  run_id: string;
  task_id: string;
  type: string;
  at: string;
  agent: string | null;
  step_seq: number | null;
  data: Record<string, unknown>;
}

export interface Dashboard {
  window_days: number;
  totals: { tasks: number; active_tasks: number; finished_runs: number };
  task_success_rate: number | null;
  avg_latency_s: number | null;
  avg_cost_usd: number | null;
  security_findings_high: number;
  enough_data: boolean;
}

export interface EvaluationResult {
  benchmark_id: string;
  passed: boolean;
  build_ok: boolean;
  lint_ok: boolean;
  tests_ok: boolean;
  security_ok: boolean;
  regression: boolean;
  repair_iterations: number;
  latency_s: number;
  cost_usd: number;
  judge_score: number | null;
}

export interface Evaluation {
  id: string;
  benchmark_set: string;
  model: string;
  status: string;
  task_success_rate: number | null;
  test_pass_rate: number | null;
  regression_rate: number | null;
  security_violation_rate: number | null;
  avg_latency_s: number | null;
  avg_cost_usd: number | null;
  has_regression: boolean;
  created_at: string;
  results: EvaluationResult[];
}
