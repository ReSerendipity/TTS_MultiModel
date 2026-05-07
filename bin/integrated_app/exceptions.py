# -*- coding: utf-8 -*-
"""统一异常层次结构与错误处理装饰器"""

import functools


class TTSError(Exception):
    """TTS 基础异常"""
    def __init__(self, message="", error_code="TTS_ERROR"):
        self.error_code = error_code
        super().__init__(message)


class ModelLoadError(TTSError):
    """模型加载失败"""
    def __init__(self, message="模型加载失败"):
        super().__init__(message, "MODEL_LOAD_ERROR")


class InsufficientVRAMError(TTSError):
    """显存不足"""
    def __init__(self, message="显存不足"):
        super().__init__(message, "INSUFFICIENT_VRAM")


class PersonaError(TTSError):
    """音色操作失败"""
    def __init__(self, message="音色操作失败"):
        super().__init__(message, "PERSONA_ERROR")


class GenerationError(TTSError):
    """生成失败"""
    def __init__(self, message="生成失败"):
        super().__init__(message, "GENERATION_ERROR")


class EngineSwitchError(TTSError):
    """引擎切换失败"""
    def __init__(self, message="引擎切换失败"):
        super().__init__(message, "ENGINE_SWITCH_ERROR")


def tts_error_handler(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TTSError:
            raise
        except Exception as e:
            raise GenerationError(f"未知错误: {type(e).__name__}: {e}") from e
    return wrapper
