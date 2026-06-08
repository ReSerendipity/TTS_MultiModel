import os
import re
import time

import numpy as np

from ._base import (
    GenerationError,
    SAVE_DIR,
    _advanced_kwargs,
    _progress_mgr,
    _save_wav_compatible,
    cleanup_temp_files,
    get_persona_map,
    logger,
)
from .decorators import with_generation_context


@with_generation_context(phase_name="VoxCPM剧本工坊", cleanup_fn=cleanup_temp_files)
def fn_voxcpm_script_studio(
    script_text: str, advanced_cfg: float, advanced_norm: bool, advanced_denoise: float,
    advanced_steps: int, advanced_seed: int, lang: str = "中文",
    persona_map_with_wav: dict | None = None,
) -> tuple[tuple | None, str]:
    from ...model_registry import registry

    start_time = time.time()
    persona_map = get_persona_map()
    lines = script_text.strip().split("\n")
    valid_lines = [line for line in lines if "]" in line]
    total_roles = len(valid_lines)

    _progress_mgr.start(total_segments=total_roles, phase="剧本合成中...")

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

        ref_wav = persona_map[persona_key]["wav"]
        wav = registry.voxcpm_model.generate(
            text=content,
            reference_wav_path=ref_wav,
            normalize=bool(advanced_norm),
            cfg_value=advanced_cfg,
            inference_timesteps=advanced_steps,
            denoise=bool(advanced_denoise),
            min_len=2,
            **_advanced_kwargs(),
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
