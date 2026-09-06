from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app import __version__
from app.config import get_settings
from app.errors import install_error_handlers
from app.logging import configure_logging, get_logger
from app.middleware import CorrelationIdMiddleware
from app.routers import (
    auth,
    dashboard,
    evaluations,
    health,
    pull_requests,
    repositories,
    runs,
    tasks,
)

log = get_logger("startup")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.env != "development")
    problems = settings.require_for_production()
    if problems:
        for p in problems:
            log.error("config_problem", problem=p)
        raise RuntimeError(f"Refusing to start: {problems}")
    log.info("api_starting", version=__version__, env=settings.env)
    yield
    log.info("api_stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CodePilot API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    api = "/api"
    app.include_router(health.router, prefix=api)
    app.include_router(auth.router, prefix=api)
    app.include_router(dashboard.router, prefix=api)
    app.include_router(repositories.router, prefix=api)
    app.include_router(tasks.router, prefix=api)
    app.include_router(runs.router, prefix=api)
    app.include_router(evaluations.router, prefix=api)
    app.include_router(pull_requests.router, prefix=api)

    @app.get("/api/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "codepilot-api", "version": __version__, "docs": "/api/docs"}

    return app


app = create_app()
