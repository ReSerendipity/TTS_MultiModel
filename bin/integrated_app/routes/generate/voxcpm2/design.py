import os

from fastapi import Form, Request

from ....config import MAX_TEXT_LENGTH
from ....model_registry import registry
from ..utils import (
    _check_engine_ready,
    _error_html,
    _execute_generation,
    _merge_dialect,
    _parse_bool_form,
    logger,
    router,
)


@router.post("/voxcpm_design", summary="声音设计")
async def generate_voxcpm_design(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    persona_name: str = Form(""),
    lang: str = Form("Auto"),
    cfg: float = Form(2.0),
    steps: int = Form(10),
    denoise: str = Form("true"),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    model_not_ready = _check_engine_ready("voxcpm2")
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("文本不能为空")
    if len(text) > MAX_TEXT_LENGTH:
        return _error_html(f"文本长度超过限制（最大 {MAX_TEXT_LENGTH} 字符）")

    instruction = _merge_dialect(instruction, lang)
    advanced_denoise = _parse_bool_form(denoise)

    actual_ref_path = None
    if persona_name:
        from ....persona_manager import load_persona_embedding
        safe_name = os.path.basename(persona_name)
        persona_data = load_persona_embedding(safe_name)
        if persona_data is not None:
            wav_path, ref_text = persona_data
            if wav_path and os.path.isfile(wav_path):
                actual_ref_path = wav_path
                logger.info(f"[VoxCPM声音设计] 已加载音色 '{safe_name}' 的参考音频")
            else:
                return _error_html(f"音色文件不存在: {safe_name}")
        else:
            logger.warning(f"[VoxCPM声音设计] 音色 '{safe_name}' 不存在，将使用默认音色")

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_voice_design(text, instruction, cfg_value=cfg, inference_timesteps=steps,
                                            denoise=advanced_denoise, ref_audio_path=actual_ref_path)

    return await _execute_generation(
        text=text,
        run_fn=_run,
        endpoint_name="VoxCPM design",
        voice_or_persona=instruction[:50],
        model_type="声音设计",
        engine="voxcpm2",
        tempo_factor=tempo_factor,
        voice_enhancement=voice_enhancement,
        target_lufs=target_lufs,
    )
