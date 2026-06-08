# -*- coding: utf-8 -*-
"""GPU Backend Abstraction Layer - Unified support for CUDA/ROCM/XPU/MPS/CPU.

This module provides a unified interface for detecting and managing different
GPU backends supported by PyTorch:
- CUDA (NVIDIA GPUs)
- ROCM/HIP (AMD GPUs, hipified to use torch.cuda API)
- XPU (Intel GPUs via intel-extension-for-pytorch)
- MPS (Apple Silicon via Metal Performance Shaders)
- CPU (fallback when no GPU is available)

Note: Both AMD integrated and discrete GPUs use the same ROCM backend.
      Both Intel integrated and discrete GPUs use the same XPU backend.
"""

import logging
import torch
from enum import Enum
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("tts_multimodel")


class GPUBackend(Enum):
    """Supported GPU backends."""
    CUDA = "cuda"      # NVIDIA GPUs
    ROCM = "rocm"      # AMD GPUs (uses torch.cuda API via HIP)
    XPU = "xpu"        # Intel GPUs (integrated & discrete)
    MPS = "mps"        # Apple Silicon (Metal)
    CPU = "cpu"        # CPU fallback


# ---------------------------------------------------------------------------
# Strategy classes – one per backend family, used by GPUBackendManager
# ---------------------------------------------------------------------------

class _CUDAStrategy:
    """Strategy for CUDA/ROCM backends (ROCM uses hipified CUDA API)."""

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
                'name': props.name,
                'total_memory': props.total_memory,
                'major': props.major,
                'minor': props.minor,
            }
        return {'name': 'CPU', 'total_memory': 0}

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
            logger.debug(f"IPC collect failed: {e}")

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


