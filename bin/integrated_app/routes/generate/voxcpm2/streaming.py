"""VoxCPM2 流式生成路由。

重构说明 (S-R1/R2/R3):
- S-R1: 提取模块级辅助函数消除三路由 90% 重复
        (_load_streaming_persona / _generate_segment_sync / _generate_segment_async /
         _merge_and_save_wav / _acquire_streaming_semaphore)
- S-R2: 统一 persona 加载，复用 utils.resolve_persona_ref；
        统一文本校验 pre_validate、bool 解析 _parse_bool_form、方言合并 _merge_dialect
- S-R3: 三路由加信号量+超时，复用 utils._get_generation_semaphore 与超时常量；
        _generate_segment_async 内置 asyncio.wait_for 硬超时保护
"""

import asyncio
import base64
import functools
import html
import io
import json
import os
import time
import wave
from urllib.parse import quote

import aiofiles
import numpy as np
from fastapi import Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from ....config import MAX_TEXT_LENGTH, SAVE_DIR
from ....generation import _save_wav_compatible, split_text_for_tts
from ....model_registry import registry
from ....monitor import get_health_monitor
from ..utils import (
    _apply_post_processing_to_file,
    _error_html,
    _GENERATION_HARD_TIMEOUT_S,
    _get_generation_semaphore,
    _log_generation,
    _merge_dialect,
    _parse_bool_form,
    _record_to_history_db,
    _safe_error_msg,
    _SEMAPHORE_ACQUIRE_TIMEOUT_S,
    _success_html,
    _time_estimator,
    logger,
    pre_validate,
    resolve_persona_ref,
    router,
)

# --- 常量提取 (S-R1/A3-1 消除魔法数字) ---
_STREAMING_SAMPLE_RATE = 48000  # VoxCPM2 流式生成固定采样率
_STREAMING_AUDIO_CHANNELS = 1
_STREAMING_AUDIO_SAMPLE_WIDTH = 2  # 16-bit PCM
_STREAMING_MIN_LEN = 2
_STREAMING_MAX_LEN = 4096


# ====================================================================
# S-R1: 共享辅助函数
# ====================================================================


async def _load_streaming_persona(
    request: Request,
    persona_name: str,
    ref_audio_path: str = "",
    allow_missing: bool = True,
) -> tuple[str | None, HTMLResponse | None]:
    """REFACTOR: [S-R2] 统一流式路由的 persona 加载逻辑。

    三路由原本各自实现 persona 加载，逻辑重复且行为不一致：
    - streaming_sse_generation: allow_missing=True（缺失用默认音色）
    - streaming_generation: allow_missing=False（缺失返回错误）
    - streaming_audio_generation: allow_missing=True（缺失用默认音色）

    优先级: persona_name > ref_audio_path > None。
    persona_name 加载失败且 allow_missing=True 时降级到 ref_audio_path。

    Args:
        request: FastAPI Request 对象。
        persona_name: 音色名称。
        ref_audio_path: 直接指定的参考音频路径（persona_name 缺失时降级使用）。
        allow_missing: True 时 persona 缺失返回 (ref_audio_path或None, None)；
                       False 时 persona 缺失返回 (None, error_html)。

    Returns:
        (actual_ref_path, error_html) — error_html 为 None 表示成功。
    """
    if persona_name:
        ref_path, error = await resolve_persona_ref(request, persona_name)
        if error is None:
            safe_name = os.path.basename(persona_name)
            logger.info(f"[VoxCPM流式生成] 已加载音色 '{safe_name}' 的参考音频")
            return ref_path, None
        # persona 加载失败
        if allow_missing:
            safe_name = os.path.basename(persona_name)
            logger.warning(f"[VoxCPM流式生成] 音色 '{safe_name}' 不存在，将使用默认音色")
            # 降级到 ref_audio_path
            if ref_audio_path:
                return ref_audio_path, None
            return None, None
        else:
            return None, error

    # 无 persona_name，用 ref_audio_path
    if ref_audio_path:
        return ref_audio_path, None

    return None, None


