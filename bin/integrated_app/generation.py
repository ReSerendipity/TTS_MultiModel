# -*- coding: utf-8 -*-
"""生成辅助函数：保存、文本分割、音频合并、预处理等"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import List, Tuple

import numpy as np
import soundfile as sf

from .config import SAVE_DIR, GEN_SPLIT_MAX_CHARS

logger = logging.getLogger("tts_multimodel")


def save_audio(wav: np.ndarray, sr: int, prefix: str = "audio", format: str = "wav") -> Tuple[str, str]:
    """保存音频文件到输出目录"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format == "mp3":
        try:
            from pydub import AudioSegment
            import io
            buf = io.BytesIO()
            sf.write(buf, wav, sr, format="WAV")
            buf.seek(0)
            audio = AudioSegment.from_wav(buf)
            file_path = os.path.join(SAVE_DIR, f"{prefix}_{timestamp}.mp3")
            audio.export(file_path, format="mp3", bitrate="192k")
            return file_path, os.path.basename(file_path)
        except ImportError:
            pass
    file_path = os.path.join(SAVE_DIR, f"{prefix}_{timestamp}.wav")
    sf.write(file_path, wav, sr)
    return file_path, os.path.basename(file_path)


def split_text_for_tts(text: str, max_chars: int = None) -> List[str]:
    """将长文本按语义边界分割成适合 TTS 处理的短段落

    分割策略：优先在自然断句处（句号、逗号、分号等）切分，
    保持每段不超过 max_chars 个字符。

    断点优先级：
      1. 中文句号/叹号/问号（。！？）
      2. 中文逗号/顿号（，、）
      3. 英文句号/叹号/问号/分号（.,!?;）
      4. 中文冒号（：）
      5. 中文分号（；）
    """
    if max_chars is None:
        try:
            from .config_models import AdvancedParamsConfig
            max_chars = AdvancedParamsConfig().split_max_chars
        except Exception:
            max_chars = GEN_SPLIT_MAX_CHARS
    if len(text) <= max_chars:
        return [text]

    segments = []
    current = []
    current_len = 0

    for char in text:
        current.append(char)
        current_len += 1

        if current_len >= max_chars:
            joined = "".join(current)
            # 按优先级从高到低查找最佳分割点（最后一个匹配的标点）
            split_idx = _find_best_split_point(joined)

            if split_idx > max_chars // 3:
                # 找到合理的自然断句点
                segments.append(joined[:split_idx + 1])
                remaining = joined[split_idx + 1:]
                current = list(remaining)
                current_len = len(current)
            else:
                # 断句点太靠近段首，强制在当前位置截断
                segments.append(joined)
                current = []
                current_len = 0

    if current:
        segments.append("".join(current))

    # 过滤空段
    return [s for s in segments if s] if segments else [text]


def _is_decimal_point(text: str, idx: int) -> bool:
    """判断 text[idx] 处的 '.' 是否为数字小数点（前后均为数字）"""
    if idx < 0 or idx >= len(text) or text[idx] != '.':
        return False
    has_digit_before = idx > 0 and text[idx - 1].isdigit()
    has_digit_after = idx + 1 < len(text) and text[idx + 1].isdigit()
    return has_digit_before and has_digit_after


def _is_abbreviation(text: str, idx: int) -> bool:
    """判断 text[idx] 处的 '.' 是否属于英文缩写

    识别两种模式：
    1. 单个大写字母 + 句点，如 U.S.A. 中的每个句点
    2. 已知缩写词尾部的句点，如 Dr. Mr. vs. 等
    """
    if idx < 0 or idx >= len(text) or text[idx] != '.':
        return False

    # 模式 1：单个大写字母 + 句点（如 U.S.A.）
    if idx > 0 and text[idx - 1].isupper() and text[idx - 1].isalpha():
        # 确保大写字母前面是句点或字符串开头，即连续的 大写字母. 模式
        if idx - 1 == 0 or text[idx - 2] == '.':
            return True

    # 模式 2：已知缩写词列表
    _ABBREVIATIONS = (
        "Dr", "Mr", "Mrs", "Ms", "vs", "etc", "Inc", "Ltd",
        "Prof", "Sr", "Jr", "No",
    )
    for abbr in _ABBREVIATIONS:
        start = idx - len(abbr)
        if start >= 0 and text[start:idx].lower() == abbr.lower():
            # 确保缩写词前面是空格/行首，避免误匹配
            if start == 0 or not text[start - 1].isalpha():
                return True

    return False


def _is_inside_quotes(text: str, idx: int) -> bool:
    """判断位置 idx 是否在引号对内部

    支持中文引号 "" 和英文引号 ""。
    """
    # 构建引号配对映射
    quote_pairs = [
        ('\u201c', '\u201d'),  # 中文 ""
        ('"', '"'),            # 英文 ""
    ]

    for open_q, close_q in quote_pairs:
        open_count = 0
        for i in range(idx):
            if text[i] == open_q:
                open_count += 1
            elif text[i] == close_q:
                if open_count > 0:
                    open_count -= 1
        # 如果到 idx 位置时还有未闭合的引号，则 idx 在引号内部
        if open_count > 0:
            return True

    return False


def _build_excluded_positions(text: str) -> set:
    """构建不应作为分割点的位置集合

    排除以下位置：
    - 数字小数点
    - 英文缩写中的句点
    - 引号内部的所有标点位置
    """
    excluded = set()

    # 排除小数点和缩写句点
    for i, ch in enumerate(text):
        if ch == '.':
            if _is_decimal_point(text, i) or _is_abbreviation(text, i):
                excluded.add(i)

    # 排除引号内部的标点位置
    punctuation_chars = set('。！？，、.;!?：；')
    for i, ch in enumerate(text):
        if ch in punctuation_chars and _is_inside_quotes(text, i):
            excluded.add(i)

    return excluded


