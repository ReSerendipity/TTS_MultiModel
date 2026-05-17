"""ModelRegistry: centralized, thread-safe model state management for VoxCPM2.

Single source of truth for all model state.  Implemented as a thread-safe
singleton with RLock-protected property access for the six core state
variables:

    voxcpm_model   -- VoxCPM2 main model instance
    voxcpm_asr     -- ASR model instance
    current_engine -- Active engine name  (e.g. "voxcpm2")
    current_type   -- Active model type
    current_size   -- Active model size variant
    model_loaded   -- Whether a model is currently loaded (derived, read-only)

Usage::

    from .model_registry import registry

    # Read
    model = registry.voxcpm_model

    # Write (thread-safe)
    registry.voxcpm_model = new_model

    # Batch update (single lock acquisition)
    registry.set_voxcpm_loaded(model, asr=asr_model)

    # Query helpers
    registry.is_voxcpm_ready()
    registry.get_current_model_info()
"""

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger("tts_multimodel")


class ModelRegistry:
    """Centralized, thread-safe registry for all model state.

    Singleton -- always obtain the instance via the module-level
    ``registry`` object or ``ModelRegistry()`` (both return the same
    object).

    Core state is backed by private attributes (``_voxcpm_model``, etc.)
    and exposed through ``@property`` accessors that acquire an
    ``RLock`` on every read and write, guaranteeing thread safety at the
    individual-attribute level.

    For multi-attribute updates that must be atomic, use the batch
    methods (:meth:`set_voxcpm_loaded`, :meth:`clear_voxcpm`,
    :meth:`clear_all`) which acquire the lock once for the whole
    operation.
    """

    _instance: Optional["ModelRegistry"] = None
    _init_done: bool = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def __new__(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if ModelRegistry._init_done:
            return
        ModelRegistry._init_done = True

        self._lock = threading.RLock()

        # --- Core model state (property-backed, thread-safe) ---
        self._voxcpm_model = None
        self._voxcpm_asr = None
        self._current_engine: str | None = "voxcpm2"
        self._current_type: str = "voxcpm2"
        self._current_size: str = "voxcpm2"

        # --- Extended VoxCPM2 state (simple attributes) ---
        self.voxcpm_enhancer_model = None
        self.voxcpm_ultimate: bool = False
        self.voxcpm_voiceclone_enabled: bool = False
        self.voxcpm_control_enabled: bool = False

        # --- Cache & memory management ---
        self.voice_embed_cache = None
        self.memory_monitor = None
        self.cache_size: int = 15

        # --- Persona management ---
        self.persona_manager = None
        self.persona_mode: str | None = None
        self.selected_persona: str | None = None

        # --- FFmpeg pool ---
        self.ffmpeg_pool = None

        # --- Tracking & progress ---
        self.gen_tracker = None
        self.progress_mgr = None

    # ------------------------------------------------------------------
    # Reset (for testing only)
    # ------------------------------------------------------------------

    @classmethod
    def _reset(cls) -> None:
        """Reset the singleton so the next ``ModelRegistry()`` call
        re-initializes all state.  **Only use in tests.**
        """
        cls._instance = None
        cls._init_done = False

    # ------------------------------------------------------------------
    # Core state properties (thread-safe)
    # ------------------------------------------------------------------

    @property
    def voxcpm_model(self):
        with self._lock:
            return self._voxcpm_model

    @voxcpm_model.setter
    def voxcpm_model(self, value):
        with self._lock:
            self._voxcpm_model = value

    @property
    def voxcpm_asr(self):
        with self._lock:
            return self._voxcpm_asr

    @voxcpm_asr.setter
    def voxcpm_asr(self, value):
        with self._lock:
            self._voxcpm_asr = value

    @property
    def current_engine(self) -> str | None:
        with self._lock:
            return self._current_engine

    @current_engine.setter
    def current_engine(self, value: str | None):
        with self._lock:
            self._current_engine = value

    @property
    def current_type(self) -> str:
        with self._lock:
            return self._current_type

    @current_type.setter
    def current_type(self, value: str):
        with self._lock:
            self._current_type = value

    @property
    def current_size(self) -> str:
        with self._lock:
            return self._current_size

    @current_size.setter
    def current_size(self, value: str):
        with self._lock:
            self._current_size = value

    @property
    def model_loaded(self) -> bool:
        """Read-only: ``True`` when a model instance is present."""
        with self._lock:
            return self._voxcpm_model is not None

    # ------------------------------------------------------------------
    # Batch update helpers (single lock acquisition)
    # ------------------------------------------------------------------

    def set_voxcpm_loaded(
        self,
        model,
        asr=None,
        enhancer_model=None,
        ultimate: bool = False,
        voiceclone: bool = False,
        control: bool = False,
    ) -> None:
        """Atomically set all VoxCPM2 loaded state.

        Sets *model*, *asr*, *enhancer_model*, feature flags, and
        resets ``current_engine / current_type / current_size`` to
        ``"voxcpm2"`` -- all under a single lock acquisition.
        """
        with self._lock:
            self._voxcpm_model = model
            self._voxcpm_asr = asr
            self.voxcpm_enhancer_model = enhancer_model
            self.voxcpm_ultimate = ultimate
            self.voxcpm_voiceclone_enabled = voiceclone
            self.voxcpm_control_enabled = control
            self._current_engine = "voxcpm2"
            self._current_type = "voxcpm2"
            self._current_size = "voxcpm2"

    def clear_voxcpm(self) -> None:
        """Atomically clear all VoxCPM2 model references and flags.

        Sets model / ASR / enhancer to ``None`` and feature flags to
        ``False``.  Does **not** change ``current_engine / type / size``
        (use :meth:`clear_all` for a full reset).
        """
        with self._lock:
            self._voxcpm_model = None
            self._voxcpm_asr = None
            self.voxcpm_enhancer_model = None
            self.voxcpm_ultimate = False
            self.voxcpm_voiceclone_enabled = False
            self.voxcpm_control_enabled = False

    def clear_all(self) -> None:
        """Atomically reset all core state to defaults.

        Model / ASR become ``None``, engine becomes ``None``, type and
        size revert to ``"voxcpm2"``.
        """
        with self._lock:
            self._voxcpm_model = None
            self._voxcpm_asr = None
            self._current_engine = None
            self._current_type = "voxcpm2"
            self._current_size = "voxcpm2"
            self.voxcpm_enhancer_model = None
            self.voxcpm_ultimate = False
            self.voxcpm_voiceclone_enabled = False
            self.voxcpm_control_enabled = False

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def is_voxcpm_ready(self) -> bool:
        with self._lock:
            return (
                self._voxcpm_model is not None
                and self._current_engine == "voxcpm2"
            )

    def is_engine_ready(self) -> bool:
        return self.is_voxcpm_ready()

    def get_current_model_info(self) -> dict[str, Any]:
        with self._lock:
            if self._voxcpm_model is not None and self._current_engine == "voxcpm2":
                return {
                    "engine": self._current_engine,
                    "type": self._current_type,
                    "size": self._current_size,
                    "ready": True,
                    "is_ultimate": self.voxcpm_ultimate,
                    "voiceclone_enabled": self.voxcpm_voiceclone_enabled,
                    "control_enabled": self.voxcpm_control_enabled,
                }
            return {"ready": False}

    def switch_to(self, engine: str) -> None:
        with self._lock:
            self._current_engine = engine


# ------------------------------------------------------------------
# Module-level singleton -- the canonical access point
# ------------------------------------------------------------------
registry = ModelRegistry()
