import os
import time

from ._base import (
    EngineSwitchError,
    GenerationError,
    SAVE_DIR,
    _advanced_kwargs,
    _gen_tracker,
    _progress_mgr,
    _save_wav_compatible,
    logger,
    tts_error_handler,
)


def fn_voxcpm_prompt_continue(text: str, prompt_wav_path: str, prompt_text: str) -> tuple[tuple | None, str]:
    from ...model_manager import _check_voxcpm2_lock
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, prompt_wav_path, prompt_text):
        if not _check_voxcpm2_lock():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="Prompt 延续准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_prompt_continue_impl(text, prompt_wav_path, prompt_text, start_time)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM Prompt延续] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, prompt_wav_path, prompt_text)


def _fn_voxcpm_prompt_continue_impl(text: str, prompt_wav_path: str, prompt_text: str, start_time: float = 0) -> tuple[tuple | None, str]:
    from ...model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.update_phase("Prompt 延续推理中...")
    logger.info(f"[VoxCPM Prompt延续] Prompt: {prompt_text[:50]}...")

    wav = _voxcpm_model.generate(
        text=text,
        prompt_wav_path=prompt_wav_path,
        prompt_text=prompt_text,
        normalize=True,
        cfg_value=2.0,
        inference_timesteps=10,
        denoise=True,
        min_len=2,
        **_advanced_kwargs(),
    )

    duration_sec = len(wav) / 48000 if len(wav) > 0 else 0
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_prompt_continue_{timestamp}.wav")
    _save_wav_compatible(wav, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()
    logger.info(f"[VoxCPM Prompt延续] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
    return (48000, wav, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒。"
