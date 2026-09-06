# CodePilot API — FastAPI + Uvicorn
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv

# Deps first for layer caching (packages resolve on the second install, below)
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN pip install --upgrade pip && pip install -e "apps/api"

COPY apps/api apps/api
# Re-run so the editable finder registers the now-present `app` package.
RUN pip install -e "apps/api" --no-deps
WORKDIR /srv/apps/api

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
