# -*- coding: utf-8 -*-
"""音色管理：保存、加载、删除、列表查询、嵌入缓存等"""

import os
import re
import logging
from datetime import datetime
from typing import List, Optional, Tuple

import torch

from .config import (
    PERSONA_DIR, OFFICIAL_SPEAKERS, OFFICIAL_SPEAKER_INFO, _OFFICIAL_SPEAKERS_ORDERED, _PERSONA_NAME_RE,
)
from .exceptions import PersonaError
from .model_manager import voxcpm_model, _persona_embedding_cache
from .generation import preprocess_and_save_temp
from .persona_metadata import (
    PersonaMetadata, load_persona_metadata, save_persona_metadata,
    PersonaExporter, get_all_tags, get_categories,
)

logger = logging.getLogger("tts_multimodel")


def _validate_persona_name(name: str) -> Tuple[bool, str]:
    """验证音色名称合法性，防止路径遍历和注入"""
    if not name:
        return False, "名称不能为空"
    if not _PERSONA_NAME_RE.match(name):
        return False, "名称格式不合法（仅支持字母、数字、下划线、连字符、中文，1-50字符）"
    return True, ""


def fn_save_persona(name: str, audio_input, ref_text: str, overwrite: bool = False) -> Tuple[str, bool]:
    """保存音色到音色库（固化）"""
    if not name or audio_input is None:
        return "❌ 失败：需输入名称及音频", False

    # 输入验证
    valid, err_msg = _validate_persona_name(name)
    if not valid:
        return f"❌ {err_msg}", False

    try:
        # 使用 realpath 防止路径遍历
        wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
        txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")
        wav_real = os.path.realpath(wav_path)
        if not wav_real.startswith(os.path.realpath(PERSONA_DIR)):
            return "❌ 非法路径", False
        # 名称冲突检测
        existing = os.path.exists(wav_path) or os.path.exists(os.path.join(PERSONA_DIR, f"{name}.pt"))
        if existing and not overwrite:
            return f"⚠️ 音色 [{name}] 已存在，再次点击保存将覆盖原有音色", True
        tmp_p, sr_p, wav_p = preprocess_and_save_temp(audio_input, f"{name}.wav")
        os.replace(tmp_p, wav_path)
        
        # Create and save metadata
        meta = PersonaMetadata(
            name=name,
            description=ref_text if ref_text else "",
            voice_type="",
            traits="",
            created_at=datetime.now().isoformat(),
        )
        save_persona_metadata(PERSONA_DIR, name, meta)
        
        # VoxCPM2 内部使用 .model 访问原始方法
        items = voxcpm_model.model.create_voice_clone_prompt(ref_audio=(wav_p, sr_p), ref_text=ref_text if ref_text else "", x_vector_only_mode=False)
        payload = {"items": [{"ref_code": it.ref_code, "ref_spk_embedding": it.ref_spk_embedding, "x_vector_only_mode": it.x_vector_only_mode, "icl_mode": it.icl_mode, "ref_text": it.ref_text} for it in items]}
        torch.save(payload, os.path.join(PERSONA_DIR, f"{name}.pt"))
        return f"✅ 音色 [{name}] 已成功固化！", False
    except Exception as e:
        logger.error(f"音色固化失败: {e}")
        return f"❌ 固化失败: {str(e)}", False


