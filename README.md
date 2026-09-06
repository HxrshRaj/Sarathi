# CodePilot

**An AI software‑engineering copilot with _controlled autonomy_.**

Connect a GitHub repository, give it an engineering task ("add JWT auth and tests",
"find why checkout 500s and fix it", "add pagination to the users endpoint"), and
CodePilot plans it, retrieves the relevant code, edits files, writes and runs
tests **in a sandbox**, repairs failures, runs security analysis, reviews the
result, shows you the diff, and — with your approval — opens a pull request.

It is deliberately **not** "give an LLM a shell". Every dangerous operation goes
through an allowlisted, validated, sandboxed, audited path.

> Status: this is a from‑scratch build. The full pipeline is implemented; a few
> leaf features are marked `NotImplementedError` with docstrings rather than
> mocked (see [docs/ROADMAP.md](docs/ROADMAP.md)). **Nothing in the UI shows
> fabricated metrics or fake agent activity.**

---

## What's in the box

| Area | Implemented |
|---|---|
| **Frontend** | Next.js 15 / React 19 / TS / Tailwind. Dashboard, Repositories, Tasks, live Agent Run view (SSE), GitHub‑style diff viewer, Evaluations, Pull Requests, Settings. |
| **API** | FastAPI + async SQLAlchemy 2 + Alembic. GitHub OAuth + server sessions + CSRF, row‑level authz (cross‑tenant → 404), typed error envelope, correlation IDs, Redis token‑bucket rate limits, Prometheus metrics. |
| **Worker** | Celery. Task orchestrator state machine, cooperative cancel, per‑run budgets (tokens / cost / iterations / runtime). |
| **Agents** | RepoAnalyzer · Planner · Retriever · Coder · Tester · Debugger (repair loop, capped) · Security · Reviewer. Each returns a validated Pydantic model via a forced tool, with validate → repair → typed‑fail. |
| **LLM layer** | `LLMProvider` ABC. `AnthropicProvider` (default, `claude-sonnet-5`) + `FakeProvider` (deterministic, offline, for CI/dev/demo). Token & cost tracking, retries, timeouts. |
| **Code intelligence** | Clone → language detection → structure‑aware chunking (`ast` for Python, brace‑scan for JS/TS, line windows fallback) → secret redaction → embeddings → pgvector. Hybrid retrieval: dense (pgvector cosine) + lexical (`tsvector`) + symbol (trigram), fused with Reciprocal Rank Fusion, packed to a token budget. |
| **Embeddings** | `EmbeddingProvider` ABC — `fastembed` (local, default), `voyage` (hosted), `hash` (deterministic, offline). |
| **Sandbox** | Ephemeral Docker container per execution: `--network none`, non‑root, `--cap-drop ALL`, `no-new-privileges`, read‑only rootfs, tmpfs workspace, memory / CPU / PID limits, wall‑clock kill, forced cleanup, **no docker socket, no secrets, no host mounts**. |
| **Security** | In‑process secret scanner/redactor + `bandit` / `pip-audit` (sandboxed) + AI review over the diff. Deterministic findings are never suppressed by the AI pass. |
| **Evaluation** | Benchmark format + runner that executes the **full** orchestrator per benchmark, then grades with deterministic gates + `invariants.yaml` + an advisory LLM judge. Aggregates rates; flags **regressions** vs a baseline; model/prompt comparison groups. Seed set + sample repos included. |
| **Observability** | Every run is replayable from `agent_steps` + `tool_calls` + `file_changes` + `test_runs` + `security_findings` + `model_usage`. Structured JSON logs with a secret denylist. |
| **Infra** | `docker compose` (Postgres+pgvector, Redis, api, worker, web). Multi‑stage Dockerfiles. GitHub Actions CI (lint, format, types, migrate, tests, bandit/pip-audit/gitleaks, docker build). |

Design docs: [architecture](docs/ARCHITECTURE.md) · [decisions](docs/DECISIONS.md)
· [database](docs/DATABASE.md) · [API](docs/API.md) · [agents](docs/AGENTS.md) ·
[sandbox](docs/SANDBOX.md) · [threat model](docs/THREAT_MODEL.md) ·
[evaluation](docs/EVALUATION.md) · [roadmap](docs/ROADMAP.md).

---

## Quick start

Prerequisites: Docker (with Compose) running, and optionally an `ANTHROPIC_API_KEY`
and a GitHub OAuth app.

