# Implementation roadmap

Phased. Each phase ends green: tests pass, stack boots, docs updated, one commit.

| Phase | Deliverable | State |
|---|---|---|
| 0 | Architecture, ADRs, DB schema, API design, threat model, sandbox model, evaluation model, agent model | ✅ this dir |
| 1 | Monorepo, FastAPI skeleton, Next.js skeleton, Postgres+pgvector, Redis, docker-compose, config, structlog, health checks, Alembic + full schema migration, CI | ▶ in progress |
| 2 | GitHub OAuth, sessions, CSRF, `require_*_access`, rate limiting, `/auth/*` | |
| 3 | Repo listing/connect/branches, clone to workspace, `repository_versions`, indexing Celery job | |
| 4 | Language detection, chunker (ast/heuristic; tree-sitter optional), EmbeddingProvider (fastembed default), pgvector store, tsvector keyword, hybrid RRF retrieval, retrieval eval set | |
| 5 | Agent runtime: `LLMProvider` (Anthropic + Fake), prompt registry, ToolRegistry + validation + path jail, orchestrator state machine, budgets, cancel, SSE event bus | |
| 6 | Planner + RepoAnalyzer agents, structured-output validate/repair, agent tests | |
| 7 | Coder agent: diff hunks, 3-way apply, `file_changes`, rollback, diff API | |
| 8 | SandboxRunner (Docker SDK): network none, non-root, rlimits, tmpfs, cleanup; malicious-input tests | |
| 9 | Tester + Debugger: discovery, sandbox execution, repair loop with iteration cap | |
| 10 | Security agent: gitleaks/bandit/semgrep/pip-audit/npm audit + AI review → findings | |
| 11 | Reviewer agent: scores, gates, human-escalation reasons | |
| 12 | Evaluation harness: benchmark format, runner, 8 seed benchmarks + sample repo, regression detection, model/prompt matrix, dashboard | |
| 13 | GitHub PR: branch, commit (owner identity), PR title/body generator, approval gate | |
| 14 | Hardening: cost caps, rate-limit coverage, audit log, Prometheus metrics, error taxonomy polish, migrations review, perf (incremental indexing), backup notes | |

## What "done" excludes on purpose (documented, not faked)
- Managed vector DB integration (interface only; pgvector is the impl).
- gVisor/Kata sandbox backend (interface + docs; Docker is the impl).
- Multi-provider LLM beyond Gemini + Anthropic + Fake (interface ready).
- tree-sitter native grammars (ast + heuristic chunker is the impl; hook present).
Anything not implemented is marked `NotImplementedError` with a docstring, never
mocked to look real.

## Dependencies to provision for full functionality
- `GEMINI_API_KEY` — real agent runs + embeddings (Fake/hash providers work offline for dev/CI/demo).
- GitHub OAuth app (`GITHUB_CLIENT_ID/SECRET`) — repo connect + PRs.
- Docker daemon reachable from the worker — sandbox execution.
- `ENCRYPTION_KEY` (Fernet) — OAuth token at rest.
