"""GPU Backend Abstraction Layer - Unified support for CUDA/MPS/CPU.

This module provides a unified interface for detecting and managing different
GPU backends supported by PyTorch:
- CUDA (NVIDIA GPUs)
- MPS (Apple Silicon via Metal Performance Shaders)
- CPU (fallback when no GPU is available)

Note: This project only supports NVIDIA CUDA GPUs. The underlying TTS models
(VoxCPM2 and IndexTTS 2.0) require CUDA for GPU acceleration and do not
officially support AMD ROCm or Intel XPU backends.
"""

import logging
from enum import Enum
from typing import Any

import torch

logger = logging.getLogger("tts_multimodel")


class GPUBackend(Enum):
    """Supported GPU backends."""

    CUDA = "cuda"  # NVIDIA GPUs
    MPS = "mps"  # Apple Silicon (Metal)
    CPU = "cpu"  # CPU fallback


# ---------------------------------------------------------------------------
# Strategy classes – one per backend family, used by GPUBackendManager
# ---------------------------------------------------------------------------


class _CUDAStrategy:
    """Strategy for CUDA backend (NVIDIA GPUs)."""

    @staticmethod
    def get_device(index=0):
        return torch.device(f"cuda:{index}")

    @staticmethod
    def get_device_count():
        return torch.cuda.device_count()

    @staticmethod
    def get_device_name(index=0):
        if torch.cuda.is_available() and index < torch.cuda.device_count():
            return torch.cuda.get_device_name(index)
        return "CPU"

    @staticmethod
    def get_device_properties(index=0):
        if torch.cuda.is_available() and index < torch.cuda.device_count():
            props = torch.cuda.get_device_properties(index)
            return {
                "name": props.name,
                "total_memory": props.total_memory,
                "major": props.major,
                "minor": props.minor,
            }
        return {"name": "CPU", "total_memory": 0}

    @staticmethod
    def memory_allocated(device=None):
        return torch.cuda.memory_allocated(device)

    @staticmethod
    def memory_reserved(device=None):
        return torch.cuda.memory_reserved(device)

    @staticmethod
    def empty_cache():
        torch.cuda.empty_cache()

    @staticmethod
    def synchronize(device=None):
        if device is None:
            torch.cuda.synchronize()
        else:
            torch.cuda.synchronize(device)

    @staticmethod
    def get_memory_info(index=0):
        if not torch.cuda.is_available():
            return (0, 0, 0, 0)
        props = torch.cuda.get_device_properties(index)
        total = props.total_memory
        allocated = torch.cuda.memory_allocated(index)
        reserved = torch.cuda.memory_reserved(index)
        return (total, allocated, reserved, total - allocated)

    @staticmethod
    def get_cuda_clear_workspaces_func():
        try:
            return torch._C._cuda_clearCublasWorkspaces
        except AttributeError:
            return None

    @staticmethod
    def ipc_collect(device=None):
        try:
            if device is None:
                torch.cuda.ipc_collect()
            else:
                torch.cuda.ipc_collect(device)
        except Exception as e:
            logger.debug(f"IPC 收集失败: {e}")

    @staticmethod
    def get_grad_scaler(enabled=True):
        if enabled:
            return torch.amp.GradScaler("cuda")
        return None

    @staticmethod
    def get_autocast_device_type():
        return "cuda"

    @staticmethod
    def get_process_group_backend():
        return "nccl"

    @staticmethod
    def format_device_string(index=0):
        return f"cuda:{index}"


class _MPSStrategy:
    """Strategy for Apple MPS backend."""

    @staticmethod
    def get_device(index=0):
        return torch.device("mps")

    @staticmethod
    def get_device_count():
        return 1

    @staticmethod
    def get_device_name(index=0):
        return "Apple MPS"

    @staticmethod
    def get_device_properties(index=0):
        return {"name": "Apple MPS", "total_memory": 0}

    @staticmethod
    def memory_allocated(device=None):
        return 0

    @staticmethod
    def memory_reserved(device=None):
        return 0

    @staticmethod
    def empty_cache():
        pass

    @staticmethod
    def synchronize(device=None):
        pass

    @staticmethod
    def get_memory_info(index=0):
        return (0, 0, 0, 0)

    @staticmethod
    def get_cuda_clear_workspaces_func():
        return None

    @staticmethod
    def ipc_collect(device=None):
        pass

    @staticmethod
    def get_grad_scaler(enabled=True):
        return None

    @staticmethod
    def get_autocast_device_type():
        return "cpu"

    @staticmethod
    def get_process_group_backend():
        return "gloo"

    @staticmethod
    def format_device_string(index=0):
        return "mps"


