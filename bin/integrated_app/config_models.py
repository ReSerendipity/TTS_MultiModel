# -*- coding: utf-8 -*-
"""Pydantic models for configuration validation."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, List


class AdvancedParamsConfig(BaseModel):
    """高级生成参数配置（不可变，替代全局 _ADVANCED_PARAMS 字典）"""
    max_len: int = Field(default=3000, description="最大生成长度（固定值）")
    split_max_chars: int = Field(default=200, description="每段最大字符数（固定值）")
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


class SpeakerInfo(BaseModel):
    """Individual speaker information."""
    id: str = Field(description="Speaker unique identifier")
    name_zh: str = Field(default="", description="Chinese display name")
    description: str = Field(default="", description="Speaker description")
    type: str = Field(default="", description="Voice type tag")
    traits: str = Field(default="", description="Voice traits summary")


class SpeakerConfig(BaseModel):
    """Speaker configuration."""
    official: List[SpeakerInfo] = Field(default_factory=list, description="Official speaker list")


class ApiAuthConfig(BaseModel):
    """API authentication configuration."""
    enabled: bool = Field(default=False, description="Whether API auth is enabled")
    token: str = Field(default="", description="API auth token")

    @model_validator(mode="after")
    def validate_auth_config(self):
        if self.enabled and not self.token:
            import warnings
            warnings.warn(
                "API auth is enabled but token is empty. All requests will be rejected.",
                UserWarning,
                stacklevel=2,
            )
        return self


class GenerationDefaultsConfig(BaseModel):
    """VoxCPM2 generation default parameters (from config.yaml generation section)."""
    cfg_value: float = Field(default=2.0, description="CFG value")
    inference_timesteps: int = Field(default=10, ge=1, description="Inference timesteps")
    normalize: bool = Field(default=True, description="Normalize audio")
    denoise: bool = Field(default=True, description="Denoise audio")
    retry_badcase: bool = Field(default=True, description="Auto retry bad cases")
    retry_badcase_max_times: int = Field(default=3, ge=0, le=10, description="Max retry times")
    retry_badcase_ratio_threshold: float = Field(default=6.0, gt=0, description="Retry ratio threshold")
    min_len: int = Field(default=2, ge=1, description="Min generation length")
    max_len: int = Field(default=4096, ge=1, description="Max generation length")
    split_max_chars: int = Field(default=200, ge=50, le=500, description="Max chars per split")


class AppConfig(BaseModel):
    """Root application configuration model."""
    version: str = Field(default="0.0.0", description="Application version")
    server: ServerConfig = Field(default_factory=ServerConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    generation_defaults: GenerationDefaultsConfig = Field(default_factory=GenerationDefaultsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    i18n: I18nConfig = Field(default_factory=I18nConfig)
    speakers: SpeakerConfig = Field(default_factory=SpeakerConfig)
    api_auth: ApiAuthConfig = Field(default_factory=ApiAuthConfig)

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
    generation_defaults_data = {}
    memory_data = {}
    models_data = {}
    i18n_data = {}
    speakers_data = {}
    api_auth_data = {}
    version = "0.0.0"

    if yaml_data:
        version = str(yaml_data.get("version", "0.0.0")).strip().strip('"').strip("'")

    if "server" in yaml_data:
        s = yaml_data["server"]
        server_data = {k: v for k, v in s.items() if k in ServerConfig.model_fields}
    if "generation" in yaml_data:
        g = yaml_data["generation"]
        generation_defaults_data = {k: v for k, v in g.items() if k in GenerationDefaultsConfig.model_fields}
        generation_data = {k: v for k, v in g.items() if k in GenerationConfig.model_fields}
    if "memory" in yaml_data:
        m = yaml_data["memory"]
        memory_data = {k: v for k, v in m.items() if k in MemoryConfig.model_fields}
    if "models" in yaml_data:
        md = yaml_data["models"]
        models_data = {k: v for k, v in md.items() if k in ModelConfig.model_fields}
    if "i18n" in yaml_data:
        i18n_data = {k: v for k, v in yaml_data["i18n"].items() if k in I18nConfig.model_fields}
    if "speakers" in yaml_data:
        sp = yaml_data["speakers"]
        if isinstance(sp, dict) and "official" in sp:
            official_list = sp["official"]
            if isinstance(official_list, list):
                speakers_info = []
                for s in official_list:
                    if isinstance(s, dict) and s.get("id"):
                        speakers_info.append({
                            "id": s["id"],
                            "name_zh": s.get("name_zh", s["id"]),
                            "description": s.get("description", ""),
                            "type": s.get("type", ""),
                            "traits": s.get("traits", ""),
                        })
                speakers_data = {"official": speakers_info}
    if "api_auth" in yaml_data:
        auth = yaml_data["api_auth"]
        if isinstance(auth, dict):
            api_auth_data = {k: v for k, v in auth.items() if k in ApiAuthConfig.model_fields}

    return AppConfig(
        version=version,
        server=ServerConfig(**server_data),
        generation=GenerationConfig(**generation_data),
        generation_defaults=GenerationDefaultsConfig(**generation_defaults_data),
        memory=MemoryConfig(**memory_data),
        models=ModelConfig(**models_data),
        i18n=I18nConfig(**i18n_data),
        speakers=SpeakerConfig(**speakers_data) if speakers_data else SpeakerConfig(),
        api_auth=ApiAuthConfig(**api_auth_data) if api_auth_data else ApiAuthConfig(),
    )
