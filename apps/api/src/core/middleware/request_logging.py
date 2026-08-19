import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("api.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID and logs one structured line per request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s (%sms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response
