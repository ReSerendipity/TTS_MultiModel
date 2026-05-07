# TTS MultiModel - 模型扩展指南

> 本文档说明如何向 TTS MultiModel 项目添加新的 TTS 模型引擎

## 项目架构概述

TTS MultiModel 采用**插件式引擎架构**，核心设计原则：

- **引擎接口协议化** - 所有引擎必须实现 `TTSEngine` 或 `ControllableTTSEngine` 接口
- **模型加载解耦** - 引擎负责自己的模型加载和卸载
- **路由层统一调用** - 路由层只调用引擎接口，不关心具体实现

### 核心组件

```
bin/integrated_app/
├── engine_interface.py      # 引擎接口定义（Protocol）
├── model_registry.py        # 模型状态管理
├── model_manager.py         # 模型加载/卸载管理
├── engines/
│   ├── __init__.py          # 引擎注册
│   └── voxcpm2_engine.py    # VoxCPM2 引擎实现（参考示例）
└── routes/
    └── *.py                 # 路由层调用引擎
```

---

## 引擎接口协议

所有 TTS 引擎必须实现以下接口之一：

### 1. 基础接口：`TTSEngine`

适用于标准 TTS 模型（文本转语音）

```python
from typing import Protocol, Generator, Tuple, Optional

class TTSEngine(Protocol):
    def is_ready(self) -> bool:
        """检查引擎是否加载并准备就绪"""
        ...

    def load(self) -> None:
        """加载模型到内存/GPU"""
        ...

    def unload(self) -> None:
        """卸载模型，释放 GPU 内存"""
        ...

    def generate_voice_design(
        self,
        text: str,
        instruction: str = "",
        normalize: bool = True,
    ) -> Tuple[str, str]:
        """从文本生成语音
        返回: (音频文件路径, 状态消息)
        """
        ...

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ) -> Tuple[str, str]:
        """使用参考音频克隆音色
        返回: (音频文件路径, 状态消息)
        """
        ...

    def generate_script(
        self,
        text: str,
        speaker_map: dict,
        persona_map: dict = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """从多角色脚本文本生成语音
        返回: (音频文件路径, 状态消息)
        """
        ...

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        **kwargs,
    ) -> Generator[Any, None, None]:
        """流式生成（适用于长文本）
        返回: 音频块生成器
        """
        ...
```

### 2. 高级接口：`ControllableTTSEngine`

在 `TTSEngine` 基础上，支持更精细的控制参数：

```python
class ControllableTTSEngine(Protocol):
    # 必须实现 TTSEngine 的所有方法，再加上：

    def generate_ultimate_clone(
        self,
        text: str,
        lang: str,
        ref_audio: str,
        denoise_strength: str,
        use_random_seed: bool,
        cfg_scale: float,
        denoise_steps: int,
        seed: int,
    ) -> Tuple[str, str]:
        """使用完整可控参数生成克隆语音"""
        ...

    def generate_with_prompt(
        self,
        text: str,
        prompt_wav_path: str,
        prompt_text: str,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        normalize: bool = True,
        denoise: bool = True,
        retry_badcase: bool = True,
        retry_badcase_max_times: int = 3,
        retry_badcase_ratio_threshold: float = 6.0,
        min_len: int = 2,
        max_len: int = 4096,
    ) -> Tuple[str, str]:
        """使用提示音频继续生成"""
        ...

    def load_lora(self, lora_weights_path: str) -> Tuple[list, list]:
        """加载 LoRA 微调权重"""
        ...

    def unload_lora(self) -> None:
        """卸载 LoRA 权重"""
        ...
```

---

## 实现新引擎的步骤

### 步骤 1：创建引擎类

在 `bin/integrated_app/engines/` 目录下创建新文件，例如 `my_new_engine.py`：

