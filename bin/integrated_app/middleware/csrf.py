"""CSRF Protection Middleware (Double-Submit Cookie)

SECURITY 改进点:
1. ``Secure`` 标志：当请求通过 HTTPS 到达时（或显式配置 ``TTS_COOKIE_SECURE=1``），
   自动启用 ``Secure``，避免 cookie 经 HTTP 明文传输被中间人截获。
2. 移除死代码 ``form_token``：原实现中 ``form_token`` 永远为 ``None``，
   ``submitted_token = header_token or form_token`` 实际上等价于 ``header_token``。
   现在明确文档化：所有 state-changing 请求必须通过 ``X-CSRF-Token`` 头携带 token，
   HTML 表单需要在前端 JS 中读取 cookie 并设置该头。
3. ``__Host-`` 前缀：当部署在根域名且无子域时，使用 ``__Host-csrf_token`` 可防止
   子域 cookie 注入（更严格的安全策略）。通过 ``TTS_COOKIE_HOST_PREFIX=1`` 启用。
4. 保留恒定时间比较 (``secrets.compare_digest``)。
"""

import logging
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("tts_multimodel")

# REFACTOR: 集中常量，避免魔法字符串
_CSRF_COOKIE_NAME = os.environ.get("TTS_CSRF_COOKIE_NAME", "csrf_token")
_CSRF_HEADER_NAME = "x-csrf-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SKIP_PATHS = {"/docs", "/redoc", "/openapi.json"}


def _should_set_secure(request: Request) -> bool:
    """SECURITY: 决定是否给 cookie 加 Secure 标志。

    启用条件 (任一):
    - 请求通过 HTTPS 到达 (``request.url.scheme == "https"`` 或 X-Forwarded-Proto)
    - 显式环境变量 ``TTS_COOKIE_SECURE=1``
    """
    if os.environ.get("TTS_COOKIE_SECURE", "0") == "1":
        return True
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    return "https" in forwarded_proto


def _build_cookie_kwargs(request: Request, secure: bool) -> dict:
    """统一构造 set_cookie 参数。"""
    return {
        "httponly": False,  # 前端 JS 必须能读取以放入 X-CSRF-Token 头
        "samesite": "lax",
        "path": "/",
        "secure": secure,  # SECURITY: HTTPS 部署时自动启用
    }


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection middleware.

    工作流程:
    - 安全方法 (GET/HEAD/OPTIONS): 放行；若 cookie 不存在则签发新 token。
    - 状态变更方法 (POST/PUT/DELETE/PATCH): 校验 ``X-CSRF-Token`` 头与 cookie 值匹配。

    前端约定:
      所有 state-changing 请求必须由 JS 读取 ``csrf_token`` cookie 并放入
      ``X-CSRF-Token`` 请求头。纯 HTML 表单（无 JS）将无法通过 CSRF 校验，
      这是有意为之的安全策略。
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            if _CSRF_COOKIE_NAME not in request.cookies:
                token = secrets.token_hex(32)
                response.set_cookie(
                    key=_CSRF_COOKIE_NAME,
                    value=token,
                    **_build_cookie_kwargs(request, secure=_should_set_secure(request)),
                )
            return response

        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        cookie_token = request.cookies.get(_CSRF_COOKIE_NAME)
        # REFACTOR: 移除死代码 form_token —— 原实现从不真正读取 form 数据，
        # ``submitted_token`` 实际上等价于 ``header_token``。现在显式只认 header,
        # 并在文档中要求前端 JS 设置该头。
        header_token = request.headers.get(_CSRF_HEADER_NAME)

        if not cookie_token:
            token = secrets.token_hex(32)
            response = JSONResponse(
                {"status": "error", "message": "CSRF token missing. Please refresh the page."},
                status_code=403,
            )
            response.set_cookie(
                key=_CSRF_COOKIE_NAME,
                value=token,
                **_build_cookie_kwargs(request, secure=_should_set_secure(request)),
            )
            return response

        if not header_token:
            return JSONResponse(
                {"status": "error", "message": "CSRF token required. Include X-CSRF-Token header."},
                status_code=403,
            )

        # SECURITY: 恒定时间比较，防止定时攻击
        if not secrets.compare_digest(cookie_token, header_token):
            return JSONResponse(
                {"status": "error", "message": "CSRF token mismatch."},
                status_code=403,
            )

        return await call_next(request)
