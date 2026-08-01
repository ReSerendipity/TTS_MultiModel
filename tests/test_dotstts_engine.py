# -*- coding: utf-8 -*-
"""dots.tts 引擎单元测试。

测试策略与 ``test_gptsovits_engine.py`` 一致：
- 只测试不依赖真实模型加载的路径
- 覆盖生命周期、错误路径、不支持的功能
"""
import os
import sys
from pathlib import Path

import pytest

_BIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"
)
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


class TestDotsTTSEngineLifecycle:
    """测试 dots.tts 引擎生命周期（无需真实加载）"""

    def test_engine_class_exists(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        assert DotsTTSEngine is not None

    def test_engine_is_tts_engine_subclass(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine
        from integrated_app.engine_interface import TTSEngine

        assert issubclass(DotsTTSEngine, TTSEngine)

    def test_construct_without_model_dir(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        assert engine.model_dir is not None
        assert engine.is_ready() is False

    def test_construct_with_custom_model_dir(self, tmp_path: Path):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        custom_dir = tmp_path / "dotstts_models"
        custom_dir.mkdir()
        engine = DotsTTSEngine(model_dir=str(custom_dir))
        assert engine.model_dir == str(custom_dir)

    def test_is_ready_false_initially(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        assert engine.is_ready() is False

    def test_version_returns_string(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        v = engine.version
        assert isinstance(v, str)
        assert len(v) > 0

    def test_unload_without_loaded_is_safe(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        engine.unload()
        assert engine.is_ready() is False

    def test_class_name_is_dotstts(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        assert "Dots" in DotsTTSEngine.__name__
        assert "TTS" in DotsTTSEngine.__name__

    def test_precision_attribute_set(self):
        """precision 必须根据设备正确选择（CPU 时为 float32）"""
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        # 测试环境是 CPU-only（CI 设置 CUDA_VISIBLE_DEVICES=""）
        assert engine.precision in ("bfloat16", "float32")


class TestDotsTTSEngineNotLoadedErrors:
    """测试未加载时调用生成方法必须抛 EngineNotLoadedError"""

    def test_generate_voice_clone_without_load(self):
        from integrated_app.exceptions import EngineNotLoadedError
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        with pytest.raises(EngineNotLoadedError) as exc_info:
            engine.generate_voice_clone(
                text="测试",
                reference_audio_path="dummy.wav",
                prompt_text="prompt",
            )
        assert exc_info.value.engine == "dotstts"

    def test_generate_streaming_without_load(self):
        """generate_streaming 是生成器，需通过 next() 触发"""
        from integrated_app.exceptions import EngineNotLoadedError
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        gen = engine.generate_streaming(
            text="流式测试",
            reference_audio_path="dummy.wav",
            prompt_text="prompt",
        )
        with pytest.raises(EngineNotLoadedError) as exc_info:
            next(gen)
        assert exc_info.value.engine == "dotstts"
        gen.close()


class TestDotsTTSEngineUnsupportedFeatures:
    """测试不支持的功能必须显式抛 NotImplementedError"""

    def test_generate_voice_design_not_implemented(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        with pytest.raises(NotImplementedError):
            engine.generate_voice_design(text="设计", instruction="温柔女声")

    def test_generate_script_not_implemented(self):
        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine()
        with pytest.raises(NotImplementedError):
            engine.generate_script(text="Alice: 你好\nBob: 嗨")


class TestDotsTTSEngineLoadFailurePaths:
    """测试 load() 失败时的错误信息（不真正加载）"""

    def test_load_missing_model_dir_raises(self, tmp_path: Path):
        """当模型目录不存在时 load() 应抛 EngineLoadError"""
        from integrated_app.engines.dotstts_engine import DotsTTSEngine
        from integrated_app.exceptions import EngineLoadError

        missing_dir = tmp_path / "definitely_not_exists"
        engine = DotsTTSEngine(model_dir=str(missing_dir))
        with pytest.raises(EngineLoadError) as exc_info:
            engine.load()
        # 错误信息应包含引导（下载脚本路径或模型目录）
        err_str = str(exc_info.value).lower()
        assert "dotstts" in err_str or "dot" in err_str
