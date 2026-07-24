# -*- coding: utf-8 -*-
"""RAS (Repetition Aware Sampling) — 重复感知采样策略。

在自回归 TTS 生成过程中检测 token 级别的重复模式，
并动态调整采样参数（temperature / top_p）以打破重复循环。

参考 Fish Speech 的 RAS 实现，核心思路：
  - 滑动窗口追踪最近生成的 token
  - 检测 n-gram 重复（可配置 n 值）
  - 重复出现时自动提升 temperature 和 top_p，增加采样多样性
  - 参数设有上限，防止过度发散

典型用法::

    from bin.integrated_app.ras_sampling import RepetitionDetector, adjust_sampling_params

    detector = RepetitionDetector()
    for token in generate_tokens(...):
        detector.append(token)
        temperature, top_p = adjust_sampling_params(
            temperature=0.7, top_p=0.9, detector=detector,
        )
        # 用调整后的参数进行下一步采样
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger("tts_multimodel")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass
class RASConfig:
    """RAS 采样策略的可配置参数。

    Attributes:
        window_size: 滑动窗口大小，追踪最近 N 个 token 用于重复检测。
        ngram_n: n-gram 重复检测的 n 值。检测最近 window_size 个 token
                 中是否存在连续 n 个 token 重复出现。
        temp_increase: 每次检测到重复时 temperature 的增量。
        top_p_increase: 每次检测到重复时 top_p 的增量。
        max_temperature: temperature 的上限。
        max_top_p: top_p 的上限。
        repetition_threshold: n-gram 重复出现次数阈值，达到此值才触发调整。
        decay_factor: 非重复步骤中参数衰减因子（0 表示不衰减，1 表示立即回到原值）。
    """

    window_size: int = 50
    ngram_n: int = 3
    temp_increase: float = 0.2
    top_p_increase: float = 0.07
    max_temperature: float = 2.0
    max_top_p: float = 0.99
    repetition_threshold: int = 2
    decay_factor: float = 0.0


# ---------------------------------------------------------------------------
# 重复检测器
# ---------------------------------------------------------------------------


class RepetitionDetector:
    """基于滑动窗口的 n-gram 重复检测器。

    线程安全设计：内部使用 threading.Lock 保护状态变更。
    每个 TTS 生成任务应创建独立的检测器实例，或在任务边界调用 reset()。

    用法::

        detector = RepetitionDetector(RASConfig(window_size=60, ngram_n=3))
        for token_id in token_stream:
            detector.append(token_id)
            if detector.is_repetitive():
                # 执行参数调整逻辑
                ...
    """

    def __init__(self, config: RASConfig | None = None) -> None:
        self._config = config or RASConfig()
        self._window: deque[int] = deque(maxlen=self._config.window_size)
        self._lock = threading.Lock()
        self._repetition_count: int = 0  # 连续检测到重复的累计次数
        self._total_detections: int = 0  # 历史总检测次数（用于统计/日志）

    # -- 公共接口 --

    @property
    def config(self) -> RASConfig:
        """当前配置（只读）。"""
        return self._config

    @property
    def repetition_count(self) -> int:
        """当前连续重复检测计数。"""
        with self._lock:
            return self._repetition_count

    @property
    def total_detections(self) -> int:
        """历史总重复检测次数。"""
        with self._lock:
            return self._total_detections

    def append(self, token: int) -> None:
        """向滑动窗口追加一个 token。

        Args:
            token: 生成的 token ID。
        """
        with self._lock:
            self._window.append(token)
            # 追加后检查是否触发重复，更新内部计数
            if self._check_ngram_repetition():
                self._repetition_count += 1
                self._total_detections += 1
            else:
                # 非重复步骤：衰减计数（但不低于 0）
                if self._config.decay_factor > 0:
                    self._repetition_count = max(
                        0,
                        self._repetition_count - 1,
                    )

    def append_batch(self, tokens: Sequence[int]) -> None:
        """批量追加 token。

        Args:
            tokens: token ID 序列。
        """
        for t in tokens:
            self.append(t)

    def is_repetitive(self) -> bool:
        """判断当前是否处于重复状态。

        当连续重复检测计数 >= 配置的 repetition_threshold 时返回 True。

        Returns:
            True 表示检测到有意义的重复模式，应调整采样参数。
        """
        with self._lock:
            return self._repetition_count >= self._config.repetition_threshold

    def get_repetition_level(self) -> int:
        """获取当前重复严重程度等级。

        Returns:
            超过阈值的重复计数差值，0 表示未超过阈值。
        """
        with self._lock:
            excess = self._repetition_count - self._config.repetition_threshold
            return max(0, excess)

    def get_window_tokens(self) -> list[int]:
        """获取当前滑动窗口中的所有 token（副本）。

        Returns:
            token 列表（从旧到新）。
        """
        with self._lock:
            return list(self._window)

    def reset(self) -> None:
        """重置检测器状态，清空滑动窗口和计数器。"""
        with self._lock:
            self._window.clear()
            self._repetition_count = 0
            self._total_detections = 0

    # -- 内部方法 --

    def _check_ngram_repetition(self) -> bool:
        """检查最近 n-gram 是否在滑动窗口内重复出现。

        算法：取窗口末尾 ngram_n 个 token 作为目标 n-gram，
        在窗口剩余部分中搜索是否存在相同的 n-gram。

        Returns:
            True 表示目标 n-gram 在窗口内有重复。
        """
        n = self._config.ngram_n
        window = self._window

        if len(window) < n * 2:
            # 窗口太短，无法形成两组 n-gram 进行比较
            return False

        # 最近 n 个 token 构成的目标 n-gram
        target = list(window)[-n:]

        # 在窗口前部搜索相同 n-gram
        window_list = list(window)
        search_range = len(window_list) - n  # 不包含末尾的 target 本身
        for i in range(search_range - n + 1):
            candidate = window_list[i : i + n]
            if candidate == target:
                return True

        return False


# ---------------------------------------------------------------------------
# 采样参数调整
# ---------------------------------------------------------------------------


def adjust_sampling_params(
    temperature: float,
    top_p: float,
    detector: RepetitionDetector,
    config: RASConfig | None = None,
) -> tuple[float, float]:
    """根据重复检测状态动态调整采样参数。

    当检测器报告重复时，按以下策略调整：
      1. 根据重复严重程度（repetition_level）决定调整幅度
      2. 温和调整（level=0）：增加 temp_increase / top_p_increase
      3. 中度调整（level=1）：增加 1.5 倍幅度
      4. 强力调整（level>=2）：增加 2 倍幅度
      5. 所有调整受 max_temperature / max_top_p 约束

    Args:
        temperature: 当前 temperature 值。
        top_p: 当前 top_p 值。
        detector: 重复检测器实例。
        config: RAS 配置，默认使用 detector 自带的配置。

    Returns:
        (adjusted_temperature, adjusted_top_p) 元组。
        若无重复，返回原始参数。
    """
    if not detector.is_repetitive():
        return temperature, top_p

    cfg = config or detector.config
    level = detector.get_repetition_level()

    # 根据重复严重程度确定调整倍率
    if level == 0:
        multiplier = 1.0
    elif level == 1:
        multiplier = 1.5
    else:
        multiplier = 2.0

    new_temp = min(
        temperature + cfg.temp_increase * multiplier,
        cfg.max_temperature,
    )
    new_top_p = min(
        top_p + cfg.top_p_increase * multiplier,
        cfg.max_top_p,
    )

    logger.debug(
        f"[RAS] 检测到重复 (level={level}), "
        f"temperature: {temperature:.3f} -> {new_temp:.3f}, "
        f"top_p: {top_p:.3f} -> {new_top_p:.3f}"
    )

    return new_temp, new_top_p


# ---------------------------------------------------------------------------
# VoxCPM2 引擎集成辅助
# ---------------------------------------------------------------------------


class RASContext:
    """VoxCPM2 引擎的 RAS 上下文管理器。

    封装 RepetitionDetector + 参数调整逻辑，提供简洁的集成接口。
    建议在 VoxCPM2 生成函数中作为上下文管理器使用，确保每次
    生成任务自动重置检测器状态。

    用法::

        with RASContext() as ras:
            for token in generate_stream:
                ras.feed(token)
                temp, top_p = ras.get_params(temperature=0.7, top_p=0.9)
    """

    def __init__(self, config: RASConfig | None = None) -> None:
        self._config = config or RASConfig()
        self._detector = RepetitionDetector(self._config)

    @property
    def detector(self) -> RepetitionDetector:
        """底层检测器实例（高级用途）。"""
        return self._detector

    @property
    def config(self) -> RASConfig:
        """当前 RAS 配置。"""
        return self._config

    def feed(self, token: int) -> None:
        """向检测器喂入一个 token。

        Args:
            token: 生成的 token ID。
        """
        self._detector.append(token)

    def feed_batch(self, tokens: Sequence[int]) -> None:
        """批量喂入 token。

        Args:
            tokens: token ID 序列。
        """
        self._detector.append_batch(tokens)

    def get_params(
        self,
        temperature: float,
        top_p: float,
    ) -> tuple[float, float]:
        """获取当前调整后的采样参数。

        Args:
            temperature: 基础 temperature。
            top_p: 基础 top_p。

        Returns:
            (adjusted_temperature, adjusted_top_p) 元组。
        """
        return adjust_sampling_params(
            temperature=temperature,
            top_p=top_p,
            detector=self._detector,
            config=self._config,
        )

    def is_repetitive(self) -> bool:
        """当前是否处于重复状态。"""
        return self._detector.is_repetitive()

    def get_repetition_level(self) -> int:
        """获取当前重复严重程度。"""
        return self._detector.get_repetition_level()

    def reset(self) -> None:
        """手动重置检测器。"""
        self._detector.reset()

    def __enter__(self) -> RASContext:
        """进入上下文：重置检测器状态。"""
        self._detector.reset()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文：记录统计信息并重置。"""
        detections = self._detector.total_detections
        if detections > 0:
            logger.info(
                f"[RAS] 生成任务完成，共检测到 {detections} 次 n-gram 重复"
            )
        self._detector.reset()


def create_ras_context_from_generation_config(
    **overrides,
) -> RASContext:
    """从生成配置创建 RAS 上下文。

    优先使用传入的 override 参数，其余使用默认值。
    方便 VoxCPM2 各生成函数快速创建 RAS 上下文。

    Args:
        **overrides: 覆盖 RASConfig 默认值的参数。

    Returns:
        配置好的 RASContext 实例。
    """
    config = RASConfig(**overrides)
    return RASContext(config=config)
