# -*- coding: utf-8 -*-


def test_exception_hierarchy():
    from integrated_app.exceptions import (
        TTSError, ModelLoadError, InsufficientVRAMError,
        PersonaError, GenerationError, EngineSwitchError,
    )
    assert issubclass(ModelLoadError, TTSError)
    assert issubclass(InsufficientVRAMError, TTSError)
    assert issubclass(PersonaError, TTSError)
    assert issubclass(GenerationError, TTSError)
    assert issubclass(EngineSwitchError, TTSError)


def test_exception_error_codes():
    from integrated_app.exceptions import (
        ModelLoadError, InsufficientVRAMError,
        PersonaError, GenerationError, EngineSwitchError,
    )
    assert ModelLoadError().error_code == "MODEL_LOAD_ERROR"
    assert InsufficientVRAMError().error_code == "INSUFFICIENT_VRAM"
    assert PersonaError().error_code == "PERSONA_ERROR"
    assert GenerationError().error_code == "GENERATION_ERROR"
    assert EngineSwitchError().error_code == "ENGINE_SWITCH_ERROR"


def test_tts_error_handler():
    from integrated_app.exceptions import tts_error_handler, TTSError, GenerationError

    @tts_error_handler
    def raise_value_error():
        raise ValueError("test error")

    @tts_error_handler
    def raise_tts_error():
        raise TTSError("known error")

    import pytest
    with pytest.raises(GenerationError):
        raise_value_error()

    with pytest.raises(TTSError):
        raise_tts_error()
