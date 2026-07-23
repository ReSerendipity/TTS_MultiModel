"""vLLM acceleration backend for TTS inference.

Provides optional integration with vLLM (https://github.com/vllm-project/vllm)
for high-throughput LLM inference acceleration in the TTS pipeline.

vLLM can accelerate the language model component of VoxCPM2 by:
  - PagedAttention for efficient KV-cache management
  - Continuous batching for concurrent requests
  - Tensor parallelism for multi-GPU setups
  - Optimized CUDA kernels for attention computation

This module acts as a thin adapter layer that:
  1. Detects vLLM availability at runtime
  2. Provides a unified interface for standard vs vLLM inference
  3. Manages vLLM engine lifecycle (init, warmup, shutdown)
  4. Falls back gracefully to standard PyTorch if vLLM is unavailable

Usage:
    # Check availability
    from integrated_app.vllm_backend import is_vllm_available

    # Initialize (optional)
    from integrated_app.vllm_backend import get_vllm_backend
    backend = get_vllm_backend()
    if backend.is_available():
        backend.initialize(model_path="pretrained_models/VoxCPM2")

    # Use for inference
    output = backend.generate(input_ids, sampling_params)

Note:
    vLLM is an OPTIONAL dependency. The project works without it.
    Install with: pip install vllm>=0.6.0
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tts_multimodel.vllm_backend")


def is_vllm_available() -> bool:
    """Check if vLLM is installed and importable."""
    try:
        import vllm  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class VLLMConfig:
    """Configuration for vLLM backend."""

    tensor_parallel_size: int = 1
    gpu_memory_utilization: float = 0.85
    max_model_len: int = 4096
    dtype: str = "auto"  # "auto", "float16", "bfloat16"
    enforce_eager: bool = False  # Disable CUDA graph for debugging
    trust_remote_code: bool = True
    enable_prefix_caching: bool = True
    block_size: int = 16
    swap_space: int = 4  # GiB
    disable_log_stats: bool = True

    def to_vllm_kwargs(self) -> dict[str, Any]:
        """Convert to vLLM LLMEngine constructor kwargs."""
        return {
            "tensor_parallel_size": self.tensor_parallel_size,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "max_model_len": self.max_model_len,
            "dtype": self.dtype,
            "enforce_eager": self.enforce_eager,
            "trust_remote_code": self.trust_remote_code,
            "enable_prefix_caching": self.enable_prefix_caching,
            "block_size": self.block_size,
            "swap_space": self.swap_space,
            "disable_log_stats": self.disable_log_stats,
        }


@dataclass
class VLLMStatus:
    """Status of the vLLM backend."""

    available: bool = False
    initialized: bool = False
    model_path: str = ""
    engine_type: str = ""  # "vllm" or "fallback"
    init_time_s: float = 0.0
    error: str = ""
    gpu_count: int = 0
    gpu_memory_gb: float = 0.0


class VLLMBackend:
    """vLLM acceleration backend with automatic fallback.

    This class wraps vLLM's LLMEngine and provides:
    - Lazy initialization (only creates engine when first needed)
    - Automatic fallback to standard PyTorch inference
    - Thread-safe engine access
    - Health monitoring and status reporting

    The backend does NOT replace the existing inference pipeline.
    Instead, it can be used as an acceleration option when:
    - vLLM is installed
    - GPU has sufficient memory
    - The model architecture is compatible
    """

    def __init__(self, config: VLLMConfig | None = None):
        self._config = config or VLLMConfig()
        self._engine: Any = None  # vLLM LLMEngine instance
        self._status = VLLMStatus()
        self._lock = threading.Lock()
        self._generation_count = 0

    @property
    def is_available(self) -> bool:
        """Check if vLLM is installed."""
        return is_vllm_available()

    @property
    def is_ready(self) -> bool:
        """Check if the engine is initialized and ready."""
        return self._status.initialized and self._engine is not None

    @property
    def status(self) -> VLLMStatus:
        """Get current backend status."""
        return self._status

    def initialize(self, model_path: str) -> bool:
        """Initialize the vLLM engine.

        Args:
            model_path: Path to the model weights or HuggingFace model ID.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        with self._lock:
            if self._status.initialized:
                logger.info("[vLLM] Engine already initialized")
                return True

            if not self.is_available:
                self._status.error = "vLLM is not installed"
                logger.warning(
                    "[vLLM] vLLM not installed. Install with: pip install vllm>=0.6.0"
                )
                return False

            start_time = time.time()

            try:
                import vllm  # noqa: F401
                from vllm import LLM, SamplingParams

                logger.info(f"[vLLM] Initializing engine with model: {model_path}")
                logger.info(f"[vLLM] Config: TP={self._config.tensor_parallel_size}, "
                           f"GPU mem={self._config.gpu_memory_utilization:.0%}, "
                           f"max_len={self._config.max_model_len}")

                engine_kwargs = self._config.to_vllm_kwargs()
                engine_kwargs["model"] = model_path
                self._engine = LLM(**engine_kwargs)

                self._status.available = True
                self._status.initialized = True
                self._status.model_path = model_path
                self._status.engine_type = "vllm"
                self._status.init_time_s = time.time() - start_time

                # Get GPU info
                try:
                    import torch
                    if torch.cuda.is_available():
                        self._status.gpu_count = torch.cuda.device_count()
                        self._status.gpu_memory_gb = (
                            torch.cuda.get_device_properties(0).total_mem / (1024**3)
                        )
                except Exception:
                    pass

                logger.info(
                    f"[vLLM] Engine initialized in {self._status.init_time_s:.1f}s "
                    f"(GPUs: {self._status.gpu_count}, "
                    f"Memory: {self._status.gpu_memory_gb:.1f}GB)"
                )
                return True

            except Exception as e:
                self._status.error = str(e)
                logger.error(f"[vLLM] Initialization failed: {e}")
                return False

    def generate(
        self,
        prompt: str | list[int],
        max_tokens: int = 2048,
        temperature: float = 0.8,
        top_p: float = 0.95,
        top_k: int = 50,
        stop: list[str] | None = None,
        **kwargs,
    ) -> str | None:
        """Generate text using vLLM engine.

        Args:
            prompt: Input prompt (string or token IDs).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            top_p: Top-p sampling parameter.
            top_k: Top-k sampling parameter.
            stop: Stop sequences.
            **kwargs: Additional sampling parameters.

        Returns:
            Generated text, or None if engine is not ready.
        """
        if not self.is_ready:
            logger.warning("[vLLM] Engine not ready, falling back to standard inference")
            return None

        try:
            from vllm import SamplingParams

            sampling_params = SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                stop=stop or [],
                **kwargs,
            )

            outputs = self._engine.generate([prompt], sampling_params)
            self._generation_count += 1

            if outputs:
                return outputs[0].outputs[0].text
            return None

        except Exception as e:
            logger.error(f"[vLLM] Generation failed: {e}")
            return None

    def shutdown(self) -> None:
        """Shutdown the vLLM engine and release resources."""
        with self._lock:
            if self._engine is not None:
                try:
                    del self._engine
                    self._engine = None
                except Exception as e:
                    logger.warning(f"[vLLM] Engine shutdown error: {e}")

                # Clear GPU memory
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass

            self._status.initialized = False
            self._status.engine_type = ""
            logger.info(
                f"[vLLM] Engine shutdown. "
                f"Total generations served: {self._generation_count}"
            )

    def get_stats(self) -> dict:
        """Get backend statistics."""
        return {
            "available": self.is_available,
            "initialized": self._status.initialized,
            "engine_type": self._status.engine_type,
            "model_path": self._status.model_path,
            "init_time_s": round(self._status.init_time_s, 2),
            "generation_count": self._generation_count,
            "gpu_count": self._status.gpu_count,
            "gpu_memory_gb": round(self._status.gpu_memory_gb, 1),
            "error": self._status.error,
        }


