# CodePilot — Architecture

> AI-assisted software engineering with **controlled autonomy**.
> Not "give an LLM a shell". Every dangerous operation goes through an explicit,
> validated, sandboxed, audited path.

## 1. System overview

```
                    ┌──────────────────────────┐
   Browser  ───────▶│  apps/web  (Next.js 15)   │
                    │  React / TS / Tailwind    │
                    │  unified diff viewer       │
                    └───────────┬──────────────┘
                                │  HTTPS (cookie session + CSRF)
                    ┌───────────▼──────────────┐
                    │  apps/api  (FastAPI)      │
                    │  auth · authz · REST      │
                    │  SSE event stream         │
                    │  rate limit · cost guard  │
                    └───┬───────────────┬───────┘
             enqueue    │               │  read/write
                        │               ▼
             ┌──────────▼─────┐   ┌─────────────────────────┐
             │ Redis          │   │ PostgreSQL 16 + pgvector │
             │ queue·pubsub   │   │ system of record        │
             │ cache·ratelimit│   │ + embeddings            │
             └──────────┬─────┘   └─────────────────────────┘
                        │ consume
             ┌──────────▼─────────────────────────────────┐
             │ services/worker  (Celery)                   │
             │  ┌──────────────────────────────────────┐   │
             │  │ Task Orchestrator (state machine)    │   │
             │  └───┬──────────────────────────────────┘   │
             │      ▼                                       │
             │  Agent runtime                              │
             │   RepoAnalyzer · Planner · Retriever ·      │
             │   Coder · Tester · Debugger · Security ·    │
             │   Reviewer · EvaluationEngine              │
             │      │                                       │
             │      ▼  validated tool layer                │
             │   git · fs · search · test · lint · format ·│
             │   static-analysis · security-scan          │
             │      │                                       │
             │      ▼                                       │
             │  Sandbox launcher  ──▶ ephemeral Docker     │
             │   (no network · non-root · rlimits · tmpfs) │
             └────────────────────────────────────────────┘
```

### Why this shape

| Decision | Reason |
|---|---|
| Separate `api` and `worker` processes | Agent runs are minutes long. HTTP stays fast; work is async and cancellable. |
| Redis pub/sub for run events, SSE to browser | Standard, low-infra streaming. No websocket server to babysit. |
| Postgres is the single source of truth | Every run is fully reconstructable from rows. Redis is disposable. |
| pgvector, not a dedicated vector DB | One datastore for local dev. `VectorStore` interface allows swapping later. |
| Docker-per-execution sandbox | Real isolation boundary; industry-recognisable; disposable. |
| Provider abstraction (`LLMProvider`) | Gemini is the default impl; Anthropic + a Fake provider ship too; adding another is one class. |

## 2. Components

### apps/web
Next.js App Router. Pages: Dashboard, Repositories, Tasks, Task Run (live), Diff,
Evaluations, Runs, Pull Requests, Settings. Talks only to `apps/api`. No secrets.
A hand-rolled unified-diff viewer (Monaco was dropped — CDN-gated, and read-only review needs less). SSE client for the live run view.

### apps/api
FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic.
Responsibilities: session auth (GitHub OAuth), authorization (row-level repo
ownership), request validation, consistent error envelope, rate limiting,
cost-limit enforcement, enqueue tasks, expose SSE, serve diffs/results.
**The API never calls an LLM and never runs agent code.** It only orchestrates.

### services/worker
Celery workers. One Celery task = one `agent_run`. Runs the orchestrator, which
drives the agent state machine, writes `agent_steps` / `tool_calls` /
`file_changes` / `test_runs` / `security_findings`, and publishes events to Redis.
Honors cancellation (cooperative check between steps) and hard limits
(`MAX_TOKENS`, `MAX_COST_USD`, `MAX_ITERATIONS`, `MAX_RUNTIME_S`).

### Agent runtime (`packages`-style modules inside worker)
Small, single-purpose units. Each takes typed input, returns a validated Pydantic
model, and may only touch the world through the tool layer. See
[AGENTS.md](AGENTS.md).

