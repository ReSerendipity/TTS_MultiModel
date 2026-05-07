# -*- coding: utf-8 -*-
"""ModelRegistry: centralized model state management for VoxCPM2."""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("tts_multimodel")


class ModelRegistry:
    """Centralized registry for all model state, VoxCPM2-only."""

    def __init__(self):
        self.current_engine: str = "voxcpm2"

        # VoxCPM2 engine state
        self.voxcpm_model = None
        self.voxcpm_asr_model = None
        self.voxcpm_enhancer_model = None
        self.voxcpm_ultimate = False
        self.voxcpm_voiceclone_enabled = False
        self.voxcpm_control_enabled = False

        # Cache & memory management
        self.voice_embed_cache = None
        self.memory_monitor = None
        self.cache_size: int = 15

        # Persona & persona management
        self.persona_manager = None

        # FFmpeg pool
        self.ffmpeg_pool = None

        # Tracking & progress
        self.gen_tracker = None
        self.progress_mgr = None

        # Persona state for UI
        self.persona_mode: Optional[str] = None
        self.selected_persona: Optional[str] = None

    # --- Query helpers ---

    def is_voxcpm_ready(self) -> bool:
        return self.voxcpm_model is not None and self.current_engine == "voxcpm2"

    def is_engine_ready(self) -> bool:
        return self.is_voxcpm_ready()

    def get_current_model_info(self) -> Dict[str, Any]:
        if self.is_voxcpm_ready():
            return {
                "engine": self.current_engine,
                "ready": True,
                "is_ultimate": self.voxcpm_ultimate,
                "voiceclone_enabled": self.voxcpm_voiceclone_enabled,
                "control_enabled": self.voxcpm_control_enabled,
            }
        return {"ready": False}

    def switch_to(self, engine: str):
        self.current_engine = engine

    def set_voxcpm_loaded(self, model, asr_model=None, enhancer_model=None, ultimate: bool = False,
                         voiceclone: bool = False, control: bool = False):
        self.voxcpm_model = model
        self.voxcpm_asr_model = asr_model
        self.voxcpm_enhancer_model = enhancer_model
        self.voxcpm_ultimate = ultimate
        self.voxcpm_voiceclone_enabled = voiceclone
        self.voxcpm_control_enabled = control
        self.current_engine = "voxcpm2"

    def clear_voxcpm(self):
        self.voxcpm_model = None
        self.voxcpm_asr_model = None
        self.voxcpm_enhancer_model = None
        self.voxcpm_ultimate = False
        self.voxcpm_voiceclone_enabled = False
        self.voxcpm_control_enabled = False
