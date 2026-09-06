from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logging import correlation_id_var, get_logger

log = get_logger("http")

_HEADER = "x-correlation-id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        cid = request.headers.get(_HEADER) or uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers[_HEADER] = cid
        if not request.url.path.endswith(("/health", "/health/ready")):
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
        return response
