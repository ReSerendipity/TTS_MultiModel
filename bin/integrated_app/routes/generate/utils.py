import asyncio
import html
import logging
import os
import time
from datetime import datetime
from urllib.parse import quote

import numpy as np
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ...audio_processing import enhance_audio
from ...config import SAVE_DIR
from ...exceptions import TTSError
from ...gpu_utils import free_gpu_memory, is_oom_error
from ...history_db import create_history_db
from ...model_manager import _time_estimator
from ...monitor import get_health_monitor
from ..system import increment_generation, log_operation

router = APIRouter(prefix="/api/generate", tags=["generate"])

logger = logging.getLogger("tts_multimodel")

_history_db = None
_generation_semaphore = asyncio.Semaphore(1)
_generation_retry_counter = {"total": 0, "oom_retries": 0}

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac"}
_DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}


def _get_history_db():
    global _history_db
    if _history_db is None:
        _history_db = create_history_db(SAVE_DIR)
    return _history_db


def _check_engine_ready(engine_name: str = None):
    from ...model_manager import registry
    if engine_name is None:
        engine_name = registry.current_engine
    if engine_name == "indextts2":
        if registry.indextts2_engine is None:
            return _error_html("IndexTTS 2.0 模型未加载，请先在设置中加载模型", error_type="engine_not_ready")
    else:
        from ...model_manager import voxcpm_model
        if voxcpm_model is None:
            return _error_html("模型正在加载，请稍后再试...", error_type="engine_not_ready")
    return None


def _record_to_history_db(filepath: str, text: str, engine: str, duration: float,
                          model_type: str = None, model_size: str = None,
                          persona_name: str = None, output_format: str = "wav",
                          is_success: bool = True, error_msg: str = None):
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


def _safe_error_msg(exc):
    """Return user-friendly error message based on exception type."""
    if isinstance(exc, TTSError):
        return str(exc)
    if isinstance(exc, RuntimeError):
        if 'CUDA' in str(exc) or 'VRAM' in str(exc) or 'out of memory' in str(exc).lower():
            return '显存不足，请尝试缩短文本、关闭其他GPU程序，或在设置中切换到CPU模式'
        return f'运行时错误：{str(exc)[:200]}'
    if isinstance(exc, ValueError):
        return f'参数错误：{str(exc)[:200]}'
    if isinstance(exc, FileNotFoundError):
        return '音频文件不存在或已被删除'
    if isinstance(exc, TimeoutError):
        return '请求超时，请稍后重试'
    if isinstance(exc, ConnectionError):
        return '网络连接异常，请检查网络'
    return '生成失败，请稍后重试'


def _partial_success_html(filename, message, degraded_note):
    safe_filename = quote(filename, safe='')
    return HTMLResponse(
        f'<div data-audio-filename="{html.escape(filename)}">'
        f'<audio controls src="/api/audio/{safe_filename}" style="width:100%;margin:8px 0;"></audio>'
        f'<div class="status-message success">{html.escape(message)}</div>'
        f'<div class="status-message warning" style="margin-top:8px;color:#f59e0b;">{html.escape(degraded_note)}</div>'
        f'</div>'
    )


def _log_generation(endpoint_name, text, engine, voice_or_persona, success, duration,
                     is_degraded=False, error_msg=None):
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


def _apply_post_processing_to_file(filename, tempo_factor, voice_enhancement, target_lufs):
    if tempo_factor == 1.0 and not voice_enhancement and target_lufs == -16.0:
        return filename

    from scipy.io import wavfile

    audio_path = os.path.join(SAVE_DIR, filename) if not os.path.isabs(filename) else filename
    if not os.path.isfile(audio_path):
        logger.warning(f"Post-processing: audio file not found: {audio_path}")
        return filename

    try:
        sr, data = wavfile.read(audio_path)
        if data.dtype == np.int16:
            audio = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            audio = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.float32:
            audio = data.copy()
        else:
            audio = data.astype(np.float32)

        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        processed = enhance_audio(
            audio, sr,
            normalize=True,
            tempo_factor=tempo_factor,
            voice_enhancement=voice_enhancement,
            target_lufs=target_lufs,
        )

        base, ext = os.path.splitext(filename)
        new_filename = f"{base}_pp{ext}"
        new_path = os.path.join(SAVE_DIR, new_filename) if not os.path.isabs(new_filename) else new_filename

        output = (processed * 32768.0).clip(-32768, 32767).astype(np.int16)
        wavfile.write(new_path, sr, output)

        logger.info(f"Post-processing applied: {filename} -> {new_filename}")
        return new_filename
    except Exception as e:
        logger.error(f"Post-processing failed for {filename}: {e}")
        return filename


