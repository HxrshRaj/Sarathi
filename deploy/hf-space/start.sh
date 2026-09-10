#!/usr/bin/env bash
# Migrate, then run the Celery worker + the API in one container.
set -euo pipefail

cd /srv/apps/api
echo "[start] alembic upgrade head"
alembic upgrade head

cd /srv
echo "[start] celery worker"
celery -A worker.celery_app:celery worker --loglevel=INFO --concurrency=1 --without-gossip --without-mingle &

echo "[start] uvicorn on :${PORT:-7860}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" --proxy-headers
