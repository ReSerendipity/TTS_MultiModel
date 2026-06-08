import asyncio
import html
import os
import time
from datetime import datetime
from urllib.parse import quote

import numpy as np
from fastapi import Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from ....config import MAX_TEXT_LENGTH, SAVE_DIR
from ....model_registry import registry
from ....monitor import get_health_monitor
from ..utils import (
    _check_engine_ready,
    _error_html,
    _log_generation,
    _record_to_history_db,
    _safe_error_msg,
    _success_html,
    _time_estimator,
    _apply_post_processing_to_file,
    logger,
    router,
)


@router.post("/streaming_sse", summary="SSE 流式生成", description="通过 Server-Sent Events 实时推送生成的音频片段")
async def streaming_sse_generation(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    persona_name: str = Form(""),
    lang: str = Form("Auto"),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    denoise: str = Form("true"),
):
    from ....generation import split_text_for_tts
    from ....persona_manager import load_persona_embedding

    model_not_ready = _check_engine_ready("voxcpm2")
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("文本不能为空")
    if len(text) > MAX_TEXT_LENGTH:
        return _error_html(f"文本长度超过限制（最大 {MAX_TEXT_LENGTH} 字符）")

    stream_denoise = denoise.lower() in ("true", "1", "yes")

    _DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}
    if lang in _DIALECT_NAMES:
        instruction = (lang + "，" + instruction) if instruction.strip() else lang

    actual_ref_path = None
    if persona_name:
        safe_name = os.path.basename(persona_name)
        persona_data = load_persona_embedding(safe_name)
        if persona_data is not None:
            wav_path, ref_text = persona_data
            if wav_path and os.path.isfile(wav_path):
                actual_ref_path = wav_path
                logger.info(f"[VoxCPM流式生成] 已加载音色 '{safe_name}' 的参考音频")
            else:
                logger.warning(f"[VoxCPM流式生成] 音色文件不存在: {safe_name}")
        else:
            logger.warning(f"[VoxCPM流式生成] 音色 '{safe_name}' 不存在，将使用默认音色")

    async def audio_chunk_generator():
        try:
            segments = split_text_for_tts(text)
            total = len(segments)

            import json
            meta = json.dumps({"total_segments": total, "sample_rate": 48000, "channels": 1, "bits": 16})
            yield f"event: meta\ndata: {meta}\n\n"

            loop = asyncio.get_running_loop()
            all_chunks = []

            for idx, seg in enumerate(segments):
                seg = seg.strip()
                if not seg:
                    continue

                gen_text = seg
                if instruction and instruction.strip():
                    gen_text = "(" + instruction.strip() + ")" + seg

                progress = json.dumps({"segment": idx + 1, "total": total, "status": "generating"})
                yield f"event: progress\ndata: {progress}\n\n"

                if hasattr(registry.voxcpm_model, 'generate_streaming'):
                    current_gen_text = gen_text

                    def _gen_stream():
                        chunks = []
                        for chunk in registry.voxcpm_model.generate_streaming(
                            text=current_gen_text,
                            reference_wav_path=actual_ref_path if actual_ref_path else None,
                            normalize=True, cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                            denoise=stream_denoise, min_len=2, max_len=4096,
                        ):
                            chunks.append(chunk)
                        return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)

                    wav_data = await loop.run_in_executor(None, _gen_stream)
                else:
                    current_gen_text = gen_text
                    wav_data = await loop.run_in_executor(
                        None,
                        lambda t=current_gen_text: registry.voxcpm_model.generate(
                            text=t,
                            reference_wav_path=actual_ref_path if actual_ref_path else None,
                            normalize=True, cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                            denoise=stream_denoise, min_len=2, max_len=4096,
                        )
                    )

                pcm_data = (wav_data * 32767).astype(np.int16).tobytes()
                all_chunks.append(pcm_data)

                import base64
                b64_data = base64.b64encode(pcm_data).decode('ascii')
                yield f"event: audio\ndata: {b64_data}\n\n"

            if all_chunks:
                combined = np.concatenate([np.frombuffer(c, dtype=np.int16) for c in all_chunks])
                duration_sec = len(combined) / 48000
                timestamp = int(time.time())
                filename = f"streaming_{timestamp}.wav"

                import io
                import wave
                wav_bytes = io.BytesIO()
                with wave.open(wav_bytes, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(48000)
                    wf.writeframes(combined.tobytes())
                output_path = os.path.join(SAVE_DIR, filename)
                with open(output_path, 'wb') as f:
                    f.write(wav_bytes.getvalue())

                done = json.dumps({"status": "done", "filename": filename, "duration": round(duration_sec, 2)})
                yield f"event: done\ndata: {done}\n\n"

        except Exception as e:
            import json
            err = json.dumps({"status": "error", "message": str(e)})
            yield f"event: error\ndata: {err}\n\n"

    return StreamingResponse(
        audio_chunk_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/streaming", summary="流式生成", description="流式语音生成，逐步返回音频数据")
async def streaming_generation(
    request: Request,
    text: str = Form(""),
    ref_audio_path: str = Form(""),
    persona_name: str = Form(""),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    denoise: str = Form("true"),
    seed: int = Form(-1),
):
    model_not_ready = _check_engine_ready("voxcpm2")
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("\u6587\u672c\u4e0d\u80fd\u4e3a\u7a7a")
    if len(text) > MAX_TEXT_LENGTH:
        return _error_html(f"\u6587\u672c\u957f\u5ea6\u8d85\u8fc7\u9650\u5236\uff08\u6700\u5927 {MAX_TEXT_LENGTH} \u5b57\u7b26\uff09")

    stream_denoise = denoise.lower() in ("true", "1", "yes")

    actual_ref_path = ref_audio_path if ref_audio_path else None
    if persona_name:
        from ....persona_manager import load_persona_embedding
        safe_name = os.path.basename(persona_name)

        persona_data = load_persona_embedding(safe_name)
        if persona_data is not None:
            wav_path, ref_text = persona_data
            if wav_path and os.path.isfile(wav_path):
                actual_ref_path = wav_path
                logger.info(f"[VoxCPM流式生成] 已加载音色 '{safe_name}' 的参考音频")
            else:
                return _error_html(f"音色文件不存在: {safe_name}")
        else:
            logger.warning(f"[VoxCPM流式生成] 音色 '{safe_name}' 不存在")

    loop = asyncio.get_running_loop()

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_streaming(text, actual_ref_path,
                                         cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                                         denoise=stream_denoise, seed=seed)

    start_time = time.monotonic()
    try:
        result = await loop.run_in_executor(None, _run)
        duration = time.monotonic() - start_time
        # result is either a numpy array or list of chunks from fn_voxcpm_streaming
        if result is None:
            _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg="生成失败")
            return _error_html("生成失败")

        # Convert to standard format: merge chunks and save
        from ....generation import _save_wav_compatible

        if isinstance(result, list):
            merged = np.concatenate(result) if result else np.array([], dtype=np.float32)
        else:
            merged = result

        sample_rate = 48000
        duration_sec = len(merged) / sample_rate if len(merged) > 0 else 0
        timestamp = int(time.time())
        filename = f"streaming_{timestamp}.wav"
        out_path = os.path.join(SAVE_DIR, filename)
        _save_wav_compatible(merged, out_path, sample_rate)

        _log_generation("Streaming", text, "voxcpm2", "streaming", True, duration)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        audio_path = out_path
        _record_to_history_db(
            filepath=audio_path, text=text, engine="voxcpm2", duration=duration,
            model_type="流式生成", output_format="wav",
            is_success=True,
        )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        return _success_html(filename, f"流式生成完成！耗时 {duration:.1f}秒")
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"Streaming generation failed: {e}")
        _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/streaming_audio", summary="流式音频", description="流式音频生成与播放")
