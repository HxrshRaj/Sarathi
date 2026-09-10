#!/usr/bin/env bash
# Render free web service: migrate, then run the Celery worker + the API together.
set -euo pipefail

cd apps/api
echo "[start] alembic upgrade head"
alembic upgrade head
cd ../..

echo "[start] celery worker (concurrency 1)"
celery -A worker.celery_app:celery worker --loglevel=INFO --concurrency=1 \
  --without-gossip --without-mingle --without-heartbeat &

echo "[start] uvicorn on :${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
