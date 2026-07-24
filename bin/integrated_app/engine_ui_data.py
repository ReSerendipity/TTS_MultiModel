# -*- coding: utf-8 -*-
"""引擎选择 UI 数据提供模块 (Chapter 14)。

提供三大核心能力：
1. EngineUIDataProvider — 引擎选择卡片结构化数据（供前端渲染引擎列表）
2. WaveformVisualizer — 音频波形降采样（供 WaveSurfer.js 渲染）
3. MultiTakePlayer — 多 take 管理与对比（同一段文本的多次生成）

设计要点：
- 数据填充优先从 engine_registry.get_all_metadata() 读取，保证与引擎注册表一致
- 波形降采样使用分段取极值（peak）算法，保留视觉轮廓
- MultiTakePlayer 使用 generation_versioning.py 持久化版本链
- 所有日志统一使用 logging.getLogger("tts_multimodel")
- 延迟导入（lazy import）避免启动时加载不必要的依赖
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("tts_multimodel")


# ======================================================================
# 数据类
# ======================================================================


@dataclass(frozen=True)
class EngineUICard:
    """引擎选择卡片数据。

    Attributes:
        name: 引擎内部标识符（如 "voxcpm2" / "indextts2"）。
        display_name: UI 显示名称（如 "VoxCPM2" / "IndexTTS 2.0"）。
        description: 引擎简短描述。
        vram_gb: 最低显存需求 (GB)。
        languages: 支持语言列表。
        supported_features: 支持特性列表。
        quality: 质量等级（x-low / low / medium / high）。
        sample_rate: 输出采样率 (Hz)。
        requires_gpu: 是否必须 GPU（False 表示 CPU 可用）。
        license: 引擎许可证类型。
        icon_emoji: UI 图标 emoji。
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    vram_gb: float = 6.0
    languages: tuple[str, ...] = ("zh", "en")
    supported_features: tuple[str, ...] = ()
    quality: str = "high"
    sample_rate: int = 24000
    requires_gpu: bool = True
    license: str = ""
    icon_emoji: str = "🔊"


@dataclass(frozen=True)
class EngineUIDetail:
    """引擎详情数据（比 EngineUICard 更完整）。

    Attributes:
        card: 基础卡片数据。
        is_loaded: 当前是否已加载。
        is_current: 当前是否为活跃引擎。
        is_ready: 引擎是否就绪可推理。
        model_path: 模型文件路径（若已加载）。
        lora_active: LoRA 是否激活（仅部分引擎）。
    """

    card: EngineUICard = field(default_factory=EngineUICard)
    is_loaded: bool = False
    is_current: bool = False
    is_ready: bool = False
    model_path: str = ""
    lora_active: bool = False


@dataclass
class TakeInfo:
    """单次 take 信息。

    Attributes:
        take_number: take 编号（从 1 开始）。
        generation_id: 生成记录 ID。
        audio_path: 音频文件路径。
        params: 生成参数字典。
        version_label: 版本标签（如 "original" / "take-3"）。
        timestamp: 创建时间戳。
    """

    take_number: int = 0
    generation_id: str = ""
    audio_path: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    version_label: str = "original"
    timestamp: float = 0.0


@dataclass
class ComparisonData:
    """多 take 对比数据。

    Attributes:
        generation_id: 基准生成 ID。
        takes: 所有 take 列表。
        param_diff: 参数差异摘要（仅展示不同的参数）。
    """

    generation_id: str = ""
    takes: list[TakeInfo] = field(default_factory=list)
    param_diff: dict[str, list[Any]] = field(default_factory=dict)


# ======================================================================
# 引擎描述映射（集中管理，避免硬编码散落各处）
# ======================================================================

_ENGINE_DESCRIPTIONS: dict[str, str] = {
    "voxcpm2": "多语言高保真语音合成引擎，支持声音设计、克隆、剧本工坊、流式生成等",
    "indextts2": "零样本语音克隆引擎，支持 8 维情感向量控制与时长调节",
}

_ENGINE_ICONS: dict[str, str] = {
    "voxcpm2": "🎙️",
    "indextts2": "🎭",
}

_ENGINE_LICENSES: dict[str, str] = {
    "voxcpm2": "Apache-2.0",
    "indextts2": "MIT",
}


# ======================================================================
# EngineUIDataProvider — 引擎选择卡片数据提供者
# ======================================================================


class EngineUIDataProvider:
    """引擎选择 UI 数据提供者。

    从 engine_registry 获取元数据，转换为前端可直接渲染的
    EngineUICard / EngineUIDetail 结构。

    Usage::

        provider = EngineUIDataProvider()
        cards = provider.get_engine_list()
        detail = provider.get_engine_details("voxcpm2")
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def get_engine_list(self) -> list[EngineUICard]:
        """返回所有引擎的选择卡片数据。

        数据从 engine_registry.get_all_metadata() 填充，
        缺失字段用本地映射补全（description / icon_emoji / license）。

        Returns:
            EngineUICard 列表，按 name 字母序排列。
        """
        # 延迟导入：避免模块级循环引用
        from .engine_interface import engine_registry

        all_meta = engine_registry.get_all_metadata()
        cards: list[EngineUICard] = []

        for name, meta in all_meta.items():
            card = EngineUICard(
                name=name,
                display_name=meta.get("display_name", name),
                description=_ENGINE_DESCRIPTIONS.get(name, ""),
                vram_gb=meta.get("vram_requirement", 6.0),
                languages=tuple(meta.get("languages", ["zh", "en"])),
                supported_features=tuple(meta.get("supported_features", [])),
                quality=meta.get("quality", "high"),
                sample_rate=meta.get("sample_rate", 24000),
                requires_gpu=meta.get("requires_gpu", True),
                license=_ENGINE_LICENSES.get(name, ""),
                icon_emoji=_ENGINE_ICONS.get(name, "🔊"),
            )
            cards.append(card)

        cards.sort(key=lambda c: c.name)
        return cards

    def get_engine_details(self, engine_name: str) -> EngineUIDetail:
        """返回指定引擎的详情数据。

        在 EngineUICard 基础上补充运行时状态（是否加载、是否就绪等）。

        Args:
            engine_name: 引擎标识符（如 "voxcpm2" / "indextts2"）。

        Returns:
            EngineUIDetail 实例。若引擎不存在，返回空 detail。
        """
        # 延迟导入
        from .engine_interface import engine_registry
        from .model_registry import registry

        meta = engine_registry.get_metadata(engine_name)
        if not meta:
            logger.warning(f"[EngineUIDataProvider] 引擎 '{engine_name}' 元数据不存在")
            return EngineUIDetail()

        card = EngineUICard(
            name=engine_name,
            display_name=meta.get("display_name", engine_name),
            description=_ENGINE_DESCRIPTIONS.get(engine_name, ""),
            vram_gb=meta.get("vram_requirement", 6.0),
            languages=tuple(meta.get("languages", ["zh", "en"])),
            supported_features=tuple(meta.get("supported_features", [])),
            quality=meta.get("quality", "high"),
            sample_rate=meta.get("sample_rate", 24000),
            requires_gpu=meta.get("requires_gpu", True),
            license=_ENGINE_LICENSES.get(engine_name, ""),
            icon_emoji=_ENGINE_ICONS.get(engine_name, "🔊"),
        )

        # 运行时状态
        is_current = registry.current_engine == engine_name
        is_loaded = False
        is_ready = False
        model_path = ""
        lora_active = False

        if engine_name == "voxcpm2":
            is_loaded = registry.voxcpm_model is not None
            is_ready = registry.is_voxcpm_ready()
            if is_loaded:
                try:
                    from .config import get_config
                    cfg = get_config()
                    model_path = str(cfg.models.base_dir)
                except Exception:
                    pass
            lora_active = getattr(registry, "voxcpm_control_enabled", False)
        elif engine_name == "indextts2":
            is_loaded = registry.indextts2_engine is not None
            is_ready = registry.is_indextts2_ready()
            if is_loaded:
                try:
                    from .config import get_config
                    cfg = get_config()
                    model_path = str(cfg.models.base_dir)
                except Exception:
                    pass

        return EngineUIDetail(
            card=card,
            is_loaded=is_loaded,
            is_current=is_current,
            is_ready=is_ready,
            model_path=model_path,
            lora_active=lora_active,
        )


# ======================================================================
# WaveformVisualizer — 音频波形降采样
# ======================================================================


class WaveformVisualizer:
    """音频波形可视化数据生成器。

    将音频降采样为指定点数的振幅序列，供 WaveSurfer.js 等前端
    波形组件直接渲染。

    使用分段取极值（peak）算法：将原始音频按目标点数分段，
    每段取绝对值最大值，保留视觉轮廓的同时大幅减少数据量。

    Usage::

        viz = WaveformVisualizer()
        data = viz.process_audio("/path/to/audio.wav", num_points=300)
        # data = [0.12, 0.45, 0.78, ...]
    """

    def process_audio(self, audio_path: str, num_points: int = 300) -> list[float]:
        """从音频文件生成降采样波形数据。

        Args:
            audio_path: 音频文件路径（WAV/FLAC 等soundfile支持的格式）。
            num_points: 输出数据点数，默认 300（与 audio_player.waveform_steps 一致）。

        Returns:
            归一化振幅值列表，范围 [0.0, 1.0]，长度为 num_points。

        Raises:
            FileNotFoundError: 音频文件不存在。
            ValueError: 音频数据为空或无法读取。
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 延迟导入 soundfile，避免模块级依赖
        import numpy as np
        import soundfile as sf

        try:
            wav, sr = sf.read(audio_path, dtype="float32")
        except Exception as e:
            raise ValueError(f"无法读取音频文件: {audio_path}, 错误: {e}") from e

        if wav.size == 0:
            raise ValueError(f"音频数据为空: {audio_path}")

        # 多声道转单声道
        if wav.ndim > 1:
            wav = np.mean(wav, axis=-1)

        return self._downsample_peaks(wav, num_points)

    def process_audio_bytes(
        self,
        audio_bytes: bytes,
        sr: int,
        num_points: int = 300,
    ) -> list[float]:
        """从音频字节数据生成降采样波形数据。

        适用于 WebSocket 或 HTTP 上传的原始 PCM 字节流。

        Args:
            audio_bytes: 原始 PCM 音频字节数据。
            sr: 采样率。
            num_points: 输出数据点数，默认 300。

        Returns:
            归一化振幅值列表，范围 [0.0, 1.0]，长度为 num_points。

        Raises:
            ValueError: 字节数据无法解析。
        """
        import numpy as np

        try:
            # 假设 float32 PCM
            wav = np.frombuffer(audio_bytes, dtype=np.float32).copy()
        except (ValueError, TypeError) as e:
            raise ValueError(f"无法解析音频字节数据: {e}") from e

        if wav.size == 0:
            raise ValueError("音频字节数据为空")

        return self._downsample_peaks(wav, num_points)

    @staticmethod
    def _downsample_peaks(wav, num_points: int) -> list[float]:
        """分段取极值降采样算法。

        将 wav 等分为 num_points 段，每段取绝对值最大值，
        最后归一化到 [0.0, 1.0]。

        Args:
            wav: 单声道 float32 numpy 音频数组。
            num_points: 目标数据点数。

        Returns:
            归一化振幅列表。
        """
        import numpy as np

        total_samples = len(wav)
        if total_samples <= num_points:
            # 样本数不足，直接返回绝对值
            peaks = np.abs(wav)
        else:
            # 计算每段样本数
            chunk_size = total_samples // num_points
            peaks = np.zeros(num_points, dtype=np.float32)

            for i in range(num_points):
                start = i * chunk_size
                # 最后一段包含剩余样本
                end = start + chunk_size if i < num_points - 1 else total_samples
                segment = wav[start:end]
                peaks[i] = np.max(np.abs(segment)) if segment.size > 0 else 0.0

        # 归一化到 [0.0, 1.0]
        max_peak = np.max(peaks)
        if max_peak > 0:
            peaks = peaks / max_peak

        return peaks.tolist()


