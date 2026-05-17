# -*- coding: utf-8 -*-
"""GPU utility functions: OOM detection, VRAM management, and GPU detection."""

import gc
import logging

logger = logging.getLogger("tts_multimodel")


def is_oom_error(exc: Exception) -> bool:
    """Detect whether an exception is caused by CUDA OOM during generation or model loading."""
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
        if "CUDA" in str(exc) and ("memory" in str(exc).lower() or "alloc" in str(exc).lower()):
            return True
    return False


def free_gpu_memory():
    """Attempt to free GPU memory aggressively before retry operations."""
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        try:
            torch._C._cuda_clearCublasWorkspaces()
        except AttributeError:
            pass
        torch.cuda.ipc_collect()
        torch.cuda.empty_cache()


def get_nvidia_gpu_device():
    """Find the NVIDIA GPU device index with the most available VRAM.

    Only supports NVIDIA GPUs with CUDA. Iterates through all available
    GPU devices and filters by name patterns (NVIDIA, GeForce, RTX,
    GTX, Quadro, Tesla). If multiple GPUs are found, selects the one
    with the largest total VRAM.

    Returns:
        GPU device index for the best available NVIDIA GPU.

    Raises:
        RuntimeError: If CUDA is not available or no NVIDIA GPU is detected.
    """
    import torch

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


def get_nvidia_gpu_memory_info():
    """Get memory information for the primary NVIDIA GPU.

    Returns:
        Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes),
        or (0, 0, 0, 0) if GPU memory info cannot be retrieved.
    """
    import torch

    device = get_nvidia_gpu_device()
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
            Returns zeroed dict if CUDA is unavailable.
        """
        total, allocated, reserved, free = get_nvidia_gpu_memory_info()
        return {"total": total, "used": allocated, "free": free}

    @staticmethod
    def can_load_model(model_name="voxcpm2"):
        """Check if there is enough free VRAM to load the specified model.

        Args:
            model_name: Model identifier (currently only "voxcpm2" is supported).

        Returns:
            Tuple of (can_load: bool, free_bytes: int).
        """
        info = GPUMemoryMonitor.get_vram_info()
        needed = int(6.5 * 1024**3)  # VoxCPM2 needs ~6.5GB
        return info["free"] >= needed, info["free"]