```python
# -*- coding: utf-8 -*-
"""My New TTS Engine"""

import os
import logging
from typing import Tuple, Optional, Generator, Any

logger = logging.getLogger("tts_multimodel")


class MyNewEngine:
    """自定义 TTS 引擎实现"""

    def __init__(self, model_path: str, config: dict):
        """初始化引擎

        Args:
            model_path: 模型文件路径
            config: 引擎配置字典
        """
        self.model_path = model_path
        self.config = config
        self._model = None
        self._is_loaded = False

    def is_ready(self) -> bool:
        """检查模型是否已加载"""
        return self._is_loaded and self._model is not None

    def load(self) -> None:
        """加载模型到内存"""
        try:
            logger.info(f"Loading model from {self.model_path}")
            # 在这里实现模型加载逻辑
            # self._model = load_model(self.model_path)
            self._is_loaded = True
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def unload(self) -> None:
        """卸载模型，释放 GPU 内存"""
        try:
            logger.info("Unloading model...")
            # 在这里实现模型卸载逻辑
            # del self._model
            self._model = None
            self._is_loaded = False
            logger.info("Model unloaded successfully")
        except Exception as e:
            logger.error(f"Failed to unload model: {e}")

    def generate_voice_design(
        self,
        text: str,
        instruction: str = "",
        normalize: bool = True,
    ) -> Tuple[str, str]:
        """从文本生成语音"""
        if not self.is_ready():
            return "", "Error: Model not loaded"

        try:
            # 在这里实现语音生成逻辑
            # audio = self._model.synthesize(text, instruction=instruction)
            # audio_path = save_audio(audio)
            return "output.wav", "Voice generated successfully"
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return "", f"Error: {str(e)}"

    def generate_voice_clone(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        instruction: str = "",
        normalize: bool = True,
        **kwargs,
    ) -> Tuple[str, str]:
        """使用参考音频克隆音色"""
        if not self.is_ready():
            return "", "Error: Model not loaded"

        try:
            # 在这里实现音色克隆逻辑
            return "output_clone.wav", "Voice cloned successfully"
        except Exception as e:
            logger.error(f"Clone failed: {e}")
            return "", f"Error: {str(e)}"

    def generate_script(
        self,
        text: str,
        speaker_map: dict,
        persona_map: dict = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """从多角色脚本生成语音"""
        if not self.is_ready():
            return "", "Error: Model not loaded"

        try:
            # 在这里实现多角色脚本生成逻辑
            return "output_script.wav", "Script audio generated successfully"
        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            return "", f"Error: {str(e)}"

    def generate_streaming(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        **kwargs,
    ) -> Generator[Any, None, None]:
        """流式生成长文本语音"""
        if not self.is_ready():
            return

        try:
            # 在这里实现流式生成逻辑
            # for chunk in self._model.stream_generate(text):
            #     yield chunk
            pass
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
```

### 步骤 2：注册引擎

在 `bin/integrated_app/engines/__init__.py` 中注册新引擎：

```python
# -*- coding: utf-8 -*-
"""Engine registry and factory."""

from typing import Dict, Type, Optional
from bin.integrated_app.engine_interface import TTSEngine

# 导入引擎实现
from bin.integrated_app.engines.voxcpm2_engine import VoxCPM2Engine
from bin.integrated_app.engines.my_new_engine import MyNewEngine

# 引擎注册表
ENGINE_REGISTRY: Dict[str, Type] = {
    "voxcpm2": VoxCPM2Engine,
    "my_new_engine": MyNewEngine,  # 添加新引擎
}


def get_engine(engine_name: str) -> Optional[Type[TTSEngine]]:
    """根据名称获取引擎类"""
    return ENGINE_REGISTRY.get(engine_name)


def list_engines() -> list:
    """列出所有已注册的引擎名称"""
    return list(ENGINE_REGISTRY.keys())
```

### 步骤 3：添加模型配置

在 `bin/integrated_app/config.py` 中添加新引擎的模型路径配置：

```python
# 在 config.py 中添加新引擎配置

# My New Engine 模型路径
MY_NEW_ENGINE_MODEL_PATH = os.path.join(PRETRAINED_DIR, "MyNewEngine")
```

### 步骤 4：更新 ModelRegistry

在 `bin/integrated_app/model_registry.py` 中添加新引擎的状态管理：

```python
class ModelRegistry:
    def __init__(self):
        # ... 现有代码 ...
        
        # My New Engine 状态
        self.my_new_model = None
        self.my_new_loaded = False

    # 添加状态管理方法
    def set_my_new_loaded(self, model):
        self.my_new_model = model
        self.my_new_loaded = True
        self.current_engine = "my_new_engine"

    def clear_my_new(self):
        self.my_new_model = None
        self.my_new_loaded = False
```

### 步骤 5：更新 ModelManager

在 `bin/integrated_app/model_manager.py` 中添加新引擎的加载/卸载逻辑：

```python
def load_engine(self, engine_name: str):
    """加载指定引擎"""
    if engine_name == "my_new_engine":
        model_path = config.MY_NEW_ENGINE_MODEL_PATH
        engine = MyNewEngine(model_path=model_path, config={})
        engine.load()
        self.registry.set_my_new_loaded(engine)
```