### Tool layer
Every tool: name, JSON-schema args, an allowlist check, a path-jail check
(all paths resolved and asserted to stay inside the run workspace), size/time
caps, structured result. No `shell` tool. Execution tools (`run_tests`,
`run_linter`, …) delegate to the sandbox.

### Sandbox
`services/worker/sandbox/` launches a throwaway container per execution:
`--network none`, non-root UID, writable ephemeral layer + `tmpfs` /tmp (read-only rootfs deferred; see SANDBOX.md), `--pids-limit`,
`--memory`, `--cpus`, wall-clock timeout, `--cap-drop ALL`, no bind mounts except
the run workspace mounted read-write, **no docker socket**. Container is force-
removed on exit. See [SANDBOX.md](SANDBOX.md).

## 3. Trust boundaries

1. **Browser ↔ API** — authenticated user, still validated & rate-limited.
2. **API ↔ Worker** — via DB + Redis; worker trusts task rows (written by API after authz).
3. **Worker ↔ Repository content** — **UNTRUSTED**. Repo files, READMEs, commit
   messages, test output, dependency names are *data*, never instructions. The
   orchestrator wraps all repo-derived text in clearly delimited, role-`user`
   context and never elevates it to system/tool-authority. Prompt-injection
   corpus lives in `tests/security/`.
4. **Worker ↔ Sandbox** — sandbox is hostile-by-assumption; no secrets, no network,
   no host FS, no socket.
5. **Anything ↔ LLM** — secrets are redacted from context (`packages/shared`
   secret scanner) before any model call. OAuth tokens never enter a prompt.

## 4. Data & control flow for one task

1. `POST /api/tasks` → row in `tasks` (status `queued`), authz checked.
2. `POST /api/tasks/{id}/run` → creates `agent_runs` row, enqueues Celery job, returns run id.
3. Worker: checkout repo snapshot into workspace → `RepoAnalyzer` → `Planner`
   → `Retriever` (hybrid) → `Coder` (produces diffs) → apply to workspace →
   `Tester` in sandbox → `Debugger` repair loop (≤ `MAX_REPAIR_ITERATIONS`) →
   `Security` (deterministic tools + AI review) → `Reviewer` (score) →
   `EvaluationEngine` (optional).
4. Each step streams events to `redis pubsub run:{id}`; API relays via
   `GET /api/tasks/{id}/events` (SSE).
5. Terminal state `awaiting_approval`. `POST /api/tasks/{id}/approve` →
   (autonomy-permitting) branch + commit + PR via GitHub tool.

## 5. Autonomy levels (default = 2)

| Level | Worker may | Worker may not |
|---|---|---|
| 1 Assist | read, retrieve, plan, propose diffs | write workspace, run code |
| 2 Supervised | all of L1 + write workspace, run tests/lint/security, repair loop | push, open PR (needs explicit approve) |
| 3 Controlled autonomous | all of L2 + auto-open PR | merge, push to default branch, access arbitrary secrets, run non-allowlisted commands |

No level grants host shell, socket access, or secret exfiltration.

## 6. Tech stack (chosen)

- **Web**: Next.js 15, React 19, TypeScript, Tailwind, TanStack Query, hand-rolled diff view.
- **API**: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 async, asyncpg, Alembic.
- **Worker**: Celery 5 + Redis broker/result; Docker SDK for Python.
- **Data**: PostgreSQL 16, `pgvector` extension; Redis 7.
- **AI**: `google-genai` SDK; default model `gemini-3.5-flash` (judge `gemini-3.5-flash-lite`); `gemini-3.x-pro` on paid tiers; `LLMProvider` ABC with Anthropic + Fake alternatives.
- **Retrieval**: `tree-sitter` for symbol extraction; pgvector cosine + Postgres
  full-text (`tsvector`) for keyword; reciprocal-rank fusion for hybrid.
- **Security tooling**: `gitleaks`/`detect-secrets`, `bandit`, `semgrep`, `pip-audit`, `npm audit`.
- **Infra**: Docker Compose for local; multi-stage Dockerfiles; GitHub Actions CI.
- **Observability**: `structlog` JSON logs with correlation ids; `model_usage`
  table; every run replayable from rows.

See [DECISIONS.md](DECISIONS.md) for rejected alternatives.
