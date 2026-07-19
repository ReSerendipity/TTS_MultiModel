import os

from fastapi import Form, Request

from ....config import MAX_TEXT_LENGTH
from ....model_registry import registry
from ..utils import (
    _check_engine_ready,
    _error_html,
    _execute_generation,
    _parse_bool_form,
    logger,
    router,
)


@router.post("/voxcpm_script", summary="剧本工坊")
async def generate_voxcpm_script(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    lang: str = Form("Auto"),
    cfg: float = Form(2.0),
    norm: str = Form("true"),
    denoise: str = Form("true"),
    steps: int = Form(10),
    seed: int = Form(-1),
    persona_names: str = Form(""),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    model_not_ready = _check_engine_ready(request, "voxcpm2")
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html(request, "文本不能为空")
    if len(text) > MAX_TEXT_LENGTH:
        return _error_html(request, f"文本长度超过限制（最大 {MAX_TEXT_LENGTH} 字符）")

    advanced_norm = _parse_bool_form(norm)
    advanced_denoise = 1.0 if _parse_bool_form(denoise) else 0.0

    persona_map_with_wav = {}
    if persona_names.strip():
        from ....persona_manager import load_persona_embedding

        persona_name_list = [n.strip() for n in persona_names.split(",") if n.strip()]
        for pname in persona_name_list:
            safe_name = os.path.basename(pname)
            persona_data = load_persona_embedding(safe_name)
            if persona_data is not None:
                wav_path, ref_text = persona_data
                if wav_path and os.path.isfile(wav_path):
                    persona_map_with_wav[safe_name] = wav_path
                    logger.info(f"[VoxCPM剧本工坊] 已加载音色 '{safe_name}' 的参考音频")
                else:
                    logger.warning(f"[VoxCPM剧本工坊] 音色 '{safe_name}' 无WAV文件")
            else:
                logger.warning(f"[VoxCPM剧本工坊] 音色 '{safe_name}' 不存在")

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_script(
            text,
            persona_map=persona_map_with_wav if persona_map_with_wav else None,
            advanced_cfg=cfg,
            advanced_norm=advanced_norm,
            advanced_denoise=advanced_denoise,
            advanced_steps=steps,
            advanced_seed=seed,
            lang=lang,
        )

    def _degraded_run():
        engine = registry.get_current_engine()
        degraded_steps = max(steps // 2, 4)
        return engine.generate_script(
            text,
            persona_map=persona_map_with_wav if persona_map_with_wav else None,
            advanced_cfg=cfg,
            advanced_norm=advanced_norm,
            advanced_denoise=0.0,
            advanced_steps=degraded_steps,
            advanced_seed=seed,
            lang=lang,
        )

    return await _execute_generation(
        request,
        text=text,
        run_fn=_run,
        endpoint_name="VoxCPM script",
        voice_or_persona="script",
        model_type="剧本工坊",
        engine="voxcpm2",
        tempo_factor=tempo_factor,
        voice_enhancement=voice_enhancement,
        target_lufs=target_lufs,
        degraded_fn=_degraded_run,
    )
