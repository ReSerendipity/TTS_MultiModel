"""生成辅助函数：保存、文本分割、音频合并、预处理等"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import numpy as np
import soundfile as sf

from .config import SAVE_DIR

logger = logging.getLogger("tts_multimodel")


def save_audio(wav: np.ndarray, sr: int, prefix: str = "audio", format: str = "wav") -> tuple[str, str]:
    """保存音频文件到输出目录"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format == "mp3":
        try:
            import io

            from pydub import AudioSegment

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


def split_text_for_tts(text: str, max_chars: int = None) -> list[str]:
    """将长文本按语义边界分割成适合 TTS 处理的短段落

    分割策略：优先在自然断句处（句号、逗号、分号等）切分，
    保持每段不超过 max_chars 个字符。
    方括号标签（如 [laugh]、[uv_break]、[oral_0] 等）作为不可分割的整体单元，
    绝不会被分割到两个不同段中。

    断点优先级：
      1. 中文句号/叹号/问号（。！？）
      2. 中文逗号/顿号（，、）
      3. 英文句号/叹号/问号/分号（.,!?;）
      4. 中文冒号（：）
      5. 中文分号（；）
    """
    if max_chars is None:
        try:
            from .config import get_config

            max_chars = get_config().generation_defaults.split_max_chars
        except Exception:
            max_chars = 200
    if len(text) <= max_chars:
        return [text]

    segments = []
    current = []
    current_len = 0
    # 追踪未闭合的方括号深度，用于防止在标签内部截断
    bracket_depth = 0

    for char in text:
        current.append(char)
        current_len += 1

        # 追踪方括号嵌套深度
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)

        if current_len >= max_chars:
            # 如果当前处于未闭合的方括号标签内部，继续累积直到标签闭合
            if bracket_depth > 0:
                continue

            joined = "".join(current)
            # 按优先级从高到低查找最佳分割点（最后一个匹配的标点）
            split_idx = _find_best_split_point(joined)

            if split_idx > max_chars // 3:
                # 找到合理的自然断句点
                segments.append(joined[: split_idx + 1])
                remaining = joined[split_idx + 1 :]
                current = list(remaining)
                current_len = len(current)
            else:
                # 断句点太靠近段首，强制在当前位置截断
                # 但确保不在方括号标签内部截断
                safe_end = _find_safe_split_boundary(joined, len(joined))
                segments.append(joined[:safe_end])
                remaining = joined[safe_end:]
                current = list(remaining)
                current_len = len(current)

            # 重新计算 current 中的 bracket_depth
            bracket_depth = 0
            for c in current:
                if c == "[":
                    bracket_depth += 1
                elif c == "]":
                    bracket_depth = max(0, bracket_depth - 1)

    if current:
        segments.append("".join(current))

    # 过滤空段
    return [s for s in segments if s] if segments else [text]


def _is_decimal_point(text: str, idx: int) -> bool:
    """判断 text[idx] 处的 '.' 是否为数字小数点（前后均为数字）"""
    if idx < 0 or idx >= len(text) or text[idx] != ".":
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
    if idx < 0 or idx >= len(text) or text[idx] != ".":
        return False

    # 模式 1：单个大写字母 + 句点（如 U.S.A.）
    if idx > 0 and text[idx - 1].isupper() and text[idx - 1].isalpha() and (idx - 1 == 0 or text[idx - 2] == "."):
        return True

    # 模式 2：已知缩写词列表
    _ABBREVIATIONS = (
        "Dr",
        "Mr",
        "Mrs",
        "Ms",
        "vs",
        "etc",
        "Inc",
        "Ltd",
        "Prof",
        "Sr",
        "Jr",
        "No",
    )
    for abbr in _ABBREVIATIONS:
        start = idx - len(abbr)
        if start >= 0 and text[start:idx].lower() == abbr.lower() and (start == 0 or not text[start - 1].isalpha()):
            return True

    return False


