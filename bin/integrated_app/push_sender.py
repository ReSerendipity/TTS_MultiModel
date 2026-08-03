"""Web Push 消息发送器（Phase 3）。

架构说明：
    在生成完成时向所有已订阅的浏览器发送 Web Push 通知。
    使用 ``pywebpush`` 库实现 RFC 8030 + RFC 8291 + RFC 8292 协议栈
    （VAPID 签名 + aes128gcm 加密 + HTTP POST）。

    惰性导入策略：``pywebpush`` 可能在离线环境中未安装，首次调用时
    try-import，失败则记录警告并 no-op，不影响主应用运行。

推送流程：
    1. 从 ``push_db`` 读取所有订阅记录
    2. 对每个订阅：构造 payload JSON → ``webpush()`` 发送
    3. 发送失败（410 Gone / 404 Not Found）时自动删除过期订阅
    4. 全部异步执行，不阻塞生成响应

安全约束（AGENTS.md §7）：
    - VAPID 私钥从 config.yaml 读取，不硬编码
    - 不记录推送 payload 中的用户数据
    - 推送服务端点 URL 仅用于发送，不做其他用途

Refs:
    - pywebpush: https://github.com/web-push-libs/pywebpush
    - RFC 8030: Generic Event Delivery Using HTTP Push
    - RFC 8291: Message Encryption for WebPush
    - RFC 8292: VAPID Identification
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("tts_multimodel.push_sender")

# 惰性导入标记
_pywebpush_available: bool | None = None


def _check_pywebpush() -> bool:
    """检查 pywebpush 是否可用（惰性检测，结果缓存）。

    Returns:
        True 表示 pywebpush 已安装且可导入。
    """
    global _pywebpush_available
    if _pywebpush_available is not None:
        return _pywebpush_available
    try:
        import pywebpush  # noqa: F401

        _pywebpush_available = True
        logger.debug("pywebpush 可用")
    except ImportError:
        _pywebpush_available = False
        logger.warning("pywebpush 未安装，PWA 推送通知功能不可用。安装命令: pip install pywebpush")
    return _pywebpush_available


def _is_push_enabled() -> bool:
    """检查 PWA 推送是否已配置（VAPID 密钥已填写）。

    Returns:
        True 表示 vapid_public_key 和 vapid_private_key 都已填写。
    """
    from .config import get_config

    pwa = get_config().pydantic_config.pwa
    return bool(pwa.vapid_public_key and pwa.vapid_private_key)


def _send_push_to_subscription(
    subscription_info: dict[str, Any],
    payload: dict[str, Any],
    vapid_private_key: str,
    vapid_public_key: str,
    vapid_subject: str,
) -> bool:
    """向单个订阅发送推送消息（同步，在线程池中调用）。

    Args:
        subscription_info: 订阅信息 {endpoint, keys: {p256dh, auth}}。
        payload: 推送负载字典，将被 JSON 序列化。
        vapid_private_key: VAPID 私钥（PEM 格式）。
        vapid_public_key: VAPID 公钥（Base64URL）。
        vapid_subject: VAPID subject（mailto: 或 https:// URL）。

    Returns:
        True 表示发送成功，False 表示失败。
    """
    if not _check_pywebpush():
        return False

    from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]

    endpoint = subscription_info.get("endpoint", "")
    if not endpoint:
        return False

    try:
        payload_json = json.dumps(payload, ensure_ascii=False)
        webpush(
            subscription_info=subscription_info,
            data=payload_json,
            vapid_private_key=vapid_private_key,
            vapid_claims={
                "sub": vapid_subject or "mailto:noreply@tts-multimodel.local",
            },
            ttl=3600,  # 推送消息存活 1 小时
        )
        logger.debug("push_sender: 推送成功 endpoint=%s...", endpoint[:60])
        return True
    except WebPushException as exc:
        # 410 Gone / 404 Not Found：订阅已失效，自动清理
        status_code = getattr(exc, "response", None)
        if status_code is not None:
            http_status = getattr(status_code, "status_code", 0)
            if http_status in (404, 410):
                logger.info(
                    "push_sender: 订阅已失效 (%d)，自动清理 endpoint=%s...",
                    http_status,
                    endpoint[:60],
                )
                from .push_db import remove_subscription

                remove_subscription(endpoint)
                return False
        logger.warning("push_sender: WebPushException endpoint=%s... err=%s", endpoint[:60], exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("push_sender: 推送失败 endpoint=%s... err=%s", endpoint[:60], exc)
        return False


async def notify_generation_complete(
    text_preview: str,
    audio_url: str,
    engine: str,
    duration: float,
) -> None:
    """生成完成时向所有订阅者发送推送通知（异步，不阻塞响应）。

    Args:
        text_preview: 生成文本预览（前 50 字符）。
        audio_url: 音频访问 URL。
        engine: 引擎名称（voxcpm2 / indextts2）。
        duration: 生成耗时（秒）。
    """
    if not _is_push_enabled():
        return

    if not _check_pywebpush():
        return

    from .config import get_config
    from .push_db import get_all_subscriptions

    pwa = get_config().pydantic_config.pwa
    subscriptions = get_all_subscriptions()

    if not subscriptions:
        return

    # 构造推送 payload
    preview = text_preview[:50] + ("..." if len(text_preview) > 50 else "")
    payload: dict[str, Any] = {
        "type": "generation_complete",
        "title": "TTS 生成完成",
        "body": f"「{preview}」— {engine} ({duration:.1f}s)",
        "data": {
            "url": audio_url,
            "engine": engine,
            "duration": round(duration, 2),
        },
        "tag": "tts-generation",
        "requireInteraction": False,
    }

    vapid_private_key = pwa.vapid_private_key
    vapid_public_key = pwa.vapid_public_key
    vapid_subject = pwa.vapid_subject

    # 异步在线程池中执行推送（不阻塞事件循环）
    loop = asyncio.get_running_loop()

    async def _send_single(sub: dict[str, Any]) -> bool:
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {
                "p256dh": sub["p256dh"],
                "auth": sub["auth"],
            },
        }
        return await loop.run_in_executor(
            None,
            _send_push_to_subscription,
            subscription_info,
            payload,
            vapid_private_key,
            vapid_public_key,
            vapid_subject,
        )

    # 并发发送所有推送（最多 10 个并发）
    tasks = [_send_single(sub) for sub in subscriptions]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for r in results if r is True)
    fail_count = len(results) - success_count
    logger.info(
        "push_sender: 推送完成 — 成功 %d / 失败 %d / 总计 %d",
        success_count,
        fail_count,
        len(subscriptions),
    )