async def streaming_audio_generation(
    request: Request,
    text: str = Form(""),
    persona_name: str = Form(""),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    denoise: str = Form("true"),
):
    from ....persona_manager import load_persona_embedding

    model_not_ready = _check_engine_ready("voxcpm2")
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("\u6587\u672c\u4e0d\u80fd\u4e3a\u7a7a")
    if len(text) > MAX_TEXT_LENGTH:
        return _error_html(f"\u6587\u672c\u957f\u5ea6\u8d85\u8fc7\u9650\u5236\uff08\u6700\u5927 {MAX_TEXT_LENGTH} \u5b57\u7b26\uff09")

    stream_denoise = denoise.lower() in ("true", "1", "yes")

    actual_ref_path = None
    if persona_name:
        safe_name = os.path.basename(persona_name)
        persona_data = load_persona_embedding(safe_name)
        if persona_data is not None:
            wav_path, ref_text = persona_data
            if wav_path and os.path.isfile(wav_path):
                actual_ref_path = wav_path
                logger.info(f"[VoxCPM流式生成] 已加载音色 '{safe_name}' 的参考音频")
            else:
                logger.warning(f"[VoxCPM流式生成] 音色文件不存在: {safe_name}")
        else:
            logger.warning(f"[VoxCPM流式生成] 音色 '{safe_name}' 不存在，将使用默认音色")

    start_time = time.monotonic()
    try:
        loop = asyncio.get_running_loop()
        from ....generation import split_text_for_tts
        segments = split_text_for_tts(text)

        all_audio_data = []

        for _seg_idx, seg in enumerate(segments):
            seg = seg.strip()
            if not seg:
                continue

            wav = await loop.run_in_executor(
                None,
                lambda s=seg: registry.voxcpm_model.generate(
                    text=s,
                    reference_wav_path=actual_ref_path if actual_ref_path else None,
                    normalize=True,
                    cfg_value=cfg_value,
                    inference_timesteps=inference_timesteps,
                    denoise=stream_denoise,
                    min_len=2,
                    max_len=4096,
                )
            )

            if hasattr(wav, 'numpy'):
                wav_data = (wav.numpy() * 32767).astype(np.int16)
            else:
                wav_data = (wav * 32767).astype(np.int16)

            all_audio_data.append(wav_data)

        if all_audio_data:
            combined_audio = np.concatenate(all_audio_data)
        else:
            return _error_html("\u672a\u751f\u6210\u4efb\u4f55\u97f3\u9891\u6570\u636e")

        import io
        import wave
        wav_bytes = io.BytesIO()
        with wave.open(wav_bytes, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(combined_audio.tobytes())

        wav_bytes.seek(0)
        audio_data = wav_bytes.read()

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"streaming_{timestamp}.wav"
        output_path = os.path.join(SAVE_DIR, filename)
        with open(output_path, 'wb') as f:
            f.write(audio_data)

        duration = time.monotonic() - start_time
        _log_generation("Streaming", text, "voxcpm2", "streaming", True, duration)

        safe_filename = quote(filename)
        safe_display = html.escape(filename)
        return HTMLResponse(f'''<div class="tts-success-block">流式生成完成！音频已开始播放 ({safe_display})</div>
<audio class="tts-audio-player" autoplay controls style="width:100%;margin-top:12px;">
    <source src="/output/{safe_filename}" type="audio/wav">
</audio>
<script>
(function(){{
    var audio = document.querySelector('.tts-audio-player');
    if (audio) {{
        audio.play().catch(function(e) {{
            console.log('Auto-play prevented:', e);
        }});
    }}
}})();
</script>''')

    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"Streaming audio generation failed: {e}")
        _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/post-process", summary="后处理", description="对已生成的音频进行后处理（变速、响度标准化、人声增强）")
