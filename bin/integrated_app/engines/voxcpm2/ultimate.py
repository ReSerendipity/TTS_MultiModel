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


def fn_voxcpm_ultimate_clone(
    text: str, instruction: str, ref_audio_path: str | None,
    advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int,
) -> tuple[tuple | None, str]:
    from ...model_manager import _check_voxcpm2_lock
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, instruction, ref_audio_path, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed):
        if not _check_voxcpm2_lock():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        start_time = time.time()
        try:
            return _fn_voxcpm_ultimate_clone_impl(
                text, instruction, ref_audio_path,
                advanced_cfg, advanced_norm, advanced_denoise,
                advanced_steps, advanced_seed, start_time,
            )
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM极致克隆] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, instruction, ref_audio_path, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed)


def _fn_voxcpm_ultimate_clone_impl(
    text: str, instruction: str, ref_audio_path: str | None,
    advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int, start_time: float = 0,
) -> tuple[tuple | None, str]:
    import tempfile

    from ...model_manager import voxcpm_asr as _voxcpm_asr
    from ...model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.start(total_segments=1, phase="ASR 识别参考音频...")

    processed_ref_path_for_asr = ref_audio_path
    if ref_audio_path and hasattr(_voxcpm_model, 'denoiser') and _voxcpm_model.denoiser:
        _progress_mgr.update_phase("参考音频降噪...")
        try:
            with tempfile.NamedTemporaryFile(suffix="_denoised.wav", delete=False) as tmp:
                processed_ref_path_for_asr = tmp.name
            _voxcpm_model.denoiser.enhance(ref_audio_path, processed_ref_path_for_asr, normalize_loudness=True)
            logger.info(f"[VoxCPM极致克隆] ZipEnhancer降噪完成: {ref_audio_path} -> {processed_ref_path_for_asr}")
        except Exception as e:
            logger.warning(f"[VoxCPM极致克隆] ZipEnhancer降噪失败，使用原始音频: {e}")
            processed_ref_path_for_asr = ref_audio_path

    ref_text = ""
    if processed_ref_path_for_asr:
        try:
            res = _voxcpm_asr.generate(input=processed_ref_path_for_asr)
            if res and len(res) > 0 and "text" in res[0]:
                ref_text = res[0]["text"]
                logger.info(f"[VoxCPM极致克隆] ASR 识别成功: {ref_text[:50]}...")
        except Exception as e:
            logger.warning(f"[VoxCPM极致克隆] ASR 识别失败: {e}")
            ref_text = ""
        finally:
            if processed_ref_path_for_asr != ref_audio_path and os.path.isfile(processed_ref_path_for_asr):
                import contextlib
                with contextlib.suppress(Exception):
                    os.remove(processed_ref_path_for_asr)

    _progress_mgr.update_phase("准备极致克隆推理...")

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)
    _progress_mgr.start(total_segments=total, phase="VoxCPM2 极致推理中...")

    def _build_text(seg_text):
        if instruction and instruction.strip():
            return "(" + instruction.strip() + ")" + seg_text
        return seg_text

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        logger.info("[VoxCPM极致克隆] 第 1/1 段...")
        wav = _voxcpm_model.generate(
            text=_build_text(segments[0]),
            prompt_wav_path=ref_audio_path if ref_audio_path else "",
            prompt_text=ref_text if ref_text else "",
            normalize=bool(advanced_norm),
            cfg_value=advanced_cfg,
            inference_timesteps=advanced_steps,
            denoise=bool(advanced_denoise),
            min_len=2,
            **_advanced_kwargs(),
        )
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_ultimate_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        duration_sec = len(wav) / 48000
        logger.info(f"[VoxCPM极致克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        return (48000, wav, filename), f"生成成功！参考文本: {ref_text[:50]}..." if ref_text else "生成成功！"

    audio_segments = []
    for idx, seg in enumerate(segments):
        if _progress_mgr.should_stop():
            logger.info("[VoxCPM极致克隆] 生成已被用户取消")
            raise GenerationError("生成已取消")
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM极致克隆] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM极致克隆] 第 1/{total} 段...")

        wav = _voxcpm_model.generate(
            text=_build_text(seg),
            prompt_wav_path=ref_audio_path if ref_audio_path else "",
            prompt_text=ref_text if ref_text else "",
            normalize=bool(advanced_norm),
            cfg_value=advanced_cfg,
            inference_timesteps=advanced_steps,
            denoise=bool(advanced_denoise),
            min_len=2,
            **_advanced_kwargs(),
        )
        audio_segments.append(wav)

    if not audio_segments:
        raise GenerationError("VoxCPM2 极致克隆生成失败：无有效音频段")

    merged = np.concatenate(audio_segments)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_ultimate_{timestamp}.wav")
    _save_wav_compatible(merged, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(merged) / 48000
    logger.info(f"[VoxCPM极致克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，分段: {total}")
    return (48000, merged, filename), f"生成成功！参考文本: {ref_text[:50]}..." if ref_text else "生成成功！"
