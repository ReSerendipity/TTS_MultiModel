# -*- coding: utf-8 -*-
"""语音克隆工具函数模块

提供参考音频质量检查、多参考音频合并、参考音频隔离等语音克隆预处理工具。

Classes:
    ReferenceAudioPrechecker: 参考音频质量预检，输出 AudioQualityReport
    MultiReferenceMerger: 多参考音频合并（平均/加权/MD5缓存）
    ReferenceAudioIsolator: VoxCPM2 参考音频隔离（token 103/104 + loss_mask）
"""

from __future__ import annotations

import hashlib
import logging
import os
import struct
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("tts_multimodel")

# ---------------------------------------------------------------------------
# 延迟导入：soundfile（可选依赖，缺失时降级为原始波形读取）
# ---------------------------------------------------------------------------
_sf: Any = None
_HAS_SOUNDFILE = False
try:
    import soundfile as _sf

    _HAS_SOUNDFILE = True
except ImportError:
    _sf = None


# ======================================================================
# AudioQualityReport 数据类
# ======================================================================


class QualityRecommendation(str, Enum):
    """质量评估建议等级"""

    ACCEPT = "accept"
    WARN = "warn"
    REJECT = "reject"


@dataclass
class AudioQualityReport:
    """参考音频质量检测报告

    Attributes:
        silence_ratio: 静音比例 (0.0 ~ 1.0)
        noise_level_db: 估计噪声水平 (dB)，值越小表示噪声越低
        snr_estimate: 信噪比估计 (dB)，值越大表示信号质量越好
        duration_sec: 音频时长（秒）
        sample_rate: 采样率 (Hz)
        channels: 声道数
        clipping_ratio: 削波采样占比 (0.0 ~ 1.0)
        quality_score: 综合质量评分 (0 ~ 100)
        recommendation: 质量建议 (accept / warn / reject)
        warnings: 警告信息列表
    """

    silence_ratio: float
    noise_level_db: float
    snr_estimate: float
    duration_sec: float
    sample_rate: int
    channels: int
    clipping_ratio: float
    quality_score: float
    recommendation: QualityRecommendation
    warnings: list[str] = field(default_factory=list)


# ======================================================================
# ReferenceAudioPrechecker — 参考音频质量预检
# ======================================================================