def _is_inside_quotes(text: str, idx: int) -> bool:
    """判断位置 idx 是否在引号对内部

    支持中文引号 "" 和英文引号 ""。
    """
    # 构建引号配对映射
    quote_pairs = [
        ("\u201c", "\u201d"),  # 中文 ""
        ('"', '"'),  # 英文 ""
    ]

    for open_q, close_q in quote_pairs:
        open_count = 0
        for i in range(idx):
            if text[i] == open_q:
                open_count += 1
            elif text[i] == close_q and open_count > 0:
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
    - 方括号标签内的所有位置（副语言标签、韵律标签等）
    """
    excluded = set()

    # 排除小数点和缩写句点
    for i, ch in enumerate(text):
        if ch == "." and (_is_decimal_point(text, i) or _is_abbreviation(text, i)):
            excluded.add(i)

    # 排除引号内部的标点位置
    punctuation_chars = set("。！？，、.;!?：；")
    for i, ch in enumerate(text):
        if ch in punctuation_chars and _is_inside_quotes(text, i):
            excluded.add(i)

    # 排除方括号标签 [tag] 内的所有位置
    # 保护副语言标签如 [laugh], [uv_break], [oral_0]~[oral_9],
    # [lbreak], [lb], [vbreak], [pbreak] 等不被分割打断
    # 同时保护所有 [...] 方括号内容作为一个整体单元
    excluded.update(_find_bracket_tag_positions(text))

    return excluded


def _find_bracket_tag_positions(text: str) -> set:
    """找到所有方括号标签 [tag] 内部的位置索引集合

    保护以下类型的标签：
    - 副语言标签：[laugh], [uv_break], [lbreak], [lb], [vbreak], [pbreak]
    - 韵律标签：[oral_0] ~ [oral_9]
    - 任意 [content] 方括号对内部的所有位置

    返回所有位于 [...] 内部的字符位置索引，确保这些标签不会被分割点打断。
    """
    positions = set()
    i = 0
    while i < len(text):
        if text[i] == "[":
            # 寻找匹配的 ]
            j = text.find("]", i + 1)
            if j != -1:
                # 排除 [ 和 ] 之间所有位置（包括 [ 和 ] 本身）
                for pos in range(i, j + 1):
                    positions.add(pos)
                i = j + 1
            else:
                # 没有匹配的 ]，跳过
                i += 1
        else:
            i += 1
    return positions


def _find_safe_split_boundary(text: str, proposed_pos: int) -> int:
    """找到安全的分割边界位置，确保不在方括号标签内部截断

    如果 proposed_pos 位于某个 [tag] 内部，则向前退到该标签的 [ 之前，
    或向后推进到该标签的 ] 之后，取决于哪个方向更短。

    Args:
        text: 待分割文本
        proposed_pos: 建议的分割位置

    Returns:
        调整后的安全分割位置
    """
    if proposed_pos <= 0 or proposed_pos >= len(text):
        return proposed_pos

    bracket_positions = _find_bracket_tag_positions(text)

    if proposed_pos not in bracket_positions:
        return proposed_pos

    # proposed_pos 在某个 [tag] 内部，需要调整
    # 向前找到该标签的 [ 位置
    open_pos = proposed_pos
    while open_pos > 0 and open_pos in bracket_positions:
        open_pos -= 1
    # open_pos 现在是不在 bracket_positions 中的位置，即 [ 的前一个位置
    # 所以标签的 [ 在 open_pos + 1
    tag_start = open_pos + 1

    # 向后找到该标签的 ] 位置
    close_pos = proposed_pos
    while close_pos < len(text) and close_pos in bracket_positions:
        close_pos += 1
    # close_pos 现在是不在 bracket_positions 中的位置，即 ] 的后一个位置
    # 所以标签的 ] 在 close_pos - 1
    tag_end = close_pos  # 分割点在 ] 之后

    # 选择距离 proposed_pos 更近的安全边界
    dist_to_start = proposed_pos - tag_start
    dist_to_end = tag_end - proposed_pos

    if dist_to_start <= dist_to_end and tag_start > 0:
        return tag_start
    elif tag_end <= len(text):
        return tag_end
    else:
        return tag_start if tag_start > 0 else tag_end


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


def merge_audio_segments(
    audio_segments: list[np.ndarray],
    sr: int,
    silence_duration: float = 0.3,
    target_sr: int | None = None,
    crossfade_duration: float = 0.05,
) -> tuple[np.ndarray | None, int]:
    """合并音频段，支持交叉淡入淡出（crossfade）或静音填充

    优化说明：
      - 所有音频段预先读取到内存，统一计算总长度后一次性分配 numpy 数组
      - 避免多次 np.concatenate 导致的内存拷贝
      - 当 crossfade_duration > 0 时，使用 raised cosine 交叉淡入淡出合并段间
      - 当 crossfade_duration == 0 时，回退到段间添加指定时长的静音填充
      - 自动处理不同 dtype（float32/int16）的统一归一化和多声道转单声道
      - 支持 target_sr 参数：合并后自动重采样到目标采样率

    Crossfade 原理：
      - 段 N 末尾与段 N+1 开头重叠 crossfade_samples 个样本
      - 段 N 末尾应用 raised cosine fade-out: cos²(π·t/2T)
      - 段 N+1 开头应用 raised cosine fade-in: sin²(π·t/2T)
      - 重叠区域两段加权叠加，消除段间突变噪声

    Args:
        audio_segments: 音频 numpy 数组列表
        sr: 采样率
        silence_duration: 段间静音时长（秒），默认 0.3 秒
            （仅在 crossfade_duration <= 0 时生效）
        target_sr: 目标采样率（Hz），None 表示不重采样
        crossfade_duration: 交叉淡入淡出时长（秒），默认 0.05 秒（50ms）
            设为 0 则回退到静音填充模式

    Returns:
        (合并后的音频数组, 采样率)
    """
    if not audio_segments:
        return None, sr

    # 归一化和声道处理
    normalized_segments = []
    for seg in audio_segments:
        seg = seg.astype(np.float32)
        max_val = np.max(np.abs(seg))
        if max_val > np.float32(1.0):
            seg = seg / max_val
        if seg.ndim > 1:
            seg = np.mean(seg, axis=-1)
        normalized_segments.append(seg)

    # 单段直接返回（已经过归一化和声道处理）
    if len(normalized_segments) == 1:
        result = normalized_segments[0].astype(np.float32)
    elif crossfade_duration > 0:
        # ---------- Crossfade 合并模式 ----------
        crossfade_samples = int(sr * crossfade_duration)
        # 确保交叉淡入淡出样本数不超过最短段长度的 1/3
        min_seg_len = min(len(s) for s in normalized_segments)
        crossfade_samples = min(crossfade_samples, min_seg_len // 3)
        crossfade_samples = max(crossfade_samples, 1)  # 至少 1 个样本

        n_segs = len(normalized_segments)

        # 计算总长度：各段长度之和 - (n-1) 个重叠区域
        total_length = sum(len(s) for s in normalized_segments)
        total_length -= crossfade_samples * (n_segs - 1)

        # 一次性分配结果缓冲区
        result = np.zeros(total_length, dtype=np.float32)

        # 构建 raised cosine 淡入淡出曲线
        t = np.linspace(0, 1, crossfade_samples, dtype=np.float32)
        fade_in = np.sin(t * np.pi / 2) ** 2   # 0 -> 1
        fade_out = np.cos(t * np.pi / 2) ** 2  # 1 -> 0

        pos = 0
        for i, seg in enumerate(normalized_segments):
            seg = seg.astype(np.float32)
            seg_len = len(seg)

            if i == 0:
                # 第一段：直接写入（末尾部分将在后续重叠时处理）
                write_len = seg_len
                result[pos : pos + write_len] = seg[:write_len]
                pos += write_len
            else:
                # 非首段：开头与上一段末尾做交叉淡入淡出
                # 重叠区域的起始位置需要回退 crossfade_samples
                overlap_start = pos - crossfade_samples
                overlap_prev = result[overlap_start : overlap_start + crossfade_samples].copy()
                overlap_curr = seg[:crossfade_samples]
                blended = overlap_prev * fade_out + overlap_curr * fade_in
                result[overlap_start : overlap_start + crossfade_samples] = blended

                # pos 保持不变（因为重叠区域覆盖了上一段末尾的位置）
                # 写入重叠之后的剩余部分
                remaining_len = seg_len - crossfade_samples
                if remaining_len > 0:
                    result[pos : pos + remaining_len] = seg[crossfade_samples:]
                    pos += remaining_len

    else:
        # ---------- 静音填充模式（向后兼容） ----------
        silence_samples = int(sr * silence_duration)
        total_length = sum(len(s) for s in normalized_segments)
        total_silence = silence_samples * (len(normalized_segments) - 1)
        total_length += total_silence

        result = np.zeros(total_length, dtype=np.float32)

        pos = 0
        for i, seg in enumerate(normalized_segments):
            seg_len = len(seg)
            result[pos : pos + seg_len] = seg.astype(np.float32)
            pos += seg_len
            if i < len(normalized_segments) - 1:
                pos += silence_samples

    # 按需重采样到目标采样率
    if target_sr is not None and target_sr != sr:
        from .resampling import normalize_sample_rate

        result = normalize_sample_rate(result, sr, target_sr)
        return result, target_sr

    return result, sr


def preprocess_and_save_temp(
    audio_input: str | tuple[int, np.ndarray],
    filename: str = "temp_ref.wav",
    target_sr: int | None = None,
) -> tuple[str, int, np.ndarray]:
    """预处理并保存临时音频文件

    Args:
        audio_input: 文件路径或 (采样率, 音频数组) 元组
        filename: 临时文件名
        target_sr: 目标采样率（Hz），None 表示不重采样

    Returns:
        (临时文件路径, 采样率, 音频数组)
    """
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

    # 按需重采样到目标采样率
    if target_sr is not None and target_sr != sr:
        from .resampling import normalize_sample_rate

        wav_p = normalize_sample_rate(wav_p, sr, target_sr)
        sr = target_sr

    tmp_path = os.path.join(SAVE_DIR, filename)
    sf.write(tmp_path, wav_p, sr)
    return tmp_path, sr, wav_p


def _save_wav_compatible(wav_data: np.ndarray, out_path: str, sample_rate: int = 48000) -> str:
    """将音频数据保存为浏览器兼容的 WAV 格式（int16 PCM）"""
    if wav_data.max() > 1.0 or wav_data.min() < -1.0:
        wav_data = wav_data / max(abs(wav_data.max()), abs(wav_data.min()))
    wav_int16 = (wav_data * 32767).astype(np.int16)
    sf.write(out_path, wav_int16, sample_rate, subtype="PCM_16")
    return out_path


# ---------------------------------------------------------------------------
# Seed 增量辅助
# ---------------------------------------------------------------------------

def increment_seed(base_seed: int, chunk_index: int) -> int:
    """为每个分块生成不同的 seed，保持韵律多样性

    通过将 base_seed 与 chunk_index 相加，确保每个分块使用不同的种子。
    结果对 2^31 取模以保持在合理范围内，避免溢出。

    Args:
        base_seed: 基础种子值
        chunk_index: 分块索引（从 0 开始）

    Returns:
        新的种子值

    Examples:
        >>> increment_seed(42, 0)
        42
        >>> increment_seed(42, 1)
        43
        >>> increment_seed(42, 5)
        47
    """
    _MAX_SEED = 2**31  # 保持种子在 int32 正数范围内
    return (base_seed + chunk_index) % _MAX_SEED


# ---------------------------------------------------------------------------
# 超长文本分块（支持 50000 字符）
# ---------------------------------------------------------------------------

# 超长文本最大分块字符数（默认 5000，可按需调整）
DEFAULT_CHUNK_MAX_CHARS = 5000

# 用于识别句末边界的标点集合
_SENTENCE_END_PUNCTUATION = set("。！？.!?;\n")


def split_into_chunks(
    text: str,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    respect_sentences: bool = True,
) -> list[tuple[str, int]]:
    """将超长文本拆分为多个分块，每个分块尊重句子边界

    适用于流式处理管道中处理非常长的文本（支持 50000 字符以上）。
    每个分块不超过 max_chars 个字符，且尽量在句子边界处切分。
    方括号标签 [tag] 不会被分割到两个分块中。

    Args:
        text: 待分块的文本
        max_chars: 每个分块的最大字符数，默认 5000
        respect_sentences: 是否在句子边界处切分，默认 True
            设为 False 则严格按 max_chars 硬切

    Returns:
        由 (chunk_text, chunk_index) 元组组成的列表
        chunk_index 从 0 开始递增

    Examples:
        >>> chunks = split_into_chunks("很长的文本...", max_chars=200)
        >>> len(chunks) > 1
        True
        >>> chunks[0][1]  # 第一个分块的索引
        0
    """
    if not text:
        return [("", 0)]

    if len(text) <= max_chars:
        return [(text, 0)]

    # 先用 split_text_for_tts 进行语义分割
    # 该函数已经保护了方括号标签不被打断
    sub_segments = split_text_for_tts(text, max_chars=max_chars)

    # 将子段合并为分块，确保每个分块不超过 max_chars
    chunks = []
    current_chunk_parts = []
    current_len = 0

    for seg in sub_segments:
        seg_len = len(seg)

        # 如果单个子段就超过 max_chars 且不尊重句子边界，硬切
        if seg_len > max_chars and not respect_sentences:
            if current_chunk_parts:
                chunk_text = "".join(current_chunk_parts)
                chunks.append(chunk_text)
                current_chunk_parts = []
                current_len = 0
            # 硬切超长子段
            for start in range(0, seg_len, max_chars):
                chunks.append(seg[start : start + max_chars])
            continue

        # 如果加入当前子段会超过 max_chars，先保存当前分块
        if current_len + seg_len > max_chars and current_chunk_parts:
            chunk_text = "".join(current_chunk_parts)
            chunks.append(chunk_text)
            current_chunk_parts = []
            current_len = 0

        current_chunk_parts.append(seg)
        current_len += seg_len

    # 保存最后一个分块
    if current_chunk_parts:
        chunk_text = "".join(current_chunk_parts)
        chunks.append(chunk_text)

    # 为每个分块分配索引
    return [(chunk, idx) for idx, chunk in enumerate(chunks)]
