import logging
import re
import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.request_context import request_id_context
from app.core.request_metrics import request_metrics

logger = logging.getLogger(__name__)

METRICS_EXCLUDED_PATHS = {
    "/health",
    "/health/live",
    "/health/ready",
    "/health/worker",
    "/health/metrics",
    "/health/requests",
}

REQUEST_ID_PATTERN = re.compile(
    r"^[a-fA-F0-9]{8}-"
    r"[a-fA-F0-9]{4}-"
    r"[a-fA-F0-9]{4}-"
    r"[a-fA-F0-9]{4}-"
    r"[a-fA-F0-9]{12}$"
)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        incoming_request_id = request.headers.get("X-Request-ID", "")

        if REQUEST_ID_PATTERN.fullmatch(incoming_request_id):
            request_id = incoming_request_id
        else:
            request_id = str(uuid4())

        context_token = request_id_context.set(request_id)
        request.state.request_id = request_id

        start_time = time.perf_counter()
        status_code = 500
        track_metrics = request.url.path not in METRICS_EXCLUDED_PATHS

        if track_metrics:
            request_metrics.start_request()

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception:
            logger.exception(
                "request.failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise

        finally:
            duration_ms = round(
                (time.perf_counter() - start_time) * 1000,
                2,
            )
            if track_metrics:
                request_metrics.finish_request(
                    method=request.method,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )

            logger.info(
                "request.completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )

            request_id_context.reset(context_token)