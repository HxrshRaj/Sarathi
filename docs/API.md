# API design

FastAPI. JSON only. Auth via session cookie (`cp_session`, httpOnly, SameSite=Lax,
Secure in prod) + double-submit CSRF token header (`X-CSRF-Token`) for mutations.
OpenAPI served at `/api/docs`.

## Conventions

- Base path `/api`. Resource ids are UUIDs.
- Timestamps ISO-8601 UTC.
- Pagination: `?limit=&cursor=`; responses `{ "items": [], "next_cursor": null }`.
- **Error envelope** (all non-2xx):
  ```json
  { "error": { "category": "user|auth|not_found|rate_limit|agent|tool|
                            infra|model|sandbox|limit_exceeded|validation",
               "message": "human readable",
               "detail": {},
               "retryable": false,
               "correlation_id": "..." } }
  ```
- Every response carries `X-Correlation-ID`.

## Auth
| Method | Path | Notes |
|---|---|---|
| GET | `/api/auth/github/start` | 302 to GitHub OAuth (state cookie) |
| GET | `/api/auth/github/callback` | exchanges code, creates session, 302 to app |
| POST | `/api/auth/logout` | revokes session |
| GET | `/api/auth/me` | current user + `default_autonomy`, `csrf_token` |

## Repositories
| Method | Path | Notes |
|---|---|---|
| GET | `/api/repositories/github` | list GitHub repos the token can see (proxied, cached) |
| POST | `/api/repositories/connect` | `{github_repo_id}` → creates `repositories` row |
| GET | `/api/repositories` | connected repos for the user |
| GET | `/api/repositories/{id}` | one repo + latest version status |
| GET | `/api/repositories/{id}/branches` | branches (proxied) |
| POST | `/api/repositories/{id}/index` | `{branch}` → enqueues indexing job, returns `repository_version` |
| GET | `/api/repositories/{id}/versions` | index history |
| DELETE | `/api/repositories/{id}` | disconnect + purge snapshots/embeddings |

## Tasks & runs
| Method | Path | Notes |
|---|---|---|
| POST | `/api/tasks` | create (draft/queued). Body: repo, branch, title, description, autonomy, model, max_iterations, run_evaluation, auto_create_pr |
| GET | `/api/tasks` | list (filter by status) |
| GET | `/api/tasks/{id}` | task + latest run summary |
| POST | `/api/tasks/{id}/run` | creates `agent_runs`, enqueues, returns run id |
| POST | `/api/tasks/{id}/cancel` | cooperative cancel |
| GET | `/api/tasks/{id}/events` | **SSE**; replays persisted steps then live; honours `Last-Event-ID` |
| GET | `/api/tasks/{id}/diff` | aggregated `file_changes` (before/after/diff/stats) |
| GET | `/api/tasks/{id}/review` | reviewer output + security findings + test runs |
| POST | `/api/tasks/{id}/approve` | approve → branch/commit/PR (autonomy-gated) |
| GET | `/api/runs/{id}` | full replay payload (steps, tool_calls, usage) |

## Evaluations
| Method | Path | Notes |
|---|---|---|
| POST | `/api/evaluations/run` | `{benchmark_set, model, prompt_bundle, baseline_evaluation_id?}` → enqueues |
| GET | `/api/evaluations` | list, newest first |
| GET | `/api/evaluations/{id}` | aggregates + per-benchmark `evaluation_results` |
| GET | `/api/evaluations/compare?ids=` | side-by-side for the dashboard |

## Pull requests
| Method | Path | Notes |
|---|---|---|
| GET | `/api/pull-requests` | PRs created by Sarathi for the user |
| GET | `/api/pull-requests/{id}` | one PR + generated body |

## Ops
| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | liveness `{status:"ok"}` |
| GET | `/api/health/ready` | DB + Redis + (optional) LLM key presence |
| GET | `/api/metrics` | Prometheus text (protected) |

## Rate limits (Redis token bucket, per user)
`POST /tasks` 10/min · `POST /run` 20/min · `POST /index` 5/min ·
`POST /approve` 10/min · `POST /evaluations/run` 3/min. `429` → error envelope
`category=rate_limit`, `retryable=true`, `Retry-After` header.

## Authorization
Session → `user_id`. `require_repo_access` / `require_task_access` dependencies
filter by `user_id`; cross-tenant ids return `404`. No id in a path is ever
trusted on its own.
