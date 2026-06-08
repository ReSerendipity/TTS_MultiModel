# -*- coding: utf-8 -*-
"""通用工具函数"""

import os
import glob
from typing import List, Dict, Any, Optional, Tuple

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
