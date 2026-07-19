import os
import time

from fastapi import File, Form, Request, UploadFile

from ....config import MAX_TEXT_LENGTH
from ....model_registry import registry
from ....monitor import get_health_monitor
from ..utils import (
    _apply_post_processing_to_file,
    _error_html,
    _execute_generation,
    _log_generation,
    _merge_dialect,
    _parse_bool_form,
    _partial_success_html,
    _record_to_history_db,
    _run_with_oom_retry,
    _safe_error_msg,
    _success_html,
    _time_estimator,
    logger,
    pre_validate,
    resolve_persona_ref,
    router,
    save_uploaded_audio,
)


@router.post("/voxcpm_clone", summary="可控克隆", description="使用 VoxCPM2 引擎进行可控声音克隆，上传参考音频")
async def generate_voxcpm_clone(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    ref_audio_path: str = Form(""),
    persona_name: str = Form(""),
    cfg: float = Form(2.0),
    norm: str = Form("true"),
    denoise: str = Form("true"),
    steps: int = Form(10),
    ref_audio_upload: UploadFile | None = File(None),
    lang: str = Form("Auto"),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    err = pre_validate(request, "voxcpm2", text, MAX_TEXT_LENGTH)
    if err:
        return err

    instruction = _merge_dialect(instruction, lang)

    actual_ref_path = ref_audio_path if ref_audio_path else None

    upload_path, err = await save_uploaded_audio(request, ref_audio_upload)
    if err:
        return err
    if upload_path:
        actual_ref_path = upload_path

    if not actual_ref_path and persona_name:
        ref_path, err = await resolve_persona_ref(request, persona_name)
        if err:
            return err
        if ref_path:
            actual_ref_path = ref_path
            logger.info(f"[VoxCPM克隆] 已加载音色 '{os.path.basename(persona_name)}' 的参考音频")

    clone_norm = _parse_bool_form(norm)
    clone_denoise = _parse_bool_form(denoise)

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_voice_clone(
            text=text,
            reference_audio_path=actual_ref_path,
            instruction=instruction,
            cfg_value=cfg,
            inference_timesteps=steps,
            denoise=clone_denoise,
            normalize=clone_norm,
        )

    def _degraded_run():
        engine = registry.get_current_engine()
        degraded_steps = max(steps // 2, 4)
        return engine.generate_voice_clone(
            text=text,
            reference_audio_path=actual_ref_path,
            instruction=instruction,
            cfg_value=cfg,
            inference_timesteps=degraded_steps,
            denoise=False,
            normalize=clone_norm,
        )

    return await _execute_generation(
        request,
        text=text,
        run_fn=_run,
        endpoint_name="VoxCPM clone",
        voice_or_persona=instruction[:50],
        model_type="可控克隆",
        engine="voxcpm2",
        tempo_factor=tempo_factor,
        voice_enhancement=voice_enhancement,
        target_lufs=target_lufs,
        degraded_fn=_degraded_run,
    )


@router.post("/voxcpm_ultimate", summary="极致克隆", description="使用 VoxCPM2 引擎进行极致声音克隆，支持多参考音频")
async def generate_voxcpm_ultimate(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    ref_audio_path: str = Form(""),
    persona_name: str = Form(""),
    cfg: float = Form(2.0),
    norm: str = Form("true"),
    denoise: str = Form("true"),
    steps: int = Form(10),
    seed: int = Form(-1),
    lang: str = Form("Auto"),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    err = pre_validate(request, "voxcpm2", text, MAX_TEXT_LENGTH)
    if err:
        return err

    instruction = _merge_dialect(instruction, lang)

    actual_ref_path = ref_audio_path if ref_audio_path else None

    if not actual_ref_path and persona_name:
        ref_path, err = await resolve_persona_ref(request, persona_name)
        if err:
            return err
        if ref_path:
            actual_ref_path = ref_path
            logger.info(f"[VoxCPM极致克隆] 已加载音色 '{os.path.basename(persona_name)}' 的参考音频")

    advanced_norm = _parse_bool_form(norm)
    advanced_denoise = 1.0 if _parse_bool_form(denoise) else 0.0

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_ultimate_clone(
            text,
            instruction,
            actual_ref_path if actual_ref_path else None,
            advanced_cfg=cfg,
            advanced_norm=advanced_norm,
            advanced_denoise=advanced_denoise,
            advanced_steps=steps,
            advanced_seed=seed,
        )

    def _degraded_run():
        engine = registry.get_current_engine()
        degraded_steps = max(steps // 2, 4)
        return engine.generate_ultimate_clone(
            text,
            instruction,
            actual_ref_path if actual_ref_path else None,
            advanced_cfg=cfg,
            advanced_norm=advanced_norm,
            advanced_denoise=0.0,
            advanced_steps=degraded_steps,
            advanced_seed=seed,
        )

    return await _execute_generation(
        request,
        text=text,
        run_fn=_run,
        endpoint_name="VoxCPM ultimate clone",
        voice_or_persona=instruction[:50],
        model_type="极致克隆",
        engine="voxcpm2",
        tempo_factor=tempo_factor,
        voice_enhancement=voice_enhancement,
        target_lufs=target_lufs,
        degraded_fn=_degraded_run,
    )


@router.post("/voxcpm_prompt_continue", summary="Prompt 延续", description="使用 VoxCPM2 引擎基于 Prompt 音频延续生成")
async def generate_voxcpm_prompt_continue(
    request: Request,
    text: str = Form(""),
    prompt_wav: UploadFile | None = File(None),
    prompt_text: str = Form(""),
    lang: str = Form("Auto"),
    tempo_factor: float = Form(1.0),
    voice_enhancement: bool = Form(False),
    target_lufs: float | None = Form(None),
):
    err = pre_validate(request, "voxcpm2", text, MAX_TEXT_LENGTH)
    if err:
        return err
    if not prompt_text.strip():
        return _error_html(request, "引导文本不能为空")

    prompt_wav_path, err = await save_uploaded_audio(request, prompt_wav)
    if err:
        return err

    if not prompt_wav_path:
        return _error_html(request, "请上传引导音频文件")

    import asyncio

    loop = asyncio.get_running_loop()

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_with_prompt(text, prompt_wav_path, prompt_text)

    start_time = time.monotonic()
    try:
        result, msg, degraded_note = await loop.run_in_executor(
            None, lambda: _run_with_oom_retry(_run, "VoxCPM prompt continue", degraded_fn=_run)
        )
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation("VoxCPM prompt continue", text, "voxcpm2", prompt_text[:50], False, duration, error_msg=msg)
            return _error_html(request, msg)
        is_degraded = degraded_note is not None
        _log_generation(
            "VoxCPM prompt continue", text, "voxcpm2", prompt_text[:50], True, duration, is_degraded=is_degraded
        )
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        from ....config import SAVE_DIR

        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            await asyncio.to_thread(
                _record_to_history_db,
                filepath=audio_path,
                text=text,
                engine="voxcpm2",
                duration=duration,
                model_type="Prompt延续",
                output_format="wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        pp_target_lufs = target_lufs if target_lufs is not None else -16.0
        filename = await asyncio.to_thread(
            _apply_post_processing_to_file, filename, tempo_factor, voice_enhancement, pp_target_lufs
        )
        if degraded_note:
            return _partial_success_html(filename, msg, degraded_note)
        return _success_html(filename, msg)
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"VoxCPM Prompt 延续生成失败: {e}")
        _log_generation("VoxCPM prompt continue", text, "voxcpm2", prompt_text[:50], False, duration, error_msg=str(e))
        return _error_html(request, _safe_error_msg(e))
