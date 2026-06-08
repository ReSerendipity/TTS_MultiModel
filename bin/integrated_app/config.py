# -*- coding: utf-8 -*-
"""Path configuration, constants, model path mapping, official speaker info, language list, etc.
Multi-engine configuration (VoxCPM2 + IndexTTS 2.0).

Configuration is managed through the AppConfig class, accessible via get_config().
Module-level variables are kept for backward compatibility but are deprecated.
"""

import os
import re
import warnings
from typing import Tuple, List, Optional

from .config_models import (
    AppConfig as _PydanticAppConfig,
    GenerationDefaultsConfig,
    SpeakerConfig as _SpeakerConfigModel,
    SpeakerInfo,
    ApiAuthConfig,
    load_config_dict,
)


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

def _set_env():
    """Set default offline environment variables."""
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['MODELSCOPE_OFFLINE'] = '1'


def _setup_environment(yaml_config: dict):
    """Set environment variables from config.yaml environment section."""
    if yaml_config and "environment" in yaml_config:
        env_cfg = yaml_config["environment"]
        if isinstance(env_cfg, dict):
            for key, value in env_cfg.items():
                os.environ[key] = str(value)


# ---------------------------------------------------------------------------
# Path configuration (computed from project root, not from YAML)
# ---------------------------------------------------------------------------

def get_project_root():
    current_path = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_path)
    if os.path.basename(parent).lower() == 'bin':
        return os.path.dirname(parent)
    if os.path.basename(current_path).lower() == 'bin':
        return os.path.dirname(current_path)
    return parent


ROOT_DIR = get_project_root()
PROJECT_ROOT = ROOT_DIR
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
PRETRAINED_DIR = os.path.join(ROOT_DIR, "pretrained_models")
SAVE_DIR = os.path.join(ROOT_DIR, "outputs")
PERSONA_DIR = os.path.join(ROOT_DIR, "personas")

# --- VoxCPM2 Model Paths ---
VOXCPM2_MODEL_PATH = os.path.join(PRETRAINED_DIR, "VoxCPM2")
VOXCPM2_ASR_PATH = os.path.join(PRETRAINED_DIR, "SenseVoiceSmall")
VOXCPM2_DENOISER_PATH = os.path.join(PRETRAINED_DIR, "speech_zipenhancer")
LORA_DIR = os.path.join(ROOT_DIR, "lora")

# --- IndexTTS 2.0 Model Paths ---
INDEXTTS2_MODEL_PATH = os.path.join(PRETRAINED_DIR, "IndexTTS2")


