"""Abstract engine interface using Python Protocol for type-safe duck typing.
Supports VoxCPM2 and IndexTTS 2.0 dual-engine architecture.
"""

from collections.abc import Generator
from typing import Any, Protocol, runtime_checkable


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
    ) -> tuple[Any, str]:
        """Generate audio from text/voice description.

        Returns (audio_path, message)
        """
        ...

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: str | None = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ) -> tuple[Any, str]:
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
    ) -> tuple[Any, str]:
        """Generate audio from multi-character script.

        Returns (audio_path, message)
        """
        ...

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: str | None = None,
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
        ref_audio_path: str | None = None,
        advanced_cfg: float = 2.0,
        advanced_norm: bool = True,
        advanced_denoise: float = 1.0,
        advanced_steps: int = 10,
        advanced_seed: int = -1,
        **kwargs,
    ) -> tuple[Any, str]:
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
    ) -> tuple[Any, str]:
        """Generate audio with prompt continuation mode.

        Returns (audio_path, message)
        """
        ...

    def load_lora(self, lora_weights_path: str) -> tuple[list, list]:
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

    def register(self, name: str, engine_class: type) -> None: ...

    def get(self, name: str) -> type | None: ...

    def list_engines(self) -> list: ...


class InMemoryEngineRegistry:
    """内存引擎注册表，支持延迟导入和线程安全实例化。

    参考 VoiceBox 后端工厂模式：
    - 注册时仅记录模块路径，不立即导入（延迟实例化）
    - 首次 get() 时通过双重检查锁 + 懒导入获取引擎类
    - 避免启动时加载所有引擎依赖，减少启动时间和内存占用
    """

    def __init__(self):
        self._engines: dict[str, type] = {}
        self._metadata: dict[str, dict] = {}
        self._lazy_modules: dict[str, str] = {}  # name -> "package.module:ClassName"
        self._lazy_cache: dict[str, type] = {}  # 已解析的懒导入类
        self._lock = __import__("threading").RLock()

    def register(
        self,
        name: str,
        engine_class: type | None = None,
        display_name: str = "",
        vram_requirement: float = 6.0,
        lazy_module: str = "",
        languages: list[str] | None = None,
        supported_features: list[str] | None = None,
        sample_rate: int = 24000,
        requires_gpu: bool = True,
        quality: str = "high",
    ) -> None:
        """注册引擎类或懒导入路径。

        Args:
            name: 引擎标识符
            engine_class: 引擎类（立即注册），与 lazy_module 二选一
            display_name: UI 显示名称
            vram_requirement: 显存需求 (GB)
            lazy_module: 延迟导入路径，格式 "package.module:ClassName"
            languages: 支持语言列表
            supported_features: 支持特性列表
            sample_rate: 输出采样率
            requires_gpu: 是否需要 GPU
            quality: 质量等级
        """
        with self._lock:
            if engine_class is not None:
                self._engines[name] = engine_class
            if lazy_module:
                self._lazy_modules[name] = lazy_module
            self._metadata[name] = {
                "display_name": display_name or name,
                "vram_requirement": vram_requirement,
                "languages": languages or ["zh", "en"],
                "supported_features": supported_features or [],
                "sample_rate": sample_rate,
                "requires_gpu": requires_gpu,
                "quality": quality,
            }

    def get(self, name: str) -> type | None:
        """获取引擎类，支持懒导入和双重检查锁。

        首次访问 lazy_module 引擎时，通过双重检查锁确保线程安全地
        导入模块并缓存解析结果。
        """
        # 快速路径：已注册的引擎类
        if name in self._engines:
            return self._engines.get(name)

        # 懒导入路径
        if name not in self._lazy_modules:
            return None

        # 双重检查锁：避免重复导入
        with self._lock:
            if name in self._lazy_cache:
                return self._lazy_cache[name]

            module_path = self._lazy_modules[name]
            try:
                module_name, class_name = module_path.rsplit(":", 1)
                import importlib

                module = importlib.import_module(module_name, package=__package__)
                engine_class = getattr(module, class_name)
                self._lazy_cache[name] = engine_class
                self._engines[name] = engine_class
                return engine_class
            except (ImportError, AttributeError, ValueError) as e:
                import logging

                logging.getLogger("tts_multimodel").warning(
                    f"[EngineRegistry] 懒导入引擎 '{name}' 失败: {e}"
                )
                return None

    def list_engines(self) -> list[str]:
        """列出所有已注册引擎（含懒导入引擎）。"""
        with self._lock:
            return list(set(list(self._engines.keys()) + list(self._lazy_modules.keys())))

    def get_display_name(self, name: str) -> str:
        return self._metadata.get(name, {}).get("display_name", name)

    def get_vram_requirement(self, name: str) -> float:
        return self._metadata.get(name, {}).get("vram_requirement", 6.0)

    def get_metadata(self, name: str) -> dict:
        """获取引擎完整元数据。"""
        return self._metadata.get(name, {})

    def get_all_metadata(self) -> dict[str, dict]:
        """获取所有引擎元数据（供 UI 渲染引擎列表）。"""
        return dict(self._metadata)

    def is_registered(self, name: str) -> bool:
        return name in self._engines or name in self._lazy_modules


engine_registry = InMemoryEngineRegistry()


# Register built-in engines
def _register_builtin_engines():
    """注册内置 TTS 引擎。

    使用懒导入模式注册引擎：仅记录模块路径，首次 get() 时才实际导入。
    避免启动时加载所有引擎依赖（VoxCPM2 的 voxcpm/funasr、IndexTTS2 的依赖等）。
    """
    # VoxCPM2 - 核心引擎（立即注册，因 app_server 启动时需要类引用）
    try:
        from .engines.voxcpm2.engine import VoxCPM2Engine

        engine_registry.register(
            "voxcpm2",
            engine_class=VoxCPM2Engine,
            display_name="VoxCPM2",
            vram_requirement=6.5,
            languages=["zh", "en", "ja", "ko"],
            supported_features=[
                "voice_design", "clone", "ultimate", "script",
                "streaming", "prompt", "lora",
            ],
            sample_rate=24000,
            requires_gpu=True,
            quality="high",
        )
    except ImportError:
        # 回退到懒导入
        engine_registry.register(
            "voxcpm2",
            lazy_module=".engines.voxcpm2.engine:VoxCPM2Engine",
            display_name="VoxCPM2",
            vram_requirement=6.5,
            languages=["zh", "en", "ja", "ko"],
            supported_features=[
                "voice_design", "clone", "ultimate", "script",
                "streaming", "prompt", "lora",
            ],
            sample_rate=24000,
            requires_gpu=True,
            quality="high",
        )

    # IndexTTS2 - 情感控制引擎（懒导入，减少启动依赖）
    engine_registry.register(
        "indextts2",
        lazy_module=".engines.indextts2_engine:IndexTTS2Engine",
        display_name="IndexTTS 2.0",
        vram_requirement=6.0,
        languages=["zh", "en"],
        supported_features=["clone", "emotion_control"],
        sample_rate=24000,
        requires_gpu=False,  # CPU 兜底可用
        quality="high",
    )


_register_builtin_engines()
