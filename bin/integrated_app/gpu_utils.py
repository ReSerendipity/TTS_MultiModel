# -*- coding: utf-8 -*-
"""GPU utility functions: OOM detection and VRAM management."""

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
