import asyncio
import html
import json
import logging
import os
import time
from datetime import datetime
from urllib.parse import quote

import aiofiles
import numpy as np
from fastapi import APIRouter, UploadFile
from fastapi.responses import HTMLResponse

from ...audio_processing import enhance_audio
from ...config import MAX_UPLOAD_SIZE_BYTES, SAVE_DIR
from ...exceptions import EngineSwitchError, InsufficientVRAMError, TTSError
from ...gpu_utils import free_gpu_memory, is_oom_error
from ...history_db import create_history_db
from ...model_manager import _time_estimator
from ...monitor import get_health_monitor
from ..system import increment_generation, log_operation

router = APIRouter(prefix="/api/generate", tags=["generate"])

logger = logging.getLogger("tts_multimodel")

_history_db = None
_generation_semaphores: dict[str, asyncio.Semaphore] = {}
_generation_semaphore_lock = asyncio.Lock()
_generation_retry_counter = {"total": 0, "oom_retries": 0}

# Maximum concurrent generation requests per engine. Can be overridden via
# the TTS_MAX_CONCURRENT_GENERATIONS environment variable.
_MAX_CONCURRENT_GENERATIONS = max(1, int(os.environ.get("TTS_MAX_CONCURRENT_GENERATIONS", "1")))


async def _get_generation_semaphore(engine: str) -> asyncio.Semaphore:
    """Return the per-engine semaphore, creating it lazily if needed."""
    engine = (engine or "voxcpm2").lower()
    semaphore = _generation_semaphores.get(engine)
    if semaphore is None:
        async with _generation_semaphore_lock:
            semaphore = _generation_semaphores.get(engine)
            if semaphore is None:
                semaphore = asyncio.Semaphore(_MAX_CONCURRENT_GENERATIONS)
                _generation_semaphores[engine] = semaphore
    return semaphore


ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac"}
_DIALECT_NAMES = {"四川话", "粤语", "吴语", "东北话", "河南话", "闽南语", "湖南话", "湖北话", "客家话"}


def _get_history_db():
    global _history_db
    if _history_db is None:
        _history_db = create_history_db(SAVE_DIR)
    return _history_db


def _check_engine_ready(request, engine_name: str = None):
    from ...model_registry import registry

    if engine_name is None:
        engine_name = registry.current_engine
    if engine_name == "indextts2":
        if registry.indextts2_engine is None:
            return _error_html(request, "IndexTTS 2.0 模型未加载，请先点击顶部 IndexTTS 2.0 加载模型", error_type="engine_not_ready")
    else:
        if registry.voxcpm_model is None:
            return _error_html(request, "VoxCPM2 模型未加载，请先点击顶部 VoxCPM2 加载模型", error_type="engine_not_ready")
    return None


def _record_to_history_db(
    filepath: str,
    text: str,
    engine: str,
    duration: float,
    model_type: str = None,
    model_size: str = None,
    persona_name: str = None,
    output_format: str = "wav",
    is_success: bool = True,
    error_msg: str = None,
):
    try:
        db = _get_history_db()
        filename = os.path.basename(filepath) if filepath else ""
        file_size = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0
        db.insert(
            {
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
            }
        )
    except Exception as e:
        logger.debug(f"历史记录数据库写入失败: {e}")


def _safe_error_msg(exc):
    """Return user-friendly error message based on exception type."""
    if isinstance(exc, InsufficientVRAMError):
        return f"显存不足：{str(exc)}"
    if isinstance(exc, EngineSwitchError):
        return f"引擎切换失败：{str(exc)}"
    if isinstance(exc, TTSError):
        return str(exc)
    if isinstance(exc, RuntimeError):
        if "CUDA" in str(exc) or "VRAM" in str(exc) or "out of memory" in str(exc).lower():
            return "显存不足，请尝试缩短文本、关闭其他GPU程序，或在设置中切换到CPU模式"
        return f"运行时错误：{str(exc)[:200]}"
    if isinstance(exc, ValueError):
        return f"参数错误：{str(exc)[:200]}"
    if isinstance(exc, FileNotFoundError):
        return "音频文件不存在或已被删除"
    if isinstance(exc, TimeoutError):
        return "请求超时，请稍后重试"
    if isinstance(exc, ConnectionError):
        return "网络连接异常，请检查网络"
    return "生成失败，请稍后重试"


def _partial_success_html(filename, message, degraded_note):
    safe_filename = quote(filename, safe="")
    return HTMLResponse(
        f'<div data-audio-filename="{html.escape(filename)}">'
        f'<audio class="tts-audio-hidden" src="/api/audio/{safe_filename}"></audio>'
        f'<div class="status-message success">{html.escape(message)}</div>'
        f'<div class="status-message warning" style="margin-top:8px;color:#f59e0b;">{html.escape(degraded_note)}</div>'
        f"</div>"
    )


