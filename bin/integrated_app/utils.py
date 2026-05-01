# -*- coding: utf-8 -*-
"""通用工具函数"""

import os
import glob
import time
import re
from datetime import datetime

from .config import SAVE_DIR, PERSONA_DIR, OFFICIAL_SPEAKERS, OFFICIAL_SPEAKER_INFO, _AUDIO_EXTS, _ROLE_COLOR_MAP


def cleanup_temp_files():
    """清理临时音频文件"""
    try:
        for f in glob.glob(os.path.join(SAVE_DIR, "temp_*.wav")):
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass


def get_role_color(role_name):
    """获取角色对应的颜色标识"""
    clean_name = role_name.strip("[]）")
    return _ROLE_COLOR_MAP.get(clean_name, ("blue", "#3B82F6"))


def add_tag(text, tag, is_speaker=True):
    """在文本中添加角色标签"""
    if not tag or tag == "(暂无音色)":
        return text
    prefix = "\n" if text.strip() and is_speaker else ""
    result = f"{text.rstrip()}{prefix}[{tag}] "
    return result


def generate_speaker_card_grid(selected_speaker_key="Vivian"):
    """生成官方精品音色卡片网格HTML"""
    from .config import _OFFICIAL_SPEAKERS_ORDERED
    cards = []
    for key in _OFFICIAL_SPEAKERS_ORDERED:
        info = OFFICIAL_SPEAKER_INFO[key]
        display_name = info[0]
        style_tag = info[2]
        is_selected = "selected" if key == selected_speaker_key else ""
        cards.append(f'''<div class="speaker-card {is_selected}" data-speaker="{key}" onclick="selectSpeakerCard('{key}')">
    <h4 class="speaker-card-name">{display_name}</h4>
    <div class="speaker-card-tags">
        <span class="speaker-card-tag">{style_tag}</span>
        <span class="speaker-card-tag">{key}</span>
    </div>
    <div class="speaker-card-actions">
        <span class="speaker-card-btn" onclick="event.stopPropagation(); previewSpeaker('{key}')">🔊 试听</span>
        <span class="speaker-card-btn btn-use" onclick="event.stopPropagation(); useSpeaker('{key}')">使用</span>
    </div>
</div>''')
    return '<div class="speaker-card-grid">' + '\n'.join(cards) + '</div>'


def get_generation_history(search_keyword=""):
    """获取生成历史记录"""
    kw_lower = search_keyword.lower() if search_keyword else ""
    history = []
    for f in glob.glob(os.path.join(SAVE_DIR, "*.*")):
        if os.path.isdir(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in _AUDIO_EXTS:
            continue
        basename = os.path.basename(f)
        if kw_lower and kw_lower not in basename.lower():
            continue
        stat = os.stat(f)
        history.append([
            basename,
            datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            f"{stat.st_size / 1024 / 1024:.1f} MB"
        ])
    history.sort(key=lambda x: x[1], reverse=True)
    return history if history else [["暂无记录", "-", "-"]]


def get_total_history_count():
    """获取历史记录总数"""
    count = 0
    for f in glob.glob(os.path.join(SAVE_DIR, "*.*")):
        if os.path.isdir(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in _AUDIO_EXTS:
            count += 1
    return count


def get_generation_history_enhanced(search_keyword="", time_filter="all"):
    """增强的历史记录获取，支持时间筛选"""
    kw_lower = search_keyword.lower() if search_keyword else ""
    now = time.time()
    history = []
    for f in glob.glob(os.path.join(SAVE_DIR, "*.*")):
        if os.path.isdir(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in _AUDIO_EXTS:
            continue
        basename = os.path.basename(f)
        if kw_lower and kw_lower not in basename.lower():
            continue
        stat = os.stat(f)
        mtime = stat.st_mtime
        # 时间筛选
        if time_filter == "today":
            if now - mtime > 86400:
                continue
        elif time_filter == "week":
            if now - mtime > 604800:
                continue
        elif time_filter == "month":
            if now - mtime > 2592000:
                continue
        # 估算时长 (基于文件大小粗略估算)
        duration = f"{stat.st_size / 1024 / 150:.1f}s" if stat.st_size > 1024 else "<1s"
        history.append({
            "basename": basename,
            "time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            "size": f"{stat.st_size / 1024 / 1024:.1f} MB",
            "duration": duration,
            "path": f,
            "mtime": mtime,
        })
    history.sort(key=lambda x: x["mtime"], reverse=True)
    return history


def get_history_table_data(search_keyword="", time_filter="all"):
    """获取历史记录表格数据"""
    records = get_generation_history_enhanced(search_keyword, time_filter)
    if not records:
        return [["暂无记录", "-", "-", "-"]]
    return [[r["basename"], r["time"], r["duration"], r["size"]] for r in records]
