"""VoxCPM2 Engine implementing TTSEngine Protocol."""

import logging
from collections.abc import Generator
from typing import Any

from ...engine_interface import ControllableTTSEngine, TTSEngine
from ...model_registry import registry

logger = logging.getLogger("tts_multimodel")


class VoxCPM2Engine(TTSEngine, ControllableTTSEngine):
    """VoxCPM2 engine implementing the TTSEngine Protocol.

    Delegates to the existing module-level functions in the voxcpm2 package.
    """

    def is_ready(self) -> bool:
        """Check if the VoxCPM2 model is loaded and ready."""
        return registry.voxcpm_model is not None

    def load(self) -> None:
        """Load the VoxCPM2 model. Delegates to model_manager.load_voxcpm2()."""
        from ...model_manager import load_voxcpm2

        for _ in load_voxcpm2():
            pass

    def unload(self) -> None:
        """Unload the VoxCPM2 model. Delegates to model_manager.unload_model()."""
        from ...model_manager import unload_model

        unload_model()

    def generate_voice_design(
        self,
        text: str,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ) -> tuple[Any, str]:
        """Generate audio from text/voice description."""
        from .design import fn_voxcpm_design

        return fn_voxcpm_design(
            text=text,
            instruction=instruction,
            normalize=normalize,
            **kwargs,
        )

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: str | None = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ) -> tuple[Any, str]:
        """Generate audio using voice clone from reference audio."""
        from .clone import fn_voxcpm_clone

        return fn_voxcpm_clone(
            text=text,
            ref_audio_path=reference_audio_path,
            instruction=instruction,
            normalize=normalize,
            **kwargs,
        )

    def generate_script(
        self,
        text: str,
        speaker_map: dict = None,
        persona_map: dict = None,
        **kwargs,
    ) -> tuple[Any, str]:
        """Generate audio from multi-character script.

        Accepts both Protocol-style args (speaker_map, persona_map) and
        route-style args (advanced_cfg, advanced_norm, etc.) via **kwargs.
        """
        from .script import fn_voxcpm_script_studio

        return fn_voxcpm_script_studio(
            script_text=text,
            persona_map_with_wav=persona_map,
            **kwargs,
        )

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: str | None = None,
        **kwargs,
    ) -> Generator[Any, None, None]:
        """Generate audio in streaming mode."""
        from .streaming import fn_voxcpm_streaming

        return fn_voxcpm_streaming(text=text, ref_audio_path=reference_audio_path, **kwargs)

    def generate_ultimate_clone(
        self,
        text: str,
        instruction: str = "",
        ref_audio_path: str | None = None,
        advanced_cfg: float = 2.0,
        advanced_norm: bool = True,
        advanced_denoise: float = 1.0,
        advanced_steps: int = 10,
        advanced_seed: int = -1,
        **kwargs,
    ) -> tuple[Any, str]:
        """Generate audio with full controllable parameters.

        Accepts both Protocol-style args and route-style args for
        backward compatibility.
        """
        from .ultimate import fn_voxcpm_ultimate_clone

        return fn_voxcpm_ultimate_clone(
            text=text,
            instruction=instruction,
            ref_audio_path=ref_audio_path,
            advanced_cfg=advanced_cfg,
            advanced_norm=advanced_norm,
            advanced_denoise=advanced_denoise,
            advanced_steps=advanced_steps,
            advanced_seed=advanced_seed,
        )

    def generate_with_prompt(
        self,
        text: str,
        prompt_wav_path: str,
        prompt_text: str,
        **kwargs,
    ) -> tuple[Any, str]:
        """Generate audio with prompt continuation mode."""
        from .prompt import fn_voxcpm_prompt_continue

        return fn_voxcpm_prompt_continue(
            text=text,
            prompt_wav_path=prompt_wav_path,
            prompt_text=prompt_text,
        )

    def load_lora(self, lora_weights_path: str) -> tuple[list, list]:
        """Load LoRA fine-tuning weights."""
        from .lora import load_lora_weights

        return load_lora_weights(lora_weights_path)

    def unload_lora(self) -> None:
        """Unload LoRA weights."""
        from .lora import unload_lora_weights

        unload_lora_weights()

    def set_lora_enabled(self, enabled: bool) -> None:
        """Enable or disable LoRA layers."""
        from .lora import fn_voxcpm_set_lora_enabled

        fn_voxcpm_set_lora_enabled(enabled)

    def get_lora_state_dict(self) -> dict:
        """Get current LoRA parameters state dict."""
        from .lora import get_lora_state_dict

        return get_lora_state_dict()

    @property
    def lora_enabled(self) -> bool:
        """Check if LoRA is currently configured."""
        from .lora import is_lora_enabled

        return is_lora_enabled()
