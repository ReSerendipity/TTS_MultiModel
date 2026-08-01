# -*- coding: utf-8 -*-
"""GPT-SoVITS 引擎单元测试。

测试策略：
- 只测试**不依赖真实模型加载**的方法
- 覆盖 ``is_ready`` / ``version`` / ``unload`` / 未加载时的生成调用
  以及 ``generate_voice_design`` / ``generate_script`` 的 NotImplementedError
- 不依赖 GPU、模型权重、外部依赖
"""
import os
import sys
from pathlib import Path

import pytest

# 路径设置
_BIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"
)
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

# 离线模式
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


class TestGPTSoVITSEngineLifecycle:
    """测试 GPT-SoVITS 引擎生命周期（无需真实加载）"""

    def test_engine_class_exists(self):
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        assert GPTSoVITSEngine is not None

    def test_engine_is_tts_engine_subclass(self):
        """引擎必须实现 TTSEngine Protocol"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine
        from integrated_app.engine_interface import TTSEngine

        assert issubclass(GPTSoVITSEngine, TTSEngine)

    def test_construct_without_model_dir(self):
        """默认构造应使用 config 路径，不抛异常"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        assert engine.model_dir is not None
        assert engine.is_ready() is False

    def test_construct_with_custom_model_dir(self, tmp_path: Path):
        """显式传入 model_dir 应被使用"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        custom_dir = tmp_path / "gptsovits_models"
        custom_dir.mkdir()
        engine = GPTSoVITSEngine(model_dir=str(custom_dir))
        assert engine.model_dir == str(custom_dir)

    def test_is_ready_false_initially(self):
        """未调用 load() 时 is_ready() 必须返回 False"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        assert engine.is_ready() is False

    def test_version_returns_string(self):
        """version 属性必须是字符串"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        v = engine.version
        assert isinstance(v, str)
        assert len(v) > 0

    def test_unload_without_loaded_is_safe(self):
        """未加载时调用 unload() 不应抛异常"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        engine.unload()  # 不抛异常
        assert engine.is_ready() is False

    def test_class_name_is_gptsovits(self):
        """类名应包含 GPTSoVITS 标识（调度层用类名 + 注册表匹配）"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        assert "GPT" in GPTSoVITSEngine.__name__
        assert "SoVITS" in GPTSoVITSEngine.__name__


class TestGPTSoVITSEngineNotLoadedErrors:
    """测试未加载时调用生成方法必须抛 EngineNotLoadedError"""

    def test_generate_voice_clone_without_load(self):
        from integrated_app.exceptions import EngineNotLoadedError
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        with pytest.raises(EngineNotLoadedError) as exc_info:
            engine.generate_voice_clone(
                text="测试",
                reference_audio_path="dummy.wav",
                prompt_text="prompt",
                prompt_language="zh",
                text_language="zh",
            )
        assert exc_info.value.engine == "gptsovits"

    def test_generate_streaming_without_load(self):
        """generate_streaming 是生成器，需通过 next() 触发"""
        from integrated_app.exceptions import EngineNotLoadedError
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        gen = engine.generate_streaming(
            text="流式测试",
            reference_audio_path="dummy.wav",
            prompt_text="prompt",
            prompt_language="zh",
            text_language="zh",
        )
        with pytest.raises(EngineNotLoadedError) as exc_info:
            next(gen)
        assert exc_info.value.engine == "gptsovits"
        gen.close()


class TestGPTSoVITSEngineUnsupportedFeatures:
    """测试不支持的功能必须显式抛 NotImplementedError"""

    def test_generate_voice_design_not_implemented(self):
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        with pytest.raises(NotImplementedError):
            engine.generate_voice_design(text="设计", instruction="温柔女声")

    def test_generate_script_not_implemented(self):
        """generate_script 接受 text + speaker_map + persona_map"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine

        engine = GPTSoVITSEngine()
        with pytest.raises(NotImplementedError):
            engine.generate_script(text="Alice: 你好\nBob: 嗨")


class TestGPTSoVITSEngineLoadFailurePaths:
    """测试 load() 失败时的错误信息（不真正加载）"""

    def test_load_missing_repo_dir_raises(self, tmp_path: Path):
        """当 reference_repos/GPT-SoVITS 不存在时应抛 EngineLoadError"""
        from integrated_app.engines.gptsovits_engine import GPTSoVITSEngine
        from integrated_app.exceptions import EngineLoadError

        engine = GPTSoVITSEngine()
        # 临时把模块级常量改为不存在的路径
        import integrated_app.engines.gptsovits_engine as mod

        original = mod._GPTSOVITS_REPO_DIR
        mod._GPTSOVITS_REPO_DIR = str(tmp_path / "definitely_not_exists")
        try:
            with pytest.raises(EngineLoadError) as exc_info:
                engine.load()
            # 错误信息应引导用户
            assert "gptsovits" in str(exc_info.value).lower() or "GPT-SoVITS" in str(
                exc_info.value
            )
        finally:
            mod._GPTSOVITS_REPO_DIR = original