---

## 模型路径配置规范

### 目录结构

每个引擎的模型文件应放在 `pretrained_models/` 目录下：

```
pretrained_models/
├── VoxCPM2/              # VoxCPM2 模型文件
├── SenseVoiceSmall/      # ASR 模型文件
├── speech_zipenhancer/   # 音频增强模型
└── MyNewEngine/          # 新引擎模型文件
    ├── config.json       # 模型配置
    ├── model.bin         # 模型权重
    └── tokenizer/        # 分词器（如有）
```

### 配置项命名

遵循以下命名规范：

```python
{ENGINE_NAME}_MODEL_PATH          # 主模型路径
{ENGINE_NAME}_ASR_PATH            # ASR 模型路径（如有）
{ENGINE_NAME}_DENOISER_PATH       # 降噪模型路径（如有）
{ENGINE_NAME}_CONFIG_PATH         # 配置文件路径（如有）
```

---

## 开发注意事项

### GPU 内存管理

- 引擎的 `unload()` 方法必须释放所有 GPU 内存
- 使用 `torch.cuda.empty_cache()` 清理缓存
- 避免在多次生成之间保留不必要的张量

```python
def unload(self) -> None:
    if self._model is not None:
        del self._model
        self._model = None
        self._is_loaded = False
        import torch
        torch.cuda.empty_cache()
        logger.info("GPU memory cleared")
```

### 错误处理

- 所有引擎方法必须捕获异常并返回有意义的错误消息
- 不要向用户抛出未处理的异常
- 使用 logger 记录详细错误信息

### 音频格式

- 输出音频统一使用 `.wav` 格式（16-bit PCM, 22050Hz 或 24000Hz）
- 如需其他格式，在 `audio_processing.py` 中转换

### 日志记录

```python
import logging
logger = logging.getLogger("tts_multimodel")

# 记录关键操作
logger.info("Loading model...")
logger.warning("Model already loaded, skipping")
logger.error(f"Failed to load: {e}")
```

---

## 测试新引擎

### 单元测试

在 `bin/test_integration.py` 中添加引擎测试：

```python
def test_my_new_engine():
    """测试新引擎"""
    from bin.integrated_app.engines.my_new_engine import MyNewEngine
    
    engine = MyNewEngine(model_path="test/path", config={})
    
    # 测试加载
    engine.load()
    assert engine.is_ready()
    
    # 测试生成
    audio_path, msg = engine.generate_voice_design("Hello, world!")
    assert os.path.exists(audio_path) or msg.startswith("Error")
    
    # 测试卸载
    engine.unload()
    assert not engine.is_ready()
```

### 集成测试

1. 启动应用
2. 在 UI 中切换引擎
3. 测试语音生成功能
4. 检查 GPU 内存是否正确释放

---

## 常见问题

### Q: 引擎初始化失败怎么办？

检查以下几点：
1. 模型路径是否正确
2. 模型文件是否存在
3. 依赖库是否已安装
4. GPU 内存是否充足

### Q: 如何支持多个引擎同时加载？

当前架构设计为**单引擎模式**（节省 GPU 内存）。如需多引擎支持，可修改 `model_manager.py`：

```python
class ModelManager:
    def __init__(self):
        self.engines: Dict[str, TTSEngine] = {}
    
    def load_engine(self, engine_name: str):
        if engine_name not in self.engines:
            engine = ENGINE_REGISTRY[engine_name]()
            engine.load()
            self.engines[engine_name] = engine
```

### Q: 如何处理模型下载？

建议在引擎的 `load()` 方法中检查模型是否存在，如不存在则提供清晰的错误提示：

```python
def load(self) -> None:
    if not os.path.exists(self.model_path):
        raise FileNotFoundError(
            f"Model not found at {self.model_path}\n"
            f"Please download the model and place it in this directory.\n"
            f"See MODEL_DOWNLOAD_GUIDE.md for instructions."
        )
```

---

## 贡献指南

如需将新引擎贡献到主仓库，请确保：

1. 实现所有必需的接口方法
2. 添加单元测试
3. 更新 `README.md` 和本文档
4. 模型文件**不要**提交到 Git（使用 `.gitignore` 排除）
5. 在 PR 中说明引擎的：
   - 功能特性
   - 支持的 TTS 模型
   - 下载和配置步骤
