import os
import time

from ._base import (
    GenerationError,
    _advanced_kwargs,
    _progress_mgr,
    generate_with_template,
    logger,
)
from .decorators import with_generation_context


@with_generation_context(phase_name="VoxCPM可控克隆")
def fn_voxcpm_clone(
    text: str,
    instruction: str,
    ref_audio_path: str | None,
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
    denoise: bool = True,
    normalize: bool = True,
) -> tuple[tuple | None, str]:
    from ...prompt_cache import load_cached_prompt

    start_time = time.time()

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

    def gen_kwargs_builder(seg_text, ref_path, prompt_cache):
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

    return generate_with_template(
        text=text,
        instruction=instruction,
        gen_kwargs_builder=gen_kwargs_builder,
        output_prefix="voxcpm_clone",
        phase_name="VoxCPM可控克隆",
        ref_audio_path=ref_audio_path,
        prompt_cache=cached_prompt,
        start_time=start_time,
    )
