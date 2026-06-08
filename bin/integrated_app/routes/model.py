# -*- coding: utf-8 -*-
"""Model management routes: status, load, unload, preload, engine switch, LoRA.
Supports VoxCPM2 and IndexTTS 2.0 dual-engine architecture.
"""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi import Form

from ..model_manager import (
    load_voxcpm2, load_indextts2, unload_model, switch_engine, preload_model, get_preload_status,
    _gen_tracker, _progress_mgr,
)
from ..model_registry import registry
from ..gpu_utils import is_oom_error, free_gpu_memory
from ..engines.voxcpm2_engine import (
    fn_voxcpm_load_lora,
    fn_voxcpm_unload_lora,
    fn_voxcpm_set_lora_enabled,
    fn_voxcpm_get_lora_state,
)

router = APIRouter(prefix="/api/model", tags=["model"])
switch_router = APIRouter(tags=["model"])

logger = logging.getLogger("tts_multimodel")


@router.get("/status", summary="模型状态", description="获取当前模型加载状态和 GPU 资源信息")
async def model_status(request: Request):
    return JSONResponse({
        "loaded": registry.voxcpm_model is not None or registry.indextts2_engine is not None,
        "engine": registry.current_engine,
        "voxcpm2_loaded": registry.voxcpm_model is not None,
        "indextts2_loaded": registry.indextts2_engine is not None,
        "queue": _gen_tracker.status_text(),
    })


@router.post("/load", summary="加载模型", description="加载指定的 TTS 模型到 GPU")
async def load_model_endpoint(request: Request, engine: str = Form("voxcpm2")):
    MAX_RETRIES = 2
    try:
        loop = asyncio.get_running_loop()

        if engine == "indextts2":
            load_fn = load_indextts2
        else:
            load_fn = load_voxcpm2

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
                    return JSONResponse({"status": "ok", "message": results[-1], "engine": engine})
                return JSONResponse({"status": "error", "message": "Model load returned no status"})
            except Exception as e:
                last_error = e
                if is_oom_error(e):
                    logger.warning(
                        f"Model load attempt {attempt}/{MAX_RETRIES} failed due to OOM: {e}. "
                        f"Attempting to free GPU memory and retry..."
                    )
                    free_gpu_memory()
                    continue
                else:
                    raise

        logger.error(f"Model load failed after {MAX_RETRIES} retries: {last_error}")
        return JSONResponse({
            "status": "error",
            "message": f"Model load failed after {MAX_RETRIES} retry attempts (OOM): {last_error}"
        })
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@router.post("/unload", summary="卸载模型", description="从 GPU 卸载当前模型，释放显存")
async def unload_model_endpoint(request: Request):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, unload_model)
        return JSONResponse({"status": "ok", "message": "Model unloaded, VRAM released"})
    except Exception as e:
        logger.error(f"Model unload failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@router.post("/preload", summary="预加载模型", description="后台预加载模型到 GPU")
async def preload_model_endpoint(request: Request):
    """Fire-and-forget preload endpoint. Triggers background model preloading."""
    try:
        body = await request.json()
        engine = body.get("engine", "voxcpm2")
        size = body.get("size", "voxcpm2")

        preload_model(engine, size)
        return JSONResponse({
            "status": "ok",
            "message": f"Preload started for {engine} ({size})",
        })
    except Exception as e:
        logger.error(f"Model preload failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@router.get("/preload/status", summary="预加载状态", description="查询模型预加载进度")
async def preload_status_endpoint():
    """Get current preload task status."""
    try:
        status = get_preload_status()
        return JSONResponse({"status": "ok", "preload": status})
    except Exception as e:
        logger.error(f"Preload status check failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@switch_router.post("/api/switch_engine", summary="切换引擎")
async def switch_engine_endpoint(request: Request, engine: str = Form(...)):
    try:
        prev_engine = registry.current_engine

        request.app.state.engine_switch_state = {
            "active": True,
            "step": "开始切换引擎...",
            "status": "in_progress",
            "error": None,
            "engine": engine,
        }

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
        return JSONResponse({"status": "ok", "message": final_status, "engine": registry.current_engine})
    except Exception as e:
        logger.error(f"Engine switch failed: {e}")
        rolled_back_engine = registry.current_engine if registry.current_engine else prev_engine
        rollback_msg = ""
        if rolled_back_engine:
            rollback_msg = f"已自动回滚到 {rolled_back_engine} 引擎"

        request.app.state.engine_switch_state = {
            "active": True,
            "step": f"切换失败 - {rollback_msg}",
            "status": "failed",
            "error": str(e),
            "engine": rolled_back_engine,
        }

        error_detail = str(e)
        if rollback_msg:
            error_detail = f"{error_detail}\n\n{rollback_msg}"

        return JSONResponse({
            "status": "error",
            "message": error_detail,
            "engine": rolled_back_engine,
            "rolled_back": True,
        })


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
        logger.error(f"LoRA load failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


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
        logger.error(f"LoRA unload failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


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
        logger.error(f"LoRA toggle failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@router.get("/lora/state", summary="LoRA 状态", description="获取当前 LoRA 启用状态")
async def lora_state_endpoint():
    """Get the current LoRA state."""
    try:
        if registry.current_engine != "voxcpm2":
            return JSONResponse({"status": "ok", "state": {"loaded": False, "message": "LoRA is only available for VoxCPM2 engine"}})
        state = fn_voxcpm_get_lora_state()
        return JSONResponse({"status": "ok", "state": state})
    except Exception as e:
        logger.error(f"LoRA state check failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


@router.get("/lora/list", summary="LoRA 列表", description="列出可用的 LoRA 模型")
async def lora_list_endpoint():
    """List available LoRA checkpoints."""
    import os
    import json
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
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    info["base_model"] = cfg.get("base_model_name_or_path", "")
                    info["r"] = cfg.get("r", "")
                    info["lora_alpha"] = cfg.get("lora_alpha", "")
                except Exception:
                    pass
            checkpoints.append(info)
    return JSONResponse({"status": "ok", "checkpoints": checkpoints})
