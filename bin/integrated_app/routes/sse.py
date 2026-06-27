"""统一 SSE 事件流端点

将原先的 5 个独立 SSE 轮询端点合并为单一 /api/sse/events 端点，
通过 event 字段区分消息类型，减少前端长连接数量和后端轮询开销。

事件类型：
  - progress:     生成进度更新（JSON 格式，含 HTML 进度条）
  - complete:     生成完成通知
  - status:       模型/系统状态更新
  - engine_switch: 引擎切换状态
  - cancelled:    生成取消通知
  - time_estimate: 时间估算更新
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("tts_multimodel.sse")

router = APIRouter(tags=["sse"])


class SSEEventBus:
    """SSE 事件总线 - 使用 asyncio.Event 通知机制替代定时轮询

    当 progress_mgr 或 engine_switch 状态变化时，通过 notify() 唤醒
    所有在 wait() 上阻塞的 SSE 连接，实现即时推送而非定时轮询。
    """

    def __init__(self):
        self._event = asyncio.Event()
        self._loop = None

    def _get_loop(self):
        """获取当前事件循环，缓存以供非 asyncio 线程使用。"""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    self._loop = asyncio.get_event_loop()
                except RuntimeError:
                    self._loop = None
        return self._loop

    def notify(self):
        """通知所有等待的 SSE 连接有新事件。

        线程安全：可从非 asyncio 线程（如线程池中的生成线程）调用。
        """
        loop = self._get_loop()
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._event.set)
            # 短暂延迟后清除，允许下一轮等待
            loop.call_later(0.05, self._event.clear)
        else:
            # 如果无法获取事件循环，直接设置（降级处理）
            self._event.set()
            try:
                loop.call_later(0.05, self._event.clear)
            except Exception:
                self._event.clear()

    async def wait(self, timeout: float = 1.0):
        """等待事件通知，带超时。

        Args:
            timeout: 超时时间（秒），超时后返回 False。

        Returns:
            True 如果收到事件通知，False 如果超时。
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False


# 全局事件总线实例
event_bus = SSEEventBus()


def _format_time_estimate(seconds: float, lang: str = "zh") -> str:
    """Format seconds into human-readable time estimate."""
    from ..i18n import t

    if seconds < 10:
        return t("sse_time_few_seconds", lang) if lang != "zh" else "几秒后完成"
    elif seconds < 60:
        about = t("sse_time_about", lang) if lang != "zh" else "约"
        unit_sec = t("sse_time_seconds", lang) if lang != "zh" else "秒"
        return f"{about} {int(seconds)} {unit_sec}"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        about = t("sse_time_about", lang) if lang != "zh" else "约"
        unit_min = t("sse_time_minutes", lang) if lang != "zh" else "分"
        unit_sec = t("sse_time_seconds", lang) if lang != "zh" else "秒"
        return f"{about} {mins} {unit_min} {secs} {unit_sec}"


