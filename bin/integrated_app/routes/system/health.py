import subprocess
import threading
from datetime import datetime
from collections import deque
from typing import List, Dict, Any, Optional

import psutil

from fastapi import APIRouter

import logging
logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])

from .gpu import _get_gpu_device, _get_gpu_utilization

_SESSION_START = datetime.now().isoformat()

_generation_counter = {"total": 0, "success": 0, "failed": 0}
_counter_lock = threading.Lock()


def increment_generation(success=True):
    with _counter_lock:
        _generation_counter["total"] += 1
        if success:
            _generation_counter["success"] += 1
        else:
            _generation_counter["failed"] += 1


def get_generation_stats():
    with _counter_lock:
        return dict(_generation_counter)


@router.get("/health", summary="健康检查", description="系统健康状态检查端点")
def get_health():
    from ...monitor import get_health_monitor, HealthMonitor

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
            health["gpu"]["memory_used_mb"] = round(used / (1024 * 1024), 1)
            health["gpu"]["memory_total_mb"] = round(total / (1024 * 1024), 1)
            if total > 0:
                health["gpu"]["memory_percent"] = round(
                    used / total * 100, 2
                )
            try:
                gpu_util = _get_gpu_utilization()
                health["gpu"]["gpu_util"] = round(float(gpu_util), 2)
                logger.debug(f"GPU utilization: {gpu_util}%")
            except Exception as e:
                health["gpu"]["gpu_util"] = 0
                logger.warning(f"GPU utilization check failed: {e}")
            try:
                health_monitor.record_vram_usage(health["gpu"]["memory_used_mb"])
            except Exception as e:
                logger.debug(f"Non-critical error: {e}")
    except ImportError:
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
        except ImportError as e:
            logger.debug(f"Non-critical error: {e}")
    except Exception as e:
        logger.debug(f"GPU health check failed: {e}")

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
                    try:
                        health_monitor.record_vram_usage(health["gpu"]["memory_used_mb"])
                    except Exception as e:
                        logger.debug(f"Non-critical error: {e}")
        except Exception as e:
            logger.debug(f"nvidia-smi GPU check failed: {e}")

    try:
        cpu_mem = psutil.virtual_memory()
        health["cpu"]["memory_used_mb"] = round(
            (cpu_mem.total - cpu_mem.available) / (1024 * 1024), 1
        )
        health["cpu"]["memory_total_mb"] = round(cpu_mem.total / (1024 * 1024), 1)
        health["cpu"]["percent"] = round(psutil.cpu_percent(interval=0), 1)
    except Exception as e:
        logger.debug(f"CPU health check failed: {e}")

    try:
        from ...model_manager import (
            _progress_mgr,
            _gen_tracker,
            get_persona_cache_stats,
        )
        from ...model_registry import registry, ENGINE_DISPLAY_NAMES

        engine_name = registry.current_engine or "none"
        engine_display = ENGINE_DISPLAY_NAMES.get(engine_name, engine_name)

        health["model"]["current_engine"] = engine_display
        health["model"]["model_size"] = registry.current_size or "none"
        health["model"]["status"] = "ready" if registry.is_engine_ready() else "not_loaded"
        health["model"]["load_time"] = _SESSION_START
        health["model"]["voxcpm2_loaded"] = registry.voxcpm_model is not None
        health["model"]["indextts2_loaded"] = registry.indextts2_engine is not None

        if "gpu" in report:
            health["gpu"]["trend"] = report["gpu"].get("trend", "stable")
            if "leak_warning" in report["gpu"]:
                health["gpu"]["leak_warning"] = report["gpu"]["leak_warning"]

        gen_stats = get_generation_stats()
        health["stats"]["total_generations"] = gen_stats["total"]
        health["stats"]["average_time"] = round(_gen_tracker.avg_gen_time, 1)
        total = gen_stats["total"]
        health["stats"]["success_rate"] = round(
            (gen_stats["success"] / total * 100) if total > 0 else 100.0, 1
        )

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
        if "cache" not in health:
            health["cache"] = {"hit_rate": 0.0, "hits": 0, "misses": 0, "size": 0, "maxsize": 0}

    return health
