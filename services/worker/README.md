# services/worker — CodePilot worker + agent runtime

Celery worker. Depends on `codepilot-api` for models/config/crypto/event contract.

## Layout
```
worker/
  celery_app.py        Celery config
  tasks.py             run_agent_task · index_repository_version · run_evaluation · create_pull_request · gc_workspaces
  orchestrator.py      the agent state machine (steps, budgets, cancel, events, persistence)
  git_ops.py           trusted-side git (clone/branch/commit/push); never runs in the sandbox
  llm/                 LLMProvider ABC + Anthropic + Fake + pricing + registry
  embeddings/          EmbeddingProvider ABC + fastembed + voyage + hash + registry
  prompts/             versioned prompts + shared safety preamble
  codeintel/           languages · chunker · secrets (redact/scan) · ingest (indexing) · retrieval (hybrid + RRF)
  tools/               base (registry + path jail) · fs · search · exec (sandbox-delegating) · git
  sandbox/             SandboxRunner — ephemeral hardened Docker container per execution
  runtime/             budget · events (sync redis) · schemas (agent outputs) · context · toolset
  agents/              repo_analyzer · planner · retriever · coder · tester · debugger · security · reviewer · pr_writer · loop
  evaluation/          benchmarks loader · runner (full pipeline + gates + regression) · cli
tests/                 path jail · secrets · chunker · tool registry · fs edits · budget/fake-llm · prompt safety · sandbox flags
```

## Run
```bash
pip install -e "../../apps/api[worker]" -e ".[dev,embeddings]"
celery -A worker.celery_app:celery worker --loglevel=INFO
pytest -q            # pure logic; no infra needed
python -m worker.evaluation.cli v1 --model claude-sonnet-5
```

## Guarantees
- No `run_shell` / `exec` tool exists. Execution tools delegate to `SandboxRunner`.
- All file-tool paths are jailed to the run workspace (`resolve_in_workspace`).
- Repo text is redacted of secrets before embedding/storage and before any model call.
- If Docker is unreachable, execution steps are reported **blocked** — code never
  runs on the worker host.
