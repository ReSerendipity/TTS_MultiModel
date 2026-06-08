# -*- coding: utf-8 -*-
"""GPU utility functions: OOM detection, VRAM management, and multi-backend GPU detection.

Supports NVIDIA CUDA, AMD ROCM, Intel XPU, Apple MPS, and CPU backends.
"""

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
        "xpu out of memory",
    ]
    for pattern in oom_patterns:
        if pattern in error_str:
            return True
    if isinstance(exc, RuntimeError):
        error_upper = str(exc).upper()
        if ("CUDA" in error_upper or "XPU" in error_upper) and ("memory" in str(exc).lower() or "alloc" in str(exc).lower()):
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
    from .gpu_backend import GPUBackendManager, GPUBackend

    backend = GPUBackendManager.detect_backend()
    is_gpu = backend in (GPUBackend.CUDA, GPUBackend.ROCM)
    is_xpu = backend == GPUBackend.XPU

    # --- Tier 1: Lightweight ---
    t0 = time.time()
    gc.collect()
    if is_gpu or is_xpu:
        GPUBackendManager.empty_cache()
    tier1_time = time.time() - t0
    logger.debug(f"[GPU清理] Tier 1 (轻量) 完成，耗时 {tier1_time:.3f}s")

    # Check if memory is still critical (only for CUDA/ROCM/XPU)
    if is_gpu or is_xpu:
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
    elif is_xpu:
        GPUBackendManager.synchronize()
        GPUBackendManager.empty_cache()
    tier2_time = time.time() - t1
    logger.debug(f"[GPU清理] Tier 2 (中等) 完成，耗时 {tier2_time:.3f}s")

    # Check again
    if is_gpu or is_xpu:
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
            try:
                clear_func()
            except Exception:
                pass
        device = get_gpu_device()
        if device is not None:
            GPUBackendManager.ipc_collect(device)
        torch.cuda.empty_cache()
    elif is_xpu:
        GPUBackendManager.empty_cache()
    tier3_time = time.time() - t2
    logger.debug(f"[GPU清理] Tier 3 (重度) 完成，耗时 {tier3_time:.3f}s")

    total_time = time.time() - t0
    logger.info(f"[GPU清理] 分层清理完成，总耗时 {total_time:.3f}s (T1={tier1_time:.3f}s, T2={tier2_time:.3f}s, T3={tier3_time:.3f}s)")


def get_gpu_device():
    """Find the best GPU device index with the most available VRAM.

    Supports multiple GPU backends: NVIDIA CUDA, AMD ROCM, Intel XPU, Apple MPS.
    Iterates through all available GPU devices and selects the one
    with the largest total VRAM if multiple GPUs are found.

    Returns:
        GPU device index for the best available GPU, or None if only CPU is available.

    Raises:
        RuntimeError: If GPU is expected but not available.
    """
    import torch
    from .gpu_backend import GPUBackendManager, GPUBackend

    backend = GPUBackendManager.detect_backend()

    # CPU backend - return None to indicate no GPU
    if backend == GPUBackend.CPU:
        return None

    if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
        if not torch.cuda.is_available():
            return None

        for i in range(torch.cuda.device_count()):
            try:
                props = torch.cuda.get_device_properties(i)
                return i
            except Exception as e:
                logger.debug(f"无法获取 GPU {i} 信息: {e}")

        return None

    elif backend == GPUBackend.XPU:
        try:
            import intel_extension_for_pytorch as ipex
            if ipex.xpu.is_available():
                for i in range(ipex.xpu.device_count()):
                    try:
                        props = ipex.xpu.get_device_properties(i)
                        return i
                    except Exception as e:
                        logger.debug(f"无法获取 Intel XPU {i} 信息: {e}")
                return None
        except ImportError:
            pass

        return None

    elif backend == GPUBackend.MPS:
        return 0

    return None


def get_nvidia_gpu_device():
    """Find the NVIDIA GPU device index with the most available VRAM.

    Deprecated: Use get_gpu_device() instead for multi-backend support.
    This function is kept for backward compatibility.

    Returns:
        GPU device index for the best available NVIDIA GPU.

    Raises:
        RuntimeError: If CUDA is not available or no NVIDIA GPU is detected.
    """
    import torch
    from .gpu_backend import GPUBackendManager, GPUBackend

    backend = GPUBackendManager.detect_backend()
    
    if backend != GPUBackend.CUDA:
        raise RuntimeError("未检测到可用的 NVIDIA 显卡。本项目当前后端为 {}，仅 NVIDIA GPU 可使用此函数。".format(backend.value))

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，请确认已安装支持 CUDA 的 NVIDIA 显卡和驱动。")

    nvidia_devices = []
    for i in range(torch.cuda.device_count()):
        try:
            props = torch.cuda.get_device_properties(i)
            name_lower = props.name.lower()
            if "nvidia" in name_lower or "geforce" in name_lower or "rtx" in name_lower or "gtx" in name_lower or "quadro" in name_lower or "tesla" in name_lower:
                nvidia_devices.append((i, props.total_memory, props.name))
            else:
                logger.debug(f"忽略非 NVIDIA GPU {i}: {props.name}")
        except Exception as e:
            logger.debug(f"无法获取 GPU {i} 信息: {e}")

    if not nvidia_devices:
        raise RuntimeError("未检测到可用的 NVIDIA 显卡。本项目仅支持 NVIDIA GPU (CUDA 加速)，不支持 Intel/AMD 显卡。")

    best_idx, best_mem, best_name = max(nvidia_devices, key=lambda x: x[1])

    if torch.cuda.device_count() > 1:
        logger.info(f"多 GPU 环境，选择 NVIDIA GPU {best_idx}: {best_name} (VRAM: {best_mem / 1024**3:.1f}GB)")

    return best_idx


def get_gpu_memory_info():
    """Get memory information for the primary GPU.

    Supports multiple GPU backends: NVIDIA CUDA, AMD ROCM, Intel XPU.

    Returns:
        Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes),
        or (0, 0, 0, 0) if GPU memory info cannot be retrieved.
    """
    import torch
    from .gpu_backend import GPUBackendManager

    device = get_gpu_device()
    return GPUBackendManager.get_memory_info(device)


def get_nvidia_gpu_memory_info():
    """Get memory information for the primary NVIDIA GPU.

    Deprecated: Use get_gpu_memory_info() instead for multi-backend support.
    This function is kept for backward compatibility.

    Returns:
        Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes),
        or (0, 0, 0, 0) if GPU memory info cannot be retrieved.
    """
    import torch
    from .gpu_backend import GPUBackendManager, GPUBackend

    try:
        device = get_nvidia_gpu_device()
    except RuntimeError:
        return (0, 0, 0, 0)

    if not torch.cuda.is_available():
        return (0, 0, 0, 0)
    try:
        props = torch.cuda.get_device_properties(device)
        total = props.total_memory
        allocated = torch.cuda.memory_allocated(device)
        reserved = torch.cuda.memory_reserved(device)
        free = total - allocated
        return (total, allocated, reserved, free)
    except Exception as e:
        logger.error(f"Failed to get GPU memory info: {e}")
        return (0, 0, 0, 0)


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
