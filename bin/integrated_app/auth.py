"""Bearer Token API 认证中间件"""

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class APIAuthMiddleware(BaseHTTPMiddleware):
    """Bearer Token 认证中间件。

    从 config.yaml 的 api_auth 配置读取启用状态和 token。
    健康检查端点（/api/health/*）和静态资源免认证。
    当 enabled=False 时完全跳过认证。
    """

    _PUBLIC_PREFIXES = ("/api/health/", "/static/", "/favicon.ico")

    def __init__(self, app, enabled: bool = False, token: str = ""):
        super().__init__(app)
        self.enabled = enabled
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        if any(path.startswith(prefix) for prefix in self._PUBLIC_PREFIXES):
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header == f"Bearer {self.token}" and self.token:
            return await call_next(request)

        raise HTTPException(status_code=401, detail="未授权访问：缺少或无效的 Bearer Token")
