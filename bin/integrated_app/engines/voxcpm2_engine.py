"""VoxCPM2 引擎：声音设计、可控克隆、极致克隆、剧本工坊"""

import logging
import os
import re
import time

import numpy as np

from ..config import SAVE_DIR
from ..exceptions import EngineSwitchError, GenerationError, tts_error_handler
from ..generation import _save_wav_compatible, split_text_for_tts
from ..model_manager import _gen_tracker, _progress_mgr
from ..persona_manager import get_persona_map
from ..utils import cleanup_temp_files

logger = logging.getLogger("tts_multimodel")

# ==================== 高级生成参数（可运行时修改） ====================
_ADVANCED_PARAMS = {
    "max_len": 4096,
    "retry_badcase": True,
    "retry_badcase_max_times": 3,
    "retry_badcase_ratio_threshold": 6.0,
    "trim_silence_vad": True,
}


def get_advanced_params():
    """Return a copy of the current advanced generation parameters."""
    return dict(_ADVANCED_PARAMS)


def update_advanced_params(params_dict):
    """Update the global advanced generation parameters dict.

    Only known keys are accepted; unknown keys are silently ignored.
    """
    global _ADVANCED_PARAMS
    for key in _ADVANCED_PARAMS:
        if key in params_dict:
            _ADVANCED_PARAMS[key] = params_dict[key]
    logger.info(f"[VoxCPM2] Advanced params updated: {_ADVANCED_PARAMS}")


# ==================== 声音设计 ====================

def fn_voxcpm_design(text: str, instruction: str,
                     cfg_value: float = 2.0, inference_timesteps: int = 10,
                     denoise: bool = True,
                     ref_audio_path: str | None = None) -> tuple[tuple | None, str]:
    """VoxCPM2 声音设计，支持参考音色"""
    from ..model_manager import _check_model_ready
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, instruction, cfg_value, inference_timesteps, denoise, ref_audio_path):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_design_impl(text, instruction, start_time,
                                          cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                                          denoise=denoise, ref_audio_path=ref_audio_path)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM声音设计] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, instruction, cfg_value, inference_timesteps, denoise, ref_audio_path)


def _fn_voxcpm_design_impl(text: str, instruction: str, start_time: float = 0,
                           cfg_value: float = 2.0, inference_timesteps: int = 10,
                           denoise: bool = True,
                           ref_audio_path: str | None = None) -> tuple[tuple | None, str]:
    """VoxCPM2 声音设计核心实现，使用官方 reference_wav_path 参数"""
    from ..model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    _progress_mgr.start(total_segments=total, phase="VoxCPM2 推理中...")

    def _build_text(seg_text):
        if instruction and instruction.strip():
            return "(" + instruction.strip() + ")" + seg_text
        return seg_text

    def _gen_kwargs(ref_path=None):
        kwargs = dict(
            normalize=True,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
            denoise=denoise,
            min_len=2,
            max_len=_ADVANCED_PARAMS["max_len"],
            retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
            retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
            retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
        )
        if ref_path:
            kwargs["reference_wav_path"] = ref_path
        return kwargs

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        logger.info(f"[VoxCPM声音设计] 第 1/1 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")
        wav = _voxcpm_model.generate(
            text=_build_text(segments[0]),
            **_gen_kwargs(ref_audio_path)
        )
        duration_sec = len(wav) / 48000 if len(wav) > 0 else 0
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_design_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        logger.info(f"[VoxCPM声音设计] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        return (48000, wav, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒。"

    # Multi-segment synthesis using reference_wav_path for voice consistency
    logger.info(f"[VoxCPM声音设计] 多段合成: {total} 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")
    audio_segments = []
    for idx, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM声音设计] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM声音设计] 第 1/{total} 段...")

        wav = _voxcpm_model.generate(
            text=_build_text(seg),
            **_gen_kwargs(ref_audio_path)
        )
        audio_segments.append(wav)

    if not audio_segments:
        raise GenerationError("VoxCPM2 声音设计生成失败：无有效音频段")

    merged = np.concatenate(audio_segments)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_design_{timestamp}.wav")
    _save_wav_compatible(merged, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(merged) / 48000
    logger.info(f"[VoxCPM声音设计] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，分段: {total}")
    return (48000, merged, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒，分段: {total}。"


# ==================== 可控克隆 ====================

def fn_voxcpm_clone(text: str, instruction: str, ref_audio_path: str | None,
                    cfg_value: float = 2.0, inference_timesteps: int = 10,
                    denoise: bool = True, normalize: bool = True) -> tuple[tuple | None, str]:
    """VoxCPM2 可控克隆 - 使用官方 reference_wav_path 参数"""
    from ..model_manager import _check_model_ready
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, instruction, ref_audio_path, cfg_value, inference_timesteps, denoise, normalize):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_clone_impl(text, instruction, ref_audio_path, start_time,
                                         cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                                         denoise=denoise, normalize=normalize)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM可控克隆] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, instruction, ref_audio_path, cfg_value, inference_timesteps, denoise, normalize)