class _CPUStrategy:
    """Strategy for CPU fallback."""

    @staticmethod
    def get_device(index=0):
        return torch.device("cpu")

    @staticmethod
    def get_device_count():
        return 0

    @staticmethod
    def get_device_name(index=0):
        return "CPU"

    @staticmethod
    def get_device_properties(index=0):
        return {"name": "CPU", "total_memory": 0}

    @staticmethod
    def memory_allocated(device=None):
        return 0

    @staticmethod
    def memory_reserved(device=None):
        return 0

    @staticmethod
    def empty_cache():
        pass

    @staticmethod
    def synchronize(device=None):
        pass

    @staticmethod
    def get_memory_info(index=0):
        return (0, 0, 0, 0)

    @staticmethod
    def get_cuda_clear_workspaces_func():
        return None

    @staticmethod
    def ipc_collect(device=None):
        pass

    @staticmethod
    def get_grad_scaler(enabled=True):
        return None

    @staticmethod
    def get_autocast_device_type():
        return "cpu"

    @staticmethod
    def get_process_group_backend():
        return "gloo"

    @staticmethod
    def format_device_string(index=0):
        return "cpu"


# ---------------------------------------------------------------------------
# GPUBackendManager – unified GPU backend manager
# ---------------------------------------------------------------------------


