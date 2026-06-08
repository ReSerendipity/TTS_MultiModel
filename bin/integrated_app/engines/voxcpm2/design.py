import time

from ._base import (
    EngineSwitchError,
    GenerationError,
    _advanced_kwargs,
    _gen_tracker,
    _progress_mgr,
    generate_with_template,
    logger,
    tts_error_handler,
)


def fn_voxcpm_design(text: str, instruction: str,
                     cfg_value: float = 2.0, inference_timesteps: int = 10,
                     denoise: bool = True,
                     ref_audio_path: str | None = None) -> tuple[tuple | None, str]:
    from ...model_manager import _check_voxcpm2_lock
    from ...model_registry import registry
    if registry.voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, instruction, cfg_value, inference_timesteps, denoise, ref_audio_path):
        if not _check_voxcpm2_lock():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="准备中...")
        start_time = time.time()
        try:
            def gen_kwargs_builder(seg_text, ref_path, prompt_cache):
                kwargs = dict(
                    text=seg_text,
                    normalize=True,
                    cfg_value=cfg_value,
                    inference_timesteps=inference_timesteps,
                    denoise=denoise,
                    min_len=2,
                    **_advanced_kwargs(),
                )
                if ref_path:
                    kwargs["reference_wav_path"] = ref_path
                return kwargs

            return generate_with_template(
                text=text,
                instruction=instruction,
                gen_kwargs_builder=gen_kwargs_builder,
                output_prefix="voxcpm_design",
                phase_name="VoxCPM声音设计",
                ref_audio_path=ref_audio_path,
                start_time=start_time,
            )
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM声音设计] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, instruction, cfg_value, inference_timesteps, denoise, ref_audio_path)
