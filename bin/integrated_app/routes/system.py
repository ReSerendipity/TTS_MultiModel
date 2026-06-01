# -*- coding: utf-8 -*-
"""System health monitoring and operation log endpoints."""

import os
import time
import json
import logging
import threading
import subprocess
from datetime import datetime
from collections import deque
from typing import List, Dict, Any, Optional

import psutil

from fastapi import APIRouter, Request

logger = logging.getLogger("tts_multimodel")

router = APIRouter(prefix="/api/system", tags=["system"])


def _get_gpu_device():
    """Get the GPU device index using unified backend manager."""
    import torch
    from ..gpu_backend import GPUBackendManager, GPUBackend
    
    if not GPUBackendManager.is_available():
        return 0
    
    backend = GPUBackendManager.detect_backend()
    
    try:
        device = GPUBackendManager.get_device()
        if isinstance(device, torch.device):
            return device.index if device.index is not None else 0
        return device
    except Exception:
        return 0

# Global NVML state with thread-safe caching
_nvml_state = {
    "handle": None,
    "initialized": False,
    "init_time": 0.0,
    "init_failed": False,
    "last_error": None,
    "device_index": 0,
}
_nvml_lock = threading.Lock()

# NVML cache duration: re-initialize after this many seconds to handle stale handles
_NVML_CACHE_TTL = 300  # 5 minutes


def _get_nvml_handle() -> Optional[Any]:
    """
    Get cached NVML handle with proper thread-safe initialization,
    error handling, and TTL-based cache expiration.

    NVML is initialized only once and the handle is cached for reuse.
    The cache expires after NVML_CACHE_TTL seconds to allow recovery
    from transient errors or driver updates.
    """
    global _nvml_state

    with _nvml_lock:
        current_time = time.time()

        # Check if we have a valid cached handle
        if (_nvml_state["initialized"] and
            _nvml_state["handle"] is not None and
            not _nvml_state["init_failed"]):
            # Check if cache has expired
            if current_time - _nvml_state["init_time"] < _NVML_CACHE_TTL:
                return _nvml_state["handle"]
            else:
                # Cache expired, will reinitialize
                logger.info("NVML handle cache expired, reinitializing...")
                _nvml_state["initialized"] = False
                _nvml_state["handle"] = None

        # Don't retry too quickly if initialization previously failed
        if _nvml_state["init_failed"]:
            last_failure_time = _nvml_state.get("failure_time", 0)
            if current_time - last_failure_time < 60:  # Wait 60 seconds before retrying failed init
                logger.debug(f"NVML init failed recently, skipping retry. Last error: {_nvml_state['last_error']}")
                return None
            else:
                # Reset failure state to allow retry
                logger.info("Retrying NVML initialization after cooldown period...")
                _nvml_state["init_failed"] = False

        # Initialize NVML and get device handle
        try:
            import pynvml

            # Initialize NVML library
            if not _nvml_state["initialized"]:
                try:
                    pynvml.nvmlInit()
                    logger.info("NVML library initialized successfully")
                except pynvml.NVMLError_LibraryNotLoaded:
                    # Already initialized, continue
                    logger.debug("NVML already initialized")
                except Exception as init_err:
                    logger.warning(f"NVML library initialization failed: {init_err}")
                    _nvml_state["init_failed"] = True
                    _nvml_state["failure_time"] = current_time
                    _nvml_state["last_error"] = str(init_err)
                    return None

                _nvml_state["initialized"] = True
                _nvml_state["init_time"] = current_time

            # Get GPU device index
            device_idx = _get_gpu_device()
            _nvml_state["device_index"] = device_idx

            # Get device handle
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(device_idx)
                _nvml_state["handle"] = handle
                logger.info(f"Successfully obtained NVML handle for GPU #{device_idx}")
            except Exception as handle_err:
                logger.warning(f"Failed to get NVML handle for GPU #{device_idx}: {handle_err}")
                # Try GPU #0 as fallback
                if device_idx != 0:
                    try:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        _nvml_state["handle"] = handle
                        _nvml_state["device_index"] = 0
                        logger.info("Successfully obtained NVML handle for GPU #0 as fallback")
                    except Exception as fallback_err:
                        logger.warning(f"Failed to get NVML handle for GPU #0 fallback: {fallback_err}")
                        _nvml_state["init_failed"] = True
                        _nvml_state["failure_time"] = current_time
                        _nvml_state["last_error"] = str(fallback_err)
                        return None
                else:
                    _nvml_state["init_failed"] = True
                    _nvml_state["failure_time"] = current_time
                    _nvml_state["last_error"] = str(handle_err)
                    return None

            return _nvml_state["handle"]

        except ImportError:
            logger.warning("pynvml not installed, GPU monitoring unavailable")
            _nvml_state["init_failed"] = True
            _nvml_state["failure_time"] = current_time
            _nvml_state["last_error"] = "pynvml not installed"
            return None
        except Exception as e:
            logger.error(f"Unexpected error during NVML initialization: {e}", exc_info=True)
            _nvml_state["init_failed"] = True
            _nvml_state["failure_time"] = current_time
            _nvml_state["last_error"] = str(e)
            return None


