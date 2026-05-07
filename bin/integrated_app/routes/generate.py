import os
import time
import asyncio
import html
import logging
import numpy as np
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from typing import Optional

from ..engines.voxcpm2_engine import (
    fn_voxcpm_design,
    fn_voxcpm_clone,
    fn_voxcpm_ultimate_clone,
    fn_voxcpm_script_studio,
    fn_voxcpm_streaming,
)
from ..exceptions import TTSError
from .system import log_operation, increment_generation
from ..gpu_utils import is_oom_error, free_gpu_memory
from ..model_manager import _time_estimator, voxcpm_model as _voxcpm_model
from ..config import SAVE_DIR
from ..audio_processing import enhance_audio
from ..monitor import get_health_monitor
from ..history_db import create_history_db

_history_db = None


def _get_history_db():
    global _history_db
    if _history_db is None:
        _history_db = create_history_db(SAVE_DIR)
    return _history_db


def _check_model_ready():
    """Check if VoxCPM2 model is loaded. Returns error HTMLResponse if not ready."""
    from ..model_manager import voxcpm_model
    if voxcpm_model is None:
        return _error_html("模型正在加载，请稍后再试...")
    return None


router = APIRouter(prefix="/api/generate", tags=["generate"])

logger = logging.getLogger("tts_multimodel")

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac"}


def _record_to_history_db(filepath: str, text: str, engine: str, duration: float,
                          model_type: str = None, model_size: str = None,
                          persona_name: str = None, output_format: str = "wav",
                          is_success: bool = True, error_msg: str = None):
    """Record a generation to the SQLite history database."""
    try:
        db = _get_history_db()
        filename = os.path.basename(filepath) if filepath else ""
        file_size = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0
        db.insert({
            "filename": filename,
            "filepath": filepath or "",
            "created_at": datetime.now().isoformat(),
            "file_size_bytes": file_size,
            "duration_seconds": round(duration, 2),
            "text_preview": text[:100] if text else "",
            "engine": engine,
            "model_type": model_type,
            "model_size": model_size,
            "persona_name": persona_name,
            "output_format": output_format,
            "is_success": is_success,
            "error_msg": error_msg,
        })
    except Exception as e:
        logger.debug(f"History DB recording failed: {e}")


# --- Generation retry counter ---
_generation_retry_counter = {"total": 0, "oom_retries": 0}


def _safe_error_msg(e):
    """Return user-friendly error message, hiding internal details for non-TTS errors."""
    if isinstance(e, TTSError):
        return str(e)
    return "生成失败，请稍后重试"


def _partial_success_html(filename, message, degraded_note):
    """Return HTML for partially successful generation with degradation note."""
    safe_filename = quote(filename, safe='')
    return HTMLResponse(
        f'<audio controls src="/api/audio/{safe_filename}" style="width:100%;margin:8px 0;"></audio>'
        f'<div class="status-message success">{html.escape(message)}</div>'
        f'<div class="status-message warning" style="margin-top:8px;color:#f59e0b;">{html.escape(degraded_note)}</div>'
    )


def _log_generation(endpoint_name, text, engine, voice_or_persona, success, duration,
                     is_degraded=False, error_msg=None):
    """Log a generation operation to the system log."""
    if success:
        increment_generation(success=True)
        details = {
            "endpoint": endpoint_name,
            "engine": engine,
            "voice_persona": voice_or_persona,
            "text_length": len(text),
            "duration": round(duration, 2),
        }
        if is_degraded:
            details["degraded"] = True
        log_operation("generation", f"{endpoint_name} success ({duration:.1f}s)", details)
    else:
        increment_generation(success=False)
        details = {
            "endpoint": endpoint_name,
            "engine": engine,
            "voice_persona": voice_or_persona,
            "text_length": len(text),
            "duration": round(duration, 2),
        }
        if error_msg:
            details["error"] = str(error_msg)
        log_operation("generation", f"{endpoint_name} failed ({duration:.1f}s)", details)


def _error_html(error_message):
    return HTMLResponse(
        f'<div class="tts-error-block">'
        f'<div class="error-title">\u751f\u6210\u5931\u8d25</div>'
        f'<div class="error-message">{html.escape(error_message)}</div>'
        f'</div>'
    )


