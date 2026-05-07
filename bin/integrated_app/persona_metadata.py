# -*- coding: utf-8 -*-
"""Persona metadata management: tags, categories, import/export."""

import os
import json
import shutil
import logging
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger("tts_multimodel")


PERSONA_METADATA_VERSION = 1


class PersonaMetadata:
    """Extended metadata for a persona/voice clone.
    
    Enhances the basic .txt info file with structured metadata including
    tags, categories, usage stats, and creation info.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        tags: List[str] = None,
        category: str = "",
        voice_type: str = "",
        traits: str = "",
        created_at: str = None,
        usage_count: int = 0,
        favorite: bool = False,
        rating: float = 0.0,
        source_audio: str = "",
        language: str = "zh",
    ):
        self.name = name
        self.description = description
        self.tags = tags or []
        self.category = category
        self.voice_type = voice_type
        self.traits = traits
        self.created_at = created_at or datetime.now().isoformat()
        self.usage_count = usage_count
        self.favorite = favorite
        self.rating = min(5.0, max(0.0, rating))
        self.source_audio = source_audio
        self.language = language

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": PERSONA_METADATA_VERSION,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "category": self.category,
            "voice_type": self.voice_type,
            "traits": self.traits,
            "created_at": self.created_at,
            "usage_count": self.usage_count,
            "favorite": self.favorite,
            "rating": self.rating,
            "source_audio": self.source_audio,
            "language": self.language,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaMetadata":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            category=data.get("category", ""),
            voice_type=data.get("voice_type", ""),
            traits=data.get("traits", ""),
            created_at=data.get("created_at"),
            usage_count=data.get("usage_count", 0),
            favorite=data.get("favorite", False),
            rating=data.get("rating", 0.0),
            source_audio=data.get("source_audio", ""),
            language=data.get("language", "zh"),
        )

    @classmethod
    def from_legacy_text(cls, name: str, text: str) -> "PersonaMetadata":
        """Parse legacy .txt info format into metadata.
        
        Legacy format:
        Line 1: Voice type (e.g., 萝莉音)
        Line 2: Description
        Line 3: Traits
        """
        lines = text.strip().split("\n")
        voice_type = lines[0].strip() if len(lines) > 0 else ""
        description = lines[1].strip() if len(lines) > 1 else ""
        traits = lines[2].strip() if len(lines) > 2 else ""
        
        return cls(
            name=name,
            description=description,
            voice_type=voice_type,
            traits=traits,
        )

    def to_legacy_text(self) -> str:
        """Convert back to legacy .txt format for compatibility."""
        return f"{self.voice_type}\n{self.description}\n{self.traits}"


# Predefined tags for voice categorization
VOICE_TAGS = {
    "gender": ["女声", "男声", "中性"],
    "age": ["萝莉", "少女", "青年", "中年", "老年", "正太", "少年"],
    "style": ["甜美", "御姐", "温柔", "活泼", "沉稳", "磁性", "清新", "知性"],
    "use_case": ["日常对话", "广告配音", "有声书", "游戏角色", "动漫角色", "新闻播报", "旁白"],
    "mood": ["欢快", "悲伤", "愤怒", "温柔", "严肃", "神秘", "可爱"],
}

# Category definitions
VOICE_CATEGORIES = ["预设音色", "自定义克隆", "声音设计", "剧本角色"]


def get_all_tags() -> Dict[str, List[str]]:
    """Get all available tag categories and their values."""
    return dict(VOICE_TAGS)


def get_categories() -> List[str]:
    """Get all available voice categories."""
    return list(VOICE_CATEGORIES)


class PersonaExporter:
    """Export and import personas as zip packages."""

    @staticmethod
    def export_persona(persona_dir: str, output_path: str) -> str:
        """Export a persona to a zip package.
        
        Args:
            persona_dir: Directory containing persona files (.wav, .txt, .pt).
            output_path: Path for the output zip file.
        
        Returns:
            Path to the created zip file.
        """
        persona_name = os.path.basename(persona_dir)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in os.listdir(persona_dir):
                filepath = os.path.join(persona_dir, filename)
                if os.path.isfile(filepath):
                    arcname = os.path.join(persona_name, filename)
                    zf.write(filepath, arcname)
            
            # Add metadata.json if it exists
            meta_path = os.path.join(persona_dir, "metadata.json")
            if not os.path.exists(meta_path):
                # Generate metadata from existing files
                meta = PersonaMetadata(name=persona_name)
                txt_path = os.path.join(persona_dir, f"{persona_name}.txt")
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        meta = PersonaMetadata.from_legacy_text(persona_name, f.read())
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)
            
            zf.write(meta_path, os.path.join(persona_name, "metadata.json"))
        
        return output_path

    @staticmethod
    def import_persona(zip_path: str, persona_dir: str) -> str:
        """Import a persona from a zip package.
        
        Args:
            zip_path: Path to the persona zip file.
            persona_dir: Directory to extract the persona into.
        
        Returns:
            Name of the imported persona.
        """
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in zf.namelist():
                # Skip directory entries and absolute paths
                if not member or member.startswith('/') or member.startswith('\\'):
                    continue
                target_path = os.path.realpath(os.path.join(persona_dir, member))
                if not target_path.startswith(os.path.realpath(persona_dir) + os.sep):
                    raise ValueError(f"Zip slip detected: {member}")
                zf.extract(member, persona_dir)
        
        # Find the persona name from the archive
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            if names:
                persona_name = names[0].split("/")[0]
                return persona_name
        
        return os.path.splitext(os.path.basename(zip_path))[0]


def load_persona_metadata(persona_dir: str, persona_name: str) -> PersonaMetadata:
    """Load persona metadata, falling back to legacy .txt if no metadata.json exists."""
    meta_path = os.path.join(persona_dir, "metadata.json")
    
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return PersonaMetadata.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load metadata.json for {persona_name}: {e}")
    
    # Fallback to legacy .txt
    txt_path = os.path.join(persona_dir, f"{persona_name}.txt")
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                return PersonaMetadata.from_legacy_text(persona_name, f.read())
        except Exception:
            pass
    
    return PersonaMetadata(name=persona_name)


def save_persona_metadata(persona_dir: str, persona_name: str, meta: PersonaMetadata):
    """Save persona metadata to metadata.json and update legacy .txt."""
    meta_path = os.path.join(persona_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)
    
    # Update legacy .txt for backward compatibility
    txt_path = os.path.join(persona_dir, f"{persona_name}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(meta.to_legacy_text())