# ======================================================================
# MultiTakePlayer — 多 take 管理与对比
# ======================================================================


class MultiTakePlayer:
    """多 take 管理器：管理同一段文本的多次生成结果。

    支持添加 take、获取所有 take、对比 take 参数差异。
    底层使用 generation_versioning.py 的 GenerationVersionManager 持久化。

    Usage::

        player = MultiTakePlayer()
        take_num = player.add_take(
            generation_id="gen-123",
            audio_path="/out/audio.wav",
            params={"cfg": 2.0, "steps": 10},
        )
        takes = player.get_takes("gen-123")
        comparison = player.compare_takes("gen-123")
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # 内存缓存：generation_id -> list[TakeInfo]
        self._takes_cache: dict[str, list[TakeInfo]] = {}

    def add_take(
        self,
        generation_id: str,
        audio_path: str,
        params: dict[str, Any],
        engine: str = "voxcpm2",
    ) -> int:
        """添加一次 take 并返回 take 编号。

        将 take 信息持久化到 GenerationVersionManager，
        同时更新内存缓存。

        Args:
            generation_id: 生成任务 ID（同一文本的多次生成共享此 ID）。
            audio_path: 生成音频文件路径。
            params: 生成参数字典。
            engine: 使用的引擎名称。

        Returns:
            take 编号（从 1 开始递增）。
        """
        with self._lock:
            try:
                from .generation_versioning import get_version_manager

                vm = get_version_manager()

                # 确定父 ID：首次 take 无 parent，后续 take 以第一次为 parent
                existing = self._takes_cache.get(generation_id, [])
                parent_id = existing[0].generation_id if existing else None

                new_gen_id = vm.save_generation(
                    audio_path=audio_path,
                    text="",  # take 管理器不存储文本，由上层负责
                    params=params,
                    engine=engine,
                    parent_id=parent_id,
                )

                take_number = len(existing) + 1
                version_chain = vm.get_version_chain(generation_id)
                version_label = (
                    version_chain[-1].version_label
                    if version_chain
                    else f"take-{take_number}"
                )

                take_info = TakeInfo(
                    take_number=take_number,
                    generation_id=new_gen_id,
                    audio_path=audio_path,
                    params=params,
                    version_label=version_label,
                )

                if generation_id not in self._takes_cache:
                    self._takes_cache[generation_id] = []
                self._takes_cache[generation_id].append(take_info)

                logger.info(
                    f"[MultiTakePlayer] 已添加 take #{take_number} "
                    f"for generation_id={generation_id[:8]}..."
                )
                return take_number

            except Exception as e:
                logger.error(f"[MultiTakePlayer] 添加 take 失败: {e}")
                # 降级：仅在内存中记录
                existing = self._takes_cache.get(generation_id, [])
                take_number = len(existing) + 1
                take_info = TakeInfo(
                    take_number=take_number,
                    generation_id=f"mem-{take_number}",
                    audio_path=audio_path,
                    params=params,
                    version_label=f"take-{take_number}",
                )
                if generation_id not in self._takes_cache:
                    self._takes_cache[generation_id] = []
                self._takes_cache[generation_id].append(take_info)
                return take_number

    def get_takes(self, generation_id: str) -> list[TakeInfo]:
        """获取指定生成任务的所有 take。

        优先从内存缓存读取；若缓存为空，尝试从
        GenerationVersionManager 持久化数据恢复。

        Args:
            generation_id: 生成任务 ID。

        Returns:
            TakeInfo 列表，按 take_number 升序排列。
        """
        with self._lock:
            # 内存缓存命中
            if generation_id in self._takes_cache and self._takes_cache[generation_id]:
                return list(self._takes_cache[generation_id])

            # 尝试从持久化恢复
            try:
                from .generation_versioning import get_version_manager

                vm = get_version_manager()
                chain = vm.get_version_chain(generation_id)
                if chain:
                    takes: list[TakeInfo] = []
                    for idx, record in enumerate(chain, start=1):
                        takes.append(
                            TakeInfo(
                                take_number=idx,
                                generation_id=record.id,
                                audio_path=record.audio_path,
                                params=record.params,
                                version_label=record.version_label,
                                timestamp=record.timestamp,
                            )
                        )
                    self._takes_cache[generation_id] = takes
                    return list(takes)
            except Exception as e:
                logger.debug(f"[MultiTakePlayer] 从持久化恢复 takes 失败: {e}")

            return []

    def compare_takes(self, generation_id: str) -> ComparisonData:
        """对比指定生成任务的所有 take 参数差异。

        提取所有 take 的 params 字典，找出取值不同的参数，
        生成差异摘要供 UI 渲染对比视图。

        Args:
            generation_id: 生成任务 ID。

        Returns:
            ComparisonData 实例，包含 take 列表和参数差异摘要。
        """
        takes = self.get_takes(generation_id)
        if not takes:
            return ComparisonData(generation_id=generation_id)

        # 收集所有参数键
        all_keys: set[str] = set()
        for take in takes:
            all_keys.update(take.params.keys())

        # 找出值有差异的参数
        param_diff: dict[str, list[Any]] = {}
        for key in sorted(all_keys):
            values = [t.params.get(key) for t in takes]
            # 检查是否所有值都相同
            if len(set(str(v) for v in values)) > 1:
                param_diff[key] = values

        return ComparisonData(
            generation_id=generation_id,
            takes=takes,
            param_diff=param_diff,
        )


# ======================================================================
# 模块级单例
# ======================================================================

_ui_data_provider: EngineUIDataProvider | None = None
_waveform_visualizer: WaveformVisualizer | None = None
_multi_take_player: MultiTakePlayer | None = None
_singleton_lock = threading.Lock()


def get_ui_data_provider() -> EngineUIDataProvider:
    """获取全局 EngineUIDataProvider 单例。"""
    global _ui_data_provider
    if _ui_data_provider is None:
        with _singleton_lock:
            if _ui_data_provider is None:
                _ui_data_provider = EngineUIDataProvider()
    return _ui_data_provider


def get_waveform_visualizer() -> WaveformVisualizer:
    """获取全局 WaveformVisualizer 单例。"""
    global _waveform_visualizer
    if _waveform_visualizer is None:
        with _singleton_lock:
            if _waveform_visualizer is None:
                _waveform_visualizer = WaveformVisualizer()
    return _waveform_visualizer


def get_multi_take_player() -> MultiTakePlayer:
    """获取全局 MultiTakePlayer 单例。"""
    global _multi_take_player
    if _multi_take_player is None:
        with _singleton_lock:
            if _multi_take_player is None:
                _multi_take_player = MultiTakePlayer()
    return _multi_take_player
