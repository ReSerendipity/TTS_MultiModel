# -*- coding: utf-8 -*-
"""Path configuration, constants, model path mapping, official speaker info, language list, etc.
VoxCPM2-exclusive configuration.
"""

import os
import re
from typing import Tuple, List

# --- Environment Settings ---
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['MODELSCOPE_OFFLINE'] = '1'

# --- Path Configuration ---
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
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(PERSONA_DIR, exist_ok=True)

# --- VoxCPM2 Model Paths ---
VOXCPM2_MODEL_PATH = os.path.join(PRETRAINED_DIR, "VoxCPM2")
VOXCPM2_ASR_PATH = os.path.join(PRETRAINED_DIR, "SenseVoiceSmall")
VOXCPM2_DENOISER_PATH = os.path.join(PRETRAINED_DIR, "speech_zipenhancer")
LORA_DIR = os.path.join(ROOT_DIR, "lora")
os.makedirs(LORA_DIR, exist_ok=True)

# --- Version and Generation Parameters (from config.yaml) ---
def _load_config():
    version = "0.0.0"
    gen_defaults = {
        "cfg_value": 2.0,
        "inference_timesteps": 10,
        "normalize": True,
        "denoise": True,
        "retry_badcase": True,
        "retry_badcase_max_times": 3,
        "retry_badcase_ratio_threshold": 6.0,
        "min_len": 2,
        "max_len": 4096,
        "split_max_chars": 200,
    }

    _default_official_speakers = {"Vivian", "阿知", "若彤", "成杰", "沐晴", "御姐", "旁白", "老伯", "少女"}
    _default_official_speaker_info = {
        "Vivian": ("薇薇安", "甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。", "少女音", "年轻活泼，语速轻快"),
        "阿知": ("阿知", "干净明亮的少年音色，充满活力，适合年轻角色和动漫配音。", "少年音", "干净明亮，少年感十足"),
        "若彤": ("若彤", "软萌可爱的萝莉音色，充满童真和活力，适合动漫角色和少女角色配音。", "萝莉音", "软萌可爱，充满童真"),
        "成杰": ("成杰", "沉稳有力的青年男声，具有磁性，适合广播、广告和角色配音。", "青年男音", "沉稳有力，磁性十足"),
        "沐晴": ("沐晴", "知性优雅的少御音色，温柔而有力量，适合知性女性角色和旁白。", "少御音", "知性优雅，富有感染力"),
        "御姐": ("御姐", "成熟性感的御姐音色，气场强大，适合成熟女性角色和高冷角色配音。", "御姐音", "成熟性感，气场强大"),
        "旁白": ("旁白", "标准大气的播音腔，庄重正式，适合新闻播报、旁白和纪录片配音。", "播音腔", "标准大气，庄重正式"),
        "老伯": ("老伯", "沧桑厚重的老年男声，充满岁月感，适合长者角色和历史题材配音。", "老年男音", "沧桑厚重，充满岁月感"),
        "少女": ("少女", "甜美可爱的少女音色，青春洋溢，适合动漫少女角色和青春题材。", "少女音", "甜美可爱，青春活力"),
    }
    _default_official_speakers_ordered = ["Vivian", "阿知", "若彤", "成杰", "沐晴", "御姐", "旁白", "老伯", "少女"]

    official_speakers = set(_default_official_speakers)
    official_speaker_info = dict(_default_official_speaker_info)
    official_speakers_ordered = list(_default_official_speakers_ordered)

    config_path = os.path.join(ROOT_DIR, "config.yaml")
    if not os.path.exists(config_path):
        return version, gen_defaults, official_speakers, official_speaker_info, official_speakers_ordered, {"enabled": False, "token": ""}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("version:"):
                    version = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception as e:
        import logging
        logging.getLogger("tts_multimodel").warning(f"Config load failed: {e}")

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            if cfg and "generation" in cfg:
                gen = cfg["generation"]
                for key, default in gen_defaults.items():
                    if key in gen:
                        gen_defaults[key] = gen[key]
            if cfg:
                official_list = cfg.get("speakers", {}).get("official")
                if official_list and isinstance(official_list, list):
                    speakers_set = set()
                    speakers_info = {}
                    speakers_ordered = []
                    for sp in official_list:
                        sid = sp.get("id")
                        if not sid:
                            continue
                        speakers_set.add(sid)
                        speakers_info[sid] = (
                            sp.get("name_zh", sid),
                            sp.get("description", ""),
                            sp.get("type", ""),
                            sp.get("traits", ""),
                        )
                        speakers_ordered.append(sid)
                    if speakers_set:
                        official_speakers = speakers_set
                        official_speaker_info = speakers_info
                        official_speakers_ordered = speakers_ordered
    except Exception as e:
        import logging
        logging.getLogger("tts_multimodel").warning(f"Config load failed: {e}")

    api_auth = {"enabled": False, "token": ""}
    try:
        if cfg and "api_auth" in cfg:
            auth_cfg = cfg["api_auth"]
            if isinstance(auth_cfg, dict):
                api_auth["enabled"] = bool(auth_cfg.get("enabled", False))
                api_auth["token"] = str(auth_cfg.get("token", ""))
    except Exception:
        pass

    return version, gen_defaults, official_speakers, official_speaker_info, official_speakers_ordered, api_auth

VERSION, GEN_DEFAULTS, OFFICIAL_SPEAKERS, OFFICIAL_SPEAKER_INFO, _OFFICIAL_SPEAKERS_ORDERED, API_AUTH = _load_config()
_OFFICIAL_SPEAKERS_LOWER = {s.lower() for s in OFFICIAL_SPEAKERS}
_OFFICIAL_DISPLAY_NAMES = [f"{OFFICIAL_SPEAKER_INFO[s][0]} ({s})" for s in _OFFICIAL_SPEAKERS_ORDERED]

# VoxCPM2 generation defaults
CFG_VALUE = GEN_DEFAULTS.get("cfg_value", 2.0)
INFERENCE_TIMESTEPS = GEN_DEFAULTS.get("inference_timesteps", 10)
NORMALIZE = GEN_DEFAULTS.get("normalize", True)
DENOISE = GEN_DEFAULTS.get("denoise", True)
RETRY_BADCASE = GEN_DEFAULTS.get("retry_badcase", True)
RETRY_BADCASE_MAX_TIMES = GEN_DEFAULTS.get("retry_badcase_max_times", 3)
RETRY_BADCASE_RATIO_THRESHOLD = GEN_DEFAULTS.get("retry_badcase_ratio_threshold", 6.0)
MIN_LEN = GEN_DEFAULTS.get("min_len", 2)
MAX_LEN = GEN_DEFAULTS.get("max_len", 4096)
GEN_SPLIT_MAX_CHARS = GEN_DEFAULTS.get("split_max_chars", 200)

# --- Model directory check (VoxCPM2 only) ---
def check_models_available() -> Tuple[bool, List[str]]:
    missing = []
    if not os.path.isdir(VOXCPM2_MODEL_PATH):
        missing.append(VOXCPM2_MODEL_PATH)
    return len(missing) == 0, missing

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
