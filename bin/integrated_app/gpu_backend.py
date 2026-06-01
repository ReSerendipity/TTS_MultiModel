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


class GPUBackendManager:
    """Unified GPU backend manager for multi-vendor GPU support.

    Automatically detects available GPU backends and provides a consistent
    API for device management, memory queries, and operations across
    different hardware vendors.

    Usage:
        backend = GPUBackendManager.detect_backend()
        device = GPUBackendManager.get_device()
        memory_info = GPUBackendManager.get_memory_info()
    """

    _cached_backend: Optional[GPUBackend] = None

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

    @classmethod
    def get_device(cls, index: int = 0) -> torch.device:
        """Get the primary compute device.

        Args:
            index: Device index (default: 0).

        Returns:
            torch.device object for the primary compute device.
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            return torch.device(f"cuda:{index}")
        elif backend == GPUBackend.XPU:
            import intel_extension_for_pytorch as ipex
            return torch.device(f"xpu:{index}")
        elif backend == GPUBackend.MPS:
            return torch.device("mps")
        else:
            return torch.device("cpu")

    @classmethod
    def get_device_count(cls) -> int:
        """Get the number of available devices.

        Returns:
            Number of devices for the current backend.
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            return torch.cuda.device_count()
        elif backend == GPUBackend.XPU:
            import intel_extension_for_pytorch as ipex
            return ipex.xpu.device_count()
        elif backend == GPUBackend.MPS:
            return 1  # MPS only supports one device
        else:
            return 0

    @classmethod
    def get_device_name(cls, index: int = 0) -> str:
        """Get the device name.

        Args:
            index: Device index (default: 0).

        Returns:
            Device name string, or "CPU" if no GPU available.
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            if torch.cuda.is_available() and index < torch.cuda.device_count():
                return torch.cuda.get_device_name(index)
        elif backend == GPUBackend.XPU:
            try:
                import intel_extension_for_pytorch as ipex
                if ipex.xpu.is_available() and index < ipex.xpu.device_count():
                    props = ipex.xpu.get_device_properties(index)
                    return props.get('name', f'Intel XPU {index}')
            except Exception as e:
                logger.debug(f"Failed to get Intel XPU device name: {e}")
        elif backend == GPUBackend.MPS:
            return "Apple MPS"

        return "CPU"

    @classmethod
    def get_device_properties(cls, index: int = 0) -> Dict[str, Any]:
        """Get device properties in a backend-agnostic way.

        Args:
            index: Device index (default: 0).

        Returns:
            Dictionary with device properties (name, total_memory, etc.).
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            if torch.cuda.is_available() and index < torch.cuda.device_count():
                props = torch.cuda.get_device_properties(index)
                return {
                    'name': props.name,
                    'total_memory': props.total_memory,
                    'major': props.major,
                    'minor': props.minor,
                }
        elif backend == GPUBackend.XPU:
            try:
                import intel_extension_for_pytorch as ipex
                if ipex.xpu.is_available() and index < ipex.xpu.device_count():
                    props = ipex.xpu.get_device_properties(index)
                    return {
                        'name': props.get('name', f'Intel XPU {index}'),
                        'total_memory': props.get('total_memory', 0),
                    }
            except Exception as e:
                logger.debug(f"Failed to get Intel XPU properties: {e}")

        return {
            'name': 'CPU',
            'total_memory': 0,
        }

    @classmethod
    def memory_allocated(cls, device=None) -> int:
        """Get currently allocated memory on the device.

        Args:
            device: Device index or torch.device (default: primary device).

        Returns:
            Allocated memory in bytes.
        """
        backend = cls.detect_backend()

        if device is None:
            device = cls.get_device()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            if isinstance(device, int):
                return torch.cuda.memory_allocated(device)
            return torch.cuda.memory_allocated(device)
        elif backend == GPUBackend.XPU:
            import intel_extension_for_pytorch as ipex
            if isinstance(device, int):
                return ipex.xpu.memory_allocated(device)
            return ipex.xpu.memory_allocated(device)
        elif backend == GPUBackend.MPS:
            # MPS doesn't provide memory allocation APIs
            return 0

        return 0

    @classmethod
    def memory_reserved(cls, device=None) -> int:
        """Get currently reserved memory on the device.

        Args:
            device: Device index or torch.device (default: primary device).

        Returns:
            Reserved memory in bytes.
        """
        backend = cls.detect_backend()

        if device is None:
            device = cls.get_device()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            if isinstance(device, int):
                return torch.cuda.memory_reserved(device)
            return torch.cuda.memory_reserved(device)
        elif backend == GPUBackend.XPU:
            import intel_extension_for_pytorch as ipex
            if isinstance(device, int):
                return ipex.xpu.memory_reserved(device)
            return ipex.xpu.memory_reserved(device)
        elif backend == GPUBackend.MPS:
            return 0

        return 0

    @classmethod
    def empty_cache(cls):
        """Empty the memory cache for the current backend."""
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            torch.cuda.empty_cache()
        elif backend == GPUBackend.XPU:
            import intel_extension_for_pytorch as ipex
            ipex.xpu.empty_cache()
        elif backend == GPUBackend.MPS:
            pass  # MPS doesn't have cache empty API

    @classmethod
    def synchronize(cls, device=None):
        """Synchronize the current device.

        Args:
            device: Device index or torch.device (default: primary device).
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            if device is None:
                torch.cuda.synchronize()
            elif isinstance(device, int):
                torch.cuda.synchronize(device)
            else:
                torch.cuda.synchronize(device)
        elif backend == GPUBackend.XPU:
            import intel_extension_for_pytorch as ipex
            if device is None:
                ipex.xpu.synchronize()
            elif isinstance(device, int):
                ipex.xpu.synchronize(device)
            else:
                ipex.xpu.synchronize(device)
        elif backend == GPUBackend.MPS:
            pass  # MPS doesn't have explicit synchronize API

    @classmethod
    def get_memory_info(cls, index: int = 0) -> Tuple[int, int, int, int]:
        """Get memory information for the primary GPU.

        Args:
            index: Device index (default: 0).

        Returns:
            Tuple of (total_bytes, allocated_bytes, reserved_bytes, free_bytes)
        """
        backend = cls.detect_backend()

        try:
            if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
                if not torch.cuda.is_available():
                    return (0, 0, 0, 0)
                props = torch.cuda.get_device_properties(index)
                total = props.total_memory
                allocated = torch.cuda.memory_allocated(index)
                reserved = torch.cuda.memory_reserved(index)
                free = total - allocated
                return (total, allocated, reserved, free)

            elif backend == GPUBackend.XPU:
                import intel_extension_for_pytorch as ipex
                if not ipex.xpu.is_available():
                    return (0, 0, 0, 0)
                props = ipex.xpu.get_device_properties(index)
                total = props.get('total_memory', 0)
                allocated = ipex.xpu.memory_allocated(index)
                reserved = ipex.xpu.memory_reserved(index)
                free = total - allocated
                return (total, allocated, reserved, free)

            elif backend == GPUBackend.MPS:
                # MPS doesn't provide memory info
                return (0, 0, 0, 0)

        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
            return (0, 0, 0, 0)

        return (0, 0, 0, 0)

    @classmethod
    def get_cuda_clear_workspaces_func(cls):
        """Get CUDA cuBLAS workspace clear function if available.

        Returns:
            Callable to clear cuBLAS workspaces, or None if not available.
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            try:
                return torch._C._cuda_clearCublasWorkspaces
            except AttributeError:
                pass

        return None

    @classmethod
    def ipc_collect(cls, device=None):
        """Perform IPC collection (CUDA-specific).

        Args:
            device: Device index (default: None).
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            try:
                if device is None:
                    torch.cuda.ipc_collect()
                else:
                    torch.cuda.ipc_collect(device)
            except Exception as e:
                logger.debug(f"IPC collect failed: {e}")

    @classmethod
    def get_grad_scaler(cls, enabled: bool = True):
        """Get the appropriate gradient scaler for the current backend.

        Args:
            enabled: Whether to enable gradient scaling.

        Returns:
            GradScaler instance or None if not applicable.
        """
        backend = cls.detect_backend()

        if enabled and (backend == GPUBackend.CUDA or backend == GPUBackend.ROCM):
            return torch.amp.GradScaler("cuda")
        elif enabled and backend == GPUBackend.XPU:
            # XPU may use different scaling strategy
            return None
        else:
            return None

    @classmethod
    def get_autocast_device_type(cls) -> str:
        """Get the device type string for autocast.

        Returns:
            Device type string for torch.amp.autocast.
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            return "cuda"
        elif backend == GPUBackend.XPU:
            return "xpu"
        else:
            return "cpu"

    @classmethod
    def get_process_group_backend(cls) -> str:
        """Get the appropriate distributed process group backend.

        Returns:
            Process group backend string ("nccl", "gloo", etc.).
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA:
            return "nccl"
        elif backend == GPUBackend.ROCM:
            return "nccl"  # ROCM also uses NCCL (hipified)
        elif backend == GPUBackend.XPU:
            return "ccl"  # Intel uses CCL
        else:
            return "gloo"  # CPU fallback

    @classmethod
    def format_device_string(cls, index: int = 0) -> str:
        """Format device string for .to() calls.

        Args:
            index: Device index (default: 0).

        Returns:
            Device string suitable for tensor.to(device_string).
        """
        backend = cls.detect_backend()

        if backend == GPUBackend.CUDA or backend == GPUBackend.ROCM:
            return f"cuda:{index}"
        elif backend == GPUBackend.XPU:
            return f"xpu:{index}"
        elif backend == GPUBackend.MPS:
            return "mps"
        else:
            return "cpu"
