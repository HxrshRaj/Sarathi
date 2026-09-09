# Sarathi worker — Celery + agent runtime. Talks to the host Docker daemon to
# launch locked-down sandbox containers (socket mounted only here, never in a sandbox).
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv

COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN pip install --upgrade pip \
 && pip install -e "apps/api[worker]" \
 && pip install -e "services/worker[embeddings]"

COPY apps/api apps/api
COPY services/worker services/worker
COPY packages/evaluation packages/evaluation

# Re-run editable installs so the finders register the now-present packages
# (`app`, `worker`). Without this the deps-only layer leaves them unimportable.
RUN pip install -e "apps/api" --no-deps && pip install -e "services/worker" --no-deps

ENV SARATHI_BENCHMARKS_DIR=/srv/packages/evaluation/benchmarks
WORKDIR /srv/services/worker

# Pre-download the embedding model so first run is fast (best-effort).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')" || true

CMD ["celery", "-A", "worker.celery_app:celery", "worker", "--loglevel=INFO", "--concurrency=2"]