@router.get("/api/sse/events", summary="SSE 事件流", description="Server-Sent Events 实时事件推送端点")
async def sse_events(request: Request):
    """统一 SSE 事件流端点。

    前端通过单一 EventSource 连接此端点，根据 event 字段分发处理。
    使用 asyncio.Event 通知机制，状态变化时即时推送，空闲时降频等待。
    """
    from ..config import get_config
    from ..i18n import get_lang
    from ..i18n import t as i18n_t
    from ..model_manager import (
        _gen_tracker,
        _progress_mgr,
    )
    from ..model_registry import registry

    config = get_config()
    sse_cfg = config.pydantic_config.sse

    lang = get_lang(request)

    async def event_stream():
        gen_start_time = None
        last_depth = 0
        idle_count = 0
        last_heartbeat = time.time()

        try:
            while True:
                if await request.is_disconnected():
                    break

                # ---- progress 事件 (原 /sse/progress, 0.5s 轮询) ----
                progress_status = _progress_mgr.get_status() if _progress_mgr else {}
                if progress_status.get("is_active", False):
                    html = _progress_mgr.get_progress_html()
                    # 统一发送 JSON 格式
                    progress_data = json.dumps(
                        {
                            "html": html or "",
                            "phase": progress_status.get("phase", ""),
                            "progress": int(
                                progress_status.get("current_segment", 0)
                                / max(progress_status.get("total_segments", 1), 1)
                                * 100
                            )
                            if progress_status.get("total_segments", 1) > 0
                            else 0,
                            "speed": "",
                            "remaining": "",
                        },
                        ensure_ascii=False,
                    )
                    yield f"event: progress\ndata: {progress_data}\n\n"
                    if progress_status.get("is_complete", False):
                        yield "event: complete\ndata: done\n\n"
                        await asyncio.sleep(1)
                        _progress_mgr.reset()
                        event_bus.notify()

                # ---- cancelled 事件 (原 /sse/cancel, 0.5s 轮询) ----
                if progress_status.get("is_cancelled", False):
                    data = json.dumps(
                        {
                            "status": "cancelled",
                            "message": i18n_t("sse_generation_cancelled", lang),
                        },
                        ensure_ascii=False,
                    )
                    yield f"event: cancelled\ndata: {data}\n\n"

                # ---- status 事件 (原 /sse/status, 2s 轮询) ----
                tracker_info = _gen_tracker.get_info() if _gen_tracker else {}
                status_text = tracker_info.get("status_text", i18n_t("sse_status_idle", lang))
                eng = registry.current_engine or "none"
                mtype = registry.current_type or "none"
                msize = registry.current_size or "none"
                status_data = json.dumps(
                    {
                        "status_text": status_text,
                        "engine": eng,
                        "model_type": mtype,
                        "model_size": msize,
                        "model_loaded": registry.model_loaded,
                    },
                    ensure_ascii=False,
                )
                yield f"event: status\ndata: {status_data}\n\n"

                # ---- engine_switch 事件 (原 /sse/engine_switch, 0.5s 轮询) ----
                switch_state = getattr(request.app.state, "engine_switch_state", None)
                if switch_state is None:
                    es_data = json.dumps(
                        {
                            "active": False,
                            "step": "",
                            "status": "idle",
                            "engine": "",
                            "model_size": "None",
                        },
                        ensure_ascii=False,
                    )
                    yield f"event: engine_switch\ndata: {es_data}\n\n"
                else:
                    step = switch_state.get("step", "")
                    status = switch_state.get("status", "in_progress")
                    error = switch_state.get("error", None)
                    engine = switch_state.get("engine", "")
                    from ..model_registry import ENGINE_DISPLAY_NAMES

                    default_size = ENGINE_DISPLAY_NAMES.get(registry.current_engine, registry.current_engine or "None")
                    model_size = switch_state.get("model_size", default_size)
                    es_data = json.dumps(
                        {
                            "active": True,
                            "step": step,
                            "status": status,
                            "error": error,
                            "engine": engine,
                            "model_size": model_size,
                        },
                        ensure_ascii=False,
                    )
                    yield f"event: engine_switch\ndata: {es_data}\n\n"
                    if status in ("completed", "failed") and hasattr(request.app.state, "engine_switch_state"):
                        del request.app.state.engine_switch_state

                # ---- time_estimate 事件 (原 /sse/time_estimate, 1s 轮询) ----
                if _gen_tracker:
                    current_depth = tracker_info.get("queue_depth", 0)
                    if current_depth > 0:
                        if last_depth == 0:
                            gen_start_time = time.time()
                        remaining = _gen_tracker.estimate_wait()
                        elapsed = time.time() - gen_start_time if gen_start_time else 0
                        est_text = _format_time_estimate(remaining, lang)
                        te_data = json.dumps(
                            {
                                "status": "generating",
                                "elapsed": round(elapsed, 1),
                                "remaining": round(remaining, 1),
                                "total_est": round(remaining + elapsed, 1),
                                "text": est_text,
                            },
                            ensure_ascii=False,
                        )
                        yield f"event: time_estimate\ndata: {te_data}\n\n"
                    else:
                        if last_depth > 0 and gen_start_time:
                            actual = time.time() - gen_start_time
                            te_data = json.dumps(
                                {
                                    "status": "complete",
                                    "actual": round(actual, 1),
                                    "text": i18n_t("sse_generation_complete", lang),
                                },
                                ensure_ascii=False,
                            )
                            yield f"event: time_estimate\ndata: {te_data}\n\n"
                            gen_start_time = None
                        else:
                            te_data = json.dumps(
                                {
                                    "status": "idle",
                                    "text": tracker_info.get("status_text", i18n_t("sse_status_idle", lang)),
                                },
                                ensure_ascii=False,
                            )
                            yield f"event: time_estimate\ndata: {te_data}\n\n"
                    last_depth = current_depth

                # ---- 心跳机制 ----
                if time.time() - last_heartbeat >= sse_cfg.heartbeat_interval:
                    yield "event: heartbeat\ndata: {}\n\n"
                    last_heartbeat = time.time()

                # ---- 计算等待间隔 ----
                has_active = False
                if progress_status.get("is_active", False):
                    has_active = True
                if _gen_tracker and tracker_info.get("queue_depth", 0) > 0:
                    has_active = True
                switch_state = getattr(request.app.state, "engine_switch_state", None)
                if switch_state is not None:
                    has_active = True

                if has_active:
                    idle_count = 0
                    interval = sse_cfg.active_interval
                else:
                    idle_count += 1
                    interval = min(
                        sse_cfg.idle_base_interval + idle_count * sse_cfg.idle_step, sse_cfg.idle_max_interval
                    )

                # ---- 使用 event_bus.wait() 替代 asyncio.sleep() ----
                # 有事件通知时立即唤醒，无事件时等待超时
                await event_bus.wait(timeout=interval)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            try:
                error_data = json.dumps(
                    {
                        "status": "error",
                        "message": "SSE 连接异常，请刷新页面重试",
                    },
                    ensure_ascii=False,
                )
                yield f"event: error\ndata: {error_data}\n\n"
            except Exception:
                pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")
