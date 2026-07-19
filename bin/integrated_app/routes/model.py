"""Model management routes: status, load, unload, preload, engine switch, LoRA.
Supports VoxCPM2 and IndexTTS 2.0 dual-engine architecture.

重构说明 (S-R6):
- S-R6: 修复 L72 is_oom_error 错误模式 — 将 Exception(last_msg) 改为
        RuntimeError(last_msg)，启用 is_oom_error 对 RuntimeError 的
        额外检查路径（检查 "CUDA" + "memory"/"alloc" 关键字组合）
- S-R6: 错误消息脱敏 — 新增 _safe_error_message 辅助函数，对所有返回
        给客户端的错误消息进行脱敏（移除文件路径、限制长度、对特定异常
        类型返回友好提示），遵循 D6 永不信任原则
- S-R6: 日志增强 — 所有 except 块添加 exc_info=True，确保服务端日志
        记录完整堆栈用于调试
"""

import asyncio
import logging
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from ..engines.voxcpm2_engine import (
    fn_voxcpm_get_lora_state,
    fn_voxcpm_load_lora,
    fn_voxcpm_set_lora_enabled,
    fn_voxcpm_unload_lora,
)
from ..exceptions import EngineSwitchError, InsufficientVRAMError, TTSError
from ..gpu_utils import free_gpu_memory, is_oom_error
from ..model_manager import (
    _gen_tracker,
    get_preload_status,
    load_indextts2,
    load_voxcpm2,
    preload_model,
    switch_engine,
    unload_model,
)
from ..model_registry import registry

router = APIRouter(prefix="/api/model", tags=["model"])

logger = logging.getLogger("tts_multimodel")

# S-R6: 错误消息脱敏 — 匹配 Windows/Unix 文件路径
# SECURITY: [D6] 文件路径可能泄露服务器目录结构，需替换为 [PATH]
_SENSITIVE_PATH_PATTERN = re.compile(
    r"[A-Za-z]:\\[^\s\"'<>|*?]+|/(?:[^\s\"'<>|*?]+/)+[^\s\"'<>|*?]*"
)

# S-R6: 错误消息最大长度（字符）
_ERROR_MESSAGE_MAX_LENGTH = 200


def _safe_error_message(exc: Exception, max_length: int = _ERROR_MESSAGE_MAX_LENGTH) -> str:
    """REFACTOR: [S-R6] 对错误消息进行脱敏，避免向客户端泄露敏感信息。

    Security:
        [D6] 永不信任原则 — 错误消息可能包含文件路径、SQL 语句、
        堆栈细节等敏感信息。本函数：
        1. 对特定异常类型返回友好提示（FileNotFoundError, TimeoutError 等）
        2. 将文件路径替换为 [PATH]
        3. 限制消息长度，防止超长错误消息

    Args:
        exc: 异常对象。
        max_length: 返回消息的最大字符数。

    Returns:
        脱敏后的错误消息字符串。
    """
    if exc is None:
        return "未知错误"

    # 对特定异常类型返回友好提示
    if isinstance(exc, InsufficientVRAMError):
        return f"显存不足：{str(exc)[:max_length]}"
    if isinstance(exc, EngineSwitchError):
        return f"引擎切换失败：{str(exc)[:max_length]}"
    if isinstance(exc, TTSError):
        return str(exc)[:max_length]
    if isinstance(exc, FileNotFoundError):
        return "文件不存在或已被删除"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "操作超时，请稍后重试"
    if isinstance(exc, PermissionError):
        return "权限不足，无法访问所需资源"
    if isinstance(exc, OSError):
        # OSError 可能包含路径信息
        msg = str(exc)
        msg = _SENSITIVE_PATH_PATTERN.sub("[PATH]", msg)
        return f"系统错误：{msg[:max_length]}"

    # 通用处理：脱敏 + 限长
    msg = str(exc)
    msg = _SENSITIVE_PATH_PATTERN.sub("[PATH]", msg)
    if len(msg) > max_length:
        msg = msg[:max_length] + "..."
    return msg


@router.get("/status", summary="模型状态", description="获取当前模型加载状态和 GPU 资源信息")
async def model_status(request: Request):
    return JSONResponse(
        {
            "loaded": registry.voxcpm_model is not None or registry.indextts2_engine is not None,
            "engine": registry.current_engine,
            "voxcpm2_loaded": registry.voxcpm_model is not None,
            "indextts2_loaded": registry.indextts2_engine is not None,
            "queue": _gen_tracker.status_text(),
        }
    )