def _success_html(filename, status_message):
    safe_filename = quote(filename, safe='')
    return HTMLResponse(
        f'<audio controls src="/api/audio/{safe_filename}" style="width:100%;margin:8px 0;"></audio>'
        f'<div class="status-message success">{html.escape(status_message)}</div>'
    )


def _run_with_oom_retry(run_fn, endpoint_name, degraded_fn=None):
    """Run a generation function with one OOM retry attempt.

    Returns (result, msg, degraded_note) where degraded_note is None on success.
    On OOM retry success, degraded_note explains the quality reduction.
    On final failure, result is None and msg contains the error.
    """
    _generation_retry_counter["total"] += 1
    degraded_note = None

    try:
        result, msg = run_fn()
        return result, msg, degraded_note
    except Exception as e:
        if not is_oom_error(e):
            logger.error(f"{endpoint_name} failed (non-OOM): {e}")
            raise

        logger.warning(
            f"{endpoint_name} hit OOM on first attempt: {e}. "
            f"Retrying with degraded quality parameters..."
        )
        _generation_retry_counter["oom_retries"] += 1
        free_gpu_memory()

        if degraded_fn:
            try:
                degraded_note = "\u7531\u4e8e\u663e\u5b58\u9650\u5236\uff0c\u5df2\u81ea\u52a8\u964d\u4f4e\u751f\u6210\u8d28\u91cf\u53c2\u6570\u4ee5\u5b8c\u6210\u751f\u6210\u3002"
                result, msg = degraded_fn()
                return result, msg, degraded_note
            except Exception as e2:
                logger.error(f"{endpoint_name} failed after OOM retry (degraded): {e2}")
                raise
        else:
            try:
                degraded_note = "\u7531\u4e8e\u663e\u5b58\u9650\u5236\uff0c\u5df2\u81ea\u52a8\u964d\u4f4e\u751f\u6210\u8d28\u91cf\u53c2\u6570\u4ee5\u5b8c\u6210\u751f\u6210\u3002"
                result, msg = run_fn()
                return result, msg, degraded_note
            except Exception as e2:
                logger.error(f"{endpoint_name} failed after OOM retry: {e2}")
                raise


