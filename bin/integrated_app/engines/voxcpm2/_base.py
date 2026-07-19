import logging
import os
import time

import numpy as np

from ...config import SAVE_DIR
from ...config_models import AdvancedParamsConfig
from ...exceptions import EngineSwitchError, GenerationError, tts_error_handler
from ...generation import _save_wav_compatible, split_text_for_tts
from ...model_manager import _gen_tracker, _progress_mgr
from ...persona_manager import get_persona_map
from ...utils import cleanup_temp_files

logger = logging.getLogger("tts_multimodel")

_DEFAULT_ADVANCED = AdvancedParamsConfig()

__all__ = [
    "SAVE_DIR",
    "EngineSwitchError",
    "GenerationError",
    "_advanced_kwargs",
    "_gen_tracker",
    "_progress_mgr",
    "_save_wav_compatible",
    "build_advanced_params",
    "cleanup_temp_files",
    "generate_with_template",
    "get_advanced_params",
    "get_persona_map",
    "logger",
    "split_text_for_tts",
    "tts_error_handler",
]


def get_advanced_params() -> dict:
    return _DEFAULT_ADVANCED.to_dict()


def build_advanced_params(**overrides) -> AdvancedParamsConfig:
    valid_keys = AdvancedParamsConfig.model_fields.keys()
    filtered = {k: v for k, v in overrides.items() if k in valid_keys}
    return AdvancedParamsConfig(**filtered)


def _advanced_kwargs(advanced: AdvancedParamsConfig | None = None) -> dict:
    if advanced is None:
        advanced = _DEFAULT_ADVANCED
    return dict(
        max_len=advanced.max_len,
        retry_badcase=advanced.retry_badcase,
        retry_badcase_max_times=advanced.retry_badcase_max_times,
        retry_badcase_ratio_threshold=advanced.retry_badcase_ratio_threshold,
    )


def generate_with_template(
    text: str,
    instruction: str,
    gen_kwargs_builder,
    output_prefix: str,
    phase_name: str,
    sample_rate: int = 48000,
    ref_audio_path: str | None = None,
    prompt_cache=None,
    start_time: float | None = None,
    message_builder=None,
    skip_progress_start: bool = False,
) -> tuple[tuple | None, str]:
    """VoxCPM2 公共生成模板函数。

    封装了文本分割→逐段推理(含进度追踪)→音频合并→文件保存→返回结果的通用流程。

    Args:
        text: 待合成的输入文本。
        instruction: 指令前缀（如情感控制指令）。
        gen_kwargs_builder: 可调用对象，签名为 (seg_text_with_instruction, ref_audio_path, prompt_cache)
                           返回用于 model.generate() 的 kwargs 字典。
        output_prefix: 输出文件名前缀（如 "voxcpm_clone"）。
        phase_name: 日志前缀名称（如 "VoxCPM可控克隆"）。
        sample_rate: 音频采样率（默认 48000）。
        ref_audio_path: 参考音频文件路径。
        prompt_cache: 缓存的音色特征（来自 prompt_cache 模块）。
        start_time: 用于段循环中估算剩余时间的起始时间。
        message_builder: 可选的可调用对象，签名为 (duration_sec, total_segments)，
                        返回成功消息字符串。若为 None 则使用默认格式。

    Returns:
        ((sample_rate, wav_data, filename), message) 元组。
    """
    from ...model_registry import registry

    if start_time is None:
        start_time = time.time()

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    if skip_progress_start:
        _progress_mgr.update_phase("VoxCPM2 推理中...")
    else:
        _progress_mgr.start(total_segments=total, phase="VoxCPM2 推理中...")

    def _build_text(seg_text):
        if instruction and instruction.strip():
            return "(" + instruction.strip() + ")" + seg_text
        return seg_text

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        mode_str = "reference_wav" if ref_audio_path else "默认音色"
        logger.info(f"[{phase_name}] 第 1/1 段，使用 {mode_str} 模式...")
        built_text = _build_text(segments[0])
        kwargs = gen_kwargs_builder(built_text, ref_audio_path, prompt_cache)
        wav = registry.voxcpm_model.generate(**kwargs)
        duration_sec = len(wav) / sample_rate if len(wav) > 0 else 0
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"{output_prefix}_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, sample_rate)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        logger.info(f"[{phase_name}] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        msg = message_builder(duration_sec, total) if message_builder else f"生成成功！音频时长 {duration_sec:.1f} 秒。"
        return (sample_rate, wav, filename), msg

    audio_segments = []
    for idx, seg in enumerate(segments):
        if _progress_mgr.should_stop():
            logger.info(f"[{phase_name}] 生成已被用户取消")
            raise GenerationError("生成已取消")
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx + 1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[{phase_name}] 第 {idx + 1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[{phase_name}] 第 1/{total} 段...")

        built_text = _build_text(seg)
        kwargs = gen_kwargs_builder(built_text, ref_audio_path, prompt_cache)
        wav = registry.voxcpm_model.generate(**kwargs)
        audio_segments.append(wav)

    if not audio_segments:
        raise GenerationError(f"VoxCPM2 {phase_name}生成失败：无有效音频段")

    merged = np.concatenate(audio_segments)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"{output_prefix}_{timestamp}.wav")
    _save_wav_compatible(merged, out_path, sample_rate)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(merged) / sample_rate
    logger.info(f"[{phase_name}] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，分段: {total}")
    msg = (
        message_builder(duration_sec, total)
        if message_builder
        else f"生成成功！音频时长 {duration_sec:.1f} 秒，分段: {total}。"
    )
    return (sample_rate, merged, filename), msg
