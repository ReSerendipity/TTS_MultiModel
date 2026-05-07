# -*- coding: utf-8 -*-
"""TTS 引擎模块：VoxCPM2 专用

导出所有引擎功能函数，供路由层调用。
"""

from .voxcpm2_engine import (
    fn_voxcpm_design,
    fn_voxcpm_clone,
    fn_voxcpm_ultimate_clone,
    fn_voxcpm_script_studio,
    fn_voxcpm_streaming,
    fn_voxcpm_load_lora,
    fn_voxcpm_unload_lora,
    fn_voxcpm_set_lora_enabled,
    fn_voxcpm_get_lora_state,
    fn_voxcpm_prompt_continue,
)

__all__ = [
    "fn_voxcpm_design",
    "fn_voxcpm_clone",
    "fn_voxcpm_ultimate_clone",
    "fn_voxcpm_script_studio",
    "fn_voxcpm_streaming",
    "fn_voxcpm_load_lora",
    "fn_voxcpm_unload_lora",
    "fn_voxcpm_set_lora_enabled",
    "fn_voxcpm_get_lora_state",
    "fn_voxcpm_prompt_continue",
]