class _XPUStrategy:
    """Strategy for Intel XPU backend."""

    @staticmethod
    def _get_ipex():
        import intel_extension_for_pytorch as ipex
        return ipex

    @staticmethod
    def get_device(index=0):
        return torch.device(f"xpu:{index}")

    @staticmethod
    def get_device_count():
        ipex = _XPUStrategy._get_ipex()
        return ipex.xpu.device_count()

    @staticmethod
    def get_device_name(index=0):
        try:
            ipex = _XPUStrategy._get_ipex()
            if ipex.xpu.is_available() and index < ipex.xpu.device_count():
                props = ipex.xpu.get_device_properties(index)
                return props.get('name', f'Intel XPU {index}')
        except Exception as e:
            logger.debug(f"Failed to get Intel XPU device name: {e}")
        return "CPU"

    @staticmethod
    def get_device_properties(index=0):
        try:
            ipex = _XPUStrategy._get_ipex()
            if ipex.xpu.is_available() and index < ipex.xpu.device_count():
                props = ipex.xpu.get_device_properties(index)
                return {
                    'name': props.get('name', f'Intel XPU {index}'),
                    'total_memory': props.get('total_memory', 0),
                }
        except Exception as e:
            logger.debug(f"Failed to get Intel XPU properties: {e}")
        return {'name': 'CPU', 'total_memory': 0}

    @staticmethod
    def memory_allocated(device=None):
        ipex = _XPUStrategy._get_ipex()
        return ipex.xpu.memory_allocated(device)

    @staticmethod
    def memory_reserved(device=None):
        ipex = _XPUStrategy._get_ipex()
        return ipex.xpu.memory_reserved(device)

    @staticmethod
    def empty_cache():
        ipex = _XPUStrategy._get_ipex()
        ipex.xpu.empty_cache()

    @staticmethod
    def synchronize(device=None):
        ipex = _XPUStrategy._get_ipex()
        if device is None:
            ipex.xpu.synchronize()
        else:
            ipex.xpu.synchronize(device)

    @staticmethod
    def get_memory_info(index=0):
        try:
            ipex = _XPUStrategy._get_ipex()
            if not ipex.xpu.is_available():
                return (0, 0, 0, 0)
            props = ipex.xpu.get_device_properties(index)
            total = props.get('total_memory', 0)
            allocated = ipex.xpu.memory_allocated(index)
            reserved = ipex.xpu.memory_reserved(index)
            return (total, allocated, reserved, total - allocated)
        except Exception as e:
            logger.error(f"Failed to get XPU memory info: {e}")
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
        return "xpu"

    @staticmethod
    def get_process_group_backend():
        return "ccl"

    @staticmethod
    def format_device_string(index=0):
        return f"xpu:{index}"


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
        return {'name': 'Apple MPS', 'total_memory': 0}

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
        return {'name': 'CPU', 'total_memory': 0}

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

    _cached_backend: Optional[GPUBackend] = None
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
                GPUBackend.ROCM: _CUDAStrategy,  # ROCM uses CUDA API
                GPUBackend.XPU: _XPUStrategy,
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
    def _is_amd_rocm(cls) -> bool:
        """Detect if running on AMD ROCM platform.

        ROCM uses hipified PyTorch API, so torch.cuda.is_available() returns
        True even on AMD GPUs. We detect AMD by checking device name patterns.

        Returns:
            True if AMD ROCM GPU is detected, False otherwise.
        """
        if not torch.cuda.is_available():
            return False

        try:
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                name_lower = props.name.lower()
                # AMD GPU naming patterns
                if any(pattern in name_lower for pattern in [
                    "amd", "radeon", "rx ", "vega", "navi", "gfx",
                    "instinct", "mi300", "mi200", "mi100"
                ]):
                    return True
        except Exception as e:
            logger.debug(f"Failed to detect AMD GPU: {e}")

        return False

    @classmethod
    def _is_intel_xpu(cls) -> bool:
        """Detect if Intel XPU is available.

        Requires intel-extension-for-pytorch to be installed.

        Returns:
            True if Intel XPU is available, False otherwise.
        """
        try:
            import intel_extension_for_pytorch as ipex
            if hasattr(ipex, 'xpu') and ipex.xpu.is_available():
                return True
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Failed to detect Intel XPU: {e}")

        return False

    @classmethod
    def _is_apple_mps(cls) -> bool:
        """Detect if Apple MPS (Metal Performance Shaders) is available.

        Returns:
            True if MPS is available, False otherwise.
        """
        try:
            return torch.backends.mps.is_available()
        except Exception as e:
            logger.debug(f"Failed to detect Apple MPS: {e}")
            return False

    @classmethod
    def detect_backend(cls) -> GPUBackend:
        """Automatically detect the best available GPU backend.

        Detection priority: NVIDIA CUDA > AMD ROCM > Intel XPU > Apple MPS > CPU

        Returns:
            The detected GPU backend enum.
        """
        if cls._cached_backend is not None:
            return cls._cached_backend

        # 1. Check NVIDIA CUDA
        if torch.cuda.is_available() and not cls._is_amd_rocm():
            cls._cached_backend = GPUBackend.CUDA
            logger.info(f"[GPU Backend] 检测到 NVIDIA CUDA 后端")
            return cls._cached_backend

        # 2. Check AMD ROCM (hipified CUDA)
        if torch.cuda.is_available() and cls._is_amd_rocm():
            cls._cached_backend = GPUBackend.ROCM
            logger.info(f"[GPU Backend] 检测到 AMD ROCM 后端")
            return cls._cached_backend

        # 3. Check Intel XPU
        if cls._is_intel_xpu():
            cls._cached_backend = GPUBackend.XPU
            logger.info(f"[GPU Backend] 检测到 Intel XPU 后端")
            return cls._cached_backend

        # 4. Check Apple MPS
        if cls._is_apple_mps():
            cls._cached_backend = GPUBackend.MPS
            logger.info(f"[GPU Backend] 检测到 Apple MPS 后端")
            return cls._cached_backend

        # 5. Fallback to CPU
        cls._cached_backend = GPUBackend.CPU
        logger.warning(f"[GPU Backend] 未检测到 GPU，使用 CPU 后端")
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
    def get_device_properties(cls, index: int = 0) -> Dict[str, Any]:
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
    def get_memory_info(cls, index: int = 0) -> Tuple[int, int, int, int]:
        """Get memory information for the primary GPU.

        Args:
            index: Device index (default: 0).

        Returns:
            Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes)
        """
        try:
            return cls._get_strategy().get_memory_info(index)
        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
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
