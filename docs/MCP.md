# MCP server

Sarathi ships a genuine [Model Context Protocol](https://modelcontextprotocol.io)
server that exposes its real code-intelligence to any MCP client (Claude Desktop,
the MCP Inspector, another agent). It is **not** a demo shell — every tool calls
the same functions the Sarathi worker uses.

- Code: `services/worker/worker/mcp/`
- Entry point: `python -m worker.mcp` (console script: `sarathi-mcp`)
- Transport: **stdio** (see below for why)
- Tests: `services/worker/tests/test_mcp_server.py` — spawns the server as a real
  subprocess and drives it with a real `mcp.ClientSession`.

## Why stdio (not SSE / streamable-HTTP)

stdio is how Claude Desktop and virtually every MCP client integrate: the client
spawns the server as a subprocess and speaks JSON-RPC over stdin/stdout. Adding
Sarathi to a client is a single config block — no ports, no auth, no always-on
service, and it is directly testable (`stdio_client(...)` in the test suite).

A streamable-HTTP endpoint mounted on the FastAPI app (for remote clients) is a
documented follow-up, not v1.

## Why a separate process (not mounted on the API)

The MCP server needs the *worker's* dependency set — the retrieval pipeline,
`analyze_repo`, git, embeddings, the Celery producer — and its own lifecycle. It
shares Sarathi's **database and code**, not its process. It lives inside the
`worker` package because it is a thin adapter over the worker's existing
capabilities and runs with the identical environment (same `.env`, same image).

All logging is forced to **stderr** so it never corrupts the JSON-RPC stream on
stdout.

## Tools

| Tool | Wraps | Notes |
|---|---|---|
| `list_indexed_repositories` | `repository_versions` rows | discovery — valid `repo` values for the others |
| `search_codebase` | `worker.codeintel.retrieval.hybrid_search` | dense (pgvector) + lexical (`tsvector`) + symbol (trigram), RRF-fused; returns real chunks with path, line range, score, and which retrievers matched |
| `get_repo_structure` | `worker.codeintel.languages.analyze_repo` + `code_files` rows | language/dir map from the index + a deterministic framework/manifest scan of a short-lived shallow clone; degrades to index-only if the clone fails |
| `run_evaluation` | `app.services.queue.dispatch(worker.run_evaluation)` | enqueues the benchmark harness (minutes-long, spawns sandbox containers); returns an `evaluation_id` |
| `get_evaluation_result` | `evaluations` / `evaluation_results` rows | poll the above |

Every tool has a Pydantic input **and** output schema (`worker/mcp/models.py`),
so a client renders typed results rather than opaque text.

### `run_evaluation` is asynchronous on purpose

The evaluation harness runs the full agent orchestrator against each benchmark
(real model calls, real Docker sandboxes) and takes minutes — far longer than an
MCP client will wait on a single call. So `run_evaluation` does what the web API
does: creates the `evaluations` row and enqueues the Celery task, returning an id
immediately. The client polls `get_evaluation_result`. This needs the Sarathi
worker and Docker to be running; if the broker is unreachable the tool says so.

## Prerequisites

The server talks to Sarathi's Postgres (and, for `search_codebase`, the
embedding provider). It reads the same env as the worker:

```
DATABASE_URL_SYNC=postgresql+psycopg://sarathi:sarathi@localhost:5433/sarathi
GEMINI_API_KEY=...           # or EMBEDDING_PROVIDER=hash for offline
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIM=768
```

At least one repository must be **indexed** (via the web UI, or
`python -m worker.codeintel.index_cli https://github.com/owner/name.git`).

## Run it

```bash
# from the repo root, with the venv that has `sarathi-worker` installed
python -m worker.mcp
# or
sarathi-mcp
```

It reads config from `.env` in the working directory (env vars win). Point
`DATABASE_URL_SYNC` at a reachable Postgres.

## Connect Claude Desktop

Edit `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "sarathi": {
      "command": "C:\\path\\to\\aicopilot\\apps\\api\\.venv\\Scripts\\python.exe",
      "args": ["-m", "worker.mcp"],
      "cwd": "C:\\path\\to\\aicopilot",
      "env": {
        "DATABASE_URL_SYNC": "postgresql+psycopg://sarathi:sarathi@localhost:5433/sarathi",
        "DATABASE_URL": "postgresql+asyncpg://sarathi:sarathi@localhost:5433/sarathi",
        "GEMINI_API_KEY": "your-key",
        "EMBEDDING_PROVIDER": "gemini",
        "EMBEDDING_MODEL": "gemini-embedding-001",
        "EMBEDDING_DIM": "768"
      }
    }
  }
}
```

Restart Claude Desktop. The tools appear under the 🔌 menu. Then ask, e.g.:

> "Use `list_indexed_repositories`, then `search_codebase` on that repo for
> *where the hybrid retrieval RRF fusion happens*."

Claude calls `search_codebase` and gets back the real
`worker/codeintel/retrieval.py` chunk with its line range and RRF score.

## Connect the MCP Inspector (quick check, no client config)

```bash
npx @modelcontextprotocol/inspector python -m worker.mcp
```

Opens a UI to list tools, inspect schemas, and call them by hand.

## Integration notes (what was and wasn't straightforward)

- **`search_codebase`** — trivial. `hybrid_search(db, *, repository_version_id,
  query, symbol_hints, token_budget)` was already a clean synchronous function
  returning a dataclass. The adapter is ~30 lines. The only real design point is
  repo identification: MCP clients don't know internal UUIDs, so tools take
  `repo` as `owner/name` (or a unique substring) and `list_indexed_repositories`
  makes valid values discoverable.
- **`get_repo_structure`** — `analyze_repo(root)` needs a working tree, so the
  tool does a short-lived shallow clone (reusing `git_ops.clone_at` and the
  stored OAuth token) *and* also reads the persisted `code_files` rows for the
  file tree. It degrades to the index-only view if the clone can't run.
- **`run_evaluation`** — the real friction: it is a minutes-long, sandbox-heavy
  job, so it is enqueued rather than executed inline (see above).
- **Blocking work** (DB, embeddings, git) runs in a worker thread
  (`anyio.to_thread.run_sync`) so the MCP event loop stays responsive.