def _error_html(error_message, error_type="general"):
    error_type_attr = f' data-error-type="{error_type}"'
    return HTMLResponse(
        f'<div class="tts-error-block"{error_type_attr}>'
        f'<div class="error-title">\u751f\u6210\u5931\u8d25</div>'
        f'<div class="error-message">{html.escape(error_message)}</div>'
        f'</div>'
    )


def _success_html(filename, status_message):
    safe_filename = quote(filename, safe='')
    return HTMLResponse(
        f'<div data-audio-filename="{html.escape(filename)}">'
        f'<audio controls src="/api/audio/{safe_filename}" style="width:100%;margin:8px 0;"></audio>'
        f'<div class="status-message success">{html.escape(status_message)}</div>'
        f'</div>'
    )


def _run_with_oom_retry(run_fn, endpoint_name, degraded_fn=None):
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
                raise RuntimeError('显存不足，请尝试缩短文本、关闭其他GPU程序，或在设置中切换到CPU模式') from e2
        else:
            try:
                degraded_note = "\u7531\u4e8e\u663e\u5b58\u9650\u5236\uff0c\u5df2\u81ea\u52a8\u964d\u4f4e\u751f\u6210\u8d28\u91cf\u53c2\u6570\u4ee5\u5b8c\u6210\u751f\u6210\u3002"
                result, msg = run_fn()
                return result, msg, degraded_note
            except Exception as e2:
                logger.error(f"{endpoint_name} failed after OOM retry: {e2}")
                raise RuntimeError('显存不足，请尝试缩短文本、关闭其他GPU程序，或在设置中切换到CPU模式') from e2


def _parse_bool_form(value) -> bool:
    return str(value).lower() in ("true", "1", "yes")


def _merge_dialect(instruction: str, dialect: str) -> str:
    if dialect and dialect in _DIALECT_NAMES:
        return (dialect + "，" + instruction) if instruction.strip() else dialect
    return instruction


async def _execute_generation(
    text: str,
    run_fn,
    endpoint_name: str,
    voice_or_persona: str = "",
    model_type: str = "",
    engine: str = "voxcpm2",
    tempo_factor: float = 1.0,
    voice_enhancement: str = "false",
    target_lufs: float = -16.0,
    oom_retry: bool = True,
):
    if not _generation_semaphore.locked():
        async with _generation_semaphore:
            return await _execute_generation_impl(
                text, run_fn, endpoint_name, voice_or_persona,
                model_type, engine, tempo_factor, voice_enhancement,
                target_lufs, oom_retry,
            )
    else:
        return _error_html("系统正在处理其他请求，请稍后再试")


async def _execute_generation_impl(
    text: str,
    run_fn,
    endpoint_name: str,
    voice_or_persona: str = "",
    model_type: str = "",
    engine: str = "voxcpm2",
    tempo_factor: float = 1.0,
    voice_enhancement: str = "false",
    target_lufs: float = -16.0,
    oom_retry: bool = True,
):
    loop = asyncio.get_running_loop()
    start_time = time.monotonic()
    try:
        if oom_retry:
            result, msg, degraded_note = await loop.run_in_executor(
                None, lambda: _run_with_oom_retry(run_fn, endpoint_name)
            )
        else:
            result, msg = await loop.run_in_executor(None, run_fn)
            degraded_note = None
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation(endpoint_name, text, engine, voice_or_persona, False, duration, error_msg=msg)
            return _error_html(msg)
        is_degraded = degraded_note is not None
        _log_generation(endpoint_name, text, engine, voice_or_persona, True, duration, is_degraded=is_degraded)
        _time_estimator.record(len(text), duration, engine, segment_count=1)
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            _record_to_history_db(
                filepath=audio_path, text=text, engine=engine, duration=duration,
                model_type=model_type, output_format=result[1] if len(result) > 1 else "wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        pp_voice_enhancement = _parse_bool_form(voice_enhancement)
        filename = _apply_post_processing_to_file(filename, tempo_factor, pp_voice_enhancement, target_lufs)
        if degraded_note:
            return _partial_success_html(filename, msg, degraded_note)
        return _success_html(filename, msg)
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"{endpoint_name} generation failed: {e}")
        _log_generation(endpoint_name, text, engine, voice_or_persona, False, duration, error_msg=str(e))
        error_type = "general"
        if is_oom_error(e):
            error_type = "oom"
        elif isinstance(e, (ValueError,)):
            error_type = "validation"
        return _error_html(_safe_error_msg(e), error_type=error_type)