def _ensure_dirs():
    """Create required directories."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(SAVE_DIR, exist_ok=True)
    os.makedirs(PERSONA_DIR, exist_ok=True)
    os.makedirs(LORA_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Config parsing helpers (split from the old monolithic _load_config)
# ---------------------------------------------------------------------------

def _load_yaml_config() -> dict:
    """Load config.yaml and return parsed dict, or empty dict on failure."""
    config_path = os.path.join(ROOT_DIR, "config.yaml")
    if not os.path.exists(config_path):
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        import logging
        logging.getLogger("tts_multimodel").warning(f"Config load failed: {e}")
        return {}


def _parse_version(yaml_config: dict) -> str:
    """Parse version string from config."""
    if not yaml_config:
        return "0.0.0"
    try:
        version = yaml_config.get("version", "0.0.0")
        return str(version).strip().strip('"').strip("'")
    except Exception:
        return "0.0.0"


def _parse_generation_defaults(yaml_config: dict) -> GenerationDefaultsConfig:
    """Parse generation defaults from config.yaml generation section."""
    defaults = GenerationDefaultsConfig()
    if not yaml_config:
        return defaults
    try:
        gen = yaml_config.get("generation", {})
        if isinstance(gen, dict):
            valid_keys = GenerationDefaultsConfig.model_fields.keys()
            filtered = {k: v for k, v in gen.items() if k in valid_keys}
            return GenerationDefaultsConfig(**filtered)
    except Exception as e:
        import logging
        logging.getLogger("tts_multimodel").warning(f"Generation defaults parse failed: {e}")
    return defaults


# Default speakers (used when YAML has no speakers section)
_DEFAULT_SPEAKERS = [
    SpeakerInfo(id="Vivian", name_zh="薇薇安", type="少女音", traits="年轻活泼，语速轻快",
                description="甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。"),
    SpeakerInfo(id="阿知", name_zh="阿知", type="少年音", traits="干净明亮，少年感十足",
                description="干净明亮的少年音色，充满活力，适合年轻角色和动漫配音。"),
    SpeakerInfo(id="若彤", name_zh="若彤", type="萝莉音", traits="软萌可爱，充满童真",
                description="软萌可爱的萝莉音色，充满童真和活力，适合动漫角色和少女角色配音。"),
    SpeakerInfo(id="成杰", name_zh="成杰", type="青年男音", traits="沉稳有力，磁性十足",
                description="沉稳有力的青年男声，具有磁性，适合广播、广告和角色配音。"),
    SpeakerInfo(id="沐晴", name_zh="沐晴", type="少御音", traits="知性优雅，富有感染力",
                description="知性优雅的少御音色，温柔而有力量，适合知性女性角色和旁白。"),
    SpeakerInfo(id="御姐", name_zh="御姐", type="御姐音", traits="成熟性感，气场强大",
                description="成熟性感的御姐音色，气场强大，适合成熟女性角色和高冷角色配音。"),
    SpeakerInfo(id="旁白", name_zh="旁白", type="播音腔", traits="标准大气，庄重正式",
                description="标准大气的播音腔，庄重正式，适合新闻播报、旁白和纪录片配音。"),
    SpeakerInfo(id="老伯", name_zh="老伯", type="老年男音", traits="沧桑厚重，充满岁月感",
                description="沧桑厚重的老年男声，充满岁月感，适合长者角色和历史题材配音。"),
    SpeakerInfo(id="少女", name_zh="少女", type="少女音", traits="甜美可爱，青春活力",
                description="甜美可爱的少女音色，青春洋溢，适合动漫少女角色和青春题材。"),
]


def _parse_speaker_config(yaml_config: dict) -> _SpeakerConfigModel:
    """Parse speaker configuration from config.yaml speakers section."""
    if not yaml_config:
        return _SpeakerConfigModel(official=_DEFAULT_SPEAKERS)
    try:
        official_list = yaml_config.get("speakers", {}).get("official")
        if official_list and isinstance(official_list, list):
            speakers = []
            for sp in official_list:
                sid = sp.get("id")
                if not sid:
                    continue
                speakers.append(SpeakerInfo(
                    id=sid,
                    name_zh=sp.get("name_zh", sid),
                    description=sp.get("description", ""),
                    type=sp.get("type", ""),
                    traits=sp.get("traits", ""),
                ))
            if speakers:
                return _SpeakerConfigModel(official=speakers)
    except Exception as e:
        import logging
        logging.getLogger("tts_multimodel").warning(f"Speaker config parse failed: {e}")
    return _SpeakerConfigModel(official=_DEFAULT_SPEAKERS)


def _parse_api_auth(yaml_config: dict) -> ApiAuthConfig:
    """Parse API auth settings from config.yaml api_auth section."""
    if not yaml_config:
        return ApiAuthConfig()
    try:
        auth_cfg = yaml_config.get("api_auth", {})
        if isinstance(auth_cfg, dict):
            return ApiAuthConfig(
                enabled=bool(auth_cfg.get("enabled", False)),
                token=str(auth_cfg.get("token", "")),
            )
    except Exception:
        pass
    return ApiAuthConfig()


# ---------------------------------------------------------------------------
# Centralized AppConfig
# ---------------------------------------------------------------------------

class AppConfig:
    """Centralized application configuration.

    Holds all configuration values loaded from config.yaml and provides
    property access for backward compatibility with module-level variables.

    Use ``get_config()`` to obtain the singleton instance.
    """

    def __init__(self):
        # Initialize environment and directories first
        _set_env()
        _ensure_dirs()

        # Load YAML config
        self._yaml_config = _load_yaml_config()

        # Apply environment overrides from YAML
        _setup_environment(self._yaml_config)

        # Parse all configuration sections
        self._version = _parse_version(self._yaml_config)
        self._generation_defaults = _parse_generation_defaults(self._yaml_config)
        self._speaker_config = _parse_speaker_config(self._yaml_config)
        self._api_auth = _parse_api_auth(self._yaml_config)

        # Build validated Pydantic config
        self._pydantic_config = load_config_dict(self._yaml_config or {})

    # -- Raw section accessors ------------------------------------------------

    @property
    def version(self) -> str:
        return self._version

    @property
    def generation_defaults(self) -> GenerationDefaultsConfig:
        return self._generation_defaults

    @property
    def speaker_config(self) -> _SpeakerConfigModel:
        return self._speaker_config

    @property
    def api_auth(self) -> ApiAuthConfig:
        return self._api_auth

    @property
    def pydantic_config(self) -> _PydanticAppConfig:
        return self._pydantic_config

    # -- Computed properties (backward compat with old module-level vars) -----

    @property
    def official_speakers(self) -> set:
        """Set of official speaker IDs."""
        return {s.id for s in self._speaker_config.official}

    @property
    def official_speaker_info(self) -> dict:
        """Dict mapping speaker ID -> (name_zh, description, type, traits) tuple."""
        return {
            s.id: (s.name_zh, s.description, s.type, s.traits)
            for s in self._speaker_config.official
        }

    @property
    def official_speakers_ordered(self) -> list:
        """Ordered list of official speaker IDs."""
        return [s.id for s in self._speaker_config.official]

    @property
    def gen_defaults_dict(self) -> dict:
        """Generation defaults as a plain dict (backward compat with GEN_DEFAULTS)."""
        return self._generation_defaults.model_dump()

    @property
    def api_auth_dict(self) -> dict:
        """API auth as a plain dict (backward compat with API_AUTH)."""
        return {"enabled": self._api_auth.enabled, "token": self._api_auth.token}


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_config_instance: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the application configuration singleton."""
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
    return _config_instance


