# -*- coding: utf-8 -*-
"""Abstract engine interface using Python Protocol for type-safe duck typing.
Supports VoxCPM2 and IndexTTS 2.0 dual-engine architecture.
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
        **kwargs,
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
        speaker_map: dict = None,
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
        instruction: str = "",
        ref_audio_path: Optional[str] = None,
        advanced_cfg: float = 2.0,
        advanced_norm: bool = True,
        advanced_denoise: float = 1.0,
        advanced_steps: int = 10,
        advanced_seed: int = -1,
        **kwargs,
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
        **kwargs,
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
        ...

    def get(self, name: str) -> Optional[type]:
        ...

    def list_engines(self) -> list:
        ...


class InMemoryEngineRegistry:

    def __init__(self):
        self._engines: dict[str, type] = {}
        self._metadata: dict[str, dict] = {}

    def register(self, name: str, engine_class: type, display_name: str = "", vram_requirement: float = 6.0) -> None:
        self._engines[name] = engine_class
        self._metadata[name] = {
            "display_name": display_name or name,
            "vram_requirement": vram_requirement,
        }

    def get(self, name: str) -> Optional[type]:
        return self._engines.get(name)

    def list_engines(self) -> list[str]:
        return list(self._engines.keys())

    def get_display_name(self, name: str) -> str:
        return self._metadata.get(name, {}).get("display_name", name)

    def get_vram_requirement(self, name: str) -> float:
        return self._metadata.get(name, {}).get("vram_requirement", 6.0)

    def is_registered(self, name: str) -> bool:
        return name in self._engines


engine_registry = InMemoryEngineRegistry()


# Register built-in engines
def _register_builtin_engines():
    """Register built-in TTS engines."""
    try:
        from .engines.voxcpm2.engine import VoxCPM2Engine
        engine_registry.register(
            "voxcpm2",
            VoxCPM2Engine,
            display_name="VoxCPM2",
            vram_requirement=6.0,
        )
    except ImportError:
        pass

    try:
        from .engines.indextts2_engine import IndexTTS2Engine
        engine_registry.register(
            "indextts2",
            IndexTTS2Engine,
            display_name="IndexTTS2",
            vram_requirement=4.0,
        )
    except ImportError:
        pass


_register_builtin_engines()