def _generate_segment_sync(
    seg_text: str,
    actual_ref_path: str | None,
    cfg_value: float,
    inference_timesteps: int,
    stream_denoise: bool,
    prefer_streaming: bool = True,
) -> np.ndarray:
    """REFACTOR: [S-R1] 同步生成单段音频（在 executor 线程中调用）。

    统一了 SSE 路由和 audio 路由的段生成逻辑。
    prefer_streaming=True 时优先用 generate_streaming（逐块产出后合并），
    否则用 generate（一次性生成）。SSE 路由用 True，audio 路由用 False
    以保留原行为。

    Args:
        seg_text: 已合并 instruction 的段文本。
        actual_ref_path: 参考音频路径或 None。
        cfg_value: CFG 值。
        inference_timesteps: 推理步数。
        stream_denoise: 是否降噪。
        prefer_streaming: 是否优先使用 generate_streaming 方法。

    Returns:
        numpy float32 数组音频数据。

    Raises:
        RuntimeError: VoxCPM2 模型未加载。
    """
    model = registry.voxcpm_model
    if model is None:
        raise RuntimeError("VoxCPM2 模型未加载")

    if prefer_streaming and hasattr(model, "generate_streaming"):
        chunks = list(
            model.generate_streaming(
                text=seg_text,
                reference_wav_path=actual_ref_path,
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=stream_denoise,
                min_len=_STREAMING_MIN_LEN,
                max_len=_STREAMING_MAX_LEN,
            )
        )
        return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
    else:
        return model.generate(
            text=seg_text,
            reference_wav_path=actual_ref_path,
            normalize=True,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
            denoise=stream_denoise,
            min_len=_STREAMING_MIN_LEN,
            max_len=_STREAMING_MAX_LEN,
        )


