import json
import logging
import os
from typing import Any

import aiofiles
from fastapi import APIRouter, Request

logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])

from .gpu import _get_gpu_device, _get_gpu_utilization  # noqa: E402
from .logs import log_operation  # noqa: E402

_ADVANCED_PARAMS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..",
    "advanced_params.json",
)


def _resolve_advanced_params_path() -> str:
    return os.path.abspath(_ADVANCED_PARAMS_CONFIG_PATH)


_GENERAL_SETTINGS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..",
    "general_settings.json",
)


def _resolve_general_settings_path() -> str:
    return os.path.abspath(_GENERAL_SETTINGS_CONFIG_PATH)


_GENERATION_DEFAULTS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..",
    "generation_defaults.json",
)


def _resolve_generation_defaults_path() -> str:
    return os.path.abspath(_GENERATION_DEFAULTS_CONFIG_PATH)


_DEFAULT_GENERATION_DEFAULTS = {
    "default_sample_rate": 24000,
    "default_speed": 1.0,
    "default_seed": 42,
    "script_studio_silence_secs": 0.4,
}


_DEFAULT_GENERAL_SETTINGS = {
    "language": "zh-CN",
    "theme": "dark",
    "auto_save": True,
    "auto_play": False,
    "notifications": True,
    "output_format": "wav",
}