def _get_gpu_utilization_from_nvml() -> Optional[int]:
    """
    Get GPU utilization from NVML with proper error handling.

    Returns:
        GPU utilization percentage (0-100) or None if unavailable.
    """
    try:
        handle = _get_nvml_handle()
        if handle is None:
            logger.debug("NVML handle not available for GPU utilization")
            return None

        import pynvml
        util_rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        gpu_util = int(util_rates.gpu)
        logger.debug(f"GPU utilization from NVML: {gpu_util}%")
        return gpu_util

    except Exception as e:
        logger.warning(f"Failed to get GPU utilization from NVML: {e}")
        return None


def _get_gpu_utilization_from_nvidia_smi() -> Optional[int]:
    """
    Fallback method to get GPU utilization using nvidia-smi command.

    Returns:
        GPU utilization percentage (0-100) or None if unavailable.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        if result.returncode == 0 and result.stdout.strip():
            util_value = int(result.stdout.strip().split("\n")[0].strip())
            logger.debug(f"GPU utilization from nvidia-smi: {util_value}%")
            return util_value

        logger.debug(f"nvidia-smi returned empty or error output: {result.stderr}")
        return None

    except FileNotFoundError:
        logger.debug("nvidia-smi not found in PATH")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi command timed out")
        return None
    except Exception as e:
        logger.warning(f"Failed to get GPU utilization from nvidia-smi: {e}")
        return None


def _get_gpu_utilization() -> int:
    """
    Get GPU utilization percentage with multiple fallback methods.

    Tries backend-specific methods first, then falls back to vendor-specific
    commands, and finally returns 0 if all methods fail.

    Returns:
        GPU utilization percentage (0-100).
    """
    from ..gpu_backend import GPUBackendManager, GPUBackend
    
    backend = GPUBackendManager.detect_backend()
    
    # For NVIDIA CUDA backend, try NVML/nvidia-smi
    if backend == GPUBackend.CUDA:
        # Try NVML first
        nvml_util = _get_gpu_utilization_from_nvml()
        if nvml_util is not None:
            return nvml_util

        # Fallback to nvidia-smi
        smi_util = _get_gpu_utilization_from_nvidia_smi()
        if smi_util is not None:
            return smi_util
    
    # For other backends, vendor-specific tools may be needed
    # AMD: rocm-smi, Intel: intel_gpu_tools, etc.
    # For now, return 0 and rely on PyTorch memory metrics
    return 0


# Session start time
_SESSION_START = datetime.now().isoformat()

# Generation counter tracked independently
_generation_counter = {"total": 0, "success": 0, "failed": 0}
_counter_lock = threading.Lock()


def increment_generation(success=True):
    """Increment the generation counter. Call this from generation endpoints."""
    with _counter_lock:
        _generation_counter["total"] += 1
        if success:
            _generation_counter["success"] += 1
        else:
            _generation_counter["failed"] += 1


def get_generation_stats():
    """Return generation statistics."""
    with _counter_lock:
        return dict(_generation_counter)


# Operation log store (thread-safe circular buffer)
class OperationLog:
    def __init__(self, maxlen=200):
        self._logs: deque = deque(maxlen=maxlen)
        self._lock = threading.RLock()
        self._counter = 0

    def add(self, operation_type: str, message: str, details: dict = None):
        with self._lock:
            self._counter += 1
            entry = {
                "id": self._counter,
                "timestamp": datetime.now().isoformat(),
                "type": operation_type,
                "message": message,
                "details": details or {},
            }
            self._logs.appendleft(entry)

    def get_latest(self, limit=50, filter_type=None):
        with self._lock:
            logs = list(self._logs)
            if filter_type and filter_type != "all":
                logs = [log for log in logs if log["type"] == filter_type]
            return logs[:limit]


# Global operation log instance
_operation_log = OperationLog()


def get_operation_log() -> OperationLog:
    return _operation_log


def log_operation(operation_type: str, message: str, details: dict = None):
    """Log an operation to the system log."""
    _operation_log.add(operation_type, message, details)


@router.get("/health")
def get_health():
    """Return system health metrics including GPU, CPU, model status, and generation stats."""
    from ..monitor import get_health_monitor, HealthMonitor

    health_monitor = get_health_monitor()
    report = health_monitor.get_health_report()

    health: Dict[str, Any] = {
        "gpu": {"memory_used_mb": 0, "memory_total_mb": 0, "memory_percent": 0, "gpu_util": 0, "trend": "stable"},
        "cpu": {"memory_used_mb": 0, "memory_total_mb": 0, "percent": 0},
        "model": {
            "current_engine": "none",
            "model_size": "none",
            "status": report.get("model_status", "unknown"),
            "load_time": None,
        },
        "stats": {
            "total_generations": report.get("total_generations", 0),
            "total_errors": report.get("total_errors", 0),
            "total_oom_retries": report.get("total_oom_retries", 0),
            "average_time": 0.0,
            "success_rate": report.get("success_rate", 100.0),
            "session_start": _SESSION_START,
            "uptime_seconds": report.get("uptime_seconds", 0),
        },
    }

    # --- GPU Memory ---
    try:
        import torch
        from ..gpu_backend import GPUBackendManager, GPUBackend
        
        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            # Use unified GPU backend manager
            device = _get_gpu_device()
            props = GPUBackendManager.get_device_properties(device)
            total = props.get('total_memory', 0)
            allocated = GPUBackendManager.memory_allocated(device)
            reserved = GPUBackendManager.memory_reserved(device)
            used = max(allocated, reserved)
            health["gpu"]["memory_used_mb"] = round(used / (1024 * 1024), 1)
            health["gpu"]["memory_total_mb"] = round(total / (1024 * 1024), 1)
            if total > 0:
                health["gpu"]["memory_percent"] = round(
                    used / total * 100, 2
                )
            # Use unified GPU utilization retrieval with fallback
            try:
                gpu_util = _get_gpu_utilization()
                health["gpu"]["gpu_util"] = round(float(gpu_util), 2)
                logger.debug(f"GPU utilization: {gpu_util}%")
            except Exception as e:
                health["gpu"]["gpu_util"] = 0
                logger.warning(f"GPU utilization check failed: {e}")
            # Also record VRAM to health monitor for leak detection
            try:
                health_monitor.record_vram_usage(health["gpu"]["memory_used_mb"])
            except Exception:
                pass
    except ImportError:
        # torch not available, try WMI as fallback
        try:
            import wmi
            c = wmi.WMI()
            for gpu in c.Win32_VideoController():
                if "NVIDIA" in gpu.Name or "AMD" in gpu.Name or "Radeon" in gpu.Name:
                    if gpu.AdapterRAM:
                        total_bytes = int(gpu.AdapterRAM)
                        health["gpu"]["memory_total_mb"] = round(total_bytes / (1024 * 1024), 1)
                        health["gpu"]["memory_used_mb"] = 0
                        health["gpu"]["memory_percent"] = 0
                    break
        except ImportError:
            pass
    except Exception as e:
        logger.debug(f"GPU health check failed: {e}")

    # If still no GPU data, try nvidia-smi as final fallback
    if health["gpu"]["memory_total_mb"] == 0:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                if len(parts) >= 2:
                    total_mb = float(parts[0].strip())
                    used_mb = float(parts[1].strip())
                    health["gpu"]["memory_used_mb"] = round(used_mb, 1)
                    health["gpu"]["memory_total_mb"] = round(total_mb, 1)
                    if total_mb > 0:
                        health["gpu"]["memory_percent"] = round(used_mb / total_mb * 100, 2)
                    if len(parts) >= 3:
                        health["gpu"]["gpu_util"] = round(float(parts[2].strip()), 2)
                    else:
                        health["gpu"]["gpu_util"] = 0
                    # Also record VRAM to health monitor
                    try:
                        health_monitor.record_vram_usage(health["gpu"]["memory_used_mb"])
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"nvidia-smi GPU check failed: {e}")

    # --- CPU Memory ---
    try:
        cpu_mem = psutil.virtual_memory()
        health["cpu"]["memory_used_mb"] = round(
            (cpu_mem.total - cpu_mem.available) / (1024 * 1024), 1
        )
        health["cpu"]["memory_total_mb"] = round(cpu_mem.total / (1024 * 1024), 1)
        health["cpu"]["percent"] = round(psutil.cpu_percent(interval=0), 1)
    except Exception as e:
        logger.debug(f"CPU health check failed: {e}")

    # --- Model Status ---
    try:
        from ..model_manager import (
            current_engine,
            current_type,
            current_size,
            _progress_mgr,
            _gen_tracker,
            get_persona_cache_stats,
        )

        engine_name = current_engine or "none"
        if engine_name == "voxcpm2":
            engine_display = "VoxCPM2"
        else:
            engine_display = engine_name

        health["model"]["current_engine"] = engine_display
        health["model"]["model_size"] = current_size or "none"
        health["model"]["status"] = "ready" if current_type else "not_loaded"
        health["model"]["load_time"] = _SESSION_START

        if "gpu" in report:
            health["gpu"]["trend"] = report["gpu"].get("trend", "stable")
            if "leak_warning" in report["gpu"]:
                health["gpu"]["leak_warning"] = report["gpu"]["leak_warning"]

        # --- Generation Stats ---
        gen_stats = get_generation_stats()
        health["stats"]["total_generations"] = gen_stats["total"]
        health["stats"]["average_time"] = round(_gen_tracker.avg_gen_time, 1)
        total = gen_stats["total"]
        health["stats"]["success_rate"] = round(
            (gen_stats["success"] / total * 100) if total > 0 else 100.0, 1
        )

        # --- Persona Cache Stats ---
        try:
            cache_stats = get_persona_cache_stats()
            health["cache"] = {
                "hit_rate": cache_stats["hit_rate"],
                "hits": cache_stats["hits"],
                "misses": cache_stats["misses"],
                "size": cache_stats["size"],
                "maxsize": cache_stats["maxsize"],
            }
        except Exception as e:
            logger.debug(f"Cache stats check failed: {e}")
            health["cache"] = {"hit_rate": 0.0, "hits": 0, "misses": 0, "size": 0, "maxsize": 0}
    except Exception as e:
        logger.debug(f"Model health check failed: {e}")
        # Still provide default cache stats even if model check fails
        if "cache" not in health:
            health["cache"] = {"hit_rate": 0.0, "hits": 0, "misses": 0, "size": 0, "maxsize": 0}

    return health


@router.get("/logs")
def get_logs(limit: int = 50, filter_type: str = "all"):
    """Return latest operation logs, optionally filtered by type."""
    valid_types = {"all", "generation", "model", "config"}
    if filter_type not in valid_types:
        filter_type = "all"

    logs = _operation_log.get_latest(limit=limit, filter_type=filter_type)
    return {"logs": logs, "total": len(logs)}


# Settings page data endpoint
@router.get("/settings")
def get_settings():
    """Return settings page data including model path, device, VRAM, LoRA, cache stats."""
    try:
        from ..config import PRETRAINED_DIR, LORA_DIR
        from ..model_manager import current_engine, get_persona_cache_stats
        from ..engines.voxcpm2_engine import fn_voxcpm_get_lora_state
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
        "current_lora": "无",
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_rate": 0,
        "cache_entries": 0,
        "cache_size_mb": 0,
    }
    
    # Device info
    try:
        import torch
        from ..gpu_backend import GPUBackendManager, GPUBackend
        
        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device_name = GPUBackendManager.get_device_name()
            settings["device"] = f"{backend.value.upper()}: {device_name}"
        else:
            settings["device"] = "CPU"
    except Exception:
        settings["device"] = "CPU"
    
    # VRAM info
    try:
        import torch
        from ..gpu_backend import GPUBackendManager, GPUBackend
        
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
            
            # Get GPU utilization with fallback methods
            try:
                gpu_util = _get_gpu_utilization()
                settings["gpu_util"] = f"{int(gpu_util)}%"
            except Exception as e:
                settings["gpu_util"] = "N/A"
                logger.warning(f"Settings GPU util check failed: {e}")
    except Exception:
        pass
    
    # LoRA state
    try:
        lora_state = fn_voxcpm_get_lora_state()
        if lora_state.get("loaded"):
            settings["current_lora"] = lora_state.get("name", "已加载")
        else:
            settings["current_lora"] = "无"
    except Exception:
        pass
    
    # Cache stats
    try:
        cache_stats = get_persona_cache_stats()
        settings["cache_hits"] = cache_stats.get("hits", 0)
        settings["cache_misses"] = cache_stats.get("misses", 0)
        settings["cache_rate"] = round(cache_stats.get("hit_rate", 0), 1)
        settings["cache_entries"] = cache_stats.get("size", 0)
        # Estimate cache size (rough approximation)
        settings["cache_size_mb"] = cache_stats.get("size", 0) * 2  # ~2MB per entry
    except Exception:
        pass

    return settings


# --- Advanced Generation Parameters ---

_ADVANCED_PARAMS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "advanced_params.json",
)


def _resolve_advanced_params_path() -> str:
    """Resolve the absolute path for the advanced params config file."""
    return os.path.abspath(_ADVANCED_PARAMS_CONFIG_PATH)


@router.get("/advanced_params")
def get_advanced_params():
    """Return the current advanced generation parameters."""
    try:
        from ..engines.voxcpm2_engine import get_advanced_params as _get_params
        params = _get_params()
        return {"status": "ok", "params": params}
    except Exception as e:
        logger.warning(f"Failed to get advanced params: {e}")
        return {"status": "error", "message": str(e), "params": {}}


@router.post("/advanced_params")
async def save_advanced_params(request: Request):
    """Save advanced generation parameters to config file and update runtime."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    try:
        from ..engines.voxcpm2_engine import update_advanced_params as _update_params, get_advanced_params as _get_params

        # Validate and sanitize input
        validated = {}
        if "max_len" in payload:
            val = int(payload["max_len"])
            validated["max_len"] = max(100, min(10000, val))
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

        # Update runtime params
        _update_params(validated)

        # Persist to config file
        config_path = _resolve_advanced_params_path()
        current = _get_params()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)

        log_operation("config", "Advanced params updated", validated)
        return {"status": "ok", "params": current}

    except Exception as e:
        logger.error(f"Failed to save advanced params: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