def _fn_voxcpm_clone_impl(text: str, instruction: str, ref_audio_path: str | None, start_time: float = 0,
                           cfg_value: float = 2.0, inference_timesteps: int = 10,
                           denoise: bool = True, normalize: bool = True) -> tuple[tuple | None, str]:
    """VoxCPM2 可控克隆核心实现 - 使用官方 reference_wav_path 参数（音色克隆）"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    from ..prompt_cache import load_cached_prompt

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    if ref_audio_path:
        logger.info(f"[VoxCPM可控克隆] 使用参考音频: {ref_audio_path}")
        if not os.path.isfile(ref_audio_path):
            raise GenerationError(f"参考音频文件不存在: {ref_audio_path}")

    # Prompt Cache: 尝试从持久化缓存加载参考音频的 prompt_cache
    _progress_mgr.update_phase("加载音色缓存...")
    cached_prompt = None
    if ref_audio_path:
        cached_prompt = load_cached_prompt(ref_audio_path)
        if cached_prompt is not None:
            logger.info("[VoxCPM可控克隆] 使用缓存的音色特征，跳过重复编码")

    _progress_mgr.start(total_segments=total, phase="VoxCPM2 推理中...")

    def _build_text(seg_text):
        if instruction and instruction.strip():
            return "(" + instruction.strip() + ")" + seg_text
        return seg_text

    def _gen_kwargs(seg_text, ref_path=None, prompt_cache=None):
        kwargs = dict(
            text=seg_text,
            normalize=normalize,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
            denoise=denoise,
            min_len=2,
            max_len=_ADVANCED_PARAMS["max_len"],
            retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
            retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
            retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
        )
        if prompt_cache is not None:
            kwargs["prompt_cache"] = prompt_cache
        elif ref_path:
            kwargs["reference_wav_path"] = ref_path
        return kwargs

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        logger.info(f"[VoxCPM可控克隆] 第 1/1 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")
        wav = _voxcpm_model.generate(**_gen_kwargs(_build_text(segments[0]), ref_audio_path, cached_prompt))
        duration_sec = len(wav) / 48000 if len(wav) > 0 else 0
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_clone_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        logger.info(f"[VoxCPM可控克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        return (48000, wav, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒。"

    audio_segments = []
    for idx, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM可控克隆] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM可控克隆] 第 1/{total} 段...")

        wav = _voxcpm_model.generate(**_gen_kwargs(_build_text(seg), ref_audio_path, cached_prompt))
        audio_segments.append(wav)

    if not audio_segments:
        raise GenerationError("VoxCPM2 可控克隆生成失败：无有效音频段")

    merged = np.concatenate(audio_segments)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_clone_{timestamp}.wav")
    _save_wav_compatible(merged, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(merged) / 48000
    logger.info(f"[VoxCPM可控克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，分段: {total}")
    return (48000, merged, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒，分段: {total}。"



# ==================== 极致克隆 ====================

def fn_voxcpm_ultimate_clone(
    text: str, instruction: str, ref_audio_path: str | None,
    advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int,
) -> tuple[tuple | None, str]:
    """VoxCPM2 极致克隆（ref_continuation 组合模式）"""
    from ..model_manager import _check_model_ready
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, instruction, ref_audio_path, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        start_time = time.time()
        try:
            return _fn_voxcpm_ultimate_clone_impl(
                text, instruction, ref_audio_path,
                advanced_cfg, advanced_norm, advanced_denoise,
                advanced_steps, advanced_seed, start_time,
            )
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM极致克隆] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, instruction, ref_audio_path, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed)


def _fn_voxcpm_ultimate_clone_impl(
    text: str, instruction: str, ref_audio_path: str | None,
    advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int, start_time: float = 0,
) -> tuple[tuple | None, str]:
    """VoxCPM2 极致克隆核心实现 - prompt_wav_path + prompt_text 组合模式（官方 continuation API）"""
    import tempfile

    from ..model_manager import voxcpm_asr as _voxcpm_asr
    from ..model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.start(total_segments=1, phase="ASR 识别参考音频...")

    # ZipEnhancer降噪处理（仅用于ASR识别，不用于音色克隆）
    processed_ref_path_for_asr = ref_audio_path
    if ref_audio_path and hasattr(_voxcpm_model, 'denoiser') and _voxcpm_model.denoiser:
        _progress_mgr.update_phase("参考音频降噪...")
        try:
            with tempfile.NamedTemporaryFile(suffix="_denoised.wav", delete=False) as tmp:
                processed_ref_path_for_asr = tmp.name
            _voxcpm_model.denoiser.enhance(ref_audio_path, processed_ref_path_for_asr, normalize_loudness=True)
            logger.info(f"[VoxCPM极致克隆] ZipEnhancer降噪完成: {ref_audio_path} -> {processed_ref_path_for_asr}")
        except Exception as e:
            logger.warning(f"[VoxCPM极致克隆] ZipEnhancer降噪失败，使用原始音频: {e}")
            processed_ref_path_for_asr = ref_audio_path

    ref_text = ""
    # 使用降噪后的音频进行ASR识别（提高识别准确率）
    if processed_ref_path_for_asr:
        try:
            res = _voxcpm_asr.generate(input=processed_ref_path_for_asr)
            if res and len(res) > 0 and "text" in res[0]:
                ref_text = res[0]["text"]
                logger.info(f"[VoxCPM极致克隆] ASR 识别成功: {ref_text[:50]}...")
        except Exception as e:
            logger.warning(f"[VoxCPM极致克隆] ASR 识别失败: {e}")
            ref_text = ""
        finally:
            # Clean up temp denoised file if it was created
            if processed_ref_path_for_asr != ref_audio_path and os.path.isfile(processed_ref_path_for_asr):
                import contextlib
                with contextlib.suppress(Exception):
                    os.remove(processed_ref_path_for_asr)

    # IMPORTANT: For voice cloning, ALWAYS use original reference audio
    # Denoised audio can alter voice characteristics and cause mismatch
    _progress_mgr.update_phase("准备极致克隆推理...")

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)
    _progress_mgr.start(total_segments=total, phase="VoxCPM2 极致推理中...")

    # Prepend instruction to text for controllable generation
    def _build_text(seg_text):
        if instruction and instruction.strip():
            return "(" + instruction.strip() + ")" + seg_text
        return seg_text

    if total == 1:
        _progress_mgr.advance_segment("推理生成中...")
        logger.info("[VoxCPM极致克隆] 第 1/1 段...")
        # ref_continuation 组合模式：同时传入 prompt_wav_path + prompt_text
        wav = _voxcpm_model.generate(
            text=_build_text(segments[0]),
            prompt_wav_path=ref_audio_path if ref_audio_path else "",
            prompt_text=ref_text if ref_text else "",
            normalize=bool(advanced_norm),
            cfg_value=advanced_cfg,
            inference_timesteps=advanced_steps,
            denoise=bool(advanced_denoise),
            min_len=2,
            max_len=_ADVANCED_PARAMS["max_len"],
            retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
            retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
            retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
        )
        timestamp = int(time.time())
        out_path = os.path.join(SAVE_DIR, f"voxcpm_ultimate_{timestamp}.wav")
        _save_wav_compatible(wav, out_path, 48000)
        filename = os.path.basename(out_path)
        _progress_mgr.complete()
        duration_sec = len(wav) / 48000
        logger.info(f"[VoxCPM极致克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
        return (48000, wav, filename), f"生成成功！参考文本: {ref_text[:50]}..." if ref_text else "生成成功！"

    # Multi-segment synthesis using ref_continuation mode
    audio_segments = []
    for idx, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM极致克隆] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM极致克隆] 第 1/{total} 段...")

        wav = _voxcpm_model.generate(
            text=_build_text(seg),
            prompt_wav_path=ref_audio_path if ref_audio_path else "",
            prompt_text=ref_text if ref_text else "",
            normalize=bool(advanced_norm),
            cfg_value=advanced_cfg,
            inference_timesteps=advanced_steps,
            denoise=bool(advanced_denoise),
            min_len=2,
            max_len=_ADVANCED_PARAMS["max_len"],
            retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
            retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
            retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
        )
        audio_segments.append(wav)

    if not audio_segments:
        raise GenerationError("VoxCPM2 极致克隆生成失败：无有效音频段")

    merged = np.concatenate(audio_segments)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_ultimate_{timestamp}.wav")
    _save_wav_compatible(merged, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(merged) / 48000
    logger.info(f"[VoxCPM极致克隆] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，分段: {total}")
    return (48000, merged, filename), f"生成成功！参考文本: {ref_text[:50]}..." if ref_text else "生成成功！"


# ==================== 剧本工坊 ====================

def fn_voxcpm_script_studio(
    script_text: str, advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int, lang: str = "中文",
    persona_map_with_wav: dict | None = None,
) -> tuple[tuple | None, str]:
    """VoxCPM2 剧本工坊，使用官方 reference_wav_path 参数"""
    from ..model_manager import _check_model_ready
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(script_text, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed, lang, persona_map_with_wav):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        start_time = time.time()
        valid_lines = [line for line in script_text.strip().split("\n") if "]" in line]
        _progress_mgr.start(total_segments=len(valid_lines), phase="剧本合成中...")
        try:
            return _fn_voxcpm_script_studio_impl(
                script_text, advanced_cfg, advanced_norm, advanced_denoise,
                advanced_steps, advanced_seed, lang, start_time,
                persona_map_with_wav=persona_map_with_wav,
            )
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            cleanup_temp_files()
            logger.info(f"[VoxCPM剧本工坊] 合成耗时 {elapsed:.1f} 秒")

    return _wrapped(script_text, advanced_cfg, advanced_norm, advanced_denoise, advanced_steps, advanced_seed, lang, persona_map_with_wav)


def _fn_voxcpm_script_studio_impl(
    script_text: str, advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int, lang: str, start_time: float,
    persona_map_with_wav: dict | None = None,
) -> tuple[tuple | None, str]:
    """VoxCPM2 剧本工坊核心实现，使用官方 reference_wav_path 参数"""
    from ..model_manager import voxcpm_model as _voxcpm_model

    persona_map = get_persona_map()
    lines = script_text.strip().split("\n")
    valid_lines = [line for line in lines if "]" in line]
    total_roles = len(valid_lines)
    combined_wav = []
    sr_final = 48000
    role_idx = 0

    for line in lines:
        line = line.strip()
        if not line or "]" not in line:
            continue

        role_idx += 1
        role_name_raw = line.split("]")[0].replace("[", "").strip()
        _progress_mgr.advance_segment(f"角色 [{role_name_raw}] 合成中...")

        elapsed = time.time() - start_time
        if role_idx > 1:
            avg = elapsed / (role_idx - 1)
            remaining = avg * (total_roles - role_idx + 1)
            logger.info(f"[VoxCPM剧本工坊] 第 {role_idx}/{total_roles} 角色，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM剧本工坊] 第 {role_idx}/{total_roles} 角色...")

        match = re.match(r"\[([^\]]+)\](?:\(([^)]+)\))?\s*(.*)", line)
        if not match:
            continue

        role_name = match.group(1).strip()
        _emotion = match.group(2)
        content = match.group(3).strip()
        if not content:
            continue

        role_lower = role_name.lower()
        persona_key = next((k for k in persona_map if k.lower() == role_lower), None)
        if not persona_key:
            logger.warning(f"[VoxCPM剧本工坊] 角色 [{role_name}] 在音色库中未找到，跳过")
            continue

        # Use reference_wav_path for voice cloning (official API)
        ref_wav = persona_map[persona_key]["wav"]
        wav = _voxcpm_model.generate(
            text=content,
            reference_wav_path=ref_wav,
            normalize=bool(advanced_norm),
            cfg_value=advanced_cfg,
            inference_timesteps=advanced_steps,
            denoise=bool(advanced_denoise),
            min_len=2,
            max_len=_ADVANCED_PARAMS["max_len"],
            retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
            retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
            retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
        )
        combined_wav.append(wav)
        combined_wav.append(np.zeros(int(48000 * 0.3)))
        sr_final = 48000

    if not combined_wav:
        raise GenerationError("剧本合成失败：无匹配角色或生成失败")

    res_wav = np.concatenate(combined_wav)
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_script_{timestamp}.wav")
    _save_wav_compatible(res_wav, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()

    duration_sec = len(res_wav) / 48000
    logger.info(f"[VoxCPM剧本工坊] 音频已保存: {out_path}，时长 {duration_sec:.1f}s，角色数: {role_idx}")
    return (sr_final, res_wav, filename), f"✅ 合成完成！时长 {duration_sec:.1f} 秒，角色数: {role_idx}"


# ==================== Streaming 生成 ====================

def fn_voxcpm_streaming(text: str, ref_audio_path: str | None = None,
                        cfg_value: float = 2.0, inference_timesteps: int = 10,
                        denoise: bool = True, seed: int = -1):
    """VoxCPM2 流式生成，使用官方 reference_wav_path 参数"""
    from ..model_manager import _check_model_ready
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, ref_audio_path, cfg_value, inference_timesteps, denoise, seed):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="流式准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_streaming_impl(text, ref_audio_path, start_time,
                                              cfg_value=cfg_value, inference_timesteps=inference_timesteps,
                                              denoise=denoise, seed=seed)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM流式生成] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, ref_audio_path, cfg_value, inference_timesteps, denoise, seed)


def _fn_voxcpm_streaming_impl(text: str, ref_audio_path: str | None, start_time: float = 0,
                               cfg_value: float = 2.0, inference_timesteps: int = 10,
                               denoise: bool = True, seed: int = -1):
    """VoxCPM2 流式生成核心实现，使用官方 reference_wav_path 参数"""
    from ..model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.update_phase("文本分割中...")
    segments = split_text_for_tts(text)
    total = len(segments)

    _progress_mgr.start(total_segments=total, phase="VoxCPM2 流式推理中...")

    if total == 1:
        _progress_mgr.advance_segment("流式推理生成中...")
        logger.info(f"[VoxCPM流式生成] 第 1/1 段，使用 {'reference_wav' if ref_audio_path else '默认音色'} 模式...")

        if hasattr(_voxcpm_model, 'generate_streaming'):
            return _voxcpm_model.generate_streaming(
                text=segments[0],
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                max_len=_ADVANCED_PARAMS["max_len"],
                retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
                retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
                retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
            )
        else:
            logger.warning("[VoxCPM流式生成] 模型不支持 streaming，回退到常规生成")
            wav = _voxcpm_model.generate(
                text=segments[0],
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                max_len=_ADVANCED_PARAMS["max_len"],
                retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
                retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
                retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
            )
            _progress_mgr.complete()
            return wav

    # Multi-segment streaming synthesis
    all_chunks = []
    for idx, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue

        _progress_mgr.advance_segment(f"第 {idx+1}/{total} 段推理中...")
        elapsed = time.time() - start_time
        if idx > 0:
            avg = elapsed / idx
            remaining = avg * (total - idx)
            logger.info(f"[VoxCPM流式生成] 第 {idx+1}/{total} 段，已耗时 {elapsed:.1f}s，预计剩余 {remaining:.1f}s")
        else:
            logger.info(f"[VoxCPM流式生成] 第 {idx+1}/{total} 段...")

        if hasattr(_voxcpm_model, 'generate_streaming'):
            for chunk in _voxcpm_model.generate_streaming(
                text=seg,
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                max_len=_ADVANCED_PARAMS["max_len"],
                retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
                retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
                retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
            ):
                all_chunks.append(chunk)
        else:
            wav = _voxcpm_model.generate(
                text=seg,
                reference_wav_path=ref_audio_path if ref_audio_path else "",
                normalize=True,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                denoise=denoise,
                min_len=2,
                max_len=_ADVANCED_PARAMS["max_len"],
                retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
                retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
                retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
            )
            all_chunks.append(wav)

    _progress_mgr.complete()
    return all_chunks


# ==================== LoRA 支持 ====================

def fn_voxcpm_load_lora(lora_path: str) -> bool:
    """加载 LoRA 适配器"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.load_lora(lora_path)
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 加载 LoRA 失败: {e}")
        return False


