import os
import json
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request

import logging
logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])

from .gpu import _get_gpu_device, _get_gpu_utilization
from .logs import log_operation


_ADVANCED_PARAMS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "advanced_params.json",
)


def _resolve_advanced_params_path() -> str:
    return os.path.abspath(_ADVANCED_PARAMS_CONFIG_PATH)


_GENERAL_SETTINGS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "general_settings.json",
)


def _resolve_general_settings_path() -> str:
    return os.path.abspath(_GENERAL_SETTINGS_CONFIG_PATH)


_GENERATION_DEFAULTS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "generation_defaults.json",
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


def _load_general_settings() -> dict:
    config_path = _resolve_general_settings_path()
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(_DEFAULT_GENERAL_SETTINGS)
                merged.update(data)
                return merged
    except Exception as e:
        logger.warning(f"Failed to load general settings: {e}")
    return dict(_DEFAULT_GENERAL_SETTINGS)


def _load_generation_defaults() -> dict:
    config_path = _resolve_generation_defaults_path()
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(_DEFAULT_GENERATION_DEFAULTS)
                merged.update(data)
                return merged
    except Exception as e:
        logger.warning(f"Failed to load generation defaults: {e}")
    return dict(_DEFAULT_GENERATION_DEFAULTS)


@router.get("/settings", summary="系统设置", description="获取当前系统配置")
def get_settings():
    try:
        from ...config import PRETRAINED_DIR, LORA_DIR
        from ...model_manager import get_persona_cache_stats
        from ...model_registry import registry
        from ...engines.voxcpm2_engine import fn_voxcpm_get_lora_state
    except Exception as e:
        logger.warning(f"Failed to import modules for settings: {e}")
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
        import torch
        from ...gpu_backend import GPUBackendManager, GPUBackend

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
            logger.debug(f"CPU memory check failed: {e}")

    try:
        import torch
        from ...gpu_backend import GPUBackendManager, GPUBackend

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device = _get_gpu_device()
            props = GPUBackendManager.get_device_properties(device)
            total = props.get('total_memory', 0)
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
                logger.warning(f"Settings GPU util check failed: {e}")
    except Exception as e:
        logger.debug(f"Non-critical error: {e}")

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
        logger.debug(f"Non-critical error: {e}")

    try:
        cache_stats = get_persona_cache_stats()
        settings["cache_hits"] = cache_stats.get("hits", 0)
        settings["cache_misses"] = cache_stats.get("misses", 0)
        settings["cache_rate"] = round(cache_stats.get("hit_rate", 0), 1)
        settings["cache_entries"] = cache_stats.get("size", 0)
        settings["cache_size_mb"] = cache_stats.get("size", 0) * 2
    except Exception as e:
        logger.debug(f"Non-critical error: {e}")

    try:
        settings["general_settings"] = _load_general_settings()
    except Exception:
        settings["general_settings"] = {}

    try:
        settings["generation_defaults"] = _load_generation_defaults()
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
        logger.warning(f"Failed to get advanced params: {e}")
        return {"status": "error", "message": str(e), "params": {}}


@router.post("/advanced_params", summary="更新高级参数", description="更新高级生成参数配置")
async def save_advanced_params(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    try:
        from ...engines.voxcpm2_engine import build_advanced_params, get_advanced_params as _get_params

        validated = {}
        # max_len and split_max_chars are now fixed values, removed from UI
        if "retry_badcase" in payload:
            validated["retry_badcase"] = bool(payload["retry_badcase"])
        if "retry_badcase_max_times" in payload:
            val = int(payload["retry_badcase_max_times"])
            validated["retry_badcase_max_times"] = max(0, min(10, val))
        if "retry_badcase_ratio_threshold" in payload:
            val = float(payload["retry_badcase_ratio_threshold"])
            validated["retry_badcase_ratio_threshold"] = max(1.0, min(20.0, val))
        if "trim_silence_vad" in payload:
            validated["trim_silence_vad"] = bool(payload["trim_silence_vad"])
        if "target_lufs" in payload:
            val = float(payload["target_lufs"])
            validated["target_lufs"] = max(-30.0, min(0.0, val))
        if "idle_timeout" in payload:
            val = int(payload["idle_timeout"])
            validated["idle_timeout"] = max(60, min(3600, val))

        new_config = build_advanced_params(**validated)

        config_path = _resolve_advanced_params_path()
        current = new_config.to_dict()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)

        log_operation("config", "Advanced params updated", validated)
        return {"status": "ok", "params": current}

    except Exception as e:
        logger.error(f"Failed to save advanced params: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/general_settings", summary="保存通用设置", description="保存通用设置配置")
async def save_general_settings(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    validated = {}
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
        existing = _load_general_settings()
        existing.update(validated)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        log_operation("config", "General settings updated", validated)
        return {"status": "ok", "settings": existing}
    except Exception as e:
        logger.error(f"Failed to save general settings: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/generation_defaults", summary="默认生成参数", description="获取默认生成参数配置")
def get_generation_defaults():
    try:
        params = _load_generation_defaults()
        return {"status": "ok", "params": params}
    except Exception as e:
        logger.warning(f"Failed to get generation defaults: {e}")
        return {"status": "error", "message": str(e), "params": dict(_DEFAULT_GENERATION_DEFAULTS)}


@router.post("/generation_defaults", summary="更新默认生成参数", description="更新默认生成参数配置")
async def save_generation_defaults(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    validated = {}
    if "default_sample_rate" in payload:
        val = int(payload["default_sample_rate"])
        validated["default_sample_rate"] = max(16000, min(48000, val))
    if "default_speed" in payload:
        val = float(payload["default_speed"])
        validated["default_speed"] = max(0.1, min(3.0, val))
    if "default_seed" in payload:
        validated["default_seed"] = int(payload["default_seed"])
    if "script_studio_silence_secs" in payload:
        val = float(payload["script_studio_silence_secs"])
        validated["script_studio_silence_secs"] = max(0.0, min(2.0, val))

    config_path = _resolve_generation_defaults_path()
    try:
        existing = _load_generation_defaults()
        existing.update(validated)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        log_operation("config", "Generation defaults updated", validated)
        return {"status": "ok", "params": existing}
    except Exception as e:
        logger.error(f"Failed to save generation defaults: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