# ---------------------------------------------------------------------------
# Module-level variables (backward compatible, deprecated)
#
# New code should use get_config() instead.
# ---------------------------------------------------------------------------

_cfg = get_config()

# DEPRECATED: Use config_models.AppConfig via get_config() instead
VERSION = _cfg.version

# DEPRECATED: Use config_models.AppConfig via get_config() instead
GEN_DEFAULTS = _cfg.gen_defaults_dict

# DEPRECATED: Use config_models.AppConfig via get_config() instead
OFFICIAL_SPEAKERS = _cfg.official_speakers

# DEPRECATED: Use config_models.AppConfig via get_config() instead
OFFICIAL_SPEAKER_INFO = _cfg.official_speaker_info

# DEPRECATED: Use config_models.AppConfig via get_config() instead
_OFFICIAL_SPEAKERS_ORDERED = _cfg.official_speakers_ordered

# DEPRECATED: Use config_models.AppConfig via get_config() instead
API_AUTH = _cfg.api_auth_dict

# DEPRECATED: Use config_models.AppConfig via get_config() instead
CFG_VALUE = _cfg.generation_defaults.cfg_value
INFERENCE_TIMESTEPS = _cfg.generation_defaults.inference_timesteps
NORMALIZE = _cfg.generation_defaults.normalize
DENOISE = _cfg.generation_defaults.denoise
RETRY_BADCASE = _cfg.generation_defaults.retry_badcase
RETRY_BADCASE_MAX_TIMES = _cfg.generation_defaults.retry_badcase_max_times
RETRY_BADCASE_RATIO_THRESHOLD = _cfg.generation_defaults.retry_badcase_ratio_threshold
MIN_LEN = _cfg.generation_defaults.min_len
MAX_LEN = _cfg.generation_defaults.max_len
GEN_SPLIT_MAX_CHARS = _cfg.generation_defaults.split_max_chars

warnings.warn(
    "Module-level config variables (VERSION, HOST, PORT, etc.) are deprecated. "
    "Use config_models.AppConfig via get_config() instead.",
    DeprecationWarning,
    stacklevel=2,
)

def check_models_available() -> Tuple[bool, List[str]]:
    missing = []
    if not os.path.isdir(VOXCPM2_MODEL_PATH):
        missing.append(VOXCPM2_MODEL_PATH)
    if not os.path.isdir(INDEXTTS2_MODEL_PATH):
        missing.append(INDEXTTS2_MODEL_PATH)
    return len(missing) == 0, missing


def get_download_hints() -> dict[str, str]:
    hints = {}
    if not os.path.isdir(VOXCPM2_MODEL_PATH):
        hints["voxcpm2"] = (
            "VoxCPM2 模型未找到。下载命令:\n"
            "  pip install huggingface-hub\n"
            "  huggingface-cli download openbmb/VoxCPM2 --local-dir pretrained_models/VoxCPM2\n"
            "  或: python scripts/download_voxcpm2.py"
        )
    if not os.path.isdir(INDEXTTS2_MODEL_PATH):
        hints["indextts2"] = (
            "IndexTTS 2.0 模型未找到。下载命令:\n"
            "  pip install huggingface-hub\n"
            "  huggingface-cli download IndexTeam/IndexTTS-2 --local-dir pretrained_models/IndexTTS2\n"
            "  或: python scripts/download_indextts2.py"
        )
    return hints

# --- Language list ---
_LANGS = ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian", "Auto"]

# --- Dialect list (Chinese dialects supported by VoxCPM2) ---
_DIALECTS = [
    ("四川话", "四川话"),
    ("粤语", "粤语"),
    ("吴语", "吴语"),
    ("东北话", "东北话"),
    ("河南话", "河南话"),
    ("闽南语", "闽南语"),
    ("湖南话", "湖南话"),
    ("湖北话", "湖北话"),
    ("客家话", "客家话"),
]

# --- Audio extensions ---
_AUDIO_EXTS = {'.wav', '.mp3', '.ogg', '.flac'}

# --- Input validation limits ---
MAX_TEXT_LENGTH = 10000
MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024  # 100MB

# --- Persona name validation regex ---
_PERSONA_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]{1,50}$')

# --- Role color mapping ---
_ROLE_COLOR_MAP = {
    "御姐": ("pink", "#EC4899"),
    "旁白": ("gray", "#6B7280"),
    "萝莉": ("pink", "#F472B6"),
    "萝莉音": ("pink", "#F472B6"),
    "御姐音": ("pink", "#EC4899"),
    "少年": ("blue", "#3B82F6"),
    "少年音": ("blue", "#3B82F6"),
    "大叔": ("purple", "#8B5CF6"),
    "正太": ("green", "#22C55E"),
    "女王": ("red", "#EF4444"),
    "暖男": ("orange", "#FB923C"),
    "暖男音": ("orange", "#FB923C"),
    "低音炮": ("purple", "#8B5CF6"),
    "少女音": ("pink", "#F472B6"),
    "青年男音": ("blue", "#3B82F6"),
    "中年男音": ("purple", "#8B5CF6"),
    "日系甜音": ("pink", "#F9A8D4"),
    "韩系甜音": ("pink", "#F9A8D4"),
}
