import os
import time

import numpy as np

from ._base import (
    EngineSwitchError,
    GenerationError,
    SAVE_DIR,
    _advanced_kwargs,
    _gen_tracker,
    _progress_mgr,
    _save_wav_compatible,
    logger,
    split_text_for_tts,
    tts_error_handler,
)


def fn_voxcpm_clone(text: str, instruction: str, ref_audio_path: str | None,
                    cfg_value: float = 2.0, inference_timesteps: int = 10,
                    denoise: bool = True, normalize: bool = True) -> tuple[tuple | None, str]:
    from ...model_manager import _check_voxcpm2_lock
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, instruction, ref_audio_path, cfg_value, inference_timesteps, denoise, normalize):
        if not _check_voxcpm2_lock():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_clone_impl(text, instruction, ref_audio_path, start_time,
                                         cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                                         denoise=denoise, normalize=normalize)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM可控克隆] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, instruction, ref_audio_path, cfg_value, inference_timesteps, denoise, normalize)


def _fn_voxcpm_clone_impl(text: str, instruction: str, ref_audio_path: str | None, start_time: float = 0,
                           cfg_value: float = 2.0, inference_timesteps: int = 10,
                           denoise: bool = True, normalize: bool = True) -> tuple[tuple | None, str]:
    from ...model_manager import voxcpm_model as _voxcpm_model
    from ...prompt_cache import load_cached_prompt

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    if ref_audio_path:
        logger.info(f"[VoxCPM可控克隆] 使用参考音频: {ref_audio_path}")
        if not os.path.isfile(ref_audio_path):
            raise GenerationError(f"参考音频文件不存在: {ref_audio_path}")

    _progress_mgr.update_phase("加载音色缓存...")
    cached_prompt = None
    if ref_audio_path:
        cached_prompt = load_cached_prompt(ref_audio_path)
        if cached_prompt is not None:
            logger.info("[VoxCPM可控克隆] 使用缓存的音色特征，跳过重复编码")

    _progress_mgr.start(total_segments=total, phase="VoxCPM2 推理中...")

    def _build_text(seg_text):
        if instruction and instruction.strip():
            return "(" + instruction.strip() + ")" + seg_text
        return seg_text

    def _gen_kwargs(seg_text, ref_path=None, prompt_cache=None):
        kwargs = dict(
            text=seg_text,
            normalize=normalize,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
            denoise=denoise,
            min_len=2,
            **_advanced_kwargs(),
        )
        if prompt_cache is not None:
            kwargs["prompt_cache"] = prompt_cache
        elif ref_path:
            kwargs["reference_wav_path"] = ref_path
        return kwargs

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        logger.info(f"[VoxCPM可控克隆] 第 1/1 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")
        wav = _voxcpm_model.generate(**_gen_kwargs(_build_text(segments[0]), ref_audio_path, cached_prompt))
        duration_sec = len(wav) / 48000 if len(wav) > 0 else 0
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_clone_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        logger.info(f"[VoxCPM可控克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        return (48000, wav, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒。"

    audio_segments = []
    for idx, seg in enumerate(segments):
        if _progress_mgr.should_stop():
            logger.info("[VoxCPM克隆] 生成已被用户取消")
            raise GenerationError("生成已取消")
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM可控克隆] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM可控克隆] 第 1/{total} 段...")

        wav = _voxcpm_model.generate(**_gen_kwargs(_build_text(seg), ref_audio_path, cached_prompt))
        audio_segments.append(wav)

    if not audio_segments:
        raise GenerationError("VoxCPM2 可控克隆生成失败：无有效音频段")

    merged = np.concatenate(audio_segments)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_clone_{timestamp}.wav")
    _save_wav_compatible(merged, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(merged) / 48000
    logger.info(f"[VoxCPM可控克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，分段: {total}")
    return (48000, merged, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒，分段: {total}。"
