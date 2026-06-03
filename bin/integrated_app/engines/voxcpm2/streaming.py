import time

import numpy as np

from ._base import (
    EngineSwitchError,
    GenerationError,
    _advanced_kwargs,
    _gen_tracker,
    _progress_mgr,
    _save_wav_compatible,
    logger,
    split_text_for_tts,
    tts_error_handler,
)


def fn_voxcpm_streaming(text: str, ref_audio_path: str | None = None,
                        cfg_value: float = 2.0, inference_timesteps: int = 10,
                        denoise: bool = True, seed: int = -1):
    from ...model_manager import _check_voxcpm2_lock
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, ref_audio_path, cfg_value, inference_timesteps, denoise, seed):
        if not _check_voxcpm2_lock():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="流式准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_streaming_impl(text, ref_audio_path, start_time,
                                              cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                                              denoise=denoise, seed=seed)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM流式生成] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, ref_audio_path, cfg_value, inference_timesteps, denoise, seed)


def _fn_voxcpm_streaming_impl(text: str, ref_audio_path: str | None, start_time: float = 0,
                               cfg_value: float = 2.0, inference_timesteps: int = 10,
                               denoise: bool = True, seed: int = -1):
    from ...model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    _progress_mgr.start(total_segments=total, phase="VoxCPM2 流式推理中...")

    if total == 1:
        _progress_mgr.advance_segment("流式推理生成中...")
        logger.info(f"[VoxCPM流式生成] 第 1/1 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")

        if hasattr(_voxcpm_model, 'generate_streaming'):
            return _voxcpm_model.generate_streaming(
                text=segments[0],
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                **_advanced_kwargs(),
            )
        else:
            logger.warning("[VoxCPM流式生成] 模型不支持 streaming，回退到常规生成")
            wav = _voxcpm_model.generate(
                text=segments[0],
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                **_advanced_kwargs(),
            )
            _progress_mgr.complete()
            return wav

    all_chunks = []
    for idx, seg in enumerate(segments):
        if _progress_mgr.should_stop():
            logger.info("[VoxCPM流式] 生成已被用户取消")
            raise GenerationError("生成已取消")
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM流式生成] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM流式生成] 第 {idx+1}/{total} 段...")

        if hasattr(_voxcpm_model, 'generate_streaming'):
            for chunk in _voxcpm_model.generate_streaming(
                text=seg,
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                **_advanced_kwargs(),
            ):
                all_chunks.append(chunk)
        else:
            wav = _voxcpm_model.generate(
                text=seg,
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                **_advanced_kwargs(),
            )
            all_chunks.append(wav)

    _progress_mgr.complete()
    return all_chunks
