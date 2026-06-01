# -*- coding: utf-8 -*-
"""Enhanced health monitoring: GPU leak detection, model self-check, metrics."""

import time
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("tts_multimodel")


def _get_gpu_device():
    """Get the GPU device index using unified backend manager."""
    from .gpu_backend import GPUBackendManager
    
    if not GPUBackendManager.is_available():
        return 0
    
    try:
        device = GPUBackendManager.get_device()
        import torch
        if isinstance(device, torch.device):
            return device.index if device.index is not None else 0
        return device
    except Exception:
        return 0


class HealthMonitor:
    """Monitors application health, GPU memory trends, and model status."""

    def __init__(self):
        self._vram_samples: List[float] = []
        self._max_samples = 100
        self._leak_threshold_mb = 200  # MB increase over window to flag as leak
        self._model_last_check: float = 0.0
        self._model_status: str = "unknown"
        self._start_time: float = time.time()
        self._total_generations: int = 0
        self._total_errors: int = 0
        self._total_oom_retries: int = 0

    def record_vram_usage(self, used_mb: float):
        """Record a GPU memory sample for leak detection."""
        self._vram_samples.append(used_mb)
        if len(self._vram_samples) > self._max_samples:
            self._vram_samples = self._vram_samples[-self._max_samples:]

    def check_memory_leak(self) -> Optional[str]:
        """Check for potential GPU memory leak.
        
        Returns warning message if leak detected, None otherwise.
        """
        if len(self._vram_samples) < 10:
            return None

        # Compare average of last 5 vs first 5 in the window
        recent_avg = sum(self._vram_samples[-5:]) / 5
        old_avg = sum(self._vram_samples[:5]) / 5
        diff = recent_avg - old_avg

        if diff > self._leak_threshold_mb:
            warning = (
                f"\u26a0\ufe0f Potential GPU memory leak detected: "
                f"VRAM increased by {diff:.0f}MB over monitoring window. "
                f"Current: {self._vram_samples[-1]:.0f}MB, Baseline: {old_avg:.0f}MB"
            )
            logger.warning(warning)
            return warning
        return None

    def get_vram_trend(self) -> Dict[str, Any]:
        """Get GPU memory usage trend."""
        if not self._vram_samples:
            return {"status": "no_data"}

        current = self._vram_samples[-1]
        min_val = min(self._vram_samples)
        max_val = max(self._vram_samples)
        avg = sum(self._vram_samples) / len(self._vram_samples)

        return {
            "current_mb": round(current, 1),
            "min_mb": round(min_val, 1),
            "max_mb": round(max_val, 1),
            "avg_mb": round(avg, 1),
            "trend": "increasing" if current > avg * 1.1 else "stable",
            "sample_count": len(self._vram_samples),
        }

    def record_generation(self, success: bool = True):
        """Record a generation attempt."""
        self._total_generations += 1
        if not success:
            self._total_errors += 1

    def record_oom_retry(self):
        """Record an OOM retry event."""
        self._total_oom_retries += 1

    def set_model_status(self, status: str):
        """Update model status: loaded, unloading, ready, error, unknown."""
        self._model_status = status
        self._model_last_check = time.time()

    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        import torch
        from .gpu_backend import GPUBackendManager, GPUBackend

        report: Dict[str, Any] = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "total_generations": self._total_generations,
            "total_errors": self._total_errors,
            "total_oom_retries": self._total_oom_retries,
            "model_status": self._model_status,
            "model_last_check": self._model_last_check,
        }

        backend = GPUBackendManager.detect_backend()
        if backend != GPUBackend.CPU:
            device = _get_gpu_device()
            vram_used = GPUBackendManager.memory_allocated(device) / (1024 ** 2)
            props = GPUBackendManager.get_device_properties(device)
            vram_total = props.get('total_memory', 0) / (1024 ** 2)
            report["gpu"] = {
                "name": GPUBackendManager.get_device_name(device),
                "vram_used_mb": round(vram_used, 1),
                "vram_total_mb": round(vram_total, 1),
                "vram_usage_pct": round(vram_used / vram_total * 100, 1) if vram_total > 0 else 0,
            }
            leak_warning = self.check_memory_leak()
            if leak_warning:
                report["gpu"]["leak_warning"] = leak_warning
            report["gpu"]["trend"] = self.get_vram_trend()

        success_rate = 0.0
        if self._total_generations > 0:
            success_rate = (
                (self._total_generations - self._total_errors)
                / self._total_generations * 100
            )
        report["success_rate"] = round(success_rate, 1)

        return report


_health_monitor = HealthMonitor()


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    return _health_monitor
