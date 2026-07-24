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
from ...ras_sampling import RASContext, RASConfig
from ...utils import cleanup_temp_files

logger = logging.getLogger("tts_multimodel")

_DEFAULT_ADVANCED = AdvancedParamsConfig()

__all__ = [
    "SAVE_DIR",
    "EngineSwitchError",
    "GenerationError",
    "RASContext",
    "RASConfig",
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


def _check_segment_quality(
    wav: np.ndarray,
    sample_rate: int,
    expected_min_duration: float = 0.5,
) -> tuple[bool, str]:
    """检查单个音频段的质量，检测退化/重复输出。

    借鉴 Fish Speech RAS 的核心思想：在生成过程中检测异常模式。
    这里适配为音频段级别——检测生成的音频是否退化为静音、
    过短或能量异常低的片段。

    Args:
        wav: 生成的音频 numpy 数组。
        sample_rate: 采样率。
        expected_min_duration: 最小期望时长（秒），低于此值视为退化。

    Returns:
        (is_valid, reason) 元组。is_valid=True 表示音频质量可接受。
    """
    if wav is None or len(wav) == 0:
        return False, "空音频"

    duration = len(wav) / sample_rate
    if duration < expected_min_duration:
        return False, f"音频过短 ({duration:.2f}s < {expected_min_duration}s)"

    # 检查能量：如果均方根能量过低，可能是静音退化
    rms = float(np.sqrt(np.mean(wav.astype(np.float64) ** 2)))
    if rms < 1e-4:
        return False, f"音频能量过低 (RMS={rms:.6f})"

    # 检查方差：如果方差接近零，可能是单调重复
    variance = float(np.var(wav.astype(np.float64)))
    if variance < 1e-8:
        return False, f"音频方差过低 (var={variance:.2e})，可能为重复退化"

    return True, "OK"


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
    ras_config: RASConfig | None = None,
) -> tuple[tuple | None, str]:
    """VoxCPM2 公共生成模板函数。

    封装了文本分割->逐段推理(含进度追踪+RAS段级重复检测)->音频合并->文件保存->返回结果的通用流程。

    RAS 集成说明:
        参考 Fish Speech 的 RAS (Repetition Aware Sampling) 概念，
        适配为音频段级别检测。在多段生成过程中，对每段输出进行
        质量检查（时长、能量、方差），检测退化/重复模式。
        当检测到退化时，自动调整 cfg_value 并重试该段。

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
        ras_config: RAS 配置，None 时使用默认值。若为 None 且 AdvancedParamsConfig
                    中启用了 RAS，则自动创建默认配置。

    Returns:
        ((sample_rate, wav_data, filename), message) 元组。
    """
    from ...model_registry import registry

    if start_time is None:
        start_time = time.time()

    # RAS 段级重复检测：初始化上下文
    # 若未显式传入 ras_config，从 AdvancedParamsConfig 读取 RAS 启用状态
    _adv = _DEFAULT_ADVANCED
    if ras_config is None and _adv.enable_ras:
        ras_config = RASConfig(
            window_size=50,
            ngram_n=3,
            repetition_threshold=2,
        )
    use_ras = ras_config is not None
    ras_ctx = RASContext(config=ras_config) if use_ras else None
    _RAS_MAX_RETRIES = _adv.ras_max_retries if use_ras else 2

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

    def _generate_segment(seg_text, ref_path, prompt_cache_val, retry_count=0):
        """生成单段音频，带 RAS 重试逻辑。"""
        built_text = _build_text(seg_text)
        kwargs = gen_kwargs_builder(built_text, ref_path, prompt_cache_val)
        wav = registry.voxcpm_model.generate(**kwargs)

        if use_ras and ras_ctx is not None:
            is_valid, reason = _check_segment_quality(wav, sample_rate)
            if not is_valid and retry_count < _RAS_MAX_RETRIES:
                # 退化检测：调整 cfg_value 重试
                original_cfg = kwargs.get("cfg_value", 2.0)
                new_cfg = min(original_cfg + 0.5 * (retry_count + 1), 4.0)
                kwargs["cfg_value"] = new_cfg
                logger.warning(
                    f"[{phase_name}] RAS 段级检测: {reason}，"
                    f"cfg_value {original_cfg:.1f} -> {new_cfg:.1f}，重试 {retry_count + 1}/{_RAS_MAX_RETRIES}"
                )
                return _generate_segment(seg_text, ref_path, prompt_cache_val, retry_count + 1)
            elif not is_valid:
                logger.warning(f"[{phase_name}] RAS: 重试耗尽，接受退化输出: {reason}")

        return wav

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        mode_str = "reference_wav" if ref_audio_path else "默认音色"
        logger.info(f"[{phase_name}] 第 1/1 段，使用 {mode_str} 模式...")
        wav = _generate_segment(segments[0], ref_audio_path, prompt_cache)
        duration_sec = len(wav) / sample_rate if len(wav) > 0 else 0
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"{output_prefix}_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, sample_rate)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        logger.info(f"[{phase_name}] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        msg = message_builder(duration_sec, total) if message_builder else f"生成成功！音频时长 {duration_sec:.1f} 秒。"
        if use_ras and ras_ctx is not None and ras_ctx.is_repetitive():
            logger.info(f"[{phase_name}] RAS 统计: 检测到 {ras_ctx.get_repetition_level()} 级重复")
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

        wav = _generate_segment(seg, ref_audio_path, prompt_cache)
        audio_segments.append(wav)

        # RAS 段级重复检测：用音频段长度变化作为简易重复信号
        if use_ras and ras_ctx is not None and len(audio_segments) >= 2:
            # 用段长度的整数编码模拟 token 级检测
            seg_len = len(wav)
            prev_len = len(audio_segments[-2])
            # 如果两段长度几乎相同（差异 <5%），视为潜在重复
            if prev_len > 0 and abs(seg_len - prev_len) / prev_len < 0.05:
                ras_ctx.feed(idx)  # 用段索引作为 "token" 信号
            else:
                ras_ctx.feed(-idx)  # 不同长度，喂入不同值

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
    if use_ras and ras_ctx is not None and ras_ctx.is_repetitive():
        logger.info(f"[{phase_name}] RAS 统计: 检测到 {ras_ctx.get_repetition_level()} 级段间重复")
    msg = (
        message_builder(duration_sec, total)
        if message_builder
        else f"生成成功！音频时长 {duration_sec:.1f} 秒，分段: {total}。"
    )
    return (sample_rate, merged, filename), msg