@router.post("/voxcpm_design")
async def generate_voxcpm_design(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    lang: str = Form("Auto"),
):
    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("文本不能为空")

    # Merge dialect/language into instruction
    _DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}
    if lang in _DIALECT_NAMES:
        instruction = (lang + "，" + instruction) if instruction.strip() else lang

    loop = asyncio.get_running_loop()

    def _run():
        return fn_voxcpm_design(text, instruction)

    start_time = time.monotonic()
    try:
        result, msg, degraded_note = await loop.run_in_executor(
            None, lambda: _run_with_oom_retry(_run, "VoxCPM design")
        )
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation("VoxCPM design", text, "voxcpm2", instruction[:50], False, duration, error_msg=msg)
            return _error_html(msg)
        is_degraded = degraded_note is not None
        _log_generation("VoxCPM design", text, "voxcpm2", instruction[:50], True, duration, is_degraded=is_degraded)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        from ..config import SAVE_DIR
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            _record_to_history_db(
                filepath=audio_path, text=text, engine="voxcpm2", duration=duration,
                model_type="声音设计", output_format=result[1] if len(result) > 1 else "wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        if degraded_note:
            return _partial_success_html(filename, msg, degraded_note)
        return _success_html(filename, msg)
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"VoxCPM design generation failed: {e}")
        _log_generation("VoxCPM design", text, "voxcpm2", instruction[:50], False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/streaming_sse")
async def streaming_sse_generation(
    request: Request,
    text: str = Form(""),
    instruction: str = Form(""),
    ref_audio_path: str = Form(""),
    lang: str = Form("Auto"),
):
    """True streaming generation via SSE - sends audio chunks as they are generated."""
    from ..model_manager import voxcpm_model as _voxcpm_model
    from ..generation import split_text_for_tts
    import struct

    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("文本不能为空")

    # Merge dialect into instruction
    _DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}
    if lang in _DIALECT_NAMES:
        instruction = (lang + "，" + instruction) if instruction.strip() else lang

    async def audio_chunk_generator():
        """Generate audio chunks and yield SSE events with base64-encoded PCM data."""
        try:
            segments = split_text_for_tts(text)
            total = len(segments)

            # Send metadata event
            import json
            meta = json.dumps({"total_segments": total, "sample_rate": 48000, "channels": 1, "bits": 16})
            yield f"event: meta\ndata: {meta}\n\n"

            loop = asyncio.get_running_loop()
            all_chunks = []

            for idx, seg in enumerate(segments):
                seg = seg.strip()
                if not seg:
                    continue

                # Build text with instruction
                gen_text = seg
                if instruction and instruction.strip():
                    gen_text = "(" + instruction.strip() + ")" + seg

                # Send progress event
                progress = json.dumps({"segment": idx + 1, "total": total, "status": "generating"})
                yield f"event: progress\ndata: {progress}\n\n"

                # Generate audio chunk
                if hasattr(_voxcpm_model, 'generate_streaming'):
                    # True streaming: yield each sub-chunk
                    def _gen_stream():
                        chunks = []
                        for chunk in _voxcpm_model.generate_streaming(
                            text=gen_text,
                            reference_wav_path=ref_audio_path if ref_audio_path else None,
                            normalize=True, cfg_value=2.0, inference_timesteps=10,
                            denoise=True, min_len=2, max_len=4096,
                        ):
                            chunks.append(chunk)
                        return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)

                    wav_data = await loop.run_in_executor(None, _gen_stream)
                else:
                    # Fallback: regular generation
                    wav_data = await loop.run_in_executor(
                        None,
                        lambda t=gen_text: _voxcpm_model.generate(
                            text=t,
                            reference_wav_path=ref_audio_path if ref_audio_path else None,
                            normalize=True, cfg_value=2.0, inference_timesteps=10,
                            denoise=True, min_len=2, max_len=4096,
                        )
                    )

                # Convert float32 to int16 PCM
                pcm_data = (wav_data * 32767).astype(np.int16).tobytes()
                all_chunks.append(pcm_data)

                # Send audio chunk as base64
                import base64
                b64_data = base64.b64encode(pcm_data).decode('ascii')
                yield f"event: audio\ndata: {b64_data}\n\n"

            # Send completion event with final file info
            if all_chunks:
                combined = np.concatenate([np.frombuffer(c, dtype=np.int16) for c in all_chunks])
                duration_sec = len(combined) / 48000
                timestamp = int(time.time())
                filename = f"streaming_{timestamp}.wav"

                # Save to file
                import io, wave
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