@router.post("/load", summary="加载模型", description="加载指定的 TTS 模型到 GPU")
async def load_model_endpoint(request: Request, engine: str = Form("voxcpm2")):
    MAX_RETRIES = 2
    try:
        loop = asyncio.get_running_loop()

        load_fn = load_indextts2 if engine == "indextts2" else load_voxcpm2

        def _run_load():
            """Run model loading in a thread to avoid blocking the event loop."""
            results = []
            gen = load_fn()
            for status_text, _, _, _ in gen:
                results.append(status_text)
            return results

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                results = await loop.run_in_executor(None, _run_load)
                if results:
                    last_msg = results[-1]
                    # Generator yields error status containing "失败" on load failure
                    if "失败" in last_msg or "error" in last_msg.lower():
                        logger.error(f"模型加载失败 (attempt {attempt}/{MAX_RETRIES}): {last_msg}")
                        # S-R6: 修复 is_oom_error 错误模式
                        # 原实现 is_oom_error(Exception(last_msg)) 只走通用字符串匹配路径，
                        # 改用 RuntimeError(last_msg) 以启用 is_oom_error 对 RuntimeError 的
                        # 额外检查路径（检查 "CUDA" + "memory"/"alloc" 关键字组合）
                        if attempt < MAX_RETRIES and is_oom_error(RuntimeError(last_msg)):
                            free_gpu_memory()
                            continue
                        # S-R6: 对状态文本也进行路径脱敏
                        safe_msg = _SENSITIVE_PATH_PATTERN.sub("[PATH]", last_msg)
                        return JSONResponse({"status": "error", "message": safe_msg, "engine": engine})
                    return JSONResponse({"status": "ok", "message": last_msg, "engine": engine})
                return JSONResponse({"status": "error", "message": "Model load returned no status"})
            except Exception as e:
                last_error = e
                if is_oom_error(e):
                    logger.warning(
                        f"Model load attempt {attempt}/{MAX_RETRIES} failed due to OOM: {e}. "
                        f"Attempting to free GPU memory and retry...",
                        exc_info=True,
                    )
                    free_gpu_memory()
                    continue
                else:
                    raise

        # S-R6: 对 last_error 脱敏后再返回
        safe_error = _safe_error_message(last_error) if last_error else "unknown error"
        logger.error(f"模型加载在 {MAX_RETRIES} 次重试后失败: {last_error}", exc_info=True)
        return JSONResponse(
            {"status": "error", "message": f"Model load failed after {MAX_RETRIES} retry attempts (OOM): {safe_error}"}
        )
    except Exception as e:
        logger.error(f"模型加载失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.post("/unload", summary="卸载模型", description="从 GPU 卸载当前模型，释放显存")
async def unload_model_endpoint(request: Request):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, unload_model)
        return JSONResponse({"status": "ok", "message": "Model unloaded, VRAM released"})
    except Exception as e:
        logger.error(f"模型卸载失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.post("/preload", summary="预加载模型", description="后台预加载模型到 GPU")
async def preload_model_endpoint(request: Request):
    """Fire-and-forget preload endpoint. Triggers background model preloading."""
    try:
        body = await request.json()
        engine = body.get("engine", "voxcpm2")
        size = body.get("size", "voxcpm2")

        preload_model(engine, size)
        return JSONResponse(
            {
                "status": "ok",
                "message": f"Preload started for {engine} ({size})",
            }
        )
    except Exception as e:
        logger.error(f"模型预加载失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.get("/preload/status", summary="预加载状态", description="查询模型预加载进度")
async def preload_status_endpoint():
    """Get current preload task status."""
    try:
        status = get_preload_status()
        return JSONResponse({"status": "ok", "preload": status})
    except Exception as e:
        logger.error(f"预加载状态查询失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.post("/switch", summary="切换引擎")
async def switch_engine_endpoint(request: Request, engine: str = Form(...)):
    prev_engine = registry.current_engine
    try:
        request.app.state.engine_switch_state = {
            "active": True,
            "step": "开始切换引擎...",
            "status": "in_progress",
            "error": None,
            "engine": engine,
        }

        from .sse import event_bus

        event_bus.notify()

        def _run_switch():
            results = []
            for status_text, _, _, _ in switch_engine(engine):
                request.app.state.engine_switch_state = {
                    "active": True,
                    "step": status_text,
                    "status": "in_progress",
                    "error": None,
                    "engine": engine,
                }
                event_bus.notify()
                results.append(status_text)
            return results[-1] if results else "done"

        loop = asyncio.get_running_loop()
        final_status = await loop.run_in_executor(None, _run_switch)

        request.app.state.engine_switch_state = {
            "active": True,
            "step": final_status,
            "status": "completed",
            "error": None,
            "engine": registry.current_engine,
        }
        event_bus.notify()
        return JSONResponse({"status": "ok", "message": final_status, "engine": registry.current_engine})
    except Exception as e:
        logger.error(f"引擎切换失败: {e}", exc_info=True)
        rolled_back_engine = registry.current_engine if registry.current_engine else prev_engine
        rollback_msg = ""
        if rolled_back_engine:
            rollback_msg = f"已自动回滚到 {rolled_back_engine} 引擎"

        request.app.state.engine_switch_state = {
            "active": True,
            "step": f"切换失败 - {rollback_msg}",
            "status": "failed",
            "error": _safe_error_message(e),  # S-R6: 脱敏后存入 state
            "engine": rolled_back_engine,
        }
        event_bus.notify()

        # S-R6: 脱敏错误详情
        safe_error = _safe_error_message(e)
        error_detail = safe_error
        if rollback_msg:
            error_detail = f"{error_detail}\n\n{rollback_msg}"

        return JSONResponse(
            {
                "status": "error",
                "message": error_detail,
                "engine": rolled_back_engine,
                "rolled_back": True,
            }
        )


@router.post("/lora/load", summary="加载 LoRA", description="加载 LoRA 权重到当前模型")
async def lora_load_endpoint(request: Request):
    """Load a LoRA adapter."""
    try:
        if registry.current_engine != "voxcpm2":
            return JSONResponse({"status": "error", "message": "LoRA is only available for VoxCPM2 engine"})
        body = await request.json()
        lora_path = body.get("lora_path", "")
        if not lora_path:
            return JSONResponse({"status": "error", "message": "lora_path is required"})
        success = fn_voxcpm_load_lora(lora_path)
        if success:
            return JSONResponse({"status": "ok", "message": f"LoRA loaded: {lora_path}"})
        return JSONResponse({"status": "error", "message": "LoRA load returned False"})
    except Exception as e:
        logger.error(f"LoRA 加载失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.post("/lora/unload", summary="卸载 LoRA", description="卸载当前 LoRA 权重")
async def lora_unload_endpoint(request: Request):
    """Unload the LoRA adapter."""
    try:
        if registry.current_engine != "voxcpm2":
            return JSONResponse({"status": "error", "message": "LoRA is only available for VoxCPM2 engine"})
        success = fn_voxcpm_unload_lora()
        if success:
            return JSONResponse({"status": "ok", "message": "LoRA unloaded"})
        return JSONResponse({"status": "error", "message": "LoRA unload returned False"})
    except Exception as e:
        logger.error(f"LoRA 卸载失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.post("/lora/toggle", summary="切换 LoRA", description="启用或禁用 LoRA 权重")
async def lora_toggle_endpoint(request: Request):
    """Enable or disable the LoRA adapter."""
    try:
        if registry.current_engine != "voxcpm2":
            return JSONResponse({"status": "error", "message": "LoRA is only available for VoxCPM2 engine"})
        body = await request.json()
        enabled = body.get("enabled", False)
        success = fn_voxcpm_set_lora_enabled(enabled)
        status = "enabled" if enabled else "disabled"
        if success:
            return JSONResponse({"status": "ok", "message": f"LoRA {status}"})
        return JSONResponse({"status": "error", "message": f"LoRA {status} failed"})
    except Exception as e:
        logger.error(f"LoRA 切换失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.get("/lora/state", summary="LoRA 状态", description="获取当前 LoRA 启用状态")
async def lora_state_endpoint():
    """Get the current LoRA state."""
    try:
        if registry.current_engine != "voxcpm2":
            return JSONResponse(
                {"status": "ok", "state": {"loaded": False, "message": "LoRA is only available for VoxCPM2 engine"}}
            )
        state = fn_voxcpm_get_lora_state()
        return JSONResponse({"status": "ok", "state": state})
    except Exception as e:
        logger.error(f"LoRA 状态查询失败: {e}", exc_info=True)
        # S-R6: 脱敏错误消息
        return JSONResponse({"status": "error", "message": _safe_error_message(e)})


@router.get("/lora/list", summary="LoRA 列表", description="列出可用的 LoRA 模型")
async def lora_list_endpoint():
    """List available LoRA checkpoints."""
    import json
    import os

    from ..config import LORA_DIR

    checkpoints = []
    if os.path.isdir(LORA_DIR):
        for name in sorted(os.listdir(LORA_DIR)):
            ckpt_dir = os.path.join(LORA_DIR, name)
            if not os.path.isdir(ckpt_dir):
                continue
            info = {"name": name, "path": ckpt_dir}
            config_path = os.path.join(ckpt_dir, "adapter_config.json")
            if os.path.isfile(config_path):
                try:
                    with open(config_path, encoding="utf-8") as f:
                        cfg = json.load(f)
                    info["base_model"] = cfg.get("base_model_name_or_path", "")
                    info["r"] = cfg.get("r", "")
                    info["lora_alpha"] = cfg.get("lora_alpha", "")
                except Exception:
                    pass
            checkpoints.append(info)
    return JSONResponse({"status": "ok", "checkpoints": checkpoints})