def fn_voxcpm_unload_lora() -> bool:
    """卸载 LoRA 适配器"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.unload_lora()
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 卸载 LoRA 失败: {e}")
        return False


def fn_voxcpm_set_lora_enabled(enabled: bool) -> bool:
    """设置 LoRA 启用状态"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.set_lora_enabled(enabled)
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 设置 LoRA 状态失败: {e}")
        return False


def fn_voxcpm_get_lora_state() -> dict:
    """获取 LoRA 状态字典"""
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.get_lora_state_dict()
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 获取 LoRA 状态失败: {e}")
        return {}


# ==================== Prompt 延续模式 ====================

def fn_voxcpm_prompt_continue(text: str, prompt_wav_path: str, prompt_text: str) -> tuple[tuple | None, str]:
    """VoxCPM2 Prompt 延续模式"""
    from ..model_manager import _check_model_ready
    from ..model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

    @tts_error_handler
    def _wrapped(text, prompt_wav_path, prompt_text):
        if not _check_model_ready():
            raise GenerationError("模型正在加载或切换中，请稍后再试")
        _gen_tracker.start_generation()
        _progress_mgr.start(total_segments=1, phase="Prompt 延续准备中...")
        start_time = time.time()
        try:
            return _fn_voxcpm_prompt_continue_impl(text, prompt_wav_path, prompt_text, start_time)
        finally:
            elapsed = time.time() - start_time
            _gen_tracker.end_generation(elapsed)
            _progress_mgr.schedule_reset(delay_seconds=120)
            logger.info(f"[VoxCPM Prompt延续] 生成耗时 {elapsed:.1f} 秒")

    return _wrapped(text, prompt_wav_path, prompt_text)


