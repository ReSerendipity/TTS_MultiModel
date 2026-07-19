"""Request ID middleware for distributed tracing and log correlation.

Single source of truth: the ``_request_id_var`` ContextVar.
Background threads MUST call :func:`set_request_id` to publish their ID into
both the ContextVar (for async code) and the thread-local mirror (for sync
code / legacy logging filter).

SECURITY: Incoming ``X-Request-ID`` headers are sanitized to prevent log
injection (newlines / control characters are stripped, length capped).
"""

import contextvars
import logging
import re
import threading
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# REFACTOR: Single source of truth — both async code and the logging filter
# read from this ContextVar. Background threads populate it via
# set_request_id() so the legacy thread-local mirror is no longer needed
# for HTTP requests.
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# SECURITY: Sanitize incoming X-Request-ID to prevent log injection.
# Allow only alphanumeric + dash/underscore, max 64 chars.
_REQUEST_ID_SANITIZER = re.compile(r"[^A-Za-z0-9_\-]")
_MAX_REQUEST_ID_LEN = 64

logger = logging.getLogger("tts_multimodel.request_id")


def get_request_id() -> str:
    """Get the current request ID from the async context."""
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Publish *request_id* into the ContextVar for the current thread/task.

    Used by background threads (e.g. model loading, persona warmup) so their
    log records carry the same correlation ID. Inside an event loop the
    ContextVar is propagated automatically; outside (plain threads) we also
    mirror to a thread-local so the legacy :class:`RequestIDLogFilter`
    keeps working when no ContextVar is set on that thread.
    """
    _request_id_var.set(request_id)
    _request_id_local.request_id = request_id


_request_id_local = threading.local()


def _sanitize_request_id(raw: str) -> str:
    """SECURITY: Strip control chars / newlines and cap length.

    Prevents log injection where a malicious client sends an X-Request-ID
    containing '\\n' to forge fake log lines.
    """
    if not raw:
        return ""
    cleaned = _REQUEST_ID_SANITIZER.sub("", raw)[:_MAX_REQUEST_ID_LEN]
    return cleaned


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add a unique request ID to every HTTP request/response cycle.

    - Reads ``X-Request-ID`` from incoming headers if present (sanitized)
    - Otherwise generates a new UUID4 hex (12 chars, sufficient for ~16M IDs)
    - Stores the ID in a ContextVar for log correlation
    - Adds ``X-Request-ID`` to the response headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # SECURITY: sanitize client-supplied ID before use
        raw_id = request.headers.get("X-Request-ID", "")
        request_id = _sanitize_request_id(raw_id) or uuid.uuid4().hex[:12]

        token = _request_id_var.set(request_id)
        # REFACTOR: also mirror to thread-local so the log filter works
        # even when logging happens inside run_in_executor threads that
        # inherit the ContextVar via copy_context().
        _request_id_local.request_id = request_id
        try:
            request.state.request_id = request_id
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _request_id_var.reset(token)
            # Clear thread-local so a pooled worker thread does not leak
            # the previous request's ID to the next task.
            _request_id_local.request_id = "-"


class RequestIDLogFilter(logging.Filter):
    """Logging filter that injects the current request_id into log records.

    Resolution order:
    1. ContextVar (set by middleware or set_request_id) — preferred.
    2. Thread-local mirror (set by background threads via set_request_id).
    3. ``"-"`` fallback.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            # REFACTOR: prefer ContextVar; fall back to thread-local only
            # for background threads that have not entered an async context.
            rid = _request_id_var.get("")
            if not rid:
                rid = getattr(_request_id_local, "request_id", "-")
            record.request_id = rid
        return True