def _log_generation(
    endpoint_name, text, engine, voice_or_persona, success, duration, is_degraded=False, error_msg=None
):
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
        logger.warning(f"后处理: 音频文件未找到: {audio_path}")
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
            audio,
            sr,
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

        logger.info(f"后处理已应用: {filename} -> {new_filename}")
        return new_filename
    except Exception as e:
        logger.error(f"后处理失败 {filename}: {e}")
        return filename


def _error_html(request, error_message, error_type="general"):
    """渲染 HTML 错误片段；优先使用模板，降级时返回安全字符串。"""
    try:
        templates = request.app.state.templates
        from ...i18n import get_lang

        return templates.TemplateResponse(
            request=request,
            name="partials/error_message.html",
            context={
                "lang": get_lang(request),
                "error_message": error_message,
                "error_type": error_type,
            },
            status_code=400,
            headers={
                "HX-Trigger": json.dumps(
                    {"tts-toast": {"type": "error", "message": html.escape(error_message)}},
                    ensure_ascii=False,
                )
            },
        )
    except Exception:
        # 极端降级：仍保证转义
        return HTMLResponse(
            f'<div class="tts-error-block" data-error-type="{html.escape(error_type)}">'
            f'<div class="error-title">生成失败</div>'
            f'<div class="error-message">{html.escape(error_message)}</div>'
            f"</div>",
            status_code=400,
        )


