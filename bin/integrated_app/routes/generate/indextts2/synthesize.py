import contextlib
import os
import time

import numpy as np
from fastapi import File, Form, Request, UploadFile

from ....config import MAX_TEXT_LENGTH, SAVE_DIR
from ..utils import (
    _execute_generation,
    pre_validate,
    router,
    save_uploaded_audio,
)


@router.post("/indextts2", summary="IndexTTS2 合成", description="使用 IndexTTS2 引擎进行语音合成")
async def generate_indextts2(
    request: Request,
    text: str = Form(""),
    lang: str = Form("Auto"),
    ref_audio: UploadFile | None = File(None),
    ref_text: str = Form(""),
    seed: int = Form(0),
    emo_text: str = Form(""),
    emo_audio: UploadFile | None = File(None),
    emo_happy: float = Form(0.0),
    emo_angry: float = Form(0.0),
    emo_sad: float = Form(0.0),
    emo_afraid: float = Form(0.0),
    emo_disgusted: float = Form(0.0),
    emo_melancholic: float = Form(0.0),
    emo_surprised: float = Form(0.0),
    emo_calm: float = Form(0.0),
    emo_alpha: float = Form(0.8),
    emo_alpha_text: float = Form(0.8),
    emo_alpha_audio: float = Form(0.8),
    target_duration: float = Form(0.0),
    tempo_factor: float = Form(1.0),
    voice_enhancement: str = Form("false"),
    target_lufs: float = Form(-16.0),
):
    err = pre_validate(request, "indextts2", text, MAX_TEXT_LENGTH)
    if err:
        return err

    from ....generation import split_text_for_tts
    from ....model_registry import registry

    engine = registry.get_current_engine()

    ref_audio_path = None
    emo_audio_path = None

    ref_audio_path, err = await save_uploaded_audio(request, ref_audio)
    if err:
        return err

    emo_audio_path, err = await save_uploaded_audio(request, emo_audio)
    if err:
        return err

    emotion_mode: str | None = None
    emotion_data: str | dict[str, float] | None = None
    emotion_alpha: float = emo_alpha
    if emo_text and emo_text.strip():
        emotion_mode = "text"
        emotion_data = emo_text.strip()
        emotion_alpha = emo_alpha_text
    elif emo_audio_path:
        emotion_mode = "audio"
        emotion_data = emo_audio_path
        emotion_alpha = emo_alpha_audio
    else:
        emotion_dict = {
            "happy": emo_happy,
            "angry": emo_angry,
            "sad": emo_sad,
            "afraid": emo_afraid,
            "disgusted": emo_disgusted,
            "melancholic": emo_melancholic,
            "surprised": emo_surprised,
            "calm": emo_calm,
        }
        if any(v > 0 for v in emotion_dict.values()):
            emotion_mode = "vector"
            emotion_data = emotion_dict

    target_dur = target_duration if target_duration > 0 else None

    def _run():
        segments = split_text_for_tts(text)
        all_audio = []
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            infer_kwargs = {
                "text": seg,
                "spk_audio_prompt": ref_audio_path or "",
                "output_path": None,
                "verbose": False,
            }
            if emotion_data is not None:
                if emotion_mode == "text":
                    infer_kwargs["emo_text"] = emotion_data
                    infer_kwargs["use_emo_text"] = True
                elif emotion_mode == "audio":
                    infer_kwargs["emo_audio_prompt"] = emotion_data
                elif emotion_mode == "vector":
                    infer_kwargs["emo_vector"] = list(emotion_data.values())
            infer_kwargs["emo_alpha"] = emotion_alpha
            if target_dur is not None:
                infer_kwargs["target_duration"] = target_dur
            if seed > 0:
                infer_kwargs["seed"] = seed

            result_path = engine.infer(**infer_kwargs)
            if result_path and os.path.exists(result_path):
                import scipy.io.wavfile as wavfile

                sr, data = wavfile.read(result_path)
                if data.dtype != np.int16:
                    data = (data.astype(np.float32) * 32768.0).clip(-32768, 32767).astype(np.int16)
                all_audio.append(data)
                with contextlib.suppress(OSError):
                    os.remove(result_path)

        if not all_audio:
            return None, "生成失败：未产生任何音频数据"

        combined = np.concatenate(all_audio) if len(all_audio) > 1 else all_audio[0]
        timestamp = int(time.time())
        filename = f"indextts2_{timestamp}.wav"
        output_path = os.path.join(SAVE_DIR, filename)
        import scipy.io.wavfile as wavfile

        wavfile.write(output_path, 44100, combined)
        return (44100, "wav", filename), "IndexTTS 2.0 生成完成"

    return await _execute_generation(
        request,
        text=text,
        run_fn=_run,
        endpoint_name="IndexTTS2",
        voice_or_persona="",
        model_type="IndexTTS 2.0",
        engine="indextts2",
        tempo_factor=tempo_factor,
        voice_enhancement=voice_enhancement,
        target_lufs=target_lufs,
    )
