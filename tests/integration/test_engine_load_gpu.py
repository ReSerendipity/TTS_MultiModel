"""真实模型权重加载端到端测试框架。

此模块定义了需要 GPU 和真实模型权重才能运行的集成测试。
在 CI 离线 CPU 环境中自动跳过，仅在开发者本机手动运行。

运行方式::

    pytest tests/integration/test_engine_load_gpu.py -v -m integration

需要：
- GPU 设备（CUDA 或 MPS）
- 已下载的模型权重（dots.tts / VoxCPM2 / IndexTTS2）
- 对应的 Python 依赖已安装
"""

import os
import sys

import pytest

# 集成测试标记，需要 GPU 环境
pytestmark = [pytest.mark.integration]


@pytest.fixture
def gpu_available():
    """检查 GPU 是否可用，不可用时跳过。"""
    try:
        import torch
        if torch.cuda.is_available() or torch.backends.mps.is_available():
            return True
    except ImportError:
        pass
    pytest.skip("GPU not available, skipping integration test")


@pytest.fixture
def dotstts_weights():
    """检查 dots.tts 权重是否已下载。"""
    weights_dir = os.environ.get(
        "DOTSTTS_MODEL_PATH",
        os.path.join(os.getcwd(), "pretrained_models", "dots.tts"),
    )
    if not os.path.isdir(weights_dir):
        pytest.skip(f"dots.tts weights not found at {weights_dir}")
    # 检查目录中是否有权重文件
    weight_files = [
        f for root, _, files in os.walk(weights_dir) for f in files
        if f.endswith((".bin", ".safetensors", ".pt", ".pth"))
    ]
    if not weight_files:
        pytest.skip("dots.tts weights directory exists but no weight files found")
    return weights_dir


class TestDotsTTSLoadGPU:
    """dots.tts 引擎在 GPU 上的真实加载测试。"""

    def test_load_dotstts_engine(self, gpu_available, dotstts_weights):
        """测试 dots.tts 引擎可以成功加载权重。"""
        try:
            from dots_tts.runtime import DotsTtsRuntime
        except ImportError:
            pytest.skip("dots.tts package not installed")

        from integrated_app.engines.dotstts_engine import DotsTTSEngine

        engine = DotsTTSEngine(model_dir=dotstts_weights)
        engine.load()
        assert engine.is_ready()
        engine.unload()
