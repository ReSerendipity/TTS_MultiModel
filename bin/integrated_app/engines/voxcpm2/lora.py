from ._base import EngineSwitchError, logger


def fn_voxcpm_load_lora(lora_path: str) -> bool:
    from ...model_registry import registry

    if registry.voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return registry.voxcpm_model.load_lora(lora_path)
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 加载 LoRA 失败: {e}")
        return False


def fn_voxcpm_unload_lora() -> bool:
    from ...model_registry import registry

    if registry.voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return registry.voxcpm_model.unload_lora()
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 卸载 LoRA 失败: {e}")
        return False


def fn_voxcpm_set_lora_enabled(enabled: bool) -> bool:
    from ...model_registry import registry

    if registry.voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return registry.voxcpm_model.set_lora_enabled(enabled)
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 设置 LoRA 状态失败: {e}")
        return False


def fn_voxcpm_get_lora_state() -> dict:
    from ...model_registry import registry

    if registry.voxcpm_model is None:
        raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")
    try:
        return registry.voxcpm_model.get_lora_state_dict()
    except Exception as e:
        logger.warning(f"[VoxCPM LoRA] 获取 LoRA 状态失败: {e}")
        return {}


def is_lora_enabled() -> bool:
    """Check whether any LoRA weights are currently loaded."""
    from ...model_registry import registry

    if registry.voxcpm_model is None:
        return False
    try:
        return bool(registry.voxcpm_model.get_lora_state_dict())
    except Exception:
        return False


def load_lora_weights(lora_path: str) -> tuple[list[str], list[str]]:
    """Load LoRA weights and return (loaded_keys, skipped_keys)."""
    loaded = fn_voxcpm_load_lora(lora_path)
    return ([lora_path], []) if loaded else ([], [lora_path])


def unload_lora_weights() -> None:
    """Unload currently loaded LoRA weights."""
    fn_voxcpm_unload_lora()


def get_lora_state_dict() -> dict:
    """Return the current LoRA state dictionary."""
    return fn_voxcpm_get_lora_state()
