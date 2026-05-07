# -*- coding: utf-8 -*-
"""Abstract engine interface using Python Protocol for type-safe duck typing.
Updated for VoxCPM2-only architecture with extensible model support.
"""

from typing import Protocol, Generator, Tuple, Any, Optional, runtime_checkable
from pathlib import Path


@runtime_checkable
class TTSEngine(Protocol):
    """Protocol that all TTS engines must implement.
    
    This provides a unified interface for the route layer to call into
    any TTS engine without knowing the specific implementation details.
    """

    def is_ready(self) -> bool:
        """Check if the engine is loaded and ready for inference."""
        ...

    def load(self) -> None:
        """Load the engine and prepare for inference."""
        ...

    def unload(self) -> None:
        """Unload the engine and free GPU memory."""
        ...

    def generate_voice_design(
        self,
        text: str,
        instruction: str = "",
        normalize: bool = True,
    ) -> Tuple[str, str]:
        """Generate audio from text/voice description.
        
        Returns (audio_path, message)
        """
        ...

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ) -> Tuple[str, str]:
        """Generate audio using voice clone from reference audio.
        
        Returns (audio_path, message)
        """
        ...

    def generate_script(
        self,
        text: str,
        speaker_map: dict,
        persona_map: dict = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """Generate audio from multi-character script.
        
        Returns (audio_path, message)
        """
        ...

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        **kwargs,
    ) -> Generator[Any, None, None]:
        """Generate audio in streaming mode for long text.
        
        Yields audio chunks as they are generated.
        """
        ...


@runtime_checkable
class ControllableTTSEngine(Protocol):
    """Extended protocol for engines that support fine-grained generation control.
    
    Engines like VoxCPM2 can implement this for ultimate clone mode,
    LoRA fine-tuning, prompt continuation, and advanced parameters.
    """

    def generate_ultimate_clone(
        self,
        text: str,
        lang: str,
        ref_audio: str,
        denoise_strength: str,
        use_random_seed: bool,
        cfg_scale: float,
        denoise_steps: int,
        seed: int,
    ) -> Tuple[str, str]:
        """Generate audio with full controllable parameters.
        
        Returns (audio_path, message)
        """
        ...

    def generate_with_prompt(
        self,
        text: str,
        prompt_wav_path: str,
        prompt_text: str,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        normalize: bool = True,
        denoise: bool = True,
        retry_badcase: bool = True,
        retry_badcase_max_times: int = 3,
        retry_badcase_ratio_threshold: float = 6.0,
        min_len: int = 2,
        max_len: int = 4096,
    ) -> Tuple[str, str]:
        """Generate audio with prompt continuation mode.
        
        Returns (audio_path, message)
        """
        ...

    def load_lora(self, lora_weights_path: str) -> Tuple[list, list]:
        """Load LoRA fine-tuning weights.
        
        Returns (loaded_keys, skipped_keys)
        """
        ...

    def unload_lora(self) -> None:
        """Unload LoRA weights and reset to base model."""
        ...

    def set_lora_enabled(self, enabled: bool) -> None:
        """Enable or disable LoRA layers without unloading weights."""
        ...

    def get_lora_state_dict(self) -> dict:
        """Get current LoRA parameters state dict."""
        ...

    @property
    def lora_enabled(self) -> bool:
        """Check if LoRA is currently configured."""
        ...


@runtime_checkable
class EngineRegistry(Protocol):
    """Protocol for engine registry that manages engine discovery and instantiation."""

    def register(self, name: str, engine_class: type) -> None:
        """Register an engine class by name."""
        ...

    def get(self, name: str) -> Optional[type]:
        """Get an engine class by name."""
        ...

    def list_engines(self) -> list:
        """List all registered engine names."""
        ...
