"""
Error Handler Middleware - 全局异常处理
提供统一的错误响应格式，支持 TTSError 自定义异常和通用异常捕获

重构说明 (S-R5):
- S-R5: 补全 sqlite3.OperationalError → 503 Service Unavailable
        (数据库锁定/损坏时返回服务不可用，引导客户端重试)
- S-R5: 补全 asyncio.TimeoutError / TimeoutError → 504 Gateway Timeout
        (生成超时/外部服务超时返回网关超时)
- S-R5: 日志脱敏 — generic_error_handler 不再在响应中暴露异常详情，
        仅在服务端日志中记录完整堆栈
- S-R5: 提供 sqlite_error_handler / timeout_error_handler 专门处理器，
        可被 app_server.py 注册以实现更精细的异常路由；
        同时在 generic_error_handler 中添加类型判断作为兜底，
        确保即使不注册也能返回正确的状态码
"""
import asyncio
import json
import logging
import sqlite3

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from ..exceptions import TTSError, ValidationError

logger = logging.getLogger(__name__)

# S-R5: SQLite 错误响应建议的重试间隔（秒）
_SQLITE_RETRY_AFTER_SECONDS = 5

# S-R5: SQLite 错误关键字分类
_SQLITE_LOCKED_KEYWORDS = ("locked", "busy")
_SQLITE_DISK_KEYWORDS = ("disk", "no space", "full", "readonly", "read-only")


async def tts_error_handler(request: Request, exc: TTSError) -> JSONResponse:
    """
    TTSError 自定义异常处理器
    捕获所有 TTSError 及其子类异常，返回统一的 JSON 错误格式
    """
    logger.warning(f"TTSError: {exc.status_code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "code": exc.code,
            "message": exc.message
        }
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    RequestValidationError 处理器
    捕获 Pydantic 验证错误，返回详细的字段级错误信息
    """
    logger.warning(f"Validation error: {exc}")
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "code": "validation_error",
            "message": "请求参数验证失败",
            "details": errors
        }
    )


def _build_sqlite_error_response(exc: sqlite3.OperationalError) -> JSONResponse:
    """REFACTOR: [S-R5] 构建 SQLite OperationalError 的 JSON 响应。

    Root Cause:
        SQLite 在 WAL 模式下并发写入可能触发 "database is locked"，
        磁盘空间不足时触发 "disk I/O error"。原实现统一返回 500，
        客户端无法区分是服务故障还是临时锁竞争。

    Fix:
        返回 503 Service Unavailable + Retry-After 头，
        引导客户端稍后重试。根据错误关键字返回友好的用户提示。

    Security:
        [D6] 不向客户端泄露数据库内部细节（如文件路径、SQL 语句），
        仅在服务端日志中记录完整错误信息。
    """
    error_msg = str(exc)
    error_lower = error_msg.lower()

    # 根据具体错误类型返回友好的用户提示
    if any(kw in error_lower for kw in _SQLITE_LOCKED_KEYWORDS):
        user_message = "系统繁忙，请稍后重试"
        error_code = "database_locked"
    elif any(kw in error_lower for kw in _SQLITE_DISK_KEYWORDS):
        user_message = "存储空间不足，请联系管理员"
        error_code = "disk_error"
    else:
        user_message = "数据库服务暂时不可用，请稍后重试"
        error_code = "database_unavailable"

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "error",
            "code": error_code,
            "message": user_message,
            "retry_after": _SQLITE_RETRY_AFTER_SECONDS,
        },
        headers={"Retry-After": str(_SQLITE_RETRY_AFTER_SECONDS)},
    )


def _build_timeout_error_response(exc: Exception) -> JSONResponse:
    """REFACTOR: [S-R5] 构建 Timeout 异常的 JSON 响应。

    Root Cause:
        生成任务超时（如 _GENERATION_HARD_TIMEOUT_S 触发）或外部服务
        超时时，原实现统一返回 500，客户端无法区分是服务故障还是超时。

    Fix:
        返回 504 Gateway Timeout，引导客户端缩短文本或稍后重试。
    """
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={
            "status": "error",
            "code": "gateway_timeout",
            "message": "请求处理超时，请尝试缩短文本或稍后重试",
        },
    )


async def sqlite_error_handler(request: Request, exc: sqlite3.OperationalError) -> JSONResponse:
    """REFACTOR: [S-R5] SQLite OperationalError 处理器。

    可被 app_server.py 注册以实现更精细的异常路由：
        app.add_exception_handler(sqlite3.OperationalError, sqlite_error_handler)

    即使不注册，generic_error_handler 也会通过类型判断调用相同逻辑。
    """
    logger.warning(f"SQLite OperationalError: {exc}", exc_info=True)
    return _build_sqlite_error_response(exc)


async def timeout_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """REFACTOR: [S-R5] Timeout 异常处理器。

    捕获 asyncio.TimeoutError 和内置 TimeoutError，返回 504 Gateway Timeout。

    可被 app_server.py 注册以实现更精细的异常路由：
        app.add_exception_handler(asyncio.TimeoutError, timeout_error_handler)
        app.add_exception_handler(TimeoutError, timeout_error_handler)

    即使不注册，generic_error_handler 也会通过类型判断调用相同逻辑。
    """
    logger.warning(f"Timeout error: {type(exc).__name__}: {exc}", exc_info=True)
    return _build_timeout_error_response(exc)


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    通用异常处理器
    捕获所有未处理的异常，返回 500 错误

    S-R5: 对特定异常类型返回更合适的状态码：
    - sqlite3.OperationalError → 503 Service Unavailable
    - asyncio.TimeoutError / TimeoutError → 504 Gateway Timeout
    - 其他异常 → 500 Internal Server Error

    SECURITY: [D6] 不在响应中暴露异常详情（防止信息泄露），
    仅在服务端日志中记录完整堆栈用于调试。
    """
    # S-R5: SQLite OperationalError → 503
    if isinstance(exc, sqlite3.OperationalError):
        logger.warning(f"SQLite OperationalError (via generic handler): {exc}", exc_info=True)
        return _build_sqlite_error_response(exc)

    # S-R5: Timeout 异常 → 504
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        logger.warning(f"Timeout error (via generic handler): {type(exc).__name__}: {exc}", exc_info=True)
        return _build_timeout_error_response(exc)

    # 其他异常 → 500
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "code": "internal_error",
            "message": "服务器内部错误，请稍后重试"
        }
    )
