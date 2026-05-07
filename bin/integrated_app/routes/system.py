# -*- coding: utf-8 -*-
"""System health monitoring and operation log endpoints."""

import os
import time
import json
import logging
import threading
from datetime import datetime
from collections import deque
from typing import List, Dict, Any

import psutil

from fastapi import APIRouter

logger = logging.getLogger("tts_multimodel")

router = APIRouter(prefix="/api/system", tags=["system"])


def _get_gpu_device():
    """Get the NVIDIA GPU device index without importing model_manager."""
    import torch
    if not torch.cuda.is_available():
        return 0
    for i in range(torch.cuda.device_count()):
        try:
            props = torch.cuda.get_device_properties(i)
            name_lower = props.name.lower()
            if any(k in name_lower for k in ("nvidia", "geforce", "rtx", "gtx", "quadro", "tesla")):
                return i
        except Exception:
            continue
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
        "gpu": {"memory_used_mb": 0, "memory_total_mb": 0, "memory_percent": 0, "trend": "stable"},
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
        if torch.cuda.is_available():
            # Use direct torch calls to avoid importing model_manager
            device = _get_gpu_device()
            total = torch.cuda.get_device_properties(device).total_memory
            allocated = torch.cuda.memory_allocated(device)
            reserved = torch.cuda.memory_reserved(device)
            used = max(allocated, reserved)
            health["gpu"]["memory_used_mb"] = round(used / (1024 * 1024), 1)
            health["gpu"]["memory_total_mb"] = round(total / (1024 * 1024), 1)
            if total > 0:
                health["gpu"]["memory_percent"] = round(
                    used / total * 100, 2
                )
            # Try to get GPU utilization via pynvml
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(device if isinstance(device, int) else 0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                health["gpu"]["gpu_util"] = round(util.gpu, 2)
                pynvml.nvmlShutdown()
            except Exception:
                health["gpu"]["gpu_util"] = 0
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
            import subprocess
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
        from ..config import PRETRAINED_MODEL_DIR, LORA_DIR
        from ..model_manager import current_engine, get_persona_cache_stats
        from ..engines.voxcpm2_engine import fn_voxcpm_get_lora_state
    except Exception as e:
        logger.warning(f"Failed to import modules for settings: {e}")
        return {"status": "error", "message": "Modules not loaded yet"}

    settings = {
        "status": "ok",
        "version": "2.0",
        "model_path": PRETRAINED_MODEL_DIR,
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
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            settings["device"] = f"CUDA: {device_name}"
        else:
            settings["device"] = "CPU"
    except Exception:
        settings["device"] = "CPU"
    
    # VRAM info
    try:
        import torch
        if torch.cuda.is_available():
            device = 0
            total = torch.cuda.get_device_properties(device).total_memory
            allocated = torch.cuda.memory_allocated(device)
            reserved = torch.cuda.memory_reserved(device)
            used = max(allocated, reserved)
            free = total - used
            
            settings["vram_used"] = f"{round(used / (1024**3), 2)} GB"
            settings["vram_total"] = f"{round(total / (1024**3), 2)} GB"
            settings["vram_free"] = f"{round(free / (1024**3), 2)} GB"
            settings["vram_percent"] = round(used / total * 100, 1)
            settings["gpu_util"] = "--"  # Would need nvidia-ml-py for this
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
