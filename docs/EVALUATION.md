# Evaluation harness

A first-class subsystem, not an afterthought. It measures CodePilot itself so
that model / prompt / agent changes can be judged with evidence.

## Benchmark format

`packages/evaluation/benchmarks/<id>/`:
```
benchmark.yaml         # metadata + criteria
repo/                  # a small self-contained git repo (initial state)
expectation/
  tests/               # hidden tests run against the AGENT's output
  rubric.md            # for the LLM-judge pass (quality only)
  invariants.yaml      # deterministic assertions (files changed, endpoints, etc.)
```

`benchmark.yaml`:
```yaml
id: fix-discount-total
category: bug_fix          # add_endpoint | bug_fix | add_auth | refactor |
                           # add_tests | fix_failing_test | optimize_query |
                           # find_vuln | add_validation | modify_feature
task: >
  The checkout API returns wrong totals when a percentage discount is applied.
  Find and fix it, add a regression test.
autonomy: supervised
max_iterations: 3
weight: 1.0
criteria:
  build_ok: required
  lint_ok: required
  hidden_tests_pass: required
  no_new_high_security: required
  regression_suite_pass: required     # pre-existing tests still green
  judge_min_score: 70                 # advisory unless category=refactor
```

## Runner

`packages/evaluation/runner.py`:
1. For each benchmark: fresh workspace from `repo/`, run the full orchestrator
   with the configured model + prompt bundle, autonomy forced, PR creation off.
2. Apply the agent's diffs, then in the sandbox: build/import check, lint,
   `expectation/tests/`, the repo's own pre-existing test suite (regression),
   security scan.
3. Evaluate `invariants.yaml` deterministically.
4. LLM-judge pass over the diff + `rubric.md` → quality score (never the sole
   gate; blocked from lowering a deterministic pass to fail).
5. Write `evaluation_results` row.

Aggregate → `evaluations` row: `task_success_rate`, `test_pass_rate`,
`regression_rate`, `security_violation_rate`, `avg_latency_s`, `avg_cost_usd`,
mean `repair_iterations`, `tool_failures`.

## Deterministic vs LLM vs human

| Signal | Method |
|---|---|
| build / import ok | sandbox exit code |
| lint / typecheck ok | ruff / mypy / eslint / tsc exit code |
| tests pass | hidden + regression suites in sandbox |
| security | gitleaks / bandit / semgrep / pip-audit / npm audit |
| invariants (files, routes, schema) | `invariants.yaml` assertions |
| code quality, explanation quality, architecture | LLM judge (advisory) |
| ambiguous spec, high-risk, evaluator disagreement, low confidence | human — `escalated_to_human` with reason |

## Regression detection

`runner.py --baseline <evaluation_id>` compares against a prior run and flags a
**regression** (not an improvement) when any of:
- task_success_rate ↓ beyond noise band
- test_pass_rate ↓
- security_violation_rate ↑
- avg_latency_s ↑ > X%
- avg_cost_usd ↑ > X%
- mean repair_iterations ↑
Exit non-zero on regression → usable as a CI gate for prompt/model PRs.
A +4% task success that comes with +4% security failures is reported as a
**mixed result**, not a win.

## Model / prompt comparison

`runner.py --matrix models=claude-sonnet-5,claude-opus-5 prompts=v1,v2` runs the
grid and stores each cell as its own `evaluations` row with a shared
`comparison_group`. The Evaluations dashboard renders the grid: success, latency,
cost, security per cell, over time.

## Seed benchmarks (v1)

`fix-discount-total` (bug_fix), `add-users-pagination` (add_endpoint),
`add-jwt-auth` (add_auth), `dedupe-price-calc` (refactor),
`cover-cart-service` (add_tests), `fix-flaky-rounding-test` (fix_failing_test),
`spot-sql-injection` (find_vuln), `validate-signup-payload` (add_validation).
Each ships a tiny FastAPI "shopfront" repo variant so results are comparable.