async def post_process_audio(
    request: Request,
    audio_path: str = Form(""),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    if not audio_path.strip():
        return _error_html("audio_path is required")

    safe_name = os.path.basename(audio_path)
    if safe_name != audio_path:
        return _error_html("Invalid audio path")

    full_path = os.path.join(SAVE_DIR, safe_name)
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(os.path.realpath(SAVE_DIR)):
        return _error_html("Invalid audio path")

    if not os.path.isfile(real_path):
        return _error_html("Audio file not found")

    pp_voice_enhancement = voice_enhancement.lower() in ("true", "1", "yes")
    new_filename = _apply_post_processing_to_file(safe_name, tempo_factor, pp_voice_enhancement, target_lufs)

    if new_filename == safe_name and tempo_factor == 1.0 and not pp_voice_enhancement and target_lufs == -16.0:
        return _error_html("No post-processing changes requested")

    safe_new = quote(new_filename, safe='')
    return HTMLResponse(
        f'<div data-audio-filename="{html.escape(new_filename)}">'
        f'<audio controls src="/api/audio/{safe_new}" style="width:100%;margin:8px 0;"></audio>'
        f'<div class="status-message success">Post-processing applied</div>'
        f'</div>'
    )


@router.post("/cancel", summary="取消生成", description="取消正在进行的语音生成任务")
async def cancel_generation(request: Request):
    from ....model_manager import _progress_mgr, registry

    current_eng = registry.current_engine
    was_generating = not _progress_mgr._is_complete and _progress_mgr._phase != ""
    _progress_mgr.cancel()
    logger.info(f"[Cancel] Generation cancel requested (engine: {current_eng}, was generating: {was_generating})")
    return {"status": "ok", "message": "\u5df2\u53d1\u9001\u53d6\u6d88\u8bf7\u6c42"}