async def _generate_segment_async(
    seg_text: str,
    actual_ref_path: str | None,
    cfg_value: float,
    inference_timesteps: int,
    stream_denoise: bool,
    prefer_streaming: bool = True,
    timeout_s: float = _GENERATION_HARD_TIMEOUT_S,
) -> np.ndarray:
    """REFACTOR: [S-R1/R3] 异步生成单段音频，带超时保护。

    Args:
        seg_text: 已合并 instruction 的段文本。
        actual_ref_path: 参考音频路径或 None。
        cfg_value: CFG 值。
        inference_timesteps: 推理步数。
        stream_denoise: 是否降噪。
        prefer_streaming: 是否优先使用 generate_streaming 方法。
        timeout_s: 单段生成超时（秒）。

    Returns:
        numpy float32 数组音频数据。

    Raises:
        TimeoutError: 单段生成超时。
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,
                functools.partial(
                    _generate_segment_sync,
                    seg_text,
                    actual_ref_path,
                    cfg_value,
                    inference_timesteps,
                    stream_denoise,
                    prefer_streaming,
                ),
            ),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError as e:
        raise TimeoutError(f"单段生成超时（>{timeout_s:.0f}s）") from e


async def _merge_and_save_wav(
    audio_chunks: list[np.ndarray],
    prefix: str = "streaming",
) -> tuple[str, float]:
    """REFACTOR: [S-R1] 合并音频块并保存为 WAV 文件。

    Args:
        audio_chunks: int16 numpy 数组列表。
        prefix: 文件名前缀。

    Returns:
        (filename, duration_seconds)

    Raises:
        ValueError: audio_chunks 为空。
    """
    if not audio_chunks:
        raise ValueError("未生成任何音频数据")

    combined = np.concatenate(audio_chunks)
    duration_sec = len(combined) / _STREAMING_SAMPLE_RATE

    wav_bytes = io.BytesIO()
    with wave.open(wav_bytes, "wb") as wf:
        wf.setnchannels(_STREAMING_AUDIO_CHANNELS)
        wf.setsampwidth(_STREAMING_AUDIO_SAMPLE_WIDTH)
        wf.setframerate(_STREAMING_SAMPLE_RATE)
        wf.writeframes(combined.tobytes())

    timestamp = int(time.time())
    filename = f"{prefix}_{timestamp}.wav"
    output_path = os.path.join(SAVE_DIR, filename)
    async with aiofiles.open(output_path, "wb") as f:
        await f.write(wav_bytes.getvalue())

    return filename, duration_sec


async def _acquire_streaming_semaphore(
    request: Request, engine: str = "voxcpm2"
) -> tuple[asyncio.Semaphore | None, HTMLResponse | None]:
    """REFACTOR: [S-R3] 获取流式生成信号量，带超时保护。

    Returns:
        (semaphore, error_html) — error_html 为 None 表示成功获取。
    """
    semaphore = await _get_generation_semaphore(engine)
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=_SEMAPHORE_ACQUIRE_TIMEOUT_S)
        return semaphore, None
    except asyncio.TimeoutError:
        return None, _error_html(request, "系统繁忙，请稍后再试（等待超时）")


# ====================================================================
# 路由 1: SSE 流式生成
# ====================================================================


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
    # S-R1: 复用 pre_validate 统一文本校验 + 引擎就绪检查
    error = pre_validate(request, "voxcpm2", text, MAX_TEXT_LENGTH)
    if error:
        return error

    # S-R1: 复用 _parse_bool_form / _merge_dialect 消除重复
    stream_denoise = _parse_bool_form(denoise)
    instruction = _merge_dialect(instruction, lang)

    # S-R2: 统一 persona 加载（allow_missing=True，缺失用默认音色）
    actual_ref_path, persona_error = await _load_streaming_persona(
        request, persona_name, allow_missing=True
    )
    if persona_error:
        return persona_error

    # S-R3: 加信号量
    semaphore, sem_error = await _acquire_streaming_semaphore(request)
    if sem_error:
        return sem_error

    async def audio_chunk_generator():
        # E4: finally 中释放信号量，确保异常路径也释放
        try:
            segments = split_text_for_tts(text)
            total = len(segments)

            meta = json.dumps(
                {
                    "total_segments": total,
                    "sample_rate": _STREAMING_SAMPLE_RATE,
                    "channels": _STREAMING_AUDIO_CHANNELS,
                    "bits": _STREAMING_AUDIO_SAMPLE_WIDTH * 8,
                }
            )
            yield f"event: meta\ndata: {meta}\n\n"

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

                # S-R1: 复用 _generate_segment_async（含超时保护）
                wav_data = await _generate_segment_async(
                    gen_text, actual_ref_path, cfg_value, inference_timesteps, stream_denoise
                )

                pcm_data = (wav_data * 32767).astype(np.int16)
                all_chunks.append(pcm_data)

                b64_data = base64.b64encode(pcm_data.tobytes()).decode("ascii")
                yield f"event: audio\ndata: {b64_data}\n\n"

            if all_chunks:
                # S-R1: 复用 _merge_and_save_wav
                filename, duration_sec = await _merge_and_save_wav(all_chunks, "streaming")

                done = json.dumps(
                    {"status": "done", "filename": filename, "duration": round(duration_sec, 2)}
                )
                yield f"event: done\ndata: {done}\n\n"

        except Exception as e:
            err = json.dumps({"status": "error", "message": str(e)})
            yield f"event: error\ndata: {err}\n\n"
        finally:
            # S-R3: 确保信号量释放（E4 资源安全）
            semaphore.release()

    return StreamingResponse(
        audio_chunk_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ====================================================================
# 路由 2: 流式生成（一次性返回）
# ====================================================================


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
    # S-R1: 复用 pre_validate
    error = pre_validate(request, "voxcpm2", text, MAX_TEXT_LENGTH)
    if error:
        return error

    stream_denoise = _parse_bool_form(denoise)

    # S-R2: 统一 persona 加载（allow_missing=False，缺失返回错误）
    actual_ref_path, persona_error = await _load_streaming_persona(
        request, persona_name, ref_audio_path, allow_missing=False
    )
    if persona_error:
        return persona_error

    # S-R3: 加信号量
    semaphore, sem_error = await _acquire_streaming_semaphore(request)
    if sem_error:
        return sem_error

    loop = asyncio.get_running_loop()

    def _run():
        engine = registry.get_current_engine()
        return engine.generate_streaming(
            text,
            actual_ref_path,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
            denoise=stream_denoise,
            seed=seed,
        )

    start_time = time.monotonic()
    try:
        # S-R3: 加硬超时
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=_GENERATION_HARD_TIMEOUT_S,
        )
        duration = time.monotonic() - start_time
        if result is None:
            _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg="生成失败")
            return _error_html(request, "生成失败")

        # Convert to standard format: merge chunks and save
        if isinstance(result, list):
            merged = np.concatenate(result) if result else np.array([], dtype=np.float32)
        else:
            merged = result

        sample_rate = _STREAMING_SAMPLE_RATE
        timestamp = int(time.time())
        filename = f"streaming_{timestamp}.wav"
        out_path = os.path.join(SAVE_DIR, filename)
        await asyncio.to_thread(_save_wav_compatible, merged, out_path, sample_rate)

        _log_generation("Streaming", text, "voxcpm2", "streaming", True, duration)
        _time_estimator.record(len(text), duration, "voxcpm2", segment_count=1)
        await asyncio.to_thread(
            _record_to_history_db,
            filepath=out_path,
            text=text,
            engine="voxcpm2",
            duration=duration,
            model_type="流式生成",
            output_format="wav",
            is_success=True,
        )
        monitor = get_health_monitor()
        monitor.record_generation(success=True)
        return _success_html(filename, f"流式生成完成！耗时 {duration:.1f}秒")
    except asyncio.TimeoutError:
        duration = time.monotonic() - start_time
        logger.error(f"流式生成超时 (>{_GENERATION_HARD_TIMEOUT_S}s)，文本长度={len(text)}")
        _log_generation(
            "Streaming", text, "voxcpm2", "streaming", False, duration, error_msg="timeout"
        )
        return _error_html(
            request, f"生成超时（超过 {_GENERATION_HARD_TIMEOUT_S:.0f} 秒），请尝试缩短文本"
        )
    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"流式生成失败: {e}")
        _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg=str(e))
        return _error_html(request, _safe_error_msg(e))
    finally:
        # S-R3: 确保信号量释放（E4 资源安全）
        semaphore.release()


# ====================================================================
# 路由 3: 流式音频（分段生成 + 一次性返回 + 自动播放）
# ====================================================================


@router.post("/streaming_audio", summary="流式音频", description="流式音频生成与播放")
async def streaming_audio_generation(
    request: Request,
    text: str = Form(""),
    persona_name: str = Form(""),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    denoise: str = Form("true"),
):
    # S-R1: 复用 pre_validate
    error = pre_validate(request, "voxcpm2", text, MAX_TEXT_LENGTH)
    if error:
        return error

    stream_denoise = _parse_bool_form(denoise)

    # S-R2: 统一 persona 加载（allow_missing=True，缺失用默认音色）
    actual_ref_path, persona_error = await _load_streaming_persona(
        request, persona_name, allow_missing=True
    )
    if persona_error:
        return persona_error

    # S-R3: 加信号量
    semaphore, sem_error = await _acquire_streaming_semaphore(request)
    if sem_error:
        return sem_error

    start_time = time.monotonic()
    try:
        segments = split_text_for_tts(text)
        all_audio_data = []

        for _seg_idx, seg in enumerate(segments):
            seg = seg.strip()
            if not seg:
                continue

            # S-R1: 复用 _generate_segment_async（含超时保护）
            # prefer_streaming=False 保留原行为（用 generate 而非 generate_streaming）
            wav_data = await _generate_segment_async(
                seg, actual_ref_path, cfg_value, inference_timesteps, stream_denoise,
                prefer_streaming=False,
            )

            # 转换为 int16
            if hasattr(wav_data, "numpy"):
                wav_data = wav_data.numpy()
            all_audio_data.append((wav_data * 32767).astype(np.int16))

        # S-R1: 复用 _merge_and_save_wav
        filename, duration_sec = await _merge_and_save_wav(all_audio_data, "streaming")

        duration = time.monotonic() - start_time
        _log_generation("Streaming", text, "voxcpm2", "streaming", True, duration)

        safe_filename = quote(filename)
        safe_display = html.escape(filename)
        return HTMLResponse(
            f"""<div class="tts-success-block">流式生成完成！音频已开始播放 ({safe_display})</div>
