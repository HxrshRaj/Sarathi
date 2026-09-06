# Database schema

PostgreSQL 16 + `pgvector`. All tables `id uuid primary key default gen_random_uuid()`,
`created_at timestamptz not null default now()`, `updated_at` where mutated.
Managed by Alembic. Enums are Postgres native enums.

## Identity & repos

### users
| col | type | notes |
|---|---|---|
| github_user_id | bigint unique | from GitHub |
| login | text | |
| name | text null | |
| avatar_url | text null | |
| default_autonomy | autonomy_level | default `supervised` |
| monthly_cost_cap_usd | numeric(10,4) null | null = system default |

### github_identities
one row per user. `access_token_encrypted bytea` (Fernet), `scopes text[]`,
`token_expires_at timestamptz null`. Never serialized to any API response.

### sessions
`user_id fk`, `id` is the cookie value (opaque 256-bit), `expires_at`,
`revoked_at null`, `user_agent`, `ip inet`.

### repositories
| col | type | notes |
|---|---|---|
| user_id | fk users | owner (row-level authz key) |
| github_repo_id | bigint | |
| full_name | text | `owner/name` |
| default_branch | text | |
| private | bool | |
| clone_url | text | |
| unique (user_id, github_repo_id) | | |

### repository_versions
an indexed snapshot of a repo at a commit.
`repository_id fk`, `branch text`, `commit_sha text`, `status` (`pending`,
`indexing`, `ready`, `failed`), `file_count int`, `chunk_count int`,
`index_error text null`, `indexed_at timestamptz null`.
`unique (repository_id, commit_sha)`.

## Code intelligence

### code_files
`repository_version_id fk`, `path text`, `language text null`, `size_bytes int`,
`sha text`, `symbol_count int`. `unique (repository_version_id, path)`.

### code_chunks
| col | type | notes |
|---|---|---|
| repository_version_id | fk | denormalised for query speed |
| code_file_id | fk code_files | |
| symbol | text null | function/class/method name |
| kind | chunk_kind | `function`,`class`,`method`,`module`,`block` |
| start_line / end_line | int | |
| content | text | redacted of secrets before store |
| token_count | int | |
| embedding | vector(1536) | model-dependent dim; see prompts config |
| tsv | tsvector | generated from `content` + `symbol` |

Indexes: `ivfflat (embedding vector_cosine_ops)`, `gin (tsv)`,
`btree (repository_version_id)`.

## Tasks & runs

### tasks
| col | type | notes |
|---|---|---|
| user_id | fk | authz |
| repository_id | fk | |
| repository_version_id | fk null | resolved at run start |
| branch | text | source branch |
| title | text | |
| description | text | the engineering request (UNTRUSTED as instructions) |
| autonomy | autonomy_level | |
| model | text | e.g. `claude-sonnet-5` |
| max_iterations | int | default 3 |
| run_evaluation | bool | |
| auto_create_pr | bool | |
| status | task_status | `draft`,`queued`,`running`,`awaiting_approval`,`approved`,`completed`,`failed`,`cancelled` |

### agent_runs
one execution attempt of a task.
`task_id fk`, `status` (`running`,`succeeded`,`failed`,`cancelled`），
`autonomy`, `model`, `workspace_path text`, `started_at`, `finished_at null`,
`error_category text null`, `error_message text null`, `correlation_id text`,
`total_input_tokens int`, `total_output_tokens int`, `total_cost_usd numeric(10,6)`,
`confidence text null` (`high`/`medium`/`low`), `summary text null`.

### agent_steps
ordered timeline. `agent_run_id fk`, `seq int`, `agent text`
(`repo_analyzer`,`planner`,`retriever`,`coder`,`tester`,`debugger`,`security`,`reviewer`,`evaluation`),
`status` (`running`,`succeeded`,`failed`,`skipped`), `started_at`, `finished_at null`,
`input_json jsonb`, `output_json jsonb null`, `error text null`,
`prompt_version text null`. `unique (agent_run_id, seq)`.

### tool_calls
`agent_step_id fk`, `seq int`, `tool text`, `args_json jsonb`,
`result_json jsonb null`, `ok bool`, `error text null`, `duration_ms int`.

### file_changes
`agent_run_id fk`, `path text`, `change_type` (`create`,`modify`,`delete`),
`before_content text null`, `after_content text null`, `diff text`,
`applied bool default false`, `lines_added int`, `lines_removed int`.

### test_runs
`agent_run_id fk`, `phase` (`baseline`,`post_change`,`repair_1`,…),
`command text`, `framework text`, `exit_code int`, `passed int`, `failed int`,
`errors int`, `duration_ms int`, `stdout text`, `stderr text` (both truncated).

### security_findings
`agent_run_id fk`, `source` (`gitleaks`,`bandit`,`semgrep`,`pip_audit`,`npm_audit`,`ai_review`),
`severity` (`info`,`low`,`medium`,`high`,`critical`), `rule_id text`,
`path text null`, `line int null`, `message text`, `deterministic bool`.

## Review, evaluation, PRs, telemetry

### reviews
`agent_run_id fk`, `overall_score int`, `correctness int`, `security int`,
`maintainability int`, `testing int`, `performance int`,
`blocking_issues jsonb`, `warnings jsonb`, `suggestions jsonb`,
`production_ready bool` (deterministic gates AND score), `escalated_to_human bool`,
`escalation_reason text null`.

### evaluations
a suite execution. `benchmark_set text`, `git_ref text null`,
`model text`, `prompt_bundle text`, `status`, `started_at`, `finished_at null`,
`task_success_rate numeric`, `test_pass_rate numeric`, `regression_rate numeric`,
`security_violation_rate numeric`, `avg_latency_s numeric`, `avg_cost_usd numeric`,
`baseline_evaluation_id fk null`.

### evaluation_results
per-benchmark. `evaluation_id fk`, `benchmark_id text`, `passed bool`,
`build_ok bool`, `lint_ok bool`, `tests_ok bool`, `security_ok bool`,
`regression bool`, `repair_iterations int`, `tool_failures int`,
`latency_s numeric`, `cost_usd numeric`, `detail_json jsonb`.

### pull_requests
`task_id fk`, `agent_run_id fk`, `branch text`, `base text`,
`github_pr_number int null`, `github_pr_url text null`, `title text`,
`body text`, `state` (`draft`,`creating`,`open`,`failed`), `commit_sha text null`.

### model_usage
`agent_run_id fk null`, `agent_step_id fk null`, `provider text`, `model text`,
`prompt_version text null`, `input_tokens int`, `output_tokens int`,
`cost_usd numeric(10,6)`, `latency_ms int`, `purpose text`.

### prompt_versions
`name text`, `version text`, `description text`, `template text`,
`model_config jsonb`, `active bool`. `unique (name, version)`.

### audit_log
`user_id fk null`, `actor text`, `action text`, `target_type text`,
`target_id text`, `metadata jsonb`, `correlation_id text`.

## Row-level authorization
Every task/repo/run query is scoped by `user_id` derived from the session, never
from a request parameter. A dependency `require_repo_access(repo_id, user)` is
applied to all repo-scoped routes.