class ReferenceAudioPrechecker:
    """参考音频质量预检器

    对参考音频进行静音比例、噪声水平、时长、采样率、声道数、削波检测
    等多维度分析，输出 AudioQualityReport 并给出 accept/warn/reject 建议。

    不依赖外部 ML 模型，仅使用 numpy + soundfile 进行信号分析。
    """

    # 默认阈值配置
    DEFAULT_SILENCE_THRESHOLD_DB: float = -40.0
    DEFAULT_SILENCE_WARN_RATIO: float = 0.30
    DEFAULT_MIN_DURATION: float = 3.0
    DEFAULT_MAX_DURATION: float = 30.0
    DEFAULT_CLIPPING_THRESHOLD: float = 0.99
    DEFAULT_NOISE_FLOOR_PERCENTILE: float = 10.0

    def __init__(
        self,
        silence_threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
        silence_warn_ratio: float = DEFAULT_SILENCE_WARN_RATIO,
        min_duration: float = DEFAULT_MIN_DURATION,
        max_duration: float = DEFAULT_MAX_DURATION,
        clipping_threshold: float = DEFAULT_CLIPPING_THRESHOLD,
        noise_floor_percentile: float = DEFAULT_NOISE_FLOOR_PERCENTILE,
    ) -> None:
        """初始化预检器。

        Args:
            silence_threshold_db: 静音判定阈值 (dB)，低于此值视为静音帧。
            silence_warn_ratio: 静音比例警告阈值，超过此比例触发警告。
            min_duration: 最短推荐时长 (秒)，低于此触发警告。
            max_duration: 最长推荐时长 (秒)，超过此触发警告。
            clipping_threshold: 削波判定阈值 (绝对值)，超过此值视为削波。
            noise_floor_percentile: 噪底估计使用的百分位数。
        """
        self._silence_threshold_db = silence_threshold_db
        self._silence_warn_ratio = silence_warn_ratio
        self._min_duration = min_duration
        self._max_duration = max_duration
        self._clipping_threshold = clipping_threshold
        self._noise_floor_pct = noise_floor_percentile

    def check_quality(self, audio_path: str) -> AudioQualityReport:
        """检测参考音频质量并生成报告。

        Args:
            audio_path: 音频文件路径（支持 WAV/FLAC/OGG 等 soundfile 可读格式）。

        Returns:
            AudioQualityReport 包含所有检测结果和质量评分。

        Raises:
            FileNotFoundError: 音频文件不存在。
            ValueError: 音频文件无法读取或数据为空。
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 读取音频数据
        wav, sr = self._read_audio(audio_path)
        if wav.size == 0:
            raise ValueError(f"音频数据为空: {audio_path}")

        # 转为单声道处理
        if wav.ndim > 1:
            channels = wav.shape[1]
            wav_mono = np.mean(wav, axis=1)
        else:
            channels = 1
            wav_mono = wav

        duration = len(wav_mono) / sr

        # 1. 静音比例检测
        silence_ratio = self._compute_silence_ratio(wav_mono)

        # 2. 噪声水平与 SNR 估计
        noise_level_db, snr_estimate = self._estimate_snr(wav_mono)

        # 3. 削波检测
        clipping_ratio = self._compute_clipping_ratio(wav_mono)

        # 4. 综合评分与建议
        warnings: list[str] = []
        quality_score = self._compute_quality_score(
            silence_ratio=silence_ratio,
            snr_estimate=snr_estimate,
            duration=duration,
            clipping_ratio=clipping_ratio,
            warnings=warnings,
        )
        recommendation = self._determine_recommendation(quality_score)

        return AudioQualityReport(
            silence_ratio=silence_ratio,
            noise_level_db=noise_level_db,
            snr_estimate=snr_estimate,
            duration_sec=duration,
            sample_rate=sr,
            channels=channels,
            clipping_ratio=clipping_ratio,
            quality_score=quality_score,
            recommendation=recommendation,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _read_audio(self, audio_path: str) -> tuple[np.ndarray, int]:
        """读取音频文件，优先 soundfile，回退原始 WAV 读取。"""
        if _HAS_SOUNDFILE:
            wav, sr = _sf.read(audio_path, dtype="float32")
            return wav, sr

        # 回退：手动解析 WAV 文件头
        return self._read_wav_raw(audio_path)

    @staticmethod
    def _read_wav_raw(audio_path: str) -> tuple[np.ndarray, int]:
        """原始 WAV 文件读取（soundfile 不可用时的降级方案）。

        仅支持 PCM 16-bit WAV 格式。
        """
        with open(audio_path, "rb") as f:
            # RIFF 头
            riff = f.read(4)
            if riff != b"RIFF":
                raise ValueError(f"不是有效的 WAV 文件: {audio_path}")
            f.read(4)  # 文件大小
            wave = f.read(4)
            if wave != b"WAVE":
                raise ValueError(f"不是有效的 WAV 文件: {audio_path}")

            # 解析子块
            fmt_found = False
            channels = 1
            sr = 44100
            bits_per_sample = 16
            data_offset = 0
            data_size = 0

            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack("<I", chunk_header[4:])[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    audio_format = struct.unpack("<H", fmt_data[0:2])[0]
                    channels = struct.unpack("<H", fmt_data[2:4])[0]
                    sr = struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                    if audio_format != 1:
                        raise ValueError(f"仅支持 PCM 格式 WAV，当前格式: {audio_format}")
                    fmt_found = True
                elif chunk_id == b"data":
                    data_offset = f.tell()
                    data_size = chunk_size
                    break
                else:
                    f.read(chunk_size)

            if not fmt_found:
                raise ValueError(f"WAV 文件缺少 fmt 块: {audio_path}")

            # 读取 PCM 数据
            f.seek(data_offset)
            raw = f.read(data_size)
            if bits_per_sample == 16:
                wav = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif bits_per_sample == 24:
                # 24-bit 需要逐样本解析
                n_samples = len(raw) // 3
                wav = np.zeros(n_samples, dtype=np.float32)
                for i in range(n_samples):
                    b = raw[i * 3 : i * 3 + 3]
                    val = int.from_bytes(b, byteorder="little", signed=True)
                    wav[i] = val / 8388608.0
            elif bits_per_sample == 32:
                wav = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                raise ValueError(f"不支持的位深度: {bits_per_sample}")

            # 多声道重塑
            if channels > 1:
                wav = wav.reshape(-1, channels)

            return wav, sr

    def _compute_silence_ratio(self, wav: np.ndarray) -> float:
        """计算静音帧占比。

        使用短时能量方法：将音频分帧，帧能量低于阈值视为静音帧。
        """
        frame_size = int(0.025 * self._silence_threshold_db)  # 不依赖帧长
        frame_size = max(512, min(2048, len(wav) // 10))  # 自适应帧长
        hop = frame_size // 2
        n_frames = max(1, (len(wav) - frame_size) // hop + 1)

        silence_frames = 0
        threshold_linear = 10.0 ** (self._silence_threshold_db / 20.0)

        for i in range(n_frames):
            start = i * hop
            end = min(start + frame_size, len(wav))
            frame = wav[start:end]
            rms = np.sqrt(np.mean(frame**2))
            if rms < threshold_linear:
                silence_frames += 1

        return silence_frames / n_frames

    def _estimate_snr(self, wav: np.ndarray) -> tuple[float, float]:
        """估计噪声水平 (dB) 和信噪比 (dB)。

        使用百分位数法估计噪底：取能量最低的 N% 帧作为噪声估计，
        其余帧作为信号+噪声估计，两者差值即为 SNR。
        """
        frame_size = max(512, min(2048, len(wav) // 10))
        hop = frame_size // 2
        n_frames = max(1, (len(wav) - frame_size) // hop + 1)

        frame_energies = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop
            end = min(start + frame_size, len(wav))
            frame = wav[start:end]
            frame_energies[i] = np.mean(frame**2)

        # 噪底估计：能量最低的 pct% 帧
        pct = self._noise_floor_pct
        n_noise = max(1, int(n_frames * pct / 100.0))
        sorted_energies = np.sort(frame_energies)
        noise_power = np.mean(sorted_energies[:n_noise])

        # 信号+噪声估计：能量最高的 (100-pct)% 帧
        n_signal = max(1, n_frames - n_noise)
        signal_noise_power = np.mean(sorted_energies[n_noise:])

        # 转换为 dB
        eps = 1e-10
        noise_level_db = 10.0 * np.log10(noise_power + eps)
        signal_level_db = 10.0 * np.log10(signal_noise_power + eps)
        snr = signal_level_db - noise_level_db

        return noise_level_db, max(0.0, snr)

    def _compute_clipping_ratio(self, wav: np.ndarray) -> float:
        """计算削波采样占比。

        采样绝对值超过 clipping_threshold 视为削波。
        """
        clipped = np.sum(np.abs(wav) >= self._clipping_threshold)
        return float(clipped) / len(wav)

    def _compute_quality_score(
        self,
        silence_ratio: float,
        snr_estimate: float,
        duration: float,
        clipping_ratio: float,
        warnings: list[str],
    ) -> float:
        """计算综合质量评分 (0 ~ 100)。

        评分维度与权重：
          - 静音比例 (权重 25)：静音越少分越高
          - SNR (权重 30)：SNR 越高分越高
          - 时长合适度 (权重 20)：在推荐区间内满分
          - 削波比例 (权重 25)：削波越少分越高
        """
        # --- 静音比例得分 ---
        if silence_ratio <= 0.10:
            silence_score = 100.0
        elif silence_ratio <= self._silence_warn_ratio:
            silence_score = 100.0 - (silence_ratio - 0.10) / (self._silence_warn_ratio - 0.10) * 30.0
        else:
            silence_score = max(0.0, 70.0 - (silence_ratio - self._silence_warn_ratio) * 200.0)

        if silence_ratio > self._silence_warn_ratio:
            warnings.append(f"静音比例过高: {silence_ratio:.1%}（建议低于 {self._silence_warn_ratio:.0%}）")

        # --- SNR 得分 ---
        # SNR > 30dB 为优秀，10~30dB 为一般，< 10dB 为较差
        if snr_estimate >= 30.0:
            snr_score = 100.0
        elif snr_estimate >= 10.0:
            snr_score = 50.0 + (snr_estimate - 10.0) / 20.0 * 50.0
        else:
            snr_score = max(0.0, snr_estimate / 10.0 * 50.0)

        if snr_estimate < 15.0:
            warnings.append(f"信噪比较低: {snr_estimate:.1f} dB（建议高于 15 dB）")

        # --- 时长得分 ---
        if self._min_duration <= duration <= self._max_duration:
            duration_score = 100.0
        elif duration < self._min_duration:
            duration_score = max(0.0, duration / self._min_duration * 100.0)
            warnings.append(f"音频时长过短: {duration:.1f}s（建议不低于 {self._min_duration:.0f}s）")
        else:
            # 超长音频缓慢扣分
            overshoot = duration - self._max_duration
            duration_score = max(0.0, 100.0 - overshoot * 2.0)
            warnings.append(f"音频时长过长: {duration:.1f}s（建议不超过 {self._max_duration:.0f}s）")

        # --- 削波得分 ---
        if clipping_ratio <= 0.001:
            clipping_score = 100.0
        elif clipping_ratio <= 0.01:
            clipping_score = 100.0 - clipping_ratio / 0.01 * 30.0
        else:
            clipping_score = max(0.0, 70.0 - (clipping_ratio - 0.01) * 3000.0)

        if clipping_ratio > 0.005:
            warnings.append(f"削波比例较高: {clipping_ratio:.2%}，可能存在音频失真")

        # --- 加权综合评分 ---
        total = (
            silence_score * 0.25
            + snr_score * 0.30
            + duration_score * 0.20
            + clipping_score * 0.25
        )
        return round(max(0.0, min(100.0, total)), 1)

    def _determine_recommendation(self, quality_score: float) -> QualityRecommendation:
        """根据质量评分确定建议等级。

        - score >= 70: accept
        - score >= 40: warn
        - score < 40: reject
        """
        if quality_score >= 70.0:
            return QualityRecommendation.ACCEPT
        if quality_score >= 40.0:
            return QualityRecommendation.WARN
        return QualityRecommendation.REJECT


# ======================================================================
# MultiReferenceMerger — 多参考音频合并
# ======================================================================


class MultiReferenceMerger:
    """多参考音频合并器

    支持三种合并策略：
      - "average": 简单平均合并
      - "weighted": 按质量评分加权合并
      - "md5_cache": 基于 MD5 哈希的缓存合并，避免重复计算

    合并前会将所有音频重采样到相同采样率（以第一个音频为准），
    并裁剪到最短长度。
    """

    # 合并缓存子目录
    _MERGE_CACHE_SUBDIR = "merge_cache"

    def __init__(self, cache_dir: str | None = None) -> None:
        """初始化合并器。

        Args:
            cache_dir: MD5 缓存目录路径。为 None 时自动使用项目
                       personas 目录下的 merge_cache 子目录。
        """
        if cache_dir is not None:
            self._cache_dir = Path(cache_dir)
        else:
            try:
                from .config import PERSONA_DIR

                self._cache_dir = Path(PERSONA_DIR) / self._MERGE_CACHE_SUBDIR
            except ImportError:
                self._cache_dir = Path("./personas") / self._MERGE_CACHE_SUBDIR

        os.makedirs(self._cache_dir, exist_ok=True)
        self._prechecker = ReferenceAudioPrechecker()

    def merge_references(
        self,
        audio_paths: list[str],
        method: str = "average",
    ) -> tuple[np.ndarray, int]:
        """合并多个参考音频。

        Args:
            audio_paths: 参考音频文件路径列表（至少 1 个）。
            method: 合并方法，可选 "average"、"weighted"、"md5_cache"。

        Returns:
            (merged_wav, sample_rate) 元组，merged_wav 为 float32 numpy 数组。

        Raises:
            ValueError: 路径列表为空或方法不支持。
            FileNotFoundError: 任一音频文件不存在。
        """
        if not audio_paths:
            raise ValueError("音频路径列表不能为空")

        valid_methods = {"average", "weighted", "md5_cache"}
        if method not in valid_methods:
            raise ValueError(f"不支持的合并方法: {method}，可选: {valid_methods}")

        # 对每个路径验证文件存在
        for p in audio_paths:
            if not os.path.isfile(p):
                raise FileNotFoundError(f"音频文件不存在: {p}")

        # 仅一个音频时直接返回
        if len(audio_paths) == 1:
            wav, sr = self._read_audio(audio_paths[0])
            return wav, sr

        # md5_cache 方法：检查缓存
        if method == "md5_cache":
            cache_key = self._compute_cache_key(audio_paths)
            cached = self._load_from_cache(cache_key)
            if cached is not None:
                logger.info(f"[多参考合并] 命中 MD5 缓存: {cache_key[:12]}...")
                return cached

        # 读取所有音频
        audios: list[tuple[np.ndarray, int]] = []
        for p in audio_paths:
            wav, sr = self._read_audio(p)
            audios.append((wav, sr))

        # 统一采样率（以第一个为准）
        target_sr = audios[0][1]
        aligned: list[np.ndarray] = []
        for wav, sr in audios:
            resampled = self._resample(wav, sr, target_sr)
            aligned.append(resampled)

        # 裁剪到最短长度
        min_len = min(len(w) for w in aligned)
        aligned = [w[:min_len].astype(np.float32) for w in aligned]

        # 合并
        if method == "average":
            merged = self._merge_average(aligned)
        elif method == "weighted":
            merged = self._merge_weighted(aligned, audio_paths)
        else:
            # md5_cache: 实际计算走 average 或 weighted
            # 默认使用 average 计算后缓存
            merged = self._merge_average(aligned)

        # 缓存结果
        if method == "md5_cache":
            cache_key = self._compute_cache_key(audio_paths)
            self._save_to_cache(cache_key, merged, target_sr)
            logger.info(f"[多参考合并] 已缓存合并结果: {cache_key[:12]}...")

        return merged, target_sr

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _read_audio(audio_path: str) -> tuple[np.ndarray, int]:
        """读取音频文件。"""
        if _HAS_SOUNDFILE:
            wav, sr = _sf.read(audio_path, dtype="float32")
            return wav, sr
        # 回退到预检器的原始读取
        return ReferenceAudioPrechecker._read_wav_raw(audio_path)

    @staticmethod
    def _resample(wav: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """简易重采样（线性插值）。

        不依赖 librosa/scipy，使用 numpy 线性插值实现。
        """
        if orig_sr == target_sr:
            return wav

        if wav.ndim > 1:
            wav = np.mean(wav, axis=1)  # 先转单声道

        duration = len(wav) / orig_sr
        target_len = int(round(duration * target_sr))
        if target_len <= 0:
            return np.zeros(1, dtype=np.float32)

        # 线性插值重采样
        old_indices = np.linspace(0, len(wav) - 1, target_len)
        result = np.interp(old_indices, np.arange(len(wav)), wav)
        return result.astype(np.float32)

    @staticmethod
    def _merge_average(aligned: list[np.ndarray]) -> np.ndarray:
        """简单平均合并。"""
        return np.mean(aligned, axis=0).astype(np.float32)

    def _merge_weighted(
        self,
        aligned: list[np.ndarray],
        audio_paths: list[str],
    ) -> np.ndarray:
        """按质量评分加权合并。

        质量评分越高，权重越大。权重归一化后加权平均。
        """
        scores: list[float] = []
        for p in audio_paths:
            try:
                report = self._prechecker.check_quality(p)
                scores.append(report.quality_score)
            except Exception as e:
                logger.warning(f"[多参考合并] 质量检测失败，使用默认评分 50: {e}")
                scores.append(50.0)

        # 归一化权重
        total = sum(scores)
        if total <= 0:
            weights = [1.0 / len(scores)] * len(scores)
        else:
            weights = [s / total for s in scores]

        merged = np.zeros_like(aligned[0])
        for w, audio in zip(weights, aligned):
            merged += w * audio

        logger.info(f"[多参考合并] 加权合并权重: {[f'{w:.3f}' for w in weights]}")
        return merged.astype(np.float32)

    @staticmethod
    def _compute_cache_key(audio_paths: list[str]) -> str:
        """计算音频路径列表的 MD5 缓存键。

        对排序后的路径列表拼接后取 MD5，确保顺序无关。
        """
        sorted_paths = sorted(audio_paths)
        combined = "|".join(sorted_paths)
        return hashlib.md5(combined.encode("utf-8")).hexdigest()

    def _load_from_cache(self, cache_key: str) -> tuple[np.ndarray, int] | None:
        """从缓存加载合并结果。

        缓存格式：{cache_key}.npy（波形）+ {cache_key}.meta（采样率）。
        """
        wav_path = self._cache_dir / f"{cache_key}.npy"
        meta_path = self._cache_dir / f"{cache_key}.meta"

        if not wav_path.is_file() or not meta_path.is_file():
            return None

        try:
            wav = np.load(str(wav_path))
            with open(str(meta_path), "r", encoding="utf-8") as f:
                sr = int(f.read().strip())
            return wav, sr
        except Exception as e:
            logger.warning(f"[多参考合并] 缓存加载失败: {e}")
            return None

    def _save_to_cache(self, cache_key: str, wav: np.ndarray, sr: int) -> None:
        """保存合并结果到缓存。"""
        wav_path = self._cache_dir / f"{cache_key}.npy"
        meta_path = self._cache_dir / f"{cache_key}.meta"

        try:
            np.save(str(wav_path), wav)
            with open(str(meta_path), "w", encoding="utf-8") as f:
                f.write(str(sr))
        except Exception as e:
            logger.warning(f"[多参考合并] 缓存保存失败: {e}")


# ======================================================================
# ReferenceAudioIsolator — VoxCPM2 参考音频隔离
# ======================================================================


class ReferenceAudioIsolator:
    """VoxCPM2 参考音频隔离器

    VoxCPM2 使用特殊 token 标记参考音频区域：
      - token 103 (ref_audio_start): 标记参考音频起始
      - token 104 (ref_audio_end): 标记参考音频结束
      - token 101 (audio_start): 标记目标音频起始
      - token 102 (audio_end): 标记目标音频结束

    本类提供将文本与参考音频标记结合的方法，并生成对应的
    loss_mask 用于训练/推理时隔离参考音频上下文，使损失
    仅在目标音频段上计算。

    序列结构：
        [103, ref_audio_tokens, 104, text_tokens, 101, target_audio_tokens, 102]

    loss_mask 设计：
        - 参考音频区域 (103..104): 0 (不参与损失计算)
        - 文本区域: 0 (不参与损失计算)
        - 目标音频区域 (101..102): 1 (参与损失计算)
    """

    # VoxCPM2 特殊 token ID
    REF_AUDIO_START: int = 103
    REF_AUDIO_END: int = 104
    AUDIO_START: int = 101
    AUDIO_END: int = 102

    def __init__(self) -> None:
        """初始化参考音频隔离器。"""
        pass

    def prepare_reference(
        self,
        text: str,
        ref_audio_path: str,
    ) -> dict[str, Any]:
        """准备带参考音频隔离标记的输入序列。

        将文本用 token 103/104 标记包裹，表示此区域为参考音频上下文。
        同时生成 loss_mask，标记哪些位置参与损失计算。

        Args:
            text: 待合成的目标文本。
            ref_audio_path: 参考音频文件路径（仅用于验证存在性和
                           计算参考音频帧长度）。

        Returns:
            字典，包含以下键：
              - "isolated_text": 用 token 103/104 标记包裹后的文本。
                格式: "<ref_start><ref_audio_info><ref_end><target_text>"
              - "loss_mask": 布尔掩码列表，与 isolated_text 的 token
                序列等长。参考区域为 False，目标文本区域为 True。
              - "ref_audio_path": 参考音频路径（原样返回）。
              - "ref_frame_count": 参考音频帧数估计。
              - "sequence_structure": 序列结构描述（用于调试）。

        Raises:
            FileNotFoundError: 参考音频文件不存在。
            ValueError: 文本为空。
        """
        if not text.strip():
            raise ValueError("目标文本不能为空")

        if not os.path.isfile(ref_audio_path):
            raise FileNotFoundError(f"参考音频文件不存在: {ref_audio_path}")

        # 估计参考音频帧数
        ref_frame_count = self._estimate_ref_frames(ref_audio_path)

        # 构建隔离文本：在文本前添加参考音频标记
        # 使用特殊标记字符串表示 token 位置，实际 token 化由模型处理
        ref_start_marker = f"<|token_{self.REF_AUDIO_START}|>"
        ref_end_marker = f"<|token_{self.REF_AUDIO_END}|>"

        # 参考音频信息占位（实际推理时由模型编码器填充音频特征）
        ref_placeholder = f"<ref_audio:{ref_frame_count}frames>"

        isolated_text = f"{ref_start_marker}{ref_placeholder}{ref_end_marker}{text}"

        # 构建 loss_mask
        # 参考区域 (ref_start + ref_placeholder + ref_end): 不参与损失 → False
        # 目标文本区域: 参与损失 → True
        ref_section_tokens = 1 + ref_frame_count + 1  # start + frames + end
        text_token_count = max(1, len(text))  # 粗略估计：1 字符 ≈ 1 token

        loss_mask = [False] * ref_section_tokens + [True] * text_token_count

        # 序列结构描述
        structure = (
            f"[{self.REF_AUDIO_START}(ref_start), "
            f"ref_audio×{ref_frame_count}, "
            f"{self.REF_AUDIO_END}(ref_end), "
            f"text×{text_token_count}]"
        )

        logger.info(
            f"[参考隔离] 序列结构: {structure}, "
            f"loss_mask 长度: {len(loss_mask)}, "
            f"有效位置: {sum(loss_mask)}/{len(loss_mask)}"
        )

        return {
            "isolated_text": isolated_text,
            "loss_mask": loss_mask,
            "ref_audio_path": ref_audio_path,
            "ref_frame_count": ref_frame_count,
            "sequence_structure": structure,
        }

    def build_full_sequence(
        self,
        text_tokens: list[int],
        ref_frame_count: int,
        target_frame_count: int = 0,
    ) -> dict[str, Any]:
        """构建完整的 VoxCPM2 训练/推理序列。

        序列格式：
            [103, ref_audio×R, 104, text_tokens, 101, target_audio×T, 102]

        Args:
            text_tokens: 文本 token ID 列表。
            ref_frame_count: 参考音频帧数。
            target_frame_count: 目标音频帧数（推理时可设为 0）。

        Returns:
            字典，包含：
              - "tokens": 完整 token 序列（参考区域用 0 填充音频位置）。
              - "text_mask": 文本位置为 1，音频位置为 0。
              - "audio_mask": 音频位置为 1，文本位置为 0。
              - "loss_mask": 仅目标音频位置为 1，其余为 0。
        """
        # 参考音频区域
        ref_section = [self.REF_AUDIO_START] + [0] * ref_frame_count + [self.REF_AUDIO_END]

        # 文本区域
        text_section = list(text_tokens)

        # 目标音频区域（如果指定了帧数）
        if target_frame_count > 0:
            target_section = [self.AUDIO_START] + [0] * target_frame_count + [self.AUDIO_END]
        else:
            target_section = [self.AUDIO_START]  # 推理模式：仅起始标记

        # 组合完整序列
        tokens = ref_section + text_section + target_section

        # 构建 mask
        # 特殊 token (103/104/101/102) 属于文本类 token → text_mask=1
        # 音频位置 (0填充) 属于音频 → audio_mask=1
        ref_text_mask = [1] + [0] * ref_frame_count + [1]  # 103=文本, 音频=0, 104=文本
        ref_audio_mask = [0] + [1] * ref_frame_count + [0]

        text_text_mask = [1] * len(text_tokens)
        text_audio_mask = [0] * len(text_tokens)

        if target_frame_count > 0:
            tgt_text_mask = [1] + [0] * target_frame_count + [1]
            tgt_audio_mask = [0] + [1] * target_frame_count + [0]
            tgt_loss_mask = [0] + [1] * target_frame_count + [0]
        else:
            tgt_text_mask = [1]
            tgt_audio_mask = [0]
            tgt_loss_mask = [0]

        text_mask = ref_text_mask + text_text_mask + tgt_text_mask
        audio_mask = ref_audio_mask + text_audio_mask + tgt_audio_mask

        # loss_mask: 仅目标音频区域为 1
        ref_loss_mask = [0] * len(ref_section)
        text_loss_mask = [0] * len(text_tokens)
        loss_mask = ref_loss_mask + text_loss_mask + tgt_loss_mask

        logger.debug(
            f"[参考隔离] 完整序列长度: {len(tokens)}, "
            f"text_mask 求和: {sum(text_mask)}, "
            f"audio_mask 求和: {sum(audio_mask)}, "
            f"loss_mask 求和: {sum(loss_mask)}"
        )

        return {
            "tokens": tokens,
            "text_mask": text_mask,
            "audio_mask": audio_mask,
            "loss_mask": loss_mask,
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_ref_frames(ref_audio_path: str) -> int:
        """估计参考音频的帧数。

        VoxCPM2 的帧率 (token rate) 为 6.25 Hz，即每秒 6.25 个 patch。
        每个 patch 包含 P=4 个音频帧。

        Args:
            ref_audio_path: 参考音频文件路径。

        Returns:
            估计的参考音频帧数（patch 数量）。
        """
        try:
            if _HAS_SOUNDFILE:
                info = _sf.info(ref_audio_path)
                duration = info.duration
            else:
                # 回退：从文件大小粗略估计（仅 WAV）
                file_size = os.path.getsize(ref_audio_path)
                # 假设 16-bit PCM WAV：每秒约 sr * 2 字节
                duration = (file_size - 44) / (16000 * 2)  # 粗略估计
        except Exception as e:
            logger.warning(f"[参考隔离] 无法读取音频信息，使用默认 3s: {e}")
            duration = 3.0

        # VoxCPM2 token rate: 6.25 Hz（每秒 6.25 个 patch）
        token_rate = 6.25
        n_patches = max(1, int(round(duration * token_rate)))

        return n_patches
