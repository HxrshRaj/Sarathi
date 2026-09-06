# Architecture Decision Records

Short ADRs. Format: context → decision → alternatives rejected → consequences.

## ADR-001 — Monorepo, pnpm workspace + independent Python projects
**Decision.** One git repo. `apps/web` is a pnpm workspace. `apps/api` and
`services/worker` are Python projects; `worker` depends on `api`'s package for
models/config (installed editable). `packages/shared` holds cross-language
contracts: JSON Schemas + generated TS types + a Python pydantic mirror.
**Rejected.** Full polyglot monorepo tool (Nx/Bazel) — overkill for two runtimes.
Separate repos — contract drift, harder demo.
**Consequences.** One `docker compose up`. Type-safety across the wire via
generated types. Slight duplication of the event schema in two languages, kept
honest by a schema-compat test.

## ADR-002 — Celery + Redis for background work
**Decision.** Celery 5 with Redis broker and result backend.
**Rejected.** `arq` (async-native, cleaner with FastAPI) — less recognisable in
interviews, smaller ecosystem. RQ — weak on retries/routing. Temporal — infra
weight not justified yet. Dramatiq — fine, but Celery is the lingua franca.
**Consequences.** Sync worker code (Celery tasks are sync); agent runtime uses a
dedicated event loop per task via `asyncio.run` for the LLM SDK. Acceptable —
one task per worker slot, work is IO-bound on the model.

## ADR-003 — PostgreSQL + pgvector as the only datastore for state and vectors
**Decision.** Embeddings live in a `code_chunks` table with a `vector` column and
an IVFFlat index. Keyword search uses a `tsvector` GIN index on the same rows.
**Rejected.** Pinecone/Weaviate/Qdrant — second system to run for local dev; not
needed at this scale. In-repo FAISS file — no concurrent writers, no SQL joins to
metadata.
**Consequences.** Hybrid retrieval is a single SQL round-trip per modality plus
RRF in Python. A `VectorStore` interface still exists so a managed DB can be
dropped in for scale.

## ADR-004 — GitHub OAuth as the only sign-in
**Decision.** No local password auth in product. Every user needs GitHub for the
core feature anyway. Session = httpOnly, SameSite=Lax, Secure cookie holding a
signed session id; server-side session row. A `DEV_AUTH_BYPASS` env enables a
fake user for local/tests only, refused when `ENV=production`.
**Rejected.** Email/password + separate GitHub link — more surface, more to
secure, no user value here. Pure JWT with no server session — can't revoke.
**Consequences.** OAuth token stored encrypted (Fernet, key from env) in
`github_identities`. Never returned by any API. Never passed to the worker's LLM
calls — only to GitHub tool functions.

## ADR-005 — Structured outputs via tool-calling + validate-repair-fail
**Decision.** Every agent that must return structured data defines a Pydantic
model, exposed to the model as a single forced tool. On invalid/missing output:
one repair round-trip with the validation error, then hard fail with a typed
`AgentError`. No free-text JSON parsing.
**Consequences.** Deterministic downstream code. Costs one retry in the bad case.
Prompt + schema are versioned together in `packages/prompts`.

## ADR-006 — Diffs, not file regeneration
**Decision.** The coding agent emits unified-diff hunks against known file
contents. The worker applies them with a 3-way patch; a failed apply is an
`AgentError`, not a silent overwrite. Full-file rewrite is allowed only for new
files or files under a small line threshold.
**Rejected.** "Return the whole file" — token cost, silent drift, unreviewable.
**Consequences.** Every change has `{path, before, after, diff}` and is reversible.

## ADR-007 — SSE, not WebSocket, for run events
**Decision.** `GET /api/tasks/{id}/events` is `text/event-stream`, backed by a
Redis pub/sub subscription plus a replay of persisted `agent_steps` on connect.
**Rejected.** WebSocket — bidirectional not needed; more moving parts behind a
proxy.
**Consequences.** Trivial reconnect with `Last-Event-ID` → replay from DB.

## ADR-008 — Sandbox is Docker-out-of-Docker via the worker's own daemon access
**Decision.** The worker container gets the host docker socket **mounted only into
the worker**, and uses it to launch locked-down sibling containers for execution.
The sandbox containers themselves never see the socket.
**Rejected.** gVisor/Kata/Firecracker — stronger, heavier setup; documented as the
production upgrade path in [SANDBOX.md](SANDBOX.md). Running code in-process — not
an option.
**Consequences.** The worker is a trusted, privileged component and is treated as
such (no untrusted input executed in the worker itself; it only *orchestrates*).

## ADR-009 — Attribution
Commits use the repository owner's git identity (`Harsh Raj` / GitHub-associated
email). See project brief §49. This is set via repo-local `git config` at init.