class GPUBackendManager:
    """Unified GPU backend manager for multi-vendor GPU support.

    Automatically detects available GPU backends and provides a consistent
    API for device management, memory queries, and operations across
    different hardware vendors.

    Uses the Strategy pattern to dispatch backend-specific operations,
    avoiding repeated if/else chains across methods.

    Usage:
        backend = GPUBackendManager.detect_backend()
        device = GPUBackendManager.get_device()
        memory_info = GPUBackendManager.get_memory_info()
    """

    _cached_backend: GPUBackend | None = None
    _STRATEGY_MAP = None  # Lazy-initialized

    @classmethod
    def _get_strategy(cls, backend=None):
        """Get the strategy class for the given backend.

        Args:
            backend: GPU backend enum. If None, uses the detected backend.

        Returns:
            Strategy class with static methods for the backend.
        """
        if cls._STRATEGY_MAP is None:
            cls._STRATEGY_MAP = {
                GPUBackend.CUDA: _CUDAStrategy,
                GPUBackend.MPS: _MPSStrategy,
                GPUBackend.CPU: _CPUStrategy,
            }
        if backend is None:
            backend = cls.detect_backend()
        return cls._STRATEGY_MAP.get(backend, _CPUStrategy)

    # ------------------------------------------------------------------
    # Detection methods (no if/else pattern – kept as-is)
    # ------------------------------------------------------------------

    @classmethod
    def _is_apple_mps(cls) -> bool:
        """Detect if Apple MPS (Metal Performance Shaders) is available.

        Returns:
            True if MPS is available, False otherwise.
        """
        try:
            return torch.backends.mps.is_available()
        except Exception as e:
            logger.debug(f"检测 Apple MPS 失败: {e}")
            return False

    @classmethod
    def detect_backend(cls) -> GPUBackend:
        """Automatically detect the best available GPU backend.

        Detection priority: NVIDIA CUDA > Apple MPS > CPU

        Returns:
            The detected GPU backend enum.
        """
        if cls._cached_backend is not None:
            return cls._cached_backend

        # 1. Check NVIDIA CUDA
        if torch.cuda.is_available():
            cls._cached_backend = GPUBackend.CUDA
            logger.info("[GPU Backend] 检测到 NVIDIA CUDA 后端")
            return cls._cached_backend

        # 2. Check Apple MPS
        if cls._is_apple_mps():
            cls._cached_backend = GPUBackend.MPS
            logger.info("[GPU Backend] 检测到 Apple MPS 后端")
            return cls._cached_backend

        # 3. Fallback to CPU
        cls._cached_backend = GPUBackend.CPU
        logger.warning("[GPU Backend] 未检测到 GPU，使用 CPU 后端")
        return cls._cached_backend

    @classmethod
    def clear_cache(cls):
        """Clear cached backend detection result."""
        cls._cached_backend = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if any GPU backend is available.

        Returns:
            True if GPU is available, False if CPU-only.
        """
        backend = cls.detect_backend()
        return backend != GPUBackend.CPU

    # ------------------------------------------------------------------
    # Strategy-dispatched methods
    # ------------------------------------------------------------------

    @classmethod
    def get_device(cls, index: int = 0) -> torch.device:
        """Get the primary compute device.

        Args:
            index: Device index (default: 0).

        Returns:
            torch.device object for the primary compute device.
        """
        return cls._get_strategy().get_device(index)

    @classmethod
    def get_device_count(cls) -> int:
        """Get the number of available devices.

        Returns:
            Number of devices for the current backend.
        """
        return cls._get_strategy().get_device_count()

    @classmethod
    def get_device_name(cls, index: int = 0) -> str:
        """Get the device name.

        Args:
            index: Device index (default: 0).

        Returns:
            Device name string, or "CPU" if no GPU available.
        """
        return cls._get_strategy().get_device_name(index)

    @classmethod
    def get_device_properties(cls, index: int = 0) -> dict[str, Any]:
        """Get device properties in a backend-agnostic way.

        Args:
            index: Device index (default: 0).

        Returns:
            Dictionary with device properties (name, total_memory, etc.).
        """
        return cls._get_strategy().get_device_properties(index)

    @classmethod
    def memory_allocated(cls, device=None) -> int:
        """Get currently allocated memory on the device.

        Args:
            device: Device index or torch.device (default: primary device).

        Returns:
            Allocated memory in bytes.
        """
        if device is None:
            device = cls.get_device()
        return cls._get_strategy().memory_allocated(device)

    @classmethod
    def memory_reserved(cls, device=None) -> int:
        """Get currently reserved memory on the device.

        Args:
            device: Device index or torch.device (default: primary device).

        Returns:
            Reserved memory in bytes.
        """
        if device is None:
            device = cls.get_device()
        return cls._get_strategy().memory_reserved(device)

    @classmethod
    def empty_cache(cls):
        """Empty the memory cache for the current backend."""
        cls._get_strategy().empty_cache()

    @classmethod
    def synchronize(cls, device=None):
        """Synchronize the current device.

        Args:
            device: Device index or torch.device (default: primary device).
        """
        cls._get_strategy().synchronize(device)

    @classmethod
    def get_memory_info(cls, index: int = 0) -> tuple[int, int, int, int]:
        """Get memory information for the primary GPU.

        Args:
            index: Device index (default: 0).

        Returns:
            Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes)
        """
        try:
            return cls._get_strategy().get_memory_info(index)
        except Exception as e:
            logger.error(f"获取 GPU 显存信息失败: {e}")
            return (0, 0, 0, 0)

    @classmethod
    def get_cuda_clear_workspaces_func(cls):
        """Get CUDA cuBLAS workspace clear function if available.

        Returns:
            Callable to clear cuBLAS workspaces, or None if not available.
        """
        return cls._get_strategy().get_cuda_clear_workspaces_func()

    @classmethod
    def ipc_collect(cls, device=None):
        """Perform IPC collection (CUDA-specific).

        Args:
            device: Device index (default: None).
        """
        cls._get_strategy().ipc_collect(device)

    @classmethod
    def get_grad_scaler(cls, enabled: bool = True):
        """Get the appropriate gradient scaler for the current backend.

        Args:
            enabled: Whether to enable gradient scaling.

        Returns:
            GradScaler instance or None if not applicable.
        """
        return cls._get_strategy().get_grad_scaler(enabled)

    @classmethod
    def get_autocast_device_type(cls) -> str:
        """Get the device type string for autocast.

        Returns:
            Device type string for torch.amp.autocast.
        """
        return cls._get_strategy().get_autocast_device_type()

    @classmethod
    def get_process_group_backend(cls) -> str:
        """Get the appropriate distributed process group backend.

        Returns:
            Process group backend string ("nccl", "gloo", etc.).
        """
        return cls._get_strategy().get_process_group_backend()

    @classmethod
    def format_device_string(cls, index: int = 0) -> str:
        """Format device string for .to() calls.

        Args:
            index: Device index (default: 0).

        Returns:
            Device string suitable for tensor.to(device_string).
        """
        return cls._get_strategy().format_device_string(index)
