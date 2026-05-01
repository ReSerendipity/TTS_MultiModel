# -*- coding: utf-8 -*-
"""路径配置、常量定义、模型路径映射、官方音色信息、语言列表等"""

import os

# --- 环境与补丁设置 ---
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['MODELSCOPE_OFFLINE'] = '1'
os.environ['PYTHONHTTPSVERIFY'] = '0'

try:
    from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem
    import torch
    torch.serialization.add_safe_globals([VoiceClonePromptItem])
except ImportError:
    pass

# SSL 验证：不再全局禁用，仅在 Gradio launch 中通过 ssl_verify=False 处理


# --- 路径配置 ---
def get_project_root():
    current_path = os.path.dirname(os.path.abspath(__file__))
    # integrated_app 包在 bin/ 下，需要往上两层
    parent = os.path.dirname(current_path)
    if os.path.basename(parent).lower() == 'bin':
        return os.path.dirname(parent)
    if os.path.basename(current_path).lower() == 'bin':
        return os.path.dirname(current_path)
    return parent

ROOT_DIR = get_project_root()
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
PRETRAINED_DIR = os.path.join(ROOT_DIR, "pretrained_models")
SAVE_DIR = os.path.join(ROOT_DIR, "outputs")
PERSONA_DIR = os.path.join(ROOT_DIR, "personas")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(PERSONA_DIR, exist_ok=True)

# --- 模型路径映射 ---
MODEL_PATHS = {
    "声音设计": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "语音克隆": "Qwen3-TTS-12Hz-{size}-Base",
    "官方精品": "Qwen3-TTS-12Hz-{size}-CustomVoice",
}

VOXCPM2_MODEL_PATH = os.path.join(PRETRAINED_DIR, "VoxCPM2")
VOXCPM2_ASR_PATH = os.path.join(PRETRAINED_DIR, "SenseVoiceSmall")
VOXCPM2_DENOISER_PATH = os.path.join(PRETRAINED_DIR, "speech_zipenhancer")

# --- 官方音色信息 ---
OFFICIAL_SPEAKERS = {"Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee"}
_OFFICIAL_SPEAKERS_LOWER = {s.lower() for s in OFFICIAL_SPEAKERS}

OFFICIAL_SPEAKER_INFO = {
    "Vivian": ("薇薇安", "甜美少女音，活泼热情，适合年轻女性角色配音。擅长日常对话和情感表达。", "少女音", "年轻活泼，语速轻快"),
    "Serena": ("塞雷娜", "优雅成熟女性声线，知性大方。适合专业播报、教学讲解和商务场景。", "御姐音", "沉稳知性，语速适中"),
    "Uncle_Fu": ("傅叔叔", "中年男性沉稳声线，温和可靠。适合长辈角色、纪录片旁白和故事讲述。", "中年男音", "沉稳厚重，语速较慢"),
    "Dylan": ("迪伦", "年轻男性活力声线，阳光开朗。适合青年角色、广告配音和娱乐内容。", "青年男音", "阳光活力，语速较快"),
    "Eric": ("埃里克", "磁性低沉男声，深沉有魅力。适合悬疑叙事、有声书和电影预告。", "低音炮", "深沉磁性，语速缓慢"),
    "Ryan": ("瑞恩", "清脆少年音，干净纯粹。适合动漫角色、儿童内容和轻快解说。", "少年音", "清脆明亮，语速轻快"),
    "Aiden": ("艾登", "温暖青年男声，亲切自然。适合播客、自媒体和日常交流场景。", "暖男音", "温和亲切，语速适中"),
    "Ono_Anna": ("小野安娜", "日式甜美女声，日系二次元风格。适合动漫角色、游戏配音和轻小说。", "日系甜音", "甜美可爱，语速轻快"),
    "Sohee": ("秀熙", "韩式清甜女声，韩流风格。适合韩剧风格内容、韩语学习辅助。", "韩系甜音", "清甜温柔，语速适中"),
}

_OFFICIAL_SPEAKERS_ORDERED = ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee"]
_OFFICIAL_DISPLAY_NAMES = [f"{OFFICIAL_SPEAKER_INFO[s][0]} ({s})" for s in _OFFICIAL_SPEAKERS_ORDERED]

# --- 语言列表 ---
_LANGS = ["Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian", "Auto"]

# --- 模型类型别名映射 ---
MODEL_TYPE_ALIASES = {
    "voice_design": "声音设计",
    "voice_clone": "语音克隆",
    "custom_voice": "官方精品",
    "design": "声音设计",
    "clone": "语音克隆",
    "official": "官方精品",
}

# --- 音频扩展名 ---
_AUDIO_EXTS = {'.wav', '.mp3', '.ogg', '.flac'}

# --- 音色名称验证正则 ---
import re
_PERSONA_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]{1,50}$')

# --- 角色颜色映射 ---
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
