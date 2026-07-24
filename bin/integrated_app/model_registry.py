"""ModelRegistry: centralized, thread-safe model state management.

Single source of truth for all model state.  Implemented as a thread-safe
singleton with RLock-protected property access for the core state
variables:

    voxcpm_model      -- VoxCPM2 main model instance
    voxcpm_asr        -- ASR model instance
    indextts2_engine  -- IndexTTS 2.0 engine instance
    current_engine    -- Active engine name  (e.g. "voxcpm2" or "indextts2")
    current_type      -- Active model type
    current_size      -- Active model size variant
    model_loaded      -- Whether a model is currently loaded (derived, read-only)

Usage::

    from .model_registry import registry

    # Read
    model = registry.voxcpm_model

    # Write (thread-safe)
    registry.voxcpm_model = new_model

    # Batch update (single lock acquisition)
    registry.set_voxcpm_loaded(model, asr=asr_model)
    registry.set_indextts2_loaded(engine)

    # Query helpers
    registry.is_engine_ready()
    registry.get_current_model_info()
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Any

logger = logging.getLogger("tts_multimodel")


class EngineName(str, Enum):
    VOXCPM2 = "voxcpm2"
    INDEXTTS2 = "indextts2"


ENGINE_DISPLAY_NAMES: dict[str, str] = {
    EngineName.VOXCPM2.value: "VoxCPM2",
    EngineName.INDEXTTS2.value: "IndexTTS 2.0",
}

ENGINE_VRAM_REQUIREMENTS: dict[str, float] = {
    EngineName.VOXCPM2.value: 6.5,
    EngineName.INDEXTTS2.value: 6.0,
}

# --- 声明式引擎规格缓存（由 load_engine_specs_from_config 填充） ---
_engine_specs: dict[str, Any] = {}


def load_engine_specs_from_config(config_models_module=None) -> None:
    """从 config_models 的 EngineSpecConfig 加载引擎规格，填充缓存。

    对齐 VoiceBox 的声明式 ModelConfig 设计：引擎元数据（显存需求、
    显示名称、支持特性等）由 config.yaml 驱动，而非硬编码。
    新增引擎只需在 config.yaml 的 models.engines 中声明即可。

    Args:
        config_models_module: 可选的 config_models 模块引用。
                             若为 None 则延迟导入。
    """
    global _engine_specs
    try:
        if config_models_module is None:
            from . import config_models
        else:
            config_models = config_models_module

        # 从 AppConfig 获取引擎规格
        try:
            from .config import get_config
            app_config = get_config()
            if app_config and app_config.models and app_config.models.engines:
                for name, spec in app_config.models.engines.items():
                    _engine_specs[name] = spec
                    # 同步更新硬编码字典（保持向后兼容）
                    ENGINE_DISPLAY_NAMES[name] = spec.display_name or name
                    ENGINE_VRAM_REQUIREMENTS[name] = spec.vram_gb
                logger.info(f"[ModelRegistry] 已从配置加载 {len(_engine_specs)} 个引擎规格: {list(_engine_specs.keys())}")
            else:
                logger.debug("[ModelRegistry] 配置中未找到引擎规格，使用默认值")
        except Exception as e:
            logger.debug(f"[ModelRegistry] 加载引擎规格失败（使用默认值）: {e}")
    except Exception as e:
        logger.debug(f"[ModelRegistry] load_engine_specs_from_config 失败: {e}")


def get_engine_spec(name: str):
    """获取指定引擎的声明式规格配置。

    Args:
        name: 引擎名称（如 "voxcpm2"）。

    Returns:
        EngineSpecConfig 实例，若未找到则返回 None。
    """
    return _engine_specs.get(name)


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
    :meth:`set_indextts2_loaded`, :meth:`clear_indextts2`,
    :meth:`clear_all`) which acquire the lock once for the whole
    operation.
    """

    _instance: ModelRegistry | None = None
    _init_done: bool = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def __new__(cls) -> ModelRegistry:
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
        self._current_engine: str | None = None
        self._current_type: str = ""
        self._current_size: str = ""

        # --- IndexTTS 2.0 state (property-backed, thread-safe) ---
        self._indextts2_engine = None
        self._indextts2_model_path: str = ""

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
    def indextts2_engine(self):
        with self._lock:
            return self._indextts2_engine

    @indextts2_engine.setter
    def indextts2_engine(self, value):
        with self._lock:
            self._indextts2_engine = value

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
        """Read-only: ``True`` when any engine model instance is present."""
        with self._lock:
            return self._voxcpm_model is not None or self._indextts2_engine is not None

    # ------------------------------------------------------------------
    # Batch update helpers (single lock acquisition)
    # ------------------------------------------------------------------

    def _notify_sse(self):
        """通知 SSE 事件总线状态已变化。"""
        try:
            from .routes.sse import event_bus

            event_bus.notify()
        except Exception as e:
            logger.debug(f"[ModelRegistry] SSE 通知失败 (可忽略): {e}")

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
            self._current_engine = EngineName.VOXCPM2.value
            self._current_type = EngineName.VOXCPM2.value
            self._current_size = EngineName.VOXCPM2.value
        self._notify_sse()

    def set_indextts2_loaded(self, engine) -> None:
        """Atomically set all IndexTTS 2.0 loaded state.

        Sets *indextts2_engine* and resets ``current_engine /
        current_type / current_size`` to ``"indextts2"`` -- all under a
        single lock acquisition.
        """
        with self._lock:
            self._indextts2_engine = engine
            self._current_engine = EngineName.INDEXTTS2.value
            self._current_type = EngineName.INDEXTTS2.value
            self._current_size = EngineName.INDEXTTS2.value
        self._notify_sse()

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
            self._voxcpm2_engine_instance = None
        self._notify_sse()

    def clear_indextts2(self) -> None:
        """Atomically clear all IndexTTS 2.0 engine references.

        Sets *indextts2_engine* to ``None``.  Does **not** change
        ``current_engine / type / size`` (use :meth:`clear_all` for a
        full reset).
        """
        with self._lock:
            self._indextts2_engine = None
        self._notify_sse()

    def clear_all(self) -> None:
        """Atomically reset all core state to defaults.

        Model / ASR / IndexTTS2 engine become ``None``, engine becomes
        ``None``, type and size revert to empty strings.
        """
        with self._lock:
            self._voxcpm_model = None
            self._voxcpm_asr = None
            self._indextts2_engine = None
            self._current_engine = None
            self._current_type = ""
            self._current_size = ""
            self.voxcpm_enhancer_model = None
            self.voxcpm_ultimate = False
            self.voxcpm_voiceclone_enabled = False
            self.voxcpm_control_enabled = False
            self._voxcpm2_engine_instance = None
        self._notify_sse()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def is_voxcpm_ready(self) -> bool:
        with self._lock:
            return self._voxcpm_model is not None and self._current_engine == EngineName.VOXCPM2.value

    def is_indextts2_ready(self) -> bool:
        with self._lock:
            return self._indextts2_engine is not None and self._current_engine == EngineName.INDEXTTS2.value

    def is_engine_ready(self) -> bool:
        """Check if the current engine is ready.

        Delegates to the appropriate engine-specific check based on
        ``current_engine``.
        """
        with self._lock:
            engine = self._current_engine
        if engine == EngineName.VOXCPM2.value:
            return self.is_voxcpm_ready()
        elif engine == EngineName.INDEXTTS2.value:
            return self.is_indextts2_ready()
        return False

    def get_current_model_info(self) -> dict[str, Any]:
        """Return info dict for the currently active engine.

        Includes spec data from EngineSpecConfig when available.
        """
        with self._lock:
            engine = self._current_engine
            if engine == EngineName.VOXCPM2.value and self._voxcpm_model is not None:
                info = {
                    "engine": self._current_engine,
                    "type": self._current_type,
                    "size": self._current_size,
                    "ready": True,
                    "is_ultimate": self.voxcpm_ultimate,
                    "voiceclone_enabled": self.voxcpm_voiceclone_enabled,
                    "control_enabled": self.voxcpm_control_enabled,
                }
            elif engine == EngineName.INDEXTTS2.value and self._indextts2_engine is not None:
                info = {
                    "engine": self._current_engine,
                    "type": self._current_type,
                    "size": self._current_size,
                    "ready": True,
                }
            else:
                return {"ready": False}

        # 附加声明式引擎规格数据
        spec = _engine_specs.get(engine)
        if spec is not None:
            info["spec"] = {
                "display_name": spec.display_name,
                "vram_gb": spec.vram_gb,
                "ram_gb": spec.ram_gb,
                "languages": spec.languages,
                "quality": spec.quality,
                "license": spec.license,
                "supported_features": spec.supported_features,
                "sample_rate": spec.sample_rate,
            }
        return info

    def get_current_engine(self):
        """Get the current engine instance implementing TTSEngine protocol.

        Returns the appropriate engine instance based on ``current_engine``.
        VoxCPM2Engine instances are created lazily and cached.
        Returns ``None`` if no engine is loaded.
        """
        if self.current_engine == EngineName.VOXCPM2.value and self.voxcpm_model is not None:
            if not hasattr(self, "_voxcpm2_engine_instance") or self._voxcpm2_engine_instance is None:
                from .engines.voxcpm2.engine import VoxCPM2Engine

                self._voxcpm2_engine_instance = VoxCPM2Engine()
            return self._voxcpm2_engine_instance
        elif self.current_engine == EngineName.INDEXTTS2.value and self.indextts2_engine is not None:
            return self.indextts2_engine
        return None

    def switch_to(self, engine: str) -> None:
        if engine not in EngineName._value2member_map_:
            raise ValueError(f"Unknown engine: {engine!r}")
        with self._lock:
            self._current_engine = engine
        self._notify_sse()

    def get_engine_display_name(self, engine: str | None = None) -> str:
        """Return the display name for the given engine (or current engine)."""
        eng = engine or self.current_engine or ""
        return ENGINE_DISPLAY_NAMES.get(eng, eng or "None")


# ------------------------------------------------------------------
# Module-level singleton -- the canonical access point
# ------------------------------------------------------------------
registry = ModelRegistry()