# ============================================================================
# Module-level singleton
# ============================================================================

_backend_instance: VLLMBackend | None = None
_backend_lock = threading.Lock()


def get_vllm_backend(config: VLLMConfig | None = None) -> VLLMBackend:
    """Get or create the singleton vLLM backend instance.

    Args:
        config: Optional configuration. Only used on first call.

    Returns:
        The singleton VLLMBackend instance.
    """
    global _backend_instance
    if _backend_instance is None:
        with _backend_lock:
            if _backend_instance is None:
                _backend_instance = VLLMBackend(config)
    return _backend_instance


def check_vllm_config_compatibility(model_path: str) -> dict:
    """Check if the model is compatible with vLLM acceleration.

    Args:
        model_path: Path to the model directory.

    Returns:
        Dict with compatibility info: {compatible: bool, reason: str, ...}
    """
    result = {
        "compatible": False,
        "reason": "",
        "vllm_installed": is_vllm_available(),
        "model_path": model_path,
    }

    if not result["vllm_installed"]:
        result["reason"] = "vLLM is not installed"
        return result

    if not os.path.isdir(model_path):
        result["reason"] = f"Model path does not exist: {model_path}"
        return result

    # Check for model config
    config_path = os.path.join(model_path, "config.json")
    if not os.path.exists(config_path):
        result["reason"] = "No config.json found in model directory"
        return result

    try:
        import json

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        architecture = config.get("architecture", "")
        # vLLM supports many architectures; check common ones
        supported_archs = {
            "LlamaForCausalLM",
            "MistralForCausalLM",
            "Qwen2ForCausalLM",
            "MiniCPMForCausalLM",
            "PhiForCausalLM",
        }

        if architecture in supported_archs:
            result["compatible"] = True
            result["reason"] = f"Model architecture '{architecture}' is supported by vLLM"
        else:
            result["reason"] = (
                f"Model architecture '{architecture}' may not be directly supported. "
                f"Supported: {', '.join(sorted(supported_archs))}"
            )

    except Exception as e:
        result["reason"] = f"Failed to check model config: {e}"

    return result


# Environment variable for disabling vLLM (useful for testing)
VLLM_DISABLED = os.environ.get("TTS_VLLM_DISABLED", "0") == "1"
