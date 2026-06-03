# -*- coding: utf-8 -*-
"""Pydantic models for configuration validation."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List


class AdvancedParamsConfig(BaseModel):
    """高级生成参数配置（不可变，替代全局 _ADVANCED_PARAMS 字典）"""
    max_len: int = Field(default=3000, ge=3000, le=3000, description="最大生成长度（固定3000）")
    split_max_chars: int = Field(default=200, ge=200, le=200, description="每段最大字符数（固定200）")
    retry_badcase: bool = Field(default=True, description="自动重试坏案例")
    retry_badcase_max_times: int = Field(default=3, ge=0, le=10, description="最大重试次数")
    retry_badcase_ratio_threshold: float = Field(default=6.0, gt=0, description="重试时长比率阈值")
    trim_silence_vad: bool = Field(default=True, description="VAD 静音裁切")
    target_lufs: float = Field(default=-16.0, ge=-30, le=0, description="目标响度 (LUFS)")
    idle_timeout: int = Field(default=300, ge=60, le=3600, description="空闲超时时间 (秒)")

    def to_dict(self) -> Dict:
        """转换为字典（用于传递给模型生成函数）"""
        return self.model_dump()


class ServerConfig(BaseModel):
    """Server-related configuration."""
    host: str = Field(default="127.0.0.1", description="Bind address")
    port: int = Field(default=8080, ge=1, le=65535, description="Port number")
    port_fallback: bool = Field(default=True, description="Auto-select fallback if port occupied")
    port_fallback_min: int = Field(default=8080, ge=1, le=65535)
    port_fallback_max: int = Field(default=8090, ge=1, le=65535)
    open_browser: bool = Field(default=True, description="Auto-open browser on startup")
    workers: int = Field(default=1, ge=1, le=4, description="Worker count (1 for GPU)")


class GenerationConfig(BaseModel):
    """Generation-related configuration."""
    max_chars_per_segment: int = Field(default=200, ge=50, le=500, description="Max chars per TTS segment")
    default_sample_rate: int = Field(default=24000, description="Default audio sample rate")
    default_speed: float = Field(default=1.0, gt=0, le=3.0, description="Default speech speed")
    default_seed: int = Field(default=42, description="Default random seed")
    script_studio_silence_secs: float = Field(default=0.4, gt=0, le=2.0, description="Silence between script segments")


class MemoryConfig(BaseModel):
    """Memory management configuration."""
    max_cache_size: int = Field(default=15, ge=1, le=100, description="Max voice clone embeddings cached")
    target_max_usage: float = Field(default=0.75, gt=0, le=0.95, description="Target GPU memory usage ratio")
    check_interval: float = Field(default=0.5, gt=0, le=5.0, description="GPU memory check interval (seconds)")
    preload_buffer: int = Field(default=1024, ge=256, le=4096, description="Preload buffer size (MB)")


class ModelConfig(BaseModel):
    """Model path and parameters configuration."""
    base_dir: str = Field(default="models", description="Base directory for model weights")
    voxcpm_vram: float = Field(default=6.0, gt=0, description="VoxCPM2 VRAM requirement (GB)")
    indextts2_vram: float = Field(default=6.0, gt=0, description="IndexTTS 2.0 VRAM requirement (GB)")


class I18nConfig(BaseModel):
    """Internationalization configuration."""
    default_lang: str = Field(default="zh", pattern="^(zh|en)$", description="Default language code")
    supported_langs: List[str] = Field(default=["zh", "en"], description="Supported language codes")


class AppConfig(BaseModel):
    """Root application configuration model."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    i18n: I18nConfig = Field(default_factory=I18nConfig)

    @field_validator("server")
    @classmethod
    def validate_worker_count(cls, v: ServerConfig) -> ServerConfig:
        if v.workers > 1:
            raise ValueError("Workers > 1 not supported for GPU workloads")
        return v


def load_config_dict(yaml_data: dict) -> AppConfig:
    """Load and validate configuration from a YAML-parsed dictionary."""
    server_data = {}
    generation_data = {}
    memory_data = {}
    models_data = {}
    i18n_data = {}

    if "server" in yaml_data:
        s = yaml_data["server"]
        server_data = {k: v for k, v in s.items() if k in ServerConfig.model_fields}
    if "generation" in yaml_data:
        g = yaml_data["generation"]
        generation_data = {k: v for k, v in g.items() if k in GenerationConfig.model_fields}
    if "memory" in yaml_data:
        m = yaml_data["memory"]
        memory_data = {k: v for k, v in m.items() if k in MemoryConfig.model_fields}
    if "models" in yaml_data:
        md = yaml_data["models"]
        models_data = {k: v for k, v in md.items() if k in ModelConfig.model_fields}
    if "i18n" in yaml_data:
        i18n_data = {k: v for k, v in yaml_data["i18n"].items() if k in I18nConfig.model_fields}

    return AppConfig(
        server=ServerConfig(**server_data),
        generation=GenerationConfig(**generation_data),
        memory=MemoryConfig(**memory_data),
        models=ModelConfig(**models_data),
        i18n=I18nConfig(**i18n_data),
    )