<audio class="tts-audio-hidden" id="streaming-audio">
    <source src="/output/{safe_filename}" type="audio/wav">
</audio>
<script>
(function(){{
    var audio = document.getElementById('streaming-audio');
    if (audio && window.globalAudioPlayer) {{
        window.globalAudioPlayer.play(audio.querySelector('source').src, '{safe_display}');
    }} else if (audio) {{
        audio.play().catch(function(e) {{
            console.warn('Auto-play blocked:', e);
        }});
    }}
}})();
</script>
"""
        )

    except Exception as e:
        duration = time.monotonic() - start_time
        logger.error(f"流式音频生成失败: {e}")
        _log_generation("Streaming", text, "voxcpm2", "streaming", False, duration, error_msg=str(e))
        return _error_html(request, _safe_error_msg(e))
    finally:
        # S-R3: 确保信号量释放（E4 资源安全）
        semaphore.release()


# ====================================================================
# 路由 4: 后处理
# ====================================================================


@router.post("/post-process", summary="后处理", description="对已生成的音频进行后处理（变速、响度标准化、人声增强）")
async def post_process_audio(
    request: Request,
    audio_path: str = Form(""),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    # SECURITY: 输入校验加固（D4 路径遍历防护）
    if not audio_path.strip():
        return _error_html(request, "audio_path is required")

    safe_name = os.path.basename(audio_path)
    if safe_name != audio_path:
        return _error_html(request, "Invalid audio path")

    full_path = os.path.join(SAVE_DIR, safe_name)
    real_path = os.path.realpath(full_path)
    # SECURITY: 防止路径遍历（symlink escape）
    if not real_path.startswith(os.path.realpath(SAVE_DIR)):
        return _error_html(request, "Invalid audio path")

    if not os.path.isfile(real_path):
        return _error_html(request, "Audio file not found")

    pp_voice_enhancement = _parse_bool_form(voice_enhancement)
    new_filename = await asyncio.to_thread(
        _apply_post_processing_to_file, safe_name, tempo_factor, pp_voice_enhancement, target_lufs
    )

    if new_filename == safe_name and tempo_factor == 1.0 and not pp_voice_enhancement and target_lufs == -16.0:
        return _error_html(request, "No post-processing changes requested")

    safe_new = quote(new_filename, safe="")
    return HTMLResponse(
        f'<div data-audio-filename="{html.escape(new_filename)}">'
        f'<audio class="tts-audio-hidden" src="/api/audio/{safe_new}"></audio>'
        f'<div class="status-message success">Post-processing applied</div>'
        f"</div>"
    )


# ====================================================================
# 路由 5: 取消生成
# ====================================================================


@router.post("/cancel", summary="取消生成", description="取消正在进行的语音生成任务")
async def cancel_generation(request: Request):
    from ....model_manager import _progress_mgr

    current_eng = registry.current_engine
    was_generating = not _progress_mgr._is_complete and _progress_mgr._phase != ""
    _progress_mgr.cancel()
    logger.info(
        f"[Cancel] Generation cancel requested (engine: {current_eng}, was generating: {was_generating})"
    )
    return {"status": "ok", "message": "已发送取消请求"}
