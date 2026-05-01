# -*- coding: utf-8 -*-
"""FastAPI 端点：模型管理、音色管理、生成 API"""

import os
import re
import time
import base64
import logging
import glob

from .config import PERSONA_DIR, MODEL_TYPE_ALIASES
from fastapi.responses import FileResponse
from .exceptions import TTSError
from .model_manager import (
    load_model, unload_model, current_model, current_type, current_size,
    _gen_tracker, _persona_embedding_cache,
)
from .generation import save_audio
from .utils import cleanup_temp_files
from .persona_manager import get_persona_list, get_persona_desc
from .engines.qwen3tts_engine import fn_voice_clone_with_persona

logger = logging.getLogger("tts_multimodel")


def api_load_model(m_type="声音设计", size="1.7B"):
    """API: 加载模型"""
    try:
        resolved = MODEL_TYPE_ALIASES.get(m_type, m_type)
        m = load_model(resolved, size)
        if m is not None:
            return {"status": "ok", "message": f"Model loaded: {resolved} ({size})"}
        else:
            return {"status": "error", "message": "Model load returned None"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def api_unload_model():
    """API: 卸载模型"""
    try:
        unload_model()
        return {"status": "ok", "message": "Model unloaded, VRAM released"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def api_model_status():
    """API: 查询模型状态"""
    return {
        "loaded": current_model is not None,
        "type": current_type,
        "size": current_size,
    }


def register_api_endpoints(app):
    """在 FastAPI app 上注册所有 API 端点"""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(TTSError)
    async def tts_error_handler_api(request, exc):
        return JSONResponse(
            {"status": "error", "error_code": exc.error_code, "message": str(exc)},
            status_code=400,
        )

    @app.post("/api/load_model")
    async def _api_load_model(request: Request):
        try:
            body = await request.json()
            m_type = body.get("m_type", "声音设计")
            size = body.get("size", "1.7B")
            resolved = MODEL_TYPE_ALIASES.get(m_type, m_type)
            m = load_model(resolved, size)
            if m is not None:
                return JSONResponse({"status": "ok", "message": f"Model loaded: {resolved} ({size})"})
            else:
                return JSONResponse({"status": "error", "message": "Model load returned None"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})

    @app.post("/api/unload_model")
    async def _api_unload_model():
        try:
            unload_model()
            return JSONResponse({"status": "ok", "message": "Model unloaded, VRAM released"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})

    @app.get("/api/model_status")
    async def _api_model_status():
        return JSONResponse({
            "loaded": current_model is not None,
            "type": current_type,
            "size": current_size,
        })

    @app.get("/api/persona_list")
    async def _api_persona_list():
        return JSONResponse({"personas": get_persona_list()})

    @app.delete("/api/persona/{name}")
    async def _api_delete_persona(name: str):
        if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]+$', name):
            return JSONResponse({"status": "error", "message": "Invalid persona name"})
        try:
            for ext in [".wav", ".txt", ".pt"]:
                p = os.path.join(PERSONA_DIR, f"{name}{ext}")
                real_path = os.path.realpath(p)
                if not real_path.startswith(os.path.realpath(PERSONA_DIR)):
                    return JSONResponse({"status": "error", "message": "Path traversal detected"})
                if os.path.exists(p):
                    os.remove(p)
            if name in _persona_embedding_cache:
                del _persona_embedding_cache[name]
            return JSONResponse({"status": "ok", "message": f"音色 [{name}] 已删除"})
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)})

    @app.post("/api/generate")
    async def _api_generate(request: Request):
        import numpy as np
        try:
            body = await request.json()
            mode = body.get("mode", "voice_clone")
            text = body.get("text", "")
            lang = body.get("lang", "Auto")
            size = body.get("size", "1.7B")
            persona_name = body.get("persona_name", "(暂无音色)")
            speaker = body.get("speaker", "Vivian")
            instruct = body.get("instruct")
            ref_audio_path = body.get("ref_audio_path")
            output_format = body.get("format", "wav")

            if not text.strip():
                return JSONResponse({"status": "error", "message": "文本不能为空"}, status_code=400)

            _gen_tracker.start_generation()
            start_time = time.time()
            try:
                if mode in ("voice_clone", "clone"):
                    if persona_name and persona_name != "(暂无音色)":
                        audio_result, msg = fn_voice_clone_with_persona(text, lang, persona_name, size)
                    elif ref_audio_path and os.path.exists(ref_audio_path):
                        m = load_model("语音克隆", size)
                        al, sr = m.generate_voice_clone(text=text, language=lang, ref_audio=ref_audio_path, ref_text="")
                        save_audio(al[0], sr, f"api_clone_{size}", format=output_format)
                        audio_result = (sr, al[0])
                        msg = f"完成！({size}核心，上传音频)"
                    else:
                        return JSONResponse({"status": "error", "message": "需提供 persona_name 或 ref_audio_path"}, status_code=400)
                elif mode == "voice_design":
                    m = load_model("声音设计")
                    al, sr = m.generate_voice_design(text=text, language=lang, instruct=instruct)
                    save_audio(al[0], sr, "api_design", format=output_format)
                    audio_result = (sr, al[0])
                    msg = "生成成功！"
                elif mode in ("custom_voice", "official"):
                    m = load_model("官方精品", size)
                    al, sr = m.generate_custom_voice(text=text, language=lang, speaker=speaker.lower(), instruct=instruct)
                    save_audio(al[0], sr, f"api_custom_{speaker}", format=output_format)
                    audio_result = (sr, al[0])
                    msg = f"生成成功！({speaker})"
                else:
                    return JSONResponse({"status": "error", "message": f"未知模式: {mode}"}, status_code=400)

                elapsed = time.time() - start_time
                _gen_tracker.end_generation(elapsed)

                if audio_result is None:
                    return JSONResponse({"status": "error", "message": msg})

                sr_val, wav_val = audio_result
                audio_b64 = base64.b64encode(wav_val.tobytes()).decode() if wav_val is not None else None
                return JSONResponse({
                    "status": "ok",
                    "message": msg,
                    "elapsed": round(elapsed, 2),
                    "sample_rate": sr_val,
                    "audio_base64": audio_b64,
                    "format": output_format,
                })
            except TTSError as e:
                return JSONResponse({"status": "error", "error_code": e.error_code, "message": str(e)}, status_code=400)
            except Exception as e:
                return JSONResponse({"status": "error", "error_code": "UNKNOWN_ERROR", "message": str(e)}, status_code=500)
            finally:
                cleanup_temp_files()
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"请求解析失败: {e}"}, status_code=400)

    @app.get("/api/persona_detail")
    async def _api_persona_detail(name: str):
        if not name:
            return JSONResponse({"personas": get_persona_list()}, status_code=400)
        desc = get_persona_desc(name)
        return JSONResponse({"name": name, "description": desc})

    @app.get("/api/speaker_sample/{key}")
    async def _api_speaker_sample(key: str):
        """Serve pre-recorded sample audio for official speakers"""
        from .config import PROJECT_ROOT
        # Map speaker keys to available sample files
        samples_dir = os.path.join(PROJECT_ROOT, "faster-qwen3-tts-main", "samples", "parity")
        # Search for any wav file matching the speaker key
        if not os.path.isdir(samples_dir):
            return JSONResponse({"status": "error", "message": "Samples directory not found"}, status_code=404)
        pattern = os.path.join(samples_dir, f"*{key.lower()}*.wav")
        matches = glob.glob(pattern)
        if matches:
            return FileResponse(matches[0], media_type="audio/wav", filename=os.path.basename(matches[0]))
        return JSONResponse({"status": "error", "message": f"No sample found for speaker: {key}"}, status_code=404)
