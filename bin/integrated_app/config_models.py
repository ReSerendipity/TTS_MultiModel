"""Pydantic models for configuration validation."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AdvancedParamsConfig(BaseModel):
    """高级生成参数配置（不可变，替代全局 _ADVANCED_PARAMS 字典）"""

    model_config = ConfigDict(extra="ignore")
    max_len: int = Field(default=3000, description="最大生成长度（固定值）")
    split_max_chars: int = Field(default=200, description="每段最大字符数（固定值）")
    retry_badcase: bool = Field(default=True, description="自动重试坏案例")
    retry_badcase_max_times: int = Field(default=3, ge=0, le=10, description="最大重试次数")
    retry_badcase_ratio_threshold: float = Field(default=6.0, gt=0, description="重试时长比率阈值")
    trim_silence_vad: bool = Field(default=True, description="VAD 静音裁切")
    target_lufs: float = Field(default=-16.0, ge=-30, le=0, description="目标响度 (LUFS)")
    idle_timeout: int = Field(default=300, ge=60, le=3600, description="空闲超时时间 (秒)")

    def to_dict(self) -> dict:
        """转换为字典（用于传递给模型生成函数）"""
        return self.model_dump()


class ServerConfig(BaseModel):
    """Server-related configuration."""

    model_config = ConfigDict(extra="ignore")
    host: str = Field(default="127.0.0.1", description="Bind address")
    port: int = Field(default=8080, ge=1, le=65535, description="Port number")
    port_fallback: bool = Field(default=True, description="Auto-select fallback if port occupied")
    port_fallback_min: int = Field(default=8080, ge=1, le=65535)
    port_fallback_max: int = Field(default=8090, ge=1, le=65535)
    open_browser: bool = Field(default=True, description="Auto-open browser on startup")
    workers: int = Field(default=1, ge=1, le=4, description="Worker count (1 for GPU)")


class GenerationConfig(BaseModel):
    """Generation-related configuration."""

    model_config = ConfigDict(extra="ignore")
    max_chars_per_segment: int = Field(default=200, ge=50, le=500, description="Max chars per TTS segment")
    default_sample_rate: int = Field(default=24000, description="Default audio sample rate")
    default_speed: float = Field(default=1.0, gt=0, le=3.0, description="Default speech speed")
    default_seed: int = Field(default=42, description="Default random seed")
    script_studio_silence_secs: float = Field(default=0.4, gt=0, le=2.0, description="Silence between script segments")


class MemoryConfig(BaseModel):
    """Memory management configuration."""

    model_config = ConfigDict(extra="ignore")
    max_cache_size: int = Field(default=15, ge=1, le=100, description="Max voice clone embeddings cached")
    target_max_usage: float = Field(default=0.75, gt=0, le=0.95, description="Target GPU memory usage ratio")
    check_interval: float = Field(default=0.5, gt=0, le=5.0, description="GPU memory check interval (seconds)")
    preload_buffer: int = Field(default=1024, ge=256, le=4096, description="Preload buffer size (MB)")


class ModelConfig(BaseModel):
    """Model path and parameters configuration."""

    model_config = ConfigDict(extra="ignore")
    base_dir: str = Field(default="models", description="Base directory for model weights")
    voxcpm_vram: float = Field(default=6.0, gt=0, description="VoxCPM2 VRAM requirement (GB)")
    indextts2_vram: float = Field(default=6.0, gt=0, description="IndexTTS 2.0 VRAM requirement (GB)")


class I18nConfig(BaseModel):
    """Internationalization configuration."""

    model_config = ConfigDict(extra="ignore")
    default_lang: str = Field(default="zh", pattern="^(zh|en)$", description="Default language code")
    supported_langs: list[str] = Field(default=["zh", "en"], description="Supported language codes")


class SSEConfig(BaseModel):
    """SSE 事件流配置"""

    model_config = ConfigDict(extra="ignore")
    active_interval: float = Field(default=0.3, description="活跃状态等待超时（秒）")
    idle_base_interval: float = Field(default=1.0, description="空闲基础等待超时（秒）")
    idle_max_interval: float = Field(default=3.0, description="空闲最大等待超时（秒）")
    idle_step: float = Field(default=0.5, description="空闲间隔递增步长（秒）")
    heartbeat_interval: float = Field(default=30.0, description="心跳间隔（秒）")


class AudioPlayerConfig(BaseModel):
    """音频播放器配置"""

    model_config = ConfigDict(extra="ignore")
    waveform_steps: int = Field(default=300, description="波形采样步数")
    default_sample_rate: int = Field(default=44100, description="默认采样率")
    progress_update_ms: int = Field(default=100, description="进度更新间隔（毫秒）")


class UIConfig(BaseModel):
    """UI 布局配置"""

    model_config = ConfigDict(extra="ignore")
    sidebar_width: int = Field(default=240, description="侧边栏展开宽度（px）")
    sidebar_collapsed_width: int = Field(default=52, description="侧边栏折叠宽度（px）")


class ApiAuthConfig(BaseModel):
    """API authentication configuration."""

    model_config = ConfigDict(extra="ignore")
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

    model_config = ConfigDict(extra="ignore")
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

    model_config = ConfigDict(extra="ignore")
    version: str = Field(default="0.0.0", description="Application version")
    server: ServerConfig = Field(default_factory=ServerConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    generation_defaults: GenerationDefaultsConfig = Field(default_factory=GenerationDefaultsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    i18n: I18nConfig = Field(default_factory=I18nConfig)
    api_auth: ApiAuthConfig = Field(default_factory=ApiAuthConfig)
    sse: SSEConfig = Field(default_factory=SSEConfig)
    audio_player: AudioPlayerConfig = Field(default_factory=AudioPlayerConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @field_validator("server")
    @classmethod
    def validate_worker_count(cls, v: ServerConfig) -> ServerConfig:
        if v.workers > 1:
            raise ValueError("Workers > 1 not supported for GPU workloads")
        return v


def load_config_dict(yaml_data: dict) -> AppConfig:
    """Load and validate configuration from a YAML-parsed dictionary.

    With extra="ignore" on all models, Pydantic automatically filters unknown
    fields, so we no longer need manual per-section field filtering.
    """
    if not yaml_data:
        return AppConfig()

    version = str(yaml_data.get("version", "0.0.0")).strip().strip('"').strip("'")

    return AppConfig(
        version=version,
        server=yaml_data.get("server", {}),
        generation=yaml_data.get("generation", {}),
        generation_defaults=yaml_data.get("generation", {}),
        memory=yaml_data.get("memory", {}),
        models=yaml_data.get("models", {}),
        i18n=yaml_data.get("i18n", {}),
        api_auth=yaml_data.get("api_auth", {}),
        sse=yaml_data.get("sse", {}),
        audio_player=yaml_data.get("audio_player", {}),
        ui=yaml_data.get("ui", {}),
    )
