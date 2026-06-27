"""统一异常层次结构与错误处理装饰器"""

import asyncio
import functools


class TTSError(Exception):
    """TTS 系统基础异常"""

    def __init__(self, message="", code="TTS_ERROR"):
        self.message = message
        self.code = code
        # 保持向后兼容：error_code 是 code 的别名
        self.error_code = code
        super().__init__(message)


class ModelLoadError(TTSError):
    """模型加载失败"""

    def __init__(self, message="模型加载失败"):
        super().__init__(message, code="MODEL_LOAD_ERROR")


class InsufficientVRAMError(TTSError):
    """显存不足"""

    def __init__(self, message="显存不足"):
        super().__init__(message, code="INSUFFICIENT_VRAM")


class PersonaError(TTSError):
    """音色操作失败"""

    def __init__(self, message="音色操作失败"):
        super().__init__(message, code="PERSONA_ERROR")


class GenerationError(TTSError):
    """生成失败"""

    def __init__(self, message="生成失败", engine: str = ""):
        self.engine = engine
        super().__init__(message, code="GENERATION_ERROR")


class EngineSwitchError(TTSError):
    """引擎切换失败"""

    def __init__(self, message="引擎切换失败"):
        super().__init__(message, code="ENGINE_SWITCH_ERROR")


class EngineLoadError(TTSError):
    """引擎加载失败"""

    def __init__(self, message: str, engine: str = ""):
        self.engine = engine
        super().__init__(message, code="ENGINE_LOAD_ERROR")


class EngineNotLoadedError(TTSError):
    """引擎未加载"""

    def __init__(self, message: str = "引擎未加载，请先加载模型", engine: str = ""):
        self.engine = engine
        super().__init__(message, code="ENGINE_NOT_LOADED")


class AudioProcessingError(TTSError):
    """音频处理失败"""

    def __init__(self, message: str):
        super().__init__(message, code="AUDIO_PROCESSING_ERROR")


class ValidationError(TTSError):
    """输入验证失败"""

    def __init__(self, message: str, field: str = ""):
        self.field = field
        super().__init__(message, code="VALIDATION_ERROR")


class ModelSwitchError(TTSError):
    """模型切换失败"""

    def __init__(self, message: str, from_engine: str = "", to_engine: str = ""):
        self.from_engine = from_engine
        self.to_engine = to_engine
        super().__init__(message, code="MODEL_SWITCH_ERROR")


def tts_error_handler(func):
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TTSError:
            raise
        except Exception as e:
            raise GenerationError(f"未知错误: {type(e).__name__}: {e}") from e

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TTSError:
            raise
        except Exception as e:
            raise GenerationError(f"未知错误: {type(e).__name__}: {e}") from e

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