async def save_uploaded_audio(request, upload_file, upload_dir=None, max_size_mb=25):
    """Save an uploaded audio file and return the path, or an error HTML response."""
    if not upload_file or not upload_file.filename:
        return None, None

    if upload_dir is None:
        upload_dir = os.path.join(SAVE_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = os.path.basename(upload_file.filename)
    _, ext = os.path.splitext(safe_name)
    if ext.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        return None, _error_html(request, f"不支持的音频格式: {ext}")

    upload_path = os.path.join(upload_dir, f"{int(time.time())}_{safe_name}")
    content = await upload_file.read()
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        return None, _error_html(request, f"上传文件大小超过 {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB 限制")

    async with aiofiles.open(upload_path, "wb") as f:
        await f.write(content)

    return upload_path, None


async def resolve_persona_ref(request, persona_name):
    """Resolve a persona name to its reference audio path. Returns (path, error_html)."""
    if not persona_name:
        return None, None

    from ...persona_manager import load_persona_embedding

    safe_name = os.path.basename(persona_name)
    persona_data = load_persona_embedding(safe_name)
    if persona_data is not None:
        wav_path, ref_text = persona_data
        if wav_path and os.path.isfile(wav_path):
            return wav_path, None
        else:
            return None, _error_html(request, f"音色文件不存在: {safe_name}")
    else:
        return None, _error_html(request, f"音色不存在: {safe_name}")


def pre_validate(request, engine_name, text, max_length=None):
    """Pre-validate engine readiness and text. Returns error HTML or None if valid."""
    model_not_ready = _check_engine_ready(request, engine_name)
    if model_not_ready:
        return model_not_ready
    if not text or not text.strip():
        return _error_html(request, "文本不能为空")
    if max_length and len(text) > max_length:
        return _error_html(request, f"文本长度超过限制（最大 {max_length} 字符）")
    return None


def _success_html(filename, status_message):
    safe_filename = quote(filename, safe="")
    return HTMLResponse(
        f'<div data-audio-filename="{html.escape(filename)}">'
        f'<audio class="tts-audio-hidden" src="/api/audio/{safe_filename}"></audio>'
        f'<div class="status-message success">{html.escape(status_message)}</div>'
        f"</div>"
    )


def _run_with_oom_retry(run_fn, endpoint_name, degraded_fn=None, max_retries=2):
    _generation_retry_counter["total"] += 1
    degraded_note = None
    retry_count = 0

    try:
        result, msg = run_fn()
        return result, msg, degraded_note
    except Exception as e:
        if not is_oom_error(e):
            logger.error(f"{endpoint_name} failed (non-OOM): {e}")
            raise

        logger.warning(f"{endpoint_name} hit OOM, attempting degraded retry...")
        _generation_retry_counter["oom_retries"] += 1
        free_gpu_memory()

        while retry_count < max_retries:
            retry_count += 1
            try:
                degraded_note = "由于显存限制，已自动降低生成质量参数以完成生成。"
                if degraded_fn:
                    result, msg = degraded_fn()
                else:
                    result, msg = run_fn()
                return result, msg, degraded_note
            except Exception as retry_e:
                if not is_oom_error(retry_e):
                    raise
                logger.warning(f"{endpoint_name} OOM retry {retry_count}/{max_retries} failed")
                free_gpu_memory()

        raise RuntimeError(
            "显存不足，已尝试降级重试但仍失败。请尝试缩短文本、关闭其他GPU程序，或在设置中切换到CPU模式"
        ) from None


def _parse_bool_form(value) -> bool:
    return str(value).lower() in ("true", "1", "yes")


def _merge_dialect(instruction: str, dialect: str) -> str:
    if dialect and dialect in _DIALECT_NAMES:
        return (dialect + "，" + instruction) if instruction.strip() else dialect
    return instruction


async def _execute_generation(
    request,
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
    degraded_fn=None,
):
    semaphore = await _get_generation_semaphore(engine)
    try:
        await asyncio.wait_for(
            semaphore.acquire(),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        return _error_html(request, "系统繁忙，请稍后再试（等待超时）")
    try:
        return await _execute_generation_impl(
            request,
            text,
            run_fn,
            endpoint_name,
            voice_or_persona,
            model_type,
            engine,
            tempo_factor,
            voice_enhancement,
            target_lufs,
            oom_retry,
            degraded_fn,
        )
    finally:
        semaphore.release()


async def _execute_generation_impl(
    request,
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
    degraded_fn=None,
):
    loop = asyncio.get_running_loop()
    start_time = time.monotonic()
    try:
        if oom_retry:
            result, msg, degraded_note = await loop.run_in_executor(
                None, lambda: _run_with_oom_retry(run_fn, endpoint_name, degraded_fn=degraded_fn)
            )
        else:
            result, msg = await loop.run_in_executor(None, run_fn)
            degraded_note = None
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation(endpoint_name, text, engine, voice_or_persona, False, duration, error_msg=msg)
            return _error_html(request, msg)
        is_degraded = degraded_note is not None
        _log_generation(endpoint_name, text, engine, voice_or_persona, True, duration, is_degraded=is_degraded)
        _time_estimator.record(len(text), duration, engine, segment_count=1)
        if isinstance(result, tuple) and len(result) >= 3:
            audio_path = os.path.join(SAVE_DIR, result[2]) if not os.path.isabs(result[2]) else result[2]
            await asyncio.to_thread(
                _record_to_history_db,
                filepath=audio_path,
                text=text,
                engine=engine,
                duration=duration,
                model_type=model_type,
                output_format="wav",
                is_success=True,
            )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        filename = result[2]
        pp_voice_enhancement = _parse_bool_form(voice_enhancement)
        filename = await asyncio.to_thread(
            _apply_post_processing_to_file, filename, tempo_factor, pp_voice_enhancement, target_lufs
        )
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
        return _error_html(request, _safe_error_msg(e), error_type=error_type)


# ---------------------------------------------------------------------------
# 共享工具函数：音频上传验证、文本输入验证、参考音频加载
# ---------------------------------------------------------------------------

# 支持的音频格式（与 ALLOWED_AUDIO_EXTENSIONS 保持一致）
SUPPORTED_AUDIO_FORMATS = ALLOWED_AUDIO_EXTENSIONS
MAX_AUDIO_SIZE_MB = 50  # 最大音频文件大小（MB）
MAX_TEXT_LENGTH_DEFAULT = 5000  # 默认最大文本长度


async def validate_audio_upload(
    file: UploadFile,
    max_size_mb: int = MAX_AUDIO_SIZE_MB,
    supported_formats: set = SUPPORTED_AUDIO_FORMATS,
) -> tuple[bool, str]:
    """验证上传的音频文件

    Returns:
        (is_valid, error_message) - 验证通过时 error_message 为空字符串
    """
    if not file or not file.filename:
        return False, "未选择音频文件"

    # 检查文件扩展名
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in supported_formats:
        return False, f"不支持的音频格式: {ext}，支持: {', '.join(sorted(supported_formats))}"

    # 检查文件大小
    try:
        content = await file.read()
        await file.seek(0)  # 重置文件指针
        size_mb = len(content) / (1024 * 1024)
        if size_mb > max_size_mb:
            return False, f"音频文件过大: {size_mb:.1f}MB，最大支持: {max_size_mb}MB"
    except Exception as e:
        logger.warning(f"读取音频文件失败: {e}")
        return False, f"读取音频文件失败: {e}"

    return True, ""


def validate_text_input(
    text: str,
    max_length: int = MAX_TEXT_LENGTH_DEFAULT,
    field_name: str = "文本",
) -> tuple[bool, str]:
    """验证文本输入

    Returns:
        (is_valid, error_message) - 验证通过时 error_message 为空字符串
    """
    if not text or not text.strip():
        return False, f"请输入{field_name}"

    if len(text) > max_length:
        return False, f"{field_name}过长: {len(text)}字，最大支持: {max_length}字"

    return True, ""


async def load_reference_audio(
    request,
    file: UploadFile,
    output_dir: str,
    prefix: str = "ref",
) -> tuple[str | None, str]:
    """加载参考音频文件到指定目录

    Returns:
        (file_path, error_message) - 成功时 error_message 为空字符串，失败时 file_path 为 None
    """
    is_valid, error = await validate_audio_upload(file)
    if not is_valid:
        return None, error

    try:
        content = await file.read()
        filename = f"{prefix}_{file.filename}"
        filepath = os.path.join(output_dir, filename)

        os.makedirs(output_dir, exist_ok=True)
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)

        return filepath, ""
    except Exception as e:
        logger.error(f"保存参考音频失败: {e}")
        return None, f"保存参考音频失败: {e}"
