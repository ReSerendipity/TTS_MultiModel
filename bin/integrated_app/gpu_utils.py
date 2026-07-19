"""GPU utility functions: OOM detection, VRAM management, and multi-backend GPU detection.

Supports NVIDIA CUDA, Apple MPS, and CPU backends.
"""

import contextlib
import gc
import logging

logger = logging.getLogger("tts_multimodel")


def is_oom_error(exc: Exception) -> bool:
    """Detect whether an exception is caused by GPU OOM during generation or model loading."""
    error_str = str(exc).lower()
    oom_patterns = [
        "cuda out of memory",
        "out of memory",
        "oom",
        "insufficient vram",
        "insufficientvram",
    ]
    for pattern in oom_patterns:
        if pattern in error_str:
            return True
    if isinstance(exc, RuntimeError):
        error_upper = str(exc).upper()
        if "CUDA" in error_upper and (
            "memory" in str(exc).lower() or "alloc" in str(exc).lower()
        ):
            return True
    return False


def free_gpu_memory():
    """Attempt to free GPU memory with tiered cleanup strategy.

    Tier 1 (Lightweight): gc.collect() + empty_cache()
    Tier 2 (Medium):      + synchronize() + empty_cache()
    Tier 3 (Heavy):       + clear_workspaces() + ipc_collect() + empty_cache()

    Each tier is only applied if the previous tier did not free enough
    memory (free VRAM < 500 MB). Logs which tier was needed and timing.
    """
    import time

    import torch

    from .gpu_backend import GPUBackend, GPUBackendManager

    backend = GPUBackendManager.detect_backend()
    is_gpu = backend == GPUBackend.CUDA

    # --- Tier 1: Lightweight ---
    t0 = time.time()
    gc.collect()
    if is_gpu:
        GPUBackendManager.empty_cache()
    tier1_time = time.time() - t0
    logger.debug(f"[GPU清理] Tier 1 (轻量) 完成，耗时 {tier1_time:.3f}s")

    # Check if memory is still critical (only for CUDA)
    if is_gpu:
        try:
            device = get_gpu_device()
            mem_info = GPUBackendManager.get_memory_info(device)
            free_bytes = mem_info[3]
            if free_bytes >= 500 * 1024 * 1024:  # 500 MB
                logger.info(f"[GPU清理] Tier 1 即已释放足够显存 (空闲 {free_bytes / 1024**2:.0f}MB)，跳过后续层级")
                return
        except Exception:
            pass  # 无法检测则继续下一层级

    # --- Tier 2: Medium ---
    t1 = time.time()
    if is_gpu:
        device = get_gpu_device()
        if device is not None:
            GPUBackendManager.synchronize(device)
        torch.cuda.empty_cache()
    tier2_time = time.time() - t1
    logger.debug(f"[GPU清理] Tier 2 (中等) 完成，耗时 {tier2_time:.3f}s")

    # Check again
    if is_gpu:
        try:
            device = get_gpu_device()
            mem_info = GPUBackendManager.get_memory_info(device)
            free_bytes = mem_info[3]
            if free_bytes >= 500 * 1024 * 1024:
                logger.info(f"[GPU清理] Tier 2 释放后显存充足 (空闲 {free_bytes / 1024**2:.0f}MB)，跳过 Tier 3")
                return
        except Exception:
            pass

    # --- Tier 3: Heavy ---
    t2 = time.time()
    if is_gpu:
        clear_func = GPUBackendManager.get_cuda_clear_workspaces_func()
        if clear_func:
            with contextlib.suppress(Exception):
                clear_func()
        device = get_gpu_device()
        if device is not None:
            GPUBackendManager.ipc_collect(device)
        torch.cuda.empty_cache()
    tier3_time = time.time() - t2
    logger.debug(f"[GPU清理] Tier 3 (重度) 完成，耗时 {tier3_time:.3f}s")

    total_time = time.time() - t0
    logger.info(
        f"[GPU清理] 分层清理完成，总耗时 {total_time:.3f}s (T1={tier1_time:.3f}s, T2={tier2_time:.3f}s, T3={tier3_time:.3f}s)"
    )


def get_gpu_device():
    """Find the best GPU device index with the most available VRAM.

    Supports NVIDIA CUDA and Apple MPS backends.
    Iterates through all available GPU devices and selects the one
    with the largest total VRAM if multiple GPUs are found.

    Returns:
        GPU device index for the best available GPU, or None if only CPU is available.

    Raises:
        RuntimeError: If GPU is expected but not available.
    """
    import torch

    from .gpu_backend import GPUBackend, GPUBackendManager

    backend = GPUBackendManager.detect_backend()

    # CPU backend - return None to indicate no GPU
    if backend == GPUBackend.CPU:
        return None

    if backend == GPUBackend.CUDA:
        if not torch.cuda.is_available():
            return None

        for i in range(torch.cuda.device_count()):
            try:
                torch.cuda.get_device_properties(i)
                return i
            except Exception as e:
                logger.debug(f"无法获取 GPU {i} 信息: {e}")

        return None

    elif backend == GPUBackend.MPS:
        return 0

    return None


def get_gpu_memory_info():
    """Get memory information for the primary GPU.

    Supports NVIDIA CUDA backend.

    Returns:
        Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes),
        or (0, 0, 0, 0) if GPU memory info cannot be retrieved.
    """
    from .gpu_backend import GPUBackendManager

    device = get_gpu_device()
    return GPUBackendManager.get_memory_info(device)


class GPUMemoryMonitor:
    """Static utility class for GPU VRAM monitoring and capacity checks.

    Provides methods to query current VRAM usage and determine if
    there is sufficient free VRAM to load the model.
    """

    @staticmethod
    def get_vram_info():
        """Query current VRAM usage statistics.

        Returns:
            Dictionary with 'total', 'used', and 'free' keys in bytes.
            Returns zeroed dict if GPU is unavailable.
        """
        total, allocated, reserved, free = get_gpu_memory_info()
        return {"total": total, "used": allocated, "free": free}

    @staticmethod
    def can_load_model(model_name="voxcpm2"):
        """Check if there is enough free VRAM to load the specified model.

        Args:
            model_name: Model identifier ("voxcpm2" or "indextts2").

        Returns:
            Tuple of (can_load: bool, free_bytes: int).
        """
        from .model_registry import ENGINE_VRAM_REQUIREMENTS

        info = GPUMemoryMonitor.get_vram_info()
        needed_gb = ENGINE_VRAM_REQUIREMENTS.get(model_name, 6.5)
        needed = int(needed_gb * 1024**3)
        return info["free"] >= needed, info["free"]
