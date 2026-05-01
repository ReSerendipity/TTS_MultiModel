# -*- coding: utf-8 -*-
"""生成辅助函数：文本分割、音频合并、保存、预处理等"""

import os
import time
import logging
from datetime import datetime

import numpy as np
import soundfile as sf

from .config import SAVE_DIR

logger = logging.getLogger("tts_multimodel")


def save_audio(wav, sr, prefix="audio", format="wav"):
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
            return file_path
        except ImportError:
            pass
    file_path = os.path.join(SAVE_DIR, f"{prefix}_{timestamp}.wav")
    sf.write(file_path, wav, sr)
    return file_path


def split_text_for_tts(text, max_chars=200):
    """将长文本分割成适合 TTS 处理的短段落"""
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
            split_idx = max(
                joined.rfind("。"), joined.rfind("！"), joined.rfind("？"),
                joined.rfind("；"), joined.rfind(","), joined.rfind("，"), 0
            )
            if split_idx > max_chars // 2:
                segments.append(joined[:split_idx + 1])
                current = list(joined[split_idx + 1:])
                current_len = len(current)
            else:
                segments.append(joined)
                current = []
                current_len = 0

    if current:
        segments.append("".join(current))

    return segments if segments else [text]


def merge_audio_segments(audio_segments, sr):
    """合并音频段，段间添加静音"""
    if not audio_segments:
        return None, sr

    if len(audio_segments) == 1:
        return audio_segments[0], sr

    silence_samples = int(sr * 0.3)
    result = [audio_segments[0]]
    for seg in audio_segments[1:]:
        result.append(np.zeros(silence_samples))
        result.append(seg)

    return np.concatenate(result), sr


def preprocess_and_save_temp(audio_input, filename="temp_ref.wav"):
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


def _save_wav_compatible(wav_data, out_path, sample_rate=48000):
    """将音频数据保存为浏览器兼容的 WAV 格式（int16 PCM）"""
    # 确保数据在 [-1, 1] 范围内
    if wav_data.max() > 1.0 or wav_data.min() < -1.0:
        wav_data = wav_data / max(abs(wav_data.max()), abs(wav_data.min()))
    # 转换为 int16
    wav_int16 = (wav_data * 32767).astype(np.int16)
    sf.write(out_path, wav_int16, sample_rate, subtype='PCM_16')
    return out_path
