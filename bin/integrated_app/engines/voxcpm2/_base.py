import logging
import os
import re
import time

import numpy as np

from ...config import SAVE_DIR
from ...config_models import AdvancedParamsConfig
from ...exceptions import EngineSwitchError, GenerationError, tts_error_handler
from ...generation import _save_wav_compatible, split_text_for_tts
from ...model_manager import _gen_tracker, _progress_mgr
from ...persona_manager import get_persona_map
from ...utils import cleanup_temp_files

logger = logging.getLogger("tts_multimodel")

_DEFAULT_ADVANCED = AdvancedParamsConfig()


def get_advanced_params() -> dict:
    return _DEFAULT_ADVANCED.to_dict()


def build_advanced_params(**overrides) -> AdvancedParamsConfig:
    valid_keys = AdvancedParamsConfig.model_fields.keys()
    filtered = {k: v for k, v in overrides.items() if k in valid_keys}
    return AdvancedParamsConfig(**filtered)


def _advanced_kwargs(advanced: AdvancedParamsConfig | None = None) -> dict:
    if advanced is None:
        advanced = _DEFAULT_ADVANCED
    return dict(
        max_len=advanced.max_len,
        split_max_chars=advanced.split_max_chars,
        retry_badcase=advanced.retry_badcase,
        retry_badcase_max_times=advanced.retry_badcase_max_times,
        retry_badcase_ratio_threshold=advanced.retry_badcase_ratio_threshold,
    )
