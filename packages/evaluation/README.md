# Sarathi evaluation benchmarks

Each `benchmarks/<id>/` is a self-contained task:

```
benchmark.yaml         metadata + pass criteria
repo/                  the repository's INITIAL state (becomes a real local git repo)
expectation/
  tests/               hidden tests run against the agent's output
  invariants.yaml      deterministic assertions (files changed / not changed / contain)
  rubric.md            advisory LLM-judge rubric
```

The runner (`worker/evaluation/runner.py`) turns each `repo/` into a git repo,
runs the **full** orchestrator against it (clone → index → plan → code → test →
security → review), then grades:

| Gate | How |
|---|---|
| run succeeded | orchestrator terminal status |
| build_ok | `python -m compileall` in the sandbox |
| lint_ok | `ruff check` / `pyflakes` in the sandbox |
| hidden tests | `expectation/tests/` in the sandbox |
| regression | the repo's own pre-existing tests still pass |
| security | no new high/critical findings |
| invariants | `invariants.yaml` assertions |
| judge_score | LLM judge over the diff + rubric (advisory only) |

`runner.py` aggregates rates onto the `evaluations` row and, given a
`baseline_evaluation_id`, flags a **regression** (see `_is_regression`). A model or
prompt change that raises task success but also raises security violations is
reported as a mixed result, not a win.

Run from the API: `POST /api/evaluations/run {"benchmark_set":"v1","model":"claude-sonnet-5"}`
or `make seed && docker compose run --rm worker python -m worker.evaluation.cli v1`.

## Seed set (`v1`)

| id | category | what it exercises |
|---|---|---|
| `fix-discount-total` | bug_fix | find + fix a wrong-math bug, add a regression test |
| `add-users-pagination` | add_endpoint | extend an endpoint without breaking callers |

More categories (add_auth, refactor, fix_failing_test, optimize_query, find_vuln,
add_validation, modify_feature) follow the same layout.