def get_persona_list(include_official: bool = False, search_keyword: str = "") -> List[str]:
    """获取音色列表，可选择包含官方音色，支持搜索过滤"""
    wav_files = [f[:-4] for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    custom = sorted(wav_files) if wav_files else []

    if search_keyword:
        kw = search_keyword.lower()
        custom = [c for c in custom if kw in c.lower()]

    if include_official:
        official_list = ["[官方] " + OFFICIAL_SPEAKER_INFO.get(s, (s, "", "", ""))[0] + " (" + s + ")" for s in OFFICIAL_SPEAKERS]
        if search_keyword:
            kw = search_keyword.lower()
            official_list = [o for o in official_list if kw in o.lower()]
        return official_list + (custom if custom else [])
    return custom if custom else ["(暂无音色)"]


def get_total_persona_count() -> int:
    """获取自定义音色总数"""
    files = [f for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    return len(files)


def get_official_speaker_count() -> int:
    """获取官方音色数量"""
    return len(OFFICIAL_SPEAKERS)


def get_combined_persona_count() -> int:
    """获取总音色数（自定义 + 官方）"""
    return get_total_persona_count() + get_official_speaker_count()


def get_persona_detail_table(search_keyword: str = "") -> List[List[str]]:
    """获取音色详情表格数据（含官方音色）"""
    table = []

    for sid in _OFFICIAL_SPEAKERS_ORDERED:
        info = OFFICIAL_SPEAKER_INFO.get(sid, (sid, "", "", ""))
        display_name = f"[官方] {info[0]} ({sid})"
        if search_keyword:
            kw = search_keyword.lower()
            if kw not in display_name.lower() and kw not in sid.lower():
                continue
        table.append([
            display_name,
            "✅ 官方",
            "-",
            "-",
            f"音色类型：{info[2]} | 特点：{info[3]}",
        ])

    files = [f.replace(".wav", "") for f in os.listdir(PERSONA_DIR) if f.endswith(".wav")]
    files = sorted(files)

    if search_keyword:
        kw = search_keyword.lower()
        files = [f for f in files if kw in f.lower()]

    for name in files:
        pt_path = os.path.join(PERSONA_DIR, f"{name}.pt")
        wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
        txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")

        has_pt = "✅ 已固化" if os.path.exists(pt_path) else "❌ 未固化"
        has_wav = "✅" if os.path.exists(wav_path) else "❌"

        ref_text = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                ref_text = f.read()
            if len(ref_text) > 50:
                ref_text = ref_text[:50] + "..."

        stat = os.stat(wav_path) if os.path.exists(wav_path) else None
        wav_size = f"{stat.st_size / 1024:.1f} KB" if stat else "-"
        wav_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M") if stat else "-"

        table.append([
            name,
            has_pt,
            wav_size,
            wav_time,
            ref_text if ref_text else "-"
        ])

    if not table:
        table = [["暂无音色", "-", "-", "-", "-"]]
    return table


def get_persona_desc(name: str) -> str:
    """获取音色描述信息"""
    if name in OFFICIAL_SPEAKERS:
        info = OFFICIAL_SPEAKER_INFO.get(name, ("", "", "", ""))
        return f"🎙️ **{info[0]} ({name})**\n\n**音色类型**：{info[2]}\n**声音特点**：{info[3]}\n\n**详细说明**：{info[1]}"
    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    if os.path.exists(wav_path):
        return f"🎵 **{name}**（自定义音色）\n\n自定义音色，适用于个性化语音合成。"
    return ""


def load_persona_embedding(name: str) -> Optional[Tuple]:
    """加载已保存音色的预计算嵌入数据，支持官方音色"""
    cached = _persona_embedding_cache.get(name)
    if cached is not None:
        return cached

    if name in OFFICIAL_SPEAKERS:
        result = (None, "__official__", name)
        _persona_embedding_cache.put(name, result)
        return result

    pt_path = os.path.join(PERSONA_DIR, f"{name}.pt")
    wav_path = os.path.join(PERSONA_DIR, f"{name}.wav")
    txt_path = os.path.join(PERSONA_DIR, f"{name}.txt")

    wav_exists = os.path.exists(wav_path)
    pt_exists = os.path.exists(pt_path)
    txt_exists = os.path.exists(txt_path)

    ref_text = ""
    if txt_exists:
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read()

    if pt_exists and wav_exists:
        vcp_data = torch.load(pt_path, map_location="cpu", weights_only=True)
        result = (vcp_data, wav_path, ref_text)
    elif wav_exists:
        result = (None, wav_path, ref_text)
    else:
        return None

    _persona_embedding_cache.put(name, result)
    return result


def get_persona_map() -> dict:
    """获取音色名称到 wav 路径的映射"""
    persona_map = {}
    if not os.path.exists(PERSONA_DIR):
        return persona_map
    for f in os.listdir(PERSONA_DIR):
        if f.endswith(".wav"):
            name = f[:-4]
            wav_path = os.path.join(PERSONA_DIR, f)
            persona_map[name] = {"wav": wav_path}
    return persona_map
