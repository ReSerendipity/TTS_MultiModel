from ._base import EngineSwitchError, logger


def fn_voxcpm_load_lora(lora_path: str) -> bool:
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.load_lora(lora_path)
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 加载 LoRA 失败: {e}")
        return False


def fn_voxcpm_unload_lora() -> bool:
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.unload_lora()
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 卸载 LoRA 失败: {e}")
        return False


def fn_voxcpm_set_lora_enabled(enabled: bool) -> bool:
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.set_lora_enabled(enabled)
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 设置 LoRA 状态失败: {e}")
        return False


def fn_voxcpm_get_lora_state() -> dict:
    from ...model_manager import voxcpm_model as _voxcpm_model
    if _voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return _voxcpm_model.get_lora_state_dict()
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 获取 LoRA 状态失败: {e}")
        return {}
