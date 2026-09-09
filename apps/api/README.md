# apps/api — Sarathi API

FastAPI service. Async SQLAlchemy 2 + Alembic + Postgres/pgvector. It orchestrates
only — it never calls an LLM and never runs agent code (that's `services/worker`).

## Layout
```
app/
  config.py        env-driven settings (get_settings, cached)
  logging.py       structlog JSON + secret denylist + correlation ids
  errors.py        typed ErrorCategory + single JSON error envelope
  db.py            async + sync engines/sessions
  deps.py          auth + row-level authz dependencies
  ratelimit.py     Redis token bucket
  middleware.py    correlation id + request log
  security/        crypto (Fernet), csrf (double-submit)
  models/          SQLAlchemy models (see docs/DATABASE.md)
  schemas/         Pydantic request/response + the run-event contract
  services/        github, sessions, events (redis pubsub), queue (celery producer)
  routers/         health, auth, dashboard, repositories, tasks, runs, evaluations, pull_requests
  alembic/         migrations (0001 = full schema + pgvector + tsv trigger)
  scripts/         gen_key, seed
tests/             health/errors (no DB) + authz/tasks/schema-compat (need Postgres)
```

## Run
```bash
pip install -e ".[dev,worker]"
alembic upgrade head
uvicorn app.main:app --reload
pytest -q          # DB tests skip if DATABASE_URL_SYNC is unreachable
ruff check app && ruff format --check app
```

## Notes
- `DEV_AUTH_BYPASS=true` auto-signs-in a local `dev` user; refused when `ENV=production`.
- The app refuses to start in production if required secrets are unset
  (`Settings.require_for_production`).
