# -*- coding: utf-8 -*-
"""VoxCPM2 引擎：声音设计、可控克隆、极致克隆、剧本工坊"""

import os
import re
import time
import logging

import numpy as np

from ..config import SAVE_DIR, PERSONA_DIR
from ..model_manager import voxcpm_model, voxcpm_asr
from ..generation import _save_wav_compatible
from ..persona_manager import get_persona_map
from ..exceptions import EngineSwitchError, GenerationError, tts_error_handler

logger = logging.getLogger("tts_multimodel")


@tts_error_handler
def fn_voxcpm_design(text, instruction):
    """VoxCPM2 声音设计"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        wav = _voxcpm_model.generate(
            text=text,
            normalize=True,
            cfg_value=2.0,
            inference_timesteps=10,
            denoise=True,
            retry_badcase=False,
        )
        logger.info(f"[VoxCPM生成] wav 类型: {type(wav)}, 形状: {wav.shape if hasattr(wav, 'shape') else 'N/A'}, dtype: {wav.dtype if hasattr(wav, 'dtype') else 'N/A'}")
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_design_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        logger.info(f"[VoxCPM生成] 音频已保存: {out_path}")
        return (48000, wav), "生成成功！"
    except Exception as e:
        import traceback
        error_msg = f"VoxCPM 生成失败: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[VoxCPM生成] {error_msg}")
        raise GenerationError(error_msg)


@tts_error_handler
def fn_voxcpm_clone(text, instruction, ref_audio_path):
    """VoxCPM2 可控克隆"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        wav = _voxcpm_model.generate(
            text=text,
            reference_wav_path=ref_audio_path if ref_audio_path else None,
            normalize=True,
            cfg_value=2.0,
            inference_timesteps=10,
            denoise=True,
            retry_badcase=False,
        )
        logger.info(f"[VoxCPM生成] wav 类型: {type(wav)}, 形状: {wav.shape if hasattr(wav, 'shape') else 'N/A'}, dtype: {wav.dtype if hasattr(wav, 'dtype') else 'N/A'}")
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_clone_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        logger.info(f"[VoxCPM生成] 音频已保存: {out_path}")
        return (48000, wav), "生成成功！"
    except Exception as e:
        import traceback
        error_msg = f"VoxCPM 生成失败: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[VoxCPM生成] {error_msg}")
        raise GenerationError(error_msg)


@tts_error_handler
def fn_voxcpm_ultimate_clone(text, instruction, ref_audio_path, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed):
    """VoxCPM2 极致克隆"""
    from ..model_manager import voxcpm_model as _voxcpm_model, voxcpm_asr as _voxcpm_asr
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    # ASR 识别参考音频文本
    ref_text = ""
    if ref_audio_path:
        try:
            res = _voxcpm_asr.generate(input=ref_audio_path)
            if res and len(res) > 0 and "text" in res[0]:
                ref_text = res[0]["text"]
        except Exception:
            ref_text = ""
    # 极致克隆生成
    wav = _voxcpm_model.generate(
        text=text,
        reference_wav_path=ref_audio_path if ref_audio_path else None,
        normalize=bool(advanced_norm),
        cfg_value=advanced_cfg,
        inference_timesteps=advanced_steps,
        denoise=bool(advanced_denoise),
        retry_badcase=False,
    )
    # 保存到 output 文件夹
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_ultimate_{timestamp}.wav")
    _save_wav_compatible(wav, out_path, 48000)
    return (48000, wav), ref_text


@tts_error_handler
def fn_voxcpm_script_studio(script_text, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed, lang="中文"):
    """VoxCPM2 剧本工坊"""
    from ..model_manager import voxcpm_model as _voxcpm_model, voxcpm_asr as _voxcpm_asr
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        persona_map = get_persona_map()
        lines = script_text.strip().split("\n")
        combined_wav = []
        sr_final = 48000
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"\[([^\]]+)\](?:\(([^)]+)\))?\s*(.*)", line)
            if not match:
                continue
            role_name = match.group(1).strip()
            emotion = match.group(2)
            content = match.group(3).strip()
            role_lower = role_name.lower()
            persona_key = next((k for k in persona_map if k.lower() == role_lower), None)
            if persona_key:
                ref_wav = persona_map[persona_key]["wav"]
            else:
                continue
            # 生成音频
            wav = _voxcpm_model.generate(
                text=content,
                reference_wav_path=ref_wav,
                normalize=bool(advanced_norm),
                cfg_value=advanced_cfg,
                inference_timesteps=advanced_steps,
                denoise=bool(advanced_denoise),
                retry_badcase=False,
            )
            combined_wav.append(wav)
            # 添加 0.3 秒静音间隔
            combined_wav.append(np.zeros(int(48000 * 0.3)))
            sr_final = 48000
        if not combined_wav:
            return None, "❌ 匹配失败：请检查剧本格式或音色库"
        return (sr_final, np.concatenate(combined_wav)), "✅ 生成成功！"
    except Exception as e:
        logger.error(f"[VoxCPM剧本工坊] 错误: {e}")
        return None, f"❌ 生成失败: {e}"
