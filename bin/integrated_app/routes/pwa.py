"""PWA 推送订阅 API 路由（Phase 3）。

架构说明：
    提供 Web Push 订阅管理的 RESTful 端点，供前端 ``pwa.js`` 在
    用户授权推送后注册订阅、取消订阅、查询状态。

    所有写操作（POST/DELETE）受 CSRF 中间件保护，前端必须携带
    ``X-CSRF-Token`` 请求头。

端点列表：
    - ``POST /api/pwa/push/subscribe`` — 注册推送订阅
    - ``DELETE /api/pwa/push/subscribe`` — 取消推送订阅
    - ``GET /api/pwa/push/status`` — 查询推送功能状态 + 订阅数

Refs:
    - MDN: PushManager.subscribe()
    - RFC 8030: Generic Event Delivery Using HTTP Push
    - docs/STAGE_E_PWA_FEASIBILITY.md §7.3
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import get_config

logger = logging.getLogger("tts_multimodel.pwa_routes")

router = APIRouter(prefix="/api/pwa", tags=["pwa"])


class PushSubscription(BaseModel):
    """Web Push 订阅信息（来自浏览器 PushManager.subscribe()）。

    Attributes:
        endpoint: 推送服务端点 URL（FCM / Mozilla / Apple 等）。
        keys: 浏览器加密密钥对。
            p256dh: ECDH P-256 公钥（Base64URL），用于 payload 加密。
            auth: 认证密钥（Base64URL），用于 HKDF 密钥派生。
    """

    endpoint: str = Field(..., description="推送服务端点 URL")
    keys: dict[str, str] = Field(..., description="加密密钥 {p256dh, auth}")


@router.post("/push/subscribe", summary="注册推送订阅")
async def subscribe_push(request: Request, subscription: PushSubscription) -> JSONResponse:
    """注册 Web Push 订阅。

    前端在 ``PushManager.subscribe()`` 成功后调用本端点，将订阅信息
    发送到后端持久化。后续生成完成时，后端将向该 endpoint 发送推送。

    Args:
        request: FastAPI 请求对象（获取 User-Agent）。
        subscription: 浏览器 PushSubscription 对象。

    Returns:
        JSON ``{"status": "ok"}`` 成功；``{"status": "error", "message": ...}`` 失败。
    """
    from ..push_db import add_subscription

    p256dh = subscription.keys.get("p256dh", "")
    auth = subscription.keys.get("auth", "")
    user_agent = request.headers.get("user-agent", "")

    success = add_subscription(
        endpoint=subscription.endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=user_agent,
    )

    if success:
        return JSONResponse(
            content={"status": "ok", "message": "Push subscription saved"},
            status_code=200,
        )
    return JSONResponse(
        content={"status": "error", "message": "Failed to save subscription"},
        status_code=500,
    )


@router.delete("/push/subscribe", summary="取消推送订阅")
async def unsubscribe_push(subscription: PushSubscription) -> JSONResponse:
    """取消 Web Push 订阅。

    前端在 ``PushSubscription.unsubscribe()`` 成功后调用本端点，
    从后端数据库中删除对应订阅记录。

    Args:
        subscription: 包含 endpoint 的订阅信息。

    Returns:
        JSON ``{"status": "ok"}`` 成功。
    """
    from ..push_db import remove_subscription

    success = remove_subscription(subscription.endpoint)
    if success:
        return JSONResponse(
            content={"status": "ok", "message": "Push subscription removed"},
            status_code=200,
        )
    return JSONResponse(
        content={"status": "error", "message": "Failed to remove subscription"},
        status_code=500,
    )


@router.get("/push/status", summary="查询推送功能状态")
async def push_status() -> dict[str, Any]:
    """查询 PWA 推送功能状态和订阅统计。

    Returns:
        - ``enabled`` (bool): VAPID 密钥是否已配置
        - ``subscription_count`` (int): 当前活跃订阅数
        - ``vapid_public_key`` (str): VAPID 公钥（前端订阅用）
    """
    from ..push_db import get_subscription_count

    pwa = get_config().pydantic_config.pwa
    enabled = bool(pwa.vapid_public_key and pwa.vapid_private_key)

    return {
        "enabled": enabled,
        "subscription_count": get_subscription_count() if enabled else 0,
        "vapid_public_key": pwa.vapid_public_key if enabled else "",
    }
