"""Bearer Token API 认证中间件

SECURITY 改进点:
1. 使用 ``hmac.compare_digest`` 进行恒定时间比较，防止定时攻击逐字节爆破 token。
2. 启动时若 ``enabled=True`` 且 ``token`` 为空，记录显眼警告但不抛异常
   （保持向后兼容：所有 /api/ 请求会被安全拒绝，无鉴权 bypass 风险）。
3. 正确解析 ``Authorization`` 头：必须是 ``Bearer <token>`` 格式，否则拒绝。
"""

import hmac
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("tts_multimodel")


class APIAuthMiddleware(BaseHTTPMiddleware):
    """Bearer Token 认证中间件。

    从 config.yaml 的 api_auth 配置读取启用状态和 token。
    健康检查端点（/api/health/*）和静态资源免认证。
    当 enabled=False 时完全跳过认证。

    SECURITY: token 比较使用 ``hmac.compare_digest`` (恒定时间) 以抵御定时攻击。
    """

    _PUBLIC_PREFIXES = ("/api/health/", "/static/", "/favicon.ico")
    _BEARER_SCHEME = "Bearer"

    def __init__(self, app, enabled: bool = False, token: str = ""):
        super().__init__(app)
        # SECURITY: 当 enabled=True 但 token 为空时，记录显眼警告但不抛异常
        # （保持向后兼容：所有 /api/ 请求会被安全拒绝，无鉴权 bypass 风险）。
        # 真正的 Fail Fast 由 config 加载层在启动时校验更合适，这里只做日志告警。
        if enabled and not token:
            logger.warning(
                "[SECURITY] API 认证已启用 (api_auth.enabled=true) 但未配置 token "
                "(api_auth.token 为空)。所有 /api/ 请求将被拒绝。"
                "请在 config.yaml 中配置一个非空 token。"
            )
        self.enabled = enabled
        # 将 token 编码为 bytes 一次，避免每次请求重复编码。
        self._token_bytes = token.encode("utf-8") if token else b""
        logger.info(
            "APIAuthMiddleware initialized: enabled=%s, token_length=%d",
            enabled,
            len(token),
        )

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        if any(path.startswith(prefix) for prefix in self._PUBLIC_PREFIXES):
            return await call_next(request)

        # 仅对 /api/ 路径强制认证；Web 页面、模板渲染等不限
        if not path.startswith("/api/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not self._verify_bearer(auth_header):
            return JSONResponse(
                status_code=401,
                content={"detail": "未授权访问：缺少或无效的 Bearer Token"},
            )
        return await call_next(request)

    def _verify_bearer(self, auth_header: str) -> bool:
        """SECURITY: 恒定时间校验 Bearer token。

        - 严格按 RFC 6750 解析 ``Bearer <token>`` 格式。
        - 使用 ``hmac.compare_digest`` 抵御定时攻击。
        - 缺少 scheme / 多余字段 / 大小写不匹配都直接拒绝。
        """
        if not auth_header or not self._token_bytes:
            return False
        parts = auth_header.split(" ", 1)
        if len(parts) != 2:
            return False
        scheme, token = parts[0], parts[1]
        # SECURITY: scheme 比较也走恒定时间（避免通过 scheme 大小写差异做侧信道）。
        if not hmac.compare_digest(scheme.encode("utf-8"), self._BEARER_SCHEME.encode("utf-8")):
            return False
        # SECURITY: 核心防护——token 恒定时间比较
        return hmac.compare_digest(token.encode("utf-8"), self._token_bytes)
