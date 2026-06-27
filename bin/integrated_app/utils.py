"""通用工具函数"""

import contextlib
import glob
import os

from .config import _ROLE_COLOR_MAP, SAVE_DIR


def cleanup_temp_files():
    """清理临时音频文件"""
    try:
        for f in glob.glob(os.path.join(SAVE_DIR, "temp_*.wav")):
            with contextlib.suppress(OSError):
                os.remove(f)
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
