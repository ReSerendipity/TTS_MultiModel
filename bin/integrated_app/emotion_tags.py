"""Emotion tag system for TTS generation.

Inspired by Fish Speech's emotion tag design, provides fine-grained
emotional control through inline tags in text input.

Supported tag formats:
  - Bracket style: [whisper], [excited], [angry]
  - Parenthetical: (whisper), (excited)
  - Chinese tags: [耳语], [兴奋], [生气]

Tags are parsed, validated, and can be converted to control instructions
for the underlying TTS engine.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("tts_multimodel.emotion_tags")


@dataclass(frozen=True)
class EmotionTag:
    """Represents a parsed emotion tag."""

    name: str
    intensity: float = 1.0  # 0.0 - 1.0
    raw_text: str = ""

    @property
    def is_valid(self) -> bool:
        return self.name in EMOTION_REGISTRY


@dataclass(frozen=True)
class EmotionDefinition:
    """Definition of an emotion tag in the registry."""

    name: str
    category: str  # basic, advanced, prosody, style
    description_en: str
    description_zh: str
    synonyms: tuple[str, ...] = ()
    default_intensity: float = 1.0
    tags: tuple[str, ...] = ()


# ============================================================================
# Emotion Tag Registry
# ============================================================================

EMOTION_REGISTRY: dict[str, EmotionDefinition] = {}


def _register(defn: EmotionDefinition) -> None:
    """Register an emotion definition and all its synonyms."""
    EMOTION_REGISTRY[defn.name] = defn
    for syn in defn.synonyms:
        if syn not in EMOTION_REGISTRY:
            EMOTION_REGISTRY[syn] = defn


# --- Basic Emotions ---
_register(EmotionDefinition("happy", "basic", "Happy/Joyful", "高兴/快乐", ("joy", "glad", "cheerful", "高兴", "开心")))
_register(EmotionDefinition("sad", "basic", "Sad/Sorrowful", "悲伤/难过", ("sorrow", "grief", "melancholy", "悲伤", "难过")))
_register(EmotionDefinition("angry", "basic", "Angry/Furious", "愤怒/生气", ("fury", "rage", "mad", "愤怒", "生气", "恼怒")))
_register(EmotionDefinition("fear", "basic", "Fearful/Scared", "恐惧/害怕", ("scared", "afraid", "terrified", "恐惧", "害怕")))
_register(EmotionDefinition("surprise", "basic", "Surprised/Amazed", "惊讶/惊奇", ("amazed", "astonished", "shocked", "惊讶", "惊奇")))
_register(EmotionDefinition("disgust", "basic", "Disgusted/Repulsed", "厌恶/反感", ("repulsed", "revolted", "厌恶", "反感")))
_register(EmotionDefinition("calm", "basic", "Calm/Peaceful", "平静/安宁", ("peaceful", "serene", "relaxed", "平静", "安宁", "平和")))
_register(EmotionDefinition("neutral", "basic", "Neutral/Default", "中性/默认", ("default", "normal", "中性", "默认")))

# --- Advanced Emotions ---
_register(EmotionDefinition("excited", "advanced", "Excited/Enthusiastic", "兴奋/热情", ("enthusiastic", "thrilled", "兴奋", "热情")))
_register(EmotionDefinition("tender", "advanced", "Tender/Gentle", "温柔/柔和", ("gentle", "soft", "warm", "温柔", "柔和", "轻柔")))
_register(EmotionDefinition("confident", "advanced", "Confident/Assured", "自信/坚定", ("assured", "bold", "自信", "坚定")))
_register(EmotionDefinition("anxious", "advanced", "Anxious/Worried", "焦虑/担忧", ("worried", "nervous", "uneasy", "焦虑", "担忧")))
_register(EmotionDefinition("desperate", "advanced", "Desperate/Urgent", "绝望/迫切", ("urgent", "despairing", "绝望", "迫切")))
_register(EmotionDefinition("proud", "advanced", "Proud/Arrogant", "骄傲/傲慢", ("arrogant", "haughty", "骄傲", "傲慢")))
_register(EmotionDefinition("melancholic", "advanced", "Melancholic/Nostalgic", "忧郁/怀旧", ("nostalgic", "wistful", "忧郁", "怀旧")))

# --- Prosody / Speaking Style Tags ---
_register(EmotionDefinition("whisper", "prosody", "Whispering", "耳语", ("soft_speak", "hushed", "耳语", "低声")))
_register(EmotionDefinition("shout", "prosody", "Shouting/Loud", "大声喊", ("yell", "loud", "大声", "喊叫")))
_register(EmotionDefinition("slow", "prosody", "Slow pace", "慢速", ("slower", "unhurried", "慢速", "缓慢")))
_register(EmotionDefinition("fast", "prosody", "Fast pace", "快速", ("quicker", "rapid", "快速", "急速")))
_register(EmotionDefinition("breathy", "prosody", "Breathy voice", "气声", ("airy", "breathy", "气声", "喘息")))
_register(EmotionDefinition("nasal", "prosody", "Nasal voice", "鼻音", ("nasally", "鼻音")))
_register(EmotionDefinition("creaky", "prosody", "Creaky voice (vocal fry)", "嘎裂声", ("vocal_fry", "嘎裂声")))

# --- Style / Context Tags ---
_register(EmotionDefinition("narration", "style", "Narration style", "旁白风格", ("narrator", "旁白", "叙述")))
_register(EmotionDefinition("dialogue", "style", "Dialogue/conversational", "对话风格", ("conversational", "chat", "对话", "聊天")))
_register(EmotionDefinition("reading", "style", "Reading/audiobook style", "朗读风格", ("audiobook", "朗读", "读书")))
_register(EmotionDefinition("news", "style", "News/broadcast style", "新闻播报", ("broadcast", "新闻", "播报")))
_register(EmotionDefinition("storytelling", "style", "Storytelling style", "讲故事风格", ("story", "讲述", "故事")))

# ============================================================================
# Tag Parser
# ============================================================================

# Regex to match tags: [tag_name], [tag_name:intensity], or (tag_name)
_TAG_PATTERN = re.compile(
    r"""
    [\[\(]                    # opening bracket
    \s*                       # optional whitespace
    ([a-zA-Z_\u4e00-\u9fff]+) # tag name (English or Chinese)
    (?:                        # optional intensity
        [\s:：]\s*             # separator (colon or space)
        (\d+(?:\.\d+)?)        # intensity value
    )?
    \s*                       # optional whitespace
    [\]\)]                    # closing bracket
    """,
    re.VERBOSE,
)

# Chinese to English mapping for common emotion terms
_CHINESE_TO_ENGLISH: dict[str, str] = {
    "高兴": "happy",
    "开心": "happy",
    "快乐": "happy",
    "悲伤": "sad",
    "难过": "sad",
    "伤心": "sad",
    "愤怒": "angry",
    "生气": "angry",
    "恼怒": "angry",
    "恐惧": "fear",
    "害怕": "fear",
    "惊讶": "surprise",
    "惊奇": "surprise",
    "厌恶": "disgust",
    "反感": "disgust",
    "平静": "calm",
    "安宁": "calm",
    "平和": "calm",
    "兴奋": "excited",
    "热情": "excited",
    "温柔": "tender",
    "柔和": "tender",
    "轻柔": "tender",
    "自信": "confident",
    "坚定": "confident",
    "焦虑": "anxious",
    "担忧": "anxious",
    "绝望": "desperate",
    "迫切": "desperate",
    "骄傲": "proud",
    "傲慢": "proud",
    "忧郁": "melancholic",
    "怀旧": "melancholic",
    "耳语": "whisper",
    "低声": "whisper",
    "大声": "shout",
    "喊叫": "shout",
    "慢速": "slow",
    "缓慢": "slow",
    "快速": "fast",
    "急速": "fast",
    "气声": "breathy",
    "鼻音": "nasal",
    "嘎裂声": "creaky",
    "旁白": "narration",
    "叙述": "narration",
    "对话": "dialogue",
    "聊天": "dialogue",
    "朗读": "reading",
    "读书": "reading",
    "新闻": "news",
    "播报": "news",
    "讲故事": "storytelling",
    "故事": "storytelling",
}


def parse_tags(text: str) -> tuple[list[EmotionTag], str]:
    """Parse emotion tags from text and return (tags, cleaned_text).

    Args:
        text: Input text potentially containing emotion tags like
              "[whisper]Hello world" or "你好[温柔]世界"

    Returns:
        Tuple of (list of parsed EmotionTag, text with tags removed).

    Examples:
        >>> tags, clean = parse_tags("[whisper]Hello [excited:0.8]world")
        >>> [t.name for t in tags]
        ['whisper', 'excited']
        >>> clean
        'Hello world'
    """
    tags = []
    cleaned = text

    for match in _TAG_PATTERN.finditer(text):
        raw_name = match.group(1)
        intensity_str = match.group(2)

        # Resolve Chinese to English
        name = _CHINESE_TO_ENGLISH.get(raw_name, raw_name.lower())
        intensity = float(intensity_str) if intensity_str else 1.0
        intensity = max(0.0, min(1.0, intensity))

        tag = EmotionTag(name=name, intensity=intensity, raw_text=match.group(0))
        tags.append(tag)

        if name not in EMOTION_REGISTRY:
            logger.warning(f"Unknown emotion tag: '{raw_name}' -> '{name}'")

    # Remove tags from text
    cleaned = _TAG_PATTERN.sub("", text).strip()
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    return tags, cleaned


def tags_to_control_instruction(tags: list[EmotionTag]) -> str:
    """Convert parsed emotion tags to a control instruction string.

    The control instruction is used by the VoxCPM2 engine to guide
    the voice generation style.

    Args:
        tags: List of parsed EmotionTag objects.

    Returns:
        Control instruction string like "warm female voice, whispering".

    Examples:
        >>> tags_to_control_instruction([
        ...     EmotionTag(name="whisper", intensity=1.0),
        ...     EmotionTag(name="sad", intensity=0.8),
        ... ])
        'whispering, sad'
    """
    if not tags:
        return ""

    parts = []
    for tag in tags:
        if tag.name not in EMOTION_REGISTRY:
            continue

        defn = EMOTION_REGISTRY[tag.name]

        # Map intensity to descriptive modifier
        if tag.intensity < 0.3:
            modifier = "slightly"
        elif tag.intensity < 0.7:
            modifier = ""
        else:
            modifier = "very" if tag.intensity >= 0.9 else ""

        # Use the English description for the instruction
        desc = defn.description_en.split("/")[0].lower()
        if modifier:
            parts.append(f"{modifier} {desc}")
        else:
            parts.append(desc)

    return ", ".join(parts)


def strip_all_tags(text: str) -> str:
    """Remove all emotion tags from text, returning clean text.

    This is useful when the engine does not support emotion tags
    and we want to pass plain text.
    """
    cleaned = _TAG_PATTERN.sub("", text).strip()
    return re.sub(r"\s+", " ", cleaned)


def get_emotion_library() -> dict[str, list[dict]]:
    """Get the full emotion tag library organized by category.

    Returns:
        Dict mapping category name to list of emotion definitions.
    """
    categories: dict[str, list[dict]] = {}
    seen_names: set[str] = set()

    for defn in EMOTION_REGISTRY.values():
        if defn.name in seen_names:
            continue
        seen_names.add(defn.name)

        cat = defn.category
        if cat not in categories:
            categories[cat] = []

        categories[cat].append({
            "name": defn.name,
            "description_en": defn.description_en,
            "description_zh": defn.description_zh,
            "synonyms": list(defn.synonyms),
            "default_intensity": defn.default_intensity,
        })

    return categories


def validate_tags(tags: list[EmotionTag]) -> tuple[list[EmotionTag], list[str]]:
    """Validate tags and return (valid_tags, warnings).

    Args:
        tags: List of parsed emotion tags.

    Returns:
        Tuple of (valid tags, list of warning messages).
    """
    valid = []
    warnings = []

    for tag in tags:
        if tag.name in EMOTION_REGISTRY:
            valid.append(tag)
        else:
            warnings.append(f"Unknown emotion tag: '{tag.raw_text}' (resolved to '{tag.name}')")

    # Check for conflicting emotions
    if len(valid) > 1:
        conflicting_pairs = {
            frozenset({"happy", "sad"}),
            frozenset({"angry", "calm"}),
            frozenset({"excited", "calm"}),
            frozenset({"whisper", "shout"}),
        }
        tag_names = {t.name for t in valid}
        for pair in conflicting_pairs:
            if pair.issubset(tag_names):
                warnings.append(
                    f"Potentially conflicting emotions: {', '.join(sorted(pair))}. "
                    f"The last tag will take priority."
                )

    return valid, warnings
