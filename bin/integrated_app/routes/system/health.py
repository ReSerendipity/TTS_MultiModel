import asyncio
import logging
import os
import threading
from datetime import datetime
from typing import Any

import psutil
from fastapi import APIRouter

logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])

from .gpu import _get_gpu_device, _get_gpu_utilization  # noqa: E402

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
async def get_health():
    from ...monitor import get_health_monitor

    health_monitor = get_health_monitor()
    report = health_monitor.get_health_report()

    health: dict[str, Any] = {
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
        from ...gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device = _get_gpu_device()
            props = GPUBackendManager.get_device_properties(device)
            total = props.get("total_memory", 0)
            allocated = GPUBackendManager.memory_allocated(device)
            reserved = GPUBackendManager.memory_reserved(device)
            used = max(allocated, reserved)
            health["gpu"]["memory_used_mb"] = round(used / (1024 * 1024), 1)
            health["gpu"]["memory_total_mb"] = round(total / (1024 * 1024), 1)
            if total > 0:
                health["gpu"]["memory_percent"] = round(used / total * 100, 2)
            try:
                gpu_util = _get_gpu_utilization()
                health["gpu"]["gpu_util"] = round(float(gpu_util), 2)
                logger.debug(f"GPU 利用率: {gpu_util}%")
            except Exception as e:
                health["gpu"]["gpu_util"] = 0
                logger.warning(f"GPU 利用率检查失败: {e}")
            try:
                health_monitor.record_vram_usage(health["gpu"]["memory_used_mb"])
            except Exception as e:
                logger.debug(f"非关键错误: {e}")
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"GPU 健康检查失败: {e}")

    if health["gpu"]["memory_total_mb"] == 0:
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise
            if proc.returncode == 0 and stdout:
                output = stdout.decode("utf-8", errors="replace").strip()
                parts = output.split(",")
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
                        logger.debug(f"非关键错误: {e}")
        except Exception as e:
            logger.debug(f"nvidia-smi GPU 检查失败: {e}")

    try:
        cpu_mem = psutil.virtual_memory()
        health["cpu"]["memory_used_mb"] = round((cpu_mem.total - cpu_mem.available) / (1024 * 1024), 1)
        health["cpu"]["memory_total_mb"] = round(cpu_mem.total / (1024 * 1024), 1)
        health["cpu"]["percent"] = round(psutil.cpu_percent(interval=0), 1)
    except Exception as e:
        logger.debug(f"CPU 健康检查失败: {e}")

    try:
        from ...model_manager import (
            _gen_tracker,
            get_persona_cache_stats,
        )
        from ...model_registry import ENGINE_DISPLAY_NAMES, registry

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
        health["stats"]["success_rate"] = round((gen_stats["success"] / total * 100) if total > 0 else 100.0, 1)

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
            logger.debug(f"缓存统计检查失败: {e}")
            health["cache"] = {"hit_rate": 0.0, "hits": 0, "misses": 0, "size": 0, "maxsize": 0}
    except Exception as e:
        logger.debug(f"模型健康检查失败: {e}")
        if "cache" not in health:
            health["cache"] = {"hit_rate": 0.0, "hits": 0, "misses": 0, "size": 0, "maxsize": 0}

    return health


@router.post("/shutdown", summary="优雅关闭服务器")
def shutdown_server():
    """请求服务器优雅关闭。在后台延迟执行，给响应留出返回时间。"""
    logger.info("[SHUTDOWN] 收到关闭请求，将在 1 秒后关闭服务器...")

    def _do_shutdown():
        import time

        time.sleep(1)
        os._exit(0)

    threading.Thread(target=_do_shutdown, daemon=True).start()
    return {"status": "ok", "message": "服务器正在关闭..."}
