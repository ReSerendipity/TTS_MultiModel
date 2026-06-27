"""Request ID middleware for distributed tracing and log correlation."""

import contextvars
import logging
import threading
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_request_id_local = threading.local()

logger = logging.getLogger("tts_multimodel.request_id")


def get_request_id() -> str:
    """Get the current request ID from the async context."""
    return _request_id_var.get()


def set_request_id(request_id: str):
    _request_id_local.request_id = request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add a unique request ID to every HTTP request/response cycle.

    - Reads X-Request-ID from incoming headers if present
    - Otherwise generates a new UUID4
    - Stores the ID in a contextvars variable for log correlation
    - Adds X-Request-ID to the response headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        if not request_id:
            request_id = uuid.uuid4().hex[:12]

        token = _request_id_var.set(request_id)
        try:
            request.state.request_id = request_id
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _request_id_var.reset(token)


class RequestIDLogFilter(logging.Filter):
    """Logging filter that injects the current request_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = getattr(_request_id_local, "request_id", "-")
        return True
