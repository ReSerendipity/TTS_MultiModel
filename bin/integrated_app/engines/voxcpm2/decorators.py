# -*- coding: utf-8 -*-
"""Decorators for VoxCPM2 generation functions.

Extracts the common pattern of model checking, lock acquisition,
tracker/progress management, and error handling into reusable decorators.
"""

import functools
import time

from ...exceptions import EngineSwitchError, GenerationError, tts_error_handler
from ...model_manager import _check_voxcpm2_lock, _gen_tracker, _progress_mgr
from ...model_registry import registry

from ._base import logger


def with_generation_context(
    phase_name: str = "",
    check_model: bool = True,
    use_tracker: bool = True,
    use_progress: bool = True,
    cleanup_fn=None,
):
    """Decorator that wraps VoxCPM2 generation functions with common context management.

    Handles:
    1. Model readiness check
    2. Generation lock check
    3. Generation tracker start/end
    4. Progress manager initial start / schedule_reset
    5. Error handling via tts_error_handler
    6. Elapsed time logging

    Args:
        phase_name: Name for the generation phase (e.g., "voice_clone", "script").
        check_model: Whether to check if the model is loaded.
        use_tracker: Whether to use generation tracker.
        use_progress: Whether to use progress manager.
        cleanup_fn: Optional callable invoked in the finally block (e.g., cleanup_temp_files).

    Usage:
        @with_generation_context(phase_name="voice_clone")
        def fn_voxcpm_clone(text, **kwargs):
            # Implementation only needs to focus on the core logic
            ...
            return output_path, message
    """
    def decorator(func: callable) -> callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Check model readiness
            if check_model and registry.voxcpm_model is None:
                raise EngineSwitchError("请先切换并加载 VoxCPM2 引擎")

            # 2. Check generation lock
            if not _check_voxcpm2_lock():
                raise GenerationError("模型正在加载或切换中，请稍后再试")

            # 3. Start tracker
            if use_tracker:
                _gen_tracker.start_generation()

            # 4. Start progress with initial phase
            if use_progress and phase_name:
                _progress_mgr.start(total_segments=1, phase=f"{phase_name} 准备中...")

            start_time = time.time()
            try:
                # 5. Call the actual implementation (already wrapped with tts_error_handler)
                result = func(*args, **kwargs)
                return result

            finally:
                # 6. End tracker and progress
                elapsed = time.time() - start_time
                if use_tracker:
                    _gen_tracker.end_generation(elapsed)
                if use_progress:
                    _progress_mgr.schedule_reset(delay_seconds=120)
                if cleanup_fn:
                    cleanup_fn()
                logger.info(f"[{phase_name or func.__name__}] 生成耗时 {elapsed:.1f} 秒")

        # Apply tts_error_handler to the wrapper so unknown exceptions
        # are converted to GenerationError consistently
        return tts_error_handler(wrapper)

    return decorator