```bash
cp .env.example .env
# minimum to boot with no external accounts: leave LLM_PROVIDER=anthropic but note
# agent runs need a key; for an offline demo set LLM_PROVIDER=fake and EMBEDDING_PROVIDER=hash
python -m app.scripts.gen_key   # -> paste into ENCRYPTION_KEY  (run inside apps/api once deps are installed)

docker compose --profile sandbox-images build   # build the sandbox toolchain images
docker compose up --build                       # postgres, redis, api, worker, web
```

- Web: http://localhost:3000
- API docs: http://localhost:8000/api/docs
- With `DEV_AUTH_BYPASS=true` (default in `.env.example`) you are auto‑signed‑in as
  a local dev user — no GitHub needed to click around. Connecting real repos and
  opening PRs needs GitHub OAuth configured.

### Offline demo (no API keys)

```bash
# in .env
LLM_PROVIDER=fake
EMBEDDING_PROVIDER=hash
```

The `FakeProvider` returns deterministic, schema‑valid structured outputs so the
whole pipeline runs and the UI is fully explorable. It does **not** pretend to
reason — it is a labelled test double. Real runs use Anthropic when a key is set.

---

## Local development (without Docker for the app tier)

```bash
# API
cd apps/api
python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate
pip install -e ".[dev,worker]"
pip install -e ../../services/worker[dev]
alembic upgrade head            # needs Postgres+pgvector reachable via DATABASE_URL_SYNC
uvicorn app.main:app --reload

# Worker
celery -A worker.celery_app:celery worker --loglevel=INFO

# Web
pnpm install
pnpm --filter codepilot-web dev
```

---

## Tests

```bash
make test            # api + worker + web
# or individually:
cd apps/api && pytest -q          # DB‑backed tests skip if Postgres is unreachable
cd services/worker && pytest -q   # pure‑logic: path jail, secrets, chunker, tools, budget, sandbox flags, prompt safety
pnpm --filter codepilot-web test  # diff renderer unit tests
```

CI runs all of the above against a real `pgvector` service plus `bandit`,
`pip-audit`, `gitleaks`, and a Docker build.

---

## Evaluation

```bash
# from the API
curl -X POST localhost:8000/api/evaluations/run \
  -H 'content-type: application/json' \
  -d '{"benchmark_set":"v1","model":"claude-sonnet-5"}'

# or directly
docker compose run --rm worker python -m worker.evaluation.cli v1 --model claude-sonnet-5
```

Each benchmark becomes a real local git repo; the full orchestrator runs against
it; results are graded deterministically (`build` / `lint` / hidden tests /
regression suite / security / invariants) with an advisory LLM‑judge score.
`--baseline <evaluation_id>` flags regressions. See
[docs/EVALUATION.md](docs/EVALUATION.md) and
[packages/evaluation/](packages/evaluation/README.md).

---

## Security model (summary)

- **Repository content is untrusted.** It reaches the model only inside
  `<repository_file>` delimiters, role `user`, with a system preamble instructing
  the agent to treat embedded instructions as data and report them. No agent has
  a shell or network tool.
- **Generated code never runs on the host** — only in the locked‑down sandbox.
- **Secrets never reach the model or logs** — regex+entropy redaction on every
  chunk and every context block; OAuth tokens are Fernet‑encrypted at rest and
  passed only to GitHub tool functions.
- **Authorization** is row‑level by session user; cross‑tenant ids return 404.
- **Autonomy is gated** (L1 assist / L2 supervised / L3 controlled). No level
  grants host shell, docker socket, secret access, force‑push, or merge.

Full detail: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md),
[docs/SANDBOX.md](docs/SANDBOX.md).

---

## Repository layout

```
apps/
  api/       FastAPI service + SQLAlchemy models + Alembic + tests
  web/       Next.js app
services/
  worker/    Celery worker + agent runtime (llm, embeddings, prompts, codeintel,
             tools, sandbox, agents, orchestrator, evaluation) + tests
packages/
  shared/       TS wire contracts (run events)
  evaluation/   benchmark definitions + sample repos
infrastructure/docker/   Dockerfiles (api, worker, web, sandbox-python, sandbox-node)
docs/          architecture, ADRs, DB, API, agents, sandbox, threat model, evaluation, roadmap
.github/workflows/ci.yml
docker-compose.yml
```

---

## Known limitations (documented, not hidden)

- Sandbox isolation uses Docker namespaces (a soft boundary). The `SandboxRunner`
  interface is built so a gVisor / Kata / Firecracker backend is a drop‑in swap
  for multi‑tenant production.
- Managed vector DB, multi‑provider LLM beyond Anthropic+Fake, and tree‑sitter
  grammars are interfaces with a single implementation each.
- Dependency installation in the sandbox is offline‑from‑lockfile only; without a
  lockfile it is skipped and reported, never improvised.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan and what each phase
delivered.