def _fn_voxcpm_prompt_continue_impl(text: str, prompt_wav_path: str, prompt_text: str, start_time: float = 0) -> tuple[tuple | None, str]:
    """VoxCPM2 Prompt 延续模式核心实现"""
    from ..model_manager import voxcpm_model as _voxcpm_model

    _progress_mgr.update_phase("Prompt 延续推理中...")
    logger.info(f"[VoxCPM Prompt延续] Prompt: {prompt_text[:50]}...")

    wav = _voxcpm_model.generate(
        text=text,
        prompt_wav_path=prompt_wav_path,
        prompt_text=prompt_text,
        normalize=True,
        cfg_value=2.0,
        inference_timesteps=10,
        denoise=True,
        min_len=2,
        max_len=_ADVANCED_PARAMS["max_len"],
        retry_badcase=_ADVANCED_PARAMS["retry_badcase"],
        retry_badcase_max_times=_ADVANCED_PARAMS["retry_badcase_max_times"],
        retry_badcase_ratio_threshold=_ADVANCED_PARAMS["retry_badcase_ratio_threshold"],
    )

    duration_sec = len(wav) / 48000 if len(wav) > 0 else 0
    timestamp = int(time.time())
    out_path = os.path.join(SAVE_DIR, f"voxcpm_prompt_continue_{timestamp}.wav")
    _save_wav_compatible(wav, out_path, 48000)
    filename = os.path.basename(out_path)
    _progress_mgr.complete()
    logger.info(f"[VoxCPM Prompt延续] 音频已保存: {out_path}，时长 {duration_sec:.1f}s")
    return (48000, wav, filename), f"生成成功！音频时长 {duration_sec:.1f} 秒。"