@router.post("/voxcpm_clone")
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
    ref_audio_upload: Optional[UploadFile] = File(None),
    lang: str = Form("Auto"),
):
    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("文本不能为空")

    # Merge dialect into instruction
    _DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}
    if lang in _DIALECT_NAMES:
        instruction = (lang + "，" + instruction) if instruction.strip() else lang

    actual_ref_path = ref_audio_path if ref_audio_path else None

    # Handle file upload
    if ref_audio_upload and ref_audio_upload.filename:
        from ..config import SAVE_DIR
        upload_dir = os.path.join(SAVE_DIR, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = os.path.basename(ref_audio_upload.filename)
        # Validate file extension
        _, ext = os.path.splitext(safe_name)
        if ext.lower() not in ALLOWED_AUDIO_EXTENSIONS:
            return _error_html(f"Unsupported audio format: {ext}")
        upload_path = os.path.join(upload_dir, f"{int(time.time())}_{safe_name}")
        content = await ref_audio_upload.read()
        with open(upload_path, "wb") as f:
            f.write(content)
        actual_ref_path = upload_path

    if not actual_ref_path and persona_name:
        from ..config import PERSONA_DIR
        safe_name = os.path.basename(persona_name)
        candidate = os.path.join(PERSONA_DIR, f"{safe_name}.wav")
        real_path = os.path.realpath(candidate)
        if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
            return _error_html("非法路径")
        if os.path.isfile(candidate):
            actual_ref_path = candidate
        else:
            return _error_html(f"音色文件不存�? {safe_name}")

    loop = asyncio.get_running_loop()

    def _run():
        return fn_voxcpm_clone(text, instruction, actual_ref_path)

    start_time = time.monotonic()
    try:
        result, msg, degraded_note = await loop.run_in_executor(
            None, lambda: _run_with_oom_retry(_run, "VoxCPM clone")
        )
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation("VoxCPM clone", text, "voxcpm2", instruction[:50], False, duration, error_msg=msg)
            return _error_html(msg)
        is_degraded = degraded_note is not None
        _log_generation("VoxCPM clone", text, "voxcpm2", instruction[:50], True, duration, is_degraded=is_degraded)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        from ..config import SAVE_DIR
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            _record_to_history_db(
                filepath=audio_path, text=text, engine="voxcpm2", duration=duration,
                model_type="可控克隆", output_format=result[1] if len(result) > 1 else "wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        if degraded_note:
            return _partial_success_html(filename, msg, degraded_note)
        return _success_html(filename, msg)
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"VoxCPM clone generation failed: {e}")
        _log_generation("VoxCPM clone", text, "voxcpm2", instruction[:50], False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/voxcpm_ultimate")
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
):
    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("文本不能为空")

    # Merge dialect into instruction
    _DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}
    if lang in _DIALECT_NAMES:
        instruction = (lang + "，" + instruction) if instruction.strip() else lang

    # Resolve persona_name to actual audio file path if provided
    actual_ref_path = ref_audio_path if ref_audio_path else None
    if not actual_ref_path and persona_name:
        from ..config import PERSONA_DIR
        safe_name = os.path.basename(persona_name)
        candidate = os.path.join(PERSONA_DIR, f"{safe_name}.wav")
        real_path = os.path.realpath(candidate)
        if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
            return _error_html("非法路径")
        if os.path.isfile(candidate):
            actual_ref_path = candidate
        else:
            return _error_html(f"音色文件不存�? {safe_name}")

    advanced_norm = norm.lower() in ("true", "1", "yes")
    advanced_denoise = 1.0 if denoise.lower() in ("true", "1", "yes") else 0.0

    loop = asyncio.get_running_loop()

    def _run():
        return fn_voxcpm_ultimate_clone(
            text, instruction,
            actual_ref_path if actual_ref_path else None,
            cfg, advanced_norm, advanced_denoise, steps, seed,
        )

    start_time = time.monotonic()
    try:
        result, msg, degraded_note = await loop.run_in_executor(
            None, lambda: _run_with_oom_retry(_run, "VoxCPM ultimate clone")
        )
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation("VoxCPM ultimate clone", text, "voxcpm2", instruction[:50], False, duration, error_msg=msg)
            return _error_html(msg)
        is_degraded = degraded_note is not None
        _log_generation("VoxCPM ultimate clone", text, "voxcpm2", instruction[:50], True, duration, is_degraded=is_degraded)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        from ..config import SAVE_DIR
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            _record_to_history_db(
                filepath=audio_path, text=text, engine="voxcpm2", duration=duration,
                model_type="极致克隆", output_format=result[1] if len(result) > 1 else "wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        if degraded_note:
            return _partial_success_html(filename, msg, degraded_note)
        return _success_html(filename, msg)
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"VoxCPM ultimate clone generation failed: {e}")
        _log_generation("VoxCPM ultimate clone", text, "voxcpm2", instruction[:50], False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/voxcpm_script")
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
):
    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("\u6587\u672c\u4e0d\u80fd\u4e3a\u7a7a")

    advanced_norm = norm.lower() in ("true", "1", "yes")
    advanced_denoise = 1.0 if denoise.lower() in ("true", "1", "yes") else 0.0

    loop = asyncio.get_running_loop()

    def _run():
        return fn_voxcpm_script_studio(
            text, cfg, advanced_norm, advanced_denoise, steps, seed, lang,
        )

    start_time = time.monotonic()
    try:
        result, msg = await loop.run_in_executor(None, _run)
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation("VoxCPM script", text, "voxcpm2", "script", False, duration, error_msg=msg)
            return _error_html(msg)
        _log_generation("VoxCPM script", text, "voxcpm2", "script", True, duration)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        from ..config import SAVE_DIR
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            _record_to_history_db(
                filepath=audio_path, text=text, engine="voxcpm2", duration=duration,
                model_type="剧本工坊", output_format=result[1] if len(result) > 1 else "wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        return _success_html(filename, msg)
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"VoxCPM script generation failed: {e}")
        _log_generation("VoxCPM script", text, "voxcpm2", "script", False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/cancel")
async def cancel_generation(request: Request):
    """Cancel the current generation by setting a cancel flag."""
    from ..model_manager import _progress_mgr

    was_generating = not _progress_mgr._is_complete and _progress_mgr._phase != ""
    _progress_mgr.cancel()
    logger.info(f"[Cancel] Generation cancel requested (was generating: {was_generating})")
    return {"status": "ok", "message": "\u5df2\u53d1\u9001\u53d6\u6d88\u8bf7\u6c42"}


@router.post("/streaming")
async def streaming_generation(
    request: Request,
    text: str = Form(""),
    ref_audio_path: str = Form(""),
):
    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("\u6587\u672c\u4e0d\u80fd\u4e3a\u7a7a")

    loop = asyncio.get_running_loop()

    def _run():
        return fn_voxcpm_streaming(text, ref_audio_path if ref_audio_path else None)

    start_time = time.monotonic()
    try:
        result = await loop.run_in_executor(None, _run)
        duration = time.monotonic() - start_time
        _log_generation("Streaming", text, "voxcpm2", "streaming", True, duration)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        from ..config import SAVE_DIR
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            _record_to_history_db(
                filepath=audio_path, text=text, engine="voxcpm2", duration=duration,
                model_type="流式生成", output_format="wav", is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        return _success_html(result[2], f"\u6d41\u5f0f\u751f\u6210\u5b8c\u6210\uff01\u8017\u65f6 {duration:.1f}\u79d2")
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"Streaming generation failed: {e}")
        _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg=str(e))
        return _error_html(_safe_error_msg(e))


