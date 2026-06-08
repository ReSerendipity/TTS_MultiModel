"""CSRF Protection Middleware"""
import secrets
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("tts_multimodel")

_CSRF_COOKIE_NAME = "csrf_token"
_CSRF_HEADER_NAME = "x-csrf-token"
_CSRF_FORM_FIELD = "csrf_token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SKIP_PATHS = {"/docs", "/redoc", "/openapi.json"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection middleware."""

    async def dispatch(self, request: Request, call_next):
        # Skip for safe methods
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            # Ensure CSRF cookie exists
            if _CSRF_COOKIE_NAME not in request.cookies:
                token = secrets.token_hex(32)
                response.set_cookie(
                    key=_CSRF_COOKIE_NAME,
                    value=token,
                    httponly=False,
                    samesite="lax",
                    path="/",
                )
            return response

        # Skip for documentation paths
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        # Validate CSRF token for state-changing requests
        cookie_token = request.cookies.get(_CSRF_COOKIE_NAME)
        header_token = request.headers.get(_CSRF_HEADER_NAME)

        # Also check form data for token
        form_token = None
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            # Read form data - but we can't easily do this without consuming the body
            # For form submissions, we rely on the header or cookie double-submit
            pass

        submitted_token = header_token or form_token

        if not cookie_token:
            # No cookie yet, generate one and reject this request
            token = secrets.token_hex(32)
            response = JSONResponse(
                {"status": "error", "message": "CSRF token missing. Please refresh the page."},
                status_code=403,
            )
            response.set_cookie(
                key=_CSRF_COOKIE_NAME,
                value=token,
                httponly=False,
                samesite="lax",
                path="/",
            )
            return response

        if not submitted_token:
            return JSONResponse(
                {"status": "error", "message": "CSRF token required. Include X-CSRF-Token header."},
                status_code=403,
            )

        if not secrets.compare_digest(cookie_token, submitted_token):
            return JSONResponse(
                {"status": "error", "message": "CSRF token mismatch."},
                status_code=403,
            )

        return await call_next(request)
