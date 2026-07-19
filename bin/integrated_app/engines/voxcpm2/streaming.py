import time

from ._base import (
    GenerationError,
    _advanced_kwargs,
    _progress_mgr,
    logger,
    split_text_for_tts,
)
from .decorators import with_generation_context


@with_generation_context(phase_name="VoxCPM流式生成")
def fn_voxcpm_streaming(
    text: str,
    ref_audio_path: str | None = None,
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
    denoise: bool = True,
    seed: int = -1,
):
    from ...model_registry import registry

    start_time = time.time()

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    _progress_mgr.start(total_segments=total, phase="VoxCPM2 流式推理中...")

    if total == 1:
        _progress_mgr.advance_segment("流式推理生成中...")
        logger.info(f"[VoxCPM流式生成] 第 1/1 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")

        if hasattr(registry.voxcpm_model, "generate_streaming"):
            return registry.voxcpm_model.generate_streaming(
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
            wav = registry.voxcpm_model.generate(
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

        _progress_mgr.advance_segment(f"第 {idx + 1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM流式生成] 第 {idx + 1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM流式生成] 第 {idx + 1}/{total} 段...")

        if hasattr(registry.voxcpm_model, "generate_streaming"):
            for chunk in registry.voxcpm_model.generate_streaming(
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
            wav = registry.voxcpm_model.generate(
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