@router.post("/streaming_audio")
async def streaming_audio_generation(
    request: Request,
    text: str = Form(""),
    ref_audio_path: str = Form(""),
):
    """Streaming audio generation - generates audio progressively and returns playable result."""
    from ..model_manager import voxcpm_model as _voxcpm_model
    
    model_not_ready = _check_model_ready()
    if model_not_ready:
        return model_not_ready
    if not text.strip():
        return _error_html("\u6587\u672c\u4e0d\u80fd\u4e3a\u7a7a")
    
    start_time = time.monotonic()
    try:
        loop = asyncio.get_running_loop()
        from ..generation import split_text_for_tts
        segments = split_text_for_tts(text)
        
        all_audio_data = []
        
        for seg_idx, seg in enumerate(segments):
            seg = seg.strip()
            if not seg:
                continue
            
            # Generate audio chunk for this segment
            wav = await loop.run_in_executor(
                None,
                lambda s=seg: _voxcpm_model.generate(
                    text=s,
                    reference_wav_path=ref_audio_path if ref_audio_path else None,
                    normalize=True,
                    cfg_value=2.0,
                    inference_timesteps=10,
                    denoise=True,
                    min_len=2,
                    max_len=4096,
                )
            )
            
            # Convert audio to numpy array
            if hasattr(wav, 'numpy'):
                wav_data = (wav.numpy() * 32767).astype(np.int16)
            else:
                wav_data = (wav * 32767).astype(np.int16)
            
            all_audio_data.append(wav_data)
        
        # Concatenate all audio segments
        if all_audio_data:
            combined_audio = np.concatenate(all_audio_data)
        else:
            return _error_html("\u672a\u751f\u6210\u4efb\u4f55\u97f3\u9891\u6570\u636e")
        
        # Save as WAV file
        import io
        import wave
        wav_bytes = io.BytesIO()
        with wave.open(wav_bytes, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(48000)
            wf.writeframes(combined_audio.tobytes())
        
        wav_bytes.seek(0)
        audio_data = wav_bytes.read()
        
        # Save to output directory
        import base64
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"streaming_{timestamp}.wav"
        output_path = os.path.join(SAVE_DIR, filename)
        with open(output_path, 'wb') as f:
            f.write(audio_data)
        
        duration = time.monotonic() - start_time
        _log_generation("Streaming", text, "voxcpm2", "streaming", True, duration)
        
        # Return HTML with audio element that auto-plays
        safe_filename = quote(filename)
        safe_display = html.escape(filename)
        return HTMLResponse(f'''<div class="tts-success-block">✅ 流式生成完成！音频已开始播放 ({safe_display})</div>
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