async def _load_general_settings() -> dict:
    config_path = _resolve_general_settings_path()
    try:
        if os.path.exists(config_path):
            async with aiofiles.open(config_path, encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                merged = dict(_DEFAULT_GENERAL_SETTINGS)
                merged.update(data)
                return merged
    except Exception as e:
        logger.warning(f"加载通用设置失败: {e}")
    return dict(_DEFAULT_GENERAL_SETTINGS)


async def _load_generation_defaults() -> dict:
    config_path = _resolve_generation_defaults_path()
    try:
        if os.path.exists(config_path):
            async with aiofiles.open(config_path, encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                merged = dict(_DEFAULT_GENERATION_DEFAULTS)
                merged.update(data)
                return merged
    except Exception as e:
        logger.warning(f"加载默认生成参数失败: {e}")
    return dict(_DEFAULT_GENERATION_DEFAULTS)


@router.get("/settings", summary="系统设置", description="获取当前系统配置")
async def get_settings():
    try:
        from ...config import PRETRAINED_DIR
        from ...engines.voxcpm2_engine import fn_voxcpm_get_lora_state
        from ...model_manager import get_persona_cache_stats
    except Exception as e:
        logger.warning(f"导入设置模块失败: {e}")
        return {"status": "error", "message": str(e)}

    settings = {
        "status": "ok",
        "version": "2.0",
        "model_path": PRETRAINED_DIR,
        "device": "加载中...",
        "vram_used": "--",
        "vram_total": "--",
        "vram_free": "--",
        "vram_percent": 0,
        "gpu_util": "--",
        "memory_used": "--",
        "memory_total": "--",
        "memory_free": "--",
        "memory_percent": 0,
        "cpu_util": "--",
        "current_lora": "无",
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_rate": 0,
        "cache_entries": 0,
        "cache_size_mb": 0,
    }

    try:
        from ...gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device_name = GPUBackendManager.get_device_name()
            settings["device"] = f"{backend.value.upper()}: {device_name}"
        else:
            settings["device"] = "CPU"
    except Exception:
        settings["device"] = "CPU"

    # CPU 模式下获取内存数据
    if settings["device"] == "CPU":
        try:
            import psutil

            cpu_mem = psutil.virtual_memory()
            used = cpu_mem.total - cpu_mem.available
            free = cpu_mem.available
            settings["memory_used"] = f"{round(used / (1024**3), 2)} GB"
            settings["memory_total"] = f"{round(cpu_mem.total / (1024**3), 2)} GB"
            settings["memory_free"] = f"{round(free / (1024**3), 2)} GB"
            settings["memory_percent"] = round(used / cpu_mem.total * 100, 1) if cpu_mem.total > 0 else 0
            settings["cpu_util"] = f"{round(psutil.cpu_percent(interval=0), 1)}%"
        except Exception as e:
            logger.debug(f"CPU 内存检查失败: {e}")

    try:
        from ...gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device = _get_gpu_device()
            props = GPUBackendManager.get_device_properties(device)
            total = props.get("total_memory", 0)
            allocated = GPUBackendManager.memory_allocated(device)
            reserved = GPUBackendManager.memory_reserved(device)
            used = max(allocated, reserved)
            free = total - used

            settings["vram_used"] = f"{round(used / (1024**3), 2)} GB"
            settings["vram_total"] = f"{round(total / (1024**3), 2)} GB"
            settings["vram_free"] = f"{round(free / (1024**3), 2)} GB"
            settings["vram_percent"] = round(used / total * 100, 1) if total > 0 else 0

            try:
                gpu_util = _get_gpu_utilization()
                settings["gpu_util"] = f"{int(gpu_util)}%"
            except Exception as e:
                settings["gpu_util"] = "N/A"
                logger.warning(f"设置页面 GPU 利用率检查失败: {e}")
    except Exception as e:
        logger.debug(f"非关键错误: {e}")

    try:
        from ...model_registry import registry as _reg

        if _reg.current_engine == "voxcpm2":
            lora_state = fn_voxcpm_get_lora_state()
            if lora_state.get("loaded"):
                settings["current_lora"] = lora_state.get("name", "已加载")
            else:
                settings["current_lora"] = "无"
        else:
            settings["current_lora"] = "不适用"
    except Exception as e:
        logger.debug(f"非关键错误: {e}")

    try:
        cache_stats = get_persona_cache_stats()
        settings["cache_hits"] = cache_stats.get("hits", 0)
        settings["cache_misses"] = cache_stats.get("misses", 0)
        settings["cache_rate"] = round(cache_stats.get("hit_rate", 0), 1)
        settings["cache_entries"] = cache_stats.get("size", 0)
        settings["cache_size_mb"] = cache_stats.get("size", 0) * 2
    except Exception as e:
        logger.debug(f"非关键错误: {e}")

    try:
        settings["general_settings"] = await _load_general_settings()
    except Exception:
        settings["general_settings"] = {}

    try:
        settings["generation_defaults"] = await _load_generation_defaults()
    except Exception:
        settings["generation_defaults"] = dict(_DEFAULT_GENERATION_DEFAULTS)

    return settings


@router.get("/advanced_params", summary="高级参数", description="获取当前高级生成参数")
def get_advanced_params():
    try:
        from ...engines.voxcpm2_engine import get_advanced_params as _get_params

        params = _get_params()
        return {"status": "ok", "params": params}
    except Exception as e:
        logger.warning(f"获取高级参数失败: {e}")
        return {"status": "error", "message": str(e), "params": {}}


@router.post("/advanced_params", summary="更新高级参数", description="更新高级生成参数配置")
async def save_advanced_params(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    try:
        from ...engines.voxcpm2_engine import build_advanced_params

        validated: dict[str, Any] = {}
        # max_len and split_max_chars are now fixed values, removed from UI
        if "retry_badcase" in payload:
            validated["retry_badcase"] = bool(payload["retry_badcase"])
        if "retry_badcase_max_times" in payload:
            retry_badcase_max_times = int(payload["retry_badcase_max_times"])
            validated["retry_badcase_max_times"] = max(0, min(10, retry_badcase_max_times))
        if "retry_badcase_ratio_threshold" in payload:
            retry_badcase_ratio_threshold = float(payload["retry_badcase_ratio_threshold"])
            validated["retry_badcase_ratio_threshold"] = max(1.0, min(20.0, retry_badcase_ratio_threshold))
        if "trim_silence_vad" in payload:
            validated["trim_silence_vad"] = bool(payload["trim_silence_vad"])
        if "target_lufs" in payload:
            target_lufs = float(payload["target_lufs"])
            validated["target_lufs"] = max(-30.0, min(0.0, target_lufs))
        if "idle_timeout" in payload:
            idle_timeout = int(payload["idle_timeout"])
            validated["idle_timeout"] = max(60, min(3600, idle_timeout))

        new_config = build_advanced_params(**validated)

        config_path = _resolve_advanced_params_path()
        current = new_config.to_dict()
        async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(current, ensure_ascii=False, indent=2))

        log_operation("config", "Advanced params updated", validated)
        return {"status": "ok", "params": current}

    except Exception as e:
        logger.error(f"保存高级参数失败: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/general_settings", summary="保存通用设置", description="保存通用设置配置")
async def save_general_settings(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    validated: dict[str, Any] = {}
    if "language" in payload:
        validated["language"] = str(payload["language"])
    if "theme" in payload:
        validated["theme"] = str(payload["theme"])
    if "auto_save" in payload:
        validated["auto_save"] = bool(payload["auto_save"])
    if "auto_play" in payload:
        validated["auto_play"] = bool(payload["auto_play"])
    if "notifications" in payload:
        validated["notifications"] = bool(payload["notifications"])
    if "output_format" in payload:
        validated["output_format"] = str(payload["output_format"])

    config_path = _resolve_general_settings_path()
    try:
        existing = await _load_general_settings()
        existing.update(validated)
        async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(existing, ensure_ascii=False, indent=2))
        log_operation("config", "General settings updated", validated)
        return {"status": "ok", "settings": existing}
    except Exception as e:
        logger.error(f"保存通用设置失败: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/generation_defaults", summary="默认生成参数", description="获取默认生成参数配置")
async def get_generation_defaults():
    try:
        params = await _load_generation_defaults()
        return {"status": "ok", "params": params}
    except Exception as e:
        logger.warning(f"获取默认生成参数失败: {e}")
        return {"status": "error", "message": str(e), "params": dict(_DEFAULT_GENERATION_DEFAULTS)}


@router.post("/generation_defaults", summary="更新默认生成参数", description="更新默认生成参数配置")
async def save_generation_defaults(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    validated: dict[str, Any] = {}
    if "default_sample_rate" in payload:
        default_sample_rate = int(payload["default_sample_rate"])
        validated["default_sample_rate"] = max(16000, min(48000, default_sample_rate))
    if "default_speed" in payload:
        default_speed = float(payload["default_speed"])
        validated["default_speed"] = max(0.1, min(3.0, default_speed))
    if "default_seed" in payload:
        validated["default_seed"] = int(payload["default_seed"])
    if "script_studio_silence_secs" in payload:
        script_studio_silence_secs = float(payload["script_studio_silence_secs"])
        validated["script_studio_silence_secs"] = max(0.0, min(2.0, script_studio_silence_secs))

    config_path = _resolve_generation_defaults_path()
    try:
        existing = await _load_generation_defaults()
        existing.update(validated)
        async with aiofiles.open(config_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(existing, ensure_ascii=False, indent=2))
        log_operation("config", "Generation defaults updated", validated)
        return {"status": "ok", "params": existing}
    except Exception as e:
        logger.error(f"保存默认生成参数失败: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