def _find_best_split_point(text: str) -> int:
    """在文本中找到最佳语义分割点的位置索引

    返回同一优先级中最靠右的标点位置索引，如果未找到则返回 0。
    优先级：中文句末标点 > 中文逗号 > 英文标点 > 中文冒号 > 中文分号

    会跳过不应分割的位置（小数点、缩写、引号内部），
    如果当前优先级的所有候选点都被排除，则降级到下一优先级。
    """
    excluded = _build_excluded_positions(text)

    def _find_rightmost(candidates, excluded_set):
        """在候选字符中找到最靠右且未被排除的位置"""
        best = -1
        for ch in candidates:
            idx = len(text) - 1
            while idx >= 0:
                idx = text.rfind(ch, 0, idx + 1)
                if idx <= 0:
                    break
                if idx not in excluded_set:
                    return idx
                idx -= 1
        return -1

    # 优先级 1：中文句号/叹号/问号
    idx = _find_rightmost("。！？", excluded)
    if idx > 0:
        return idx

    # 优先级 2：中文逗号/顿号
    idx = _find_rightmost("，、", excluded)
    if idx > 0:
        return idx

    # 优先级 3：英文句号/叹号/问号/分号
    idx = _find_rightmost(".!?;", excluded)
    if idx > 0:
        return idx

    # 优先级 4：中文冒号
    idx = _find_rightmost("：", excluded)
    if idx > 0:
        return idx

    # 优先级 5：中文分号
    idx = _find_rightmost("；", excluded)
    if idx > 0:
        return idx

    # 所有优先级的候选点都被排除，回退：在引号外找任意分割点
    # 如果连回退也找不到，返回 0
    return 0


def merge_audio_segments(audio_segments: List[np.ndarray], sr: int, silence_duration: float = 0.3) -> Tuple[np.ndarray | None, int]:
    """合并音频段，使用内存缓冲区操作，段间添加静音

    优化说明：
      - 所有音频段预先读取到内存，统一计算总长度后一次性分配 numpy 数组
      - 避免多次 np.concatenate 导致的内存拷贝
      - 段间添加指定时长的静音填充
      - 自动处理不同 dtype（float32/int16）的统一归一化和多声道转单声道

    Args:
        audio_segments: 音频 numpy 数组列表
        sr: 采样率
        silence_duration: 段间静音时长（秒），默认 0.3 秒

    Returns:
        (合并后的音频数组, 采样率)
    """
    if not audio_segments:
        return None, sr

    # 预计算总长度和静音样本数
    silence_samples = int(sr * silence_duration)
    total_length = 0
    normalized_segments = []

    for seg in audio_segments:
        # 统一转换为 float64 进行处理
        seg = seg.astype(np.float32)
        # 归一化：如果值域超出 [-1, 1]，进行缩放
        max_val = np.max(np.abs(seg))
        if max_val > np.float32(1.0):
            seg = seg / max_val
        # 多声道转单声道
        if seg.ndim > 1:
            seg = np.mean(seg, axis=-1)

        normalized_segments.append(seg)
        total_length += len(seg)

    # 单段直接返回（已经过归一化和声道处理）
    if len(normalized_segments) == 1:
        return normalized_segments[0].astype(np.float32), sr

    # 段间需要 (n-1) 个静音间隙
    total_silence = silence_samples * (len(normalized_segments) - 1)
    total_length += total_silence

    # 一次性分配结果缓冲区
    result = np.zeros(total_length, dtype=np.float32)

    # 写入音频段和静音
    pos = 0
    for i, seg in enumerate(normalized_segments):
        seg_len = len(seg)
        result[pos:pos + seg_len] = seg.astype(np.float32)
        pos += seg_len

        # 在段之间添加静音（最后一段不需要静音）
        if i < len(normalized_segments) - 1:
            pos += silence_samples

    return result, sr


def preprocess_and_save_temp(audio_input: str | Tuple[int, np.ndarray], filename: str = "temp_ref.wav") -> Tuple[str, int, np.ndarray]:
    """预处理并保存临时音频文件"""
    if isinstance(audio_input, str):
        wav, sr = sf.read(audio_input)
    else:
        sr, wav = audio_input
    wav_p = wav.astype(np.float32)
    if wav.dtype == np.int16:
        wav_p = wav_p / 32768.0
    max_val = np.max(np.abs(wav_p))
    if max_val > 1.0:
        wav_p = wav_p / max_val
    if wav_p.ndim > 1:
        wav_p = np.mean(wav_p, axis=-1)
    tmp_path = os.path.join(SAVE_DIR, filename)
    sf.write(tmp_path, wav_p, sr)
    return tmp_path, sr, wav_p


def _save_wav_compatible(wav_data: np.ndarray, out_path: str, sample_rate: int = 48000) -> str:
    """将音频数据保存为浏览器兼容的 WAV 格式（int16 PCM）"""
    if wav_data.max() > 1.0 or wav_data.min() < -1.0:
        wav_data = wav_data / max(abs(wav_data.max()), abs(wav_data.min()))
    wav_int16 = (wav_data * 32767).astype(np.int16)
    sf.write(out_path, wav_int16, sample_rate, subtype='PCM_16')
    return out_path

