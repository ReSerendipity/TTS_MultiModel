"""Enhanced health monitoring: GPU leak detection, model self-check, metrics."""

import logging
import time
from typing import Any

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
    """Monitors application health, GPU memory trends, and model status.

    显存熔断机制（Ch2 P0 / Ch16 P0）：
    - 推理前调用 check_vram_circuit_breaker() 检查显存占用
    - 占用超过 90% 时抛出 InsufficientVRAMError 立即终止推理
    - 推理过程中周期性检查，超阈值则中断生成并清理缓存
    """

    # 显存熔断阈值：占用超过此比例立即终止推理
    VRAM_CIRCUIT_BREAKER_PCT = 90.0
    # 模型加载预检：可用显存需为模型大小的 1.5 倍以上
    VRAM_PRELOAD_SAFETY_FACTOR = 1.5

    def __init__(self):
        self._vram_samples: list[float] = []
        self._max_samples = 100
        self._leak_threshold_mb = 200  # MB increase over window to flag as leak
        self._model_last_check: float = 0.0
        self._model_status: str = "unknown"
        self._start_time: float = time.time()
        self._total_generations: int = 0
        self._total_errors: int = 0
        self._total_oom_retries: int = 0
        self._circuit_breaker_trips: int = 0

    def record_vram_usage(self, used_mb: float):
        """Record a GPU memory sample for leak detection."""
        self._vram_samples.append(used_mb)
        if len(self._vram_samples) > self._max_samples:
            self._vram_samples = self._vram_samples[-self._max_samples :]

    def check_memory_leak(self) -> str | None:
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

    def get_vram_trend(self) -> dict[str, Any]:
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

    def get_vram_usage_percent(self) -> float:
        """获取当前 GPU 显存占用百分比。

        Returns:
            显存占用百分比 (0-100)，无 GPU 时返回 0.0。
        """
        from .gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend == GPUBackend.CPU:
            return 0.0
        try:
            device = _get_gpu_device()
            props = GPUBackendManager.get_device_properties(device)
            total = props.get("total_memory", 0)
            if total <= 0:
                return 0.0
            allocated = GPUBackendManager.memory_allocated(device)
            return allocated / total * 100
        except Exception:
            return 0.0

    def check_vram_circuit_breaker(self) -> bool:
        """显存熔断检查：占用超过 90% 时触发熔断。

        触发熔断后会：
        1. 递增熔断计数器
        2. 清理 GPU 缓存
        3. 抛出 InsufficientVRAMError

        Returns:
            True 表示安全，False 表示熔断已触发。

        Raises:
            InsufficientVRAMError: 显存占用超过熔断阈值。
        """
        usage_pct = self.get_vram_usage_percent()
        if usage_pct > self.VRAM_CIRCUIT_BREAKER_PCT:
            self._circuit_breaker_trips += 1
            logger.error(
                f"[显存熔断] VRAM 占用 {usage_pct:.1f}% 超过阈值 "
                f"{self.VRAM_CIRCUIT_BREAKER_PCT}%，立即终止推理 "
                f"(累计触发 {self._circuit_breaker_trips} 次)"
            )
            # 立即清理缓存
            from .gpu_utils import free_gpu_memory

            free_gpu_memory()
            from .exceptions import InsufficientVRAMError

            raise InsufficientVRAMError(
                f"显存熔断触发：VRAM 占用 {usage_pct:.1f}% 超过 "
                f"{self.VRAM_CIRCUIT_BREAKER_PCT}% 安全阈值，推理已终止。"
                f"请卸载模型后重试，或减少并发任务。"
            )
        return True

    def check_vram_preload(self, model_size_gb: float) -> bool:
        """模型加载预检：可用显存需为模型大小的 1.5 倍以上。

        Args:
            model_size_gb: 模型预计占用显存 (GB)。

        Returns:
            True 表示预检通过，可以加载。

        Raises:
            InsufficientVRAMError: 可用显存不足。
        """
        from .gpu_backend import GPUBackend, GPUBackendManager

        backend = GPUBackendManager.detect_backend()
        if backend == GPUBackend.CPU:
            logger.info("[显存预检] CPU 模式，跳过预检")
            return True

        try:
            device = _get_gpu_device()
            mem_info = GPUBackendManager.get_memory_info(device)
            free_bytes = mem_info[3]
            free_gb = free_bytes / (1024**3)
            needed_gb = model_size_gb * self.VRAM_PRELOAD_SAFETY_FACTOR

            if free_gb < needed_gb:
                from .exceptions import InsufficientVRAMError

                raise InsufficientVRAMError(
                    f"显存预检失败：模型需要 {needed_gb:.1f}GB (含安全系数 "
                    f"{self.VRAM_PRELOAD_SAFETY_FACTOR}x)，"
                    f"当前可用 {free_gb:.1f}GB。"
                )
            logger.info(
                f"[显存预检] 通过：需要 {needed_gb:.1f}GB，"
                f"可用 {free_gb:.1f}GB"
            )
            return True
        except InsufficientVRAMError:
            raise
        except Exception as e:
            logger.warning(f"[显存预检] 检查失败: {e}，跳过预检")
            return True

    def set_model_status(self, status: str):
        """Update model status: loaded, unloading, ready, error, unknown."""
        self._model_status = status
        self._model_last_check = time.time()

    def get_health_report(self) -> dict[str, Any]:
        """Get comprehensive health report."""
        from .gpu_backend import GPUBackend, GPUBackendManager

        report: dict[str, Any] = {
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
            vram_used = GPUBackendManager.memory_allocated(device) / (1024**2)
            props = GPUBackendManager.get_device_properties(device)
            vram_total = props.get("total_memory", 0) / (1024**2)
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
            success_rate = (self._total_generations - self._total_errors) / self._total_generations * 100
        report["success_rate"] = round(success_rate, 1)

        return report


_health_monitor = HealthMonitor()


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    return _health_monitor
