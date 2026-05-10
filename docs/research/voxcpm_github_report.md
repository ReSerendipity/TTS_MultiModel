# VoxCPM GitHub 仓库研究报告

## 1. 仓库概览

| 属性 | 值 |
|------|------|
| **仓库地址** | https://github.com/OpenBMB/VoxCPM |
| **组织** | OpenBMB (ModelBest × THUHCSI) |
| **主要模型** | VoxCPM 0.5B / VoxCPM2 (2B) |
| **许可证** | Apache-2.0（可商用） |
| **核心架构** | Tokenizer-Free Diffusion Autoregressive |

## 2. 技术架构

### 2.1 核心架构组件

VoxCPM 采用 **LocEnc → TSLM → RALM → LocDiT** 四级流水线架构：

```
文本输入 → LocEnc (局部编码) → TSLM (时序语言模型) → RALM (残差语言模型) → LocDiT (局部扩散Transformer) → 音频输出
```

### 2.2 关键技术创新

| 技术 | 描述 |
|------|------|
| **Tokenizer-Free** | 无需离散token化，直接在连续空间建模语音 |
| **Diffusion Autoregressive** | 结合扩散模型和自回归架构 |
| **MiniCPM-4 Backbone** | 基于 MiniCPM-4 的语言模型基础 |
| **AudioVAE V2** | 非对称编解码，16kHz输入→48kHz输出 |
| **FSQ Constraints** | 通过有限标量量化增强生成稳定性 |
| **Implicit Semantic-Acoustic Decoupling** | 隐式语义-声学解耦 |

### 2.3 项目结构

```
VoxCPM/
├── src/voxcpm/          # 核心库代码
│   ├── model/           # 模型定义
│   ├── inference/       # 推理接口
│   ├── streaming/       # 流式生成
│   └── cli/             # 命令行接口
├── examples/            # 使用示例
├── scripts/             # 训练/微调脚本
├── conf/                # 配置文件
├── app.py               # Gradio Web Demo
├── pyproject.toml       # 项目配置
└── README.md            # 项目文档
```

## 3. 功能特性

### 3.1 核心功能

| 功能 | 描述 |
|------|------|
| **上下文感知语音生成** | 根据文本内容自动推断合适的韵律和表达方式 |
| **真实语音克隆** | 仅需短参考音频即可进行零样本语音克隆 |
| **高效合成** | RTX 4090 上 RTF 低至 0.17 |
| **流式生成** | 支持实时流式音频输出 |
| **多语言支持** | 支持中文和英文（VoxCPM 1.x）/ 30种语言（VoxCPM2） |

### 3.2 API 接口

**Python API:**
```python
from voxcpm import VoxCPM

model = VoxCPM.from_pretrained("openbmb/VoxCPM-0.5B")

# 非流式生成
wav = model.generate(
    text="VoxCPM is an innovative end-to-end TTS model...",
    prompt_wav_path=None,      # 可选：音色克隆参考音频
    prompt_text=None,          # 可选：参考文本
    cfg_value=2.0,             # 引导系数
    inference_timesteps=10,    # 推理步数
    normalize=True,            # 文本规范化
    denoise=True,              # 降噪
    retry_badcase=True,        # 坏情况重试
)

# 流式生成
for chunk in model.generate_streaming(text="..."):
    process(chunk)
```

**CLI 接口:**
```bash
# 直接合成
voxcpm --text "Hello world" --output out.wav

# 语音克隆
voxcpm --text "..." --prompt-audio voice.wav --prompt-text "ref transcript" --output out.wav

# 批量处理
voxcpm --input input.txt --output-dir outs

# Web Demo
python app.py
```

## 4. 性能指标

### 4.1 Seed-TTS-eval 基准测试

| 模型 | 参数 | 开源 | test-EN WER↓ | test-EN SIM↑ | test-ZH CER↓ | test-ZH SIM↑ |
|------|------|------|-------------|-------------|-------------|-------------|
| **VoxCPM** | 0.5B | ✅ | 1.85 | 72.9 | 0.93 | 77.2 |
| CosyVoice3 | 0.5B | ❌ | 2.02 | 71.8 | 1.16 | 78.0 |
| CosyVoice3 | 1.5B | ❌ | 2.22 | 72.0 | 1.12 | 78.1 |
| FireRedTTS-2 | 1.5B | ✅ | 1.95 | 66.5 | 1.14 | 73.6 |
| IndexTTS2 | 1.5B | ✅ | 2.23 | 70.6 | 1.03 | 76.5 |

### 4.2 CV3-eval 基准测试

| 模型 | zh CER↓ | zh WER↓ | hard-zh CER↓ | hard-zh SIM↑ |
|------|---------|---------|-------------|-------------|
| **VoxCPM** | 3.40 | 4.04 | 12.9 | 66.1 |
| CosyVoice2 | 4.08 | 6.32 | 12.58 | 72.6 |
| CosyVoice3-0.5B | 3.89 | 5.24 | 14.15 | 78.6 |
| IndexTTS2 | 3.58 | 4.45 | 12.8 | 74.6 |

### 4.3 硬件需求

| 属性 | 值 |
|------|------|
| **VRAM** | ~8 GB |
| **推荐 GPU** | NVIDIA RTX 4090 |
| **RTF (RTX 4090)** | ~0.30 (标准) / ~0.13 (Nano-vLLM) |
| **采样率** | 16kHz 输入 → 48kHz 输出 |

## 5. 社区支持

### 5.1 生态项目

| 项目 | 描述 |
|------|------|
| [NanoVLLM-VoxCPM](https://github.com/a710128/nanovllm-voxcpm) | 高吞吐量 GPU 服务 |
| [vLLM-Omni](https://github.com/vllm-project/vllm-omni) | 官方 vLLM 堆栈服务 |
| [VoxCPM.cpp](https://github.com/bluryar/VoxCPM.cpp) | ggml/GGUF CPU/CUDA/Vulkan 推理 |
| [VoxCPMANE](https://github.com/0seba/VoxCPMANE) | Apple Neural Engine 部署 |
| [ComfyUI-VoxCPM](https://github.com/wildminder/ComfyUI-VoxCPM) | 节点式工作流 |
| [MLX-Audio](https://github.com/Blaizzy/mlx-audio) | Apple Silicon MLX 推理 |

### 5.2 社区渠道

| 渠道 | 链接 |
|------|------|
| **Discord** | https://discord.gg/KZUx7tVNwz |
| **飞书群** | https://applink.feishu.cn/client/chat/chatter/add_by_link |
| **HuggingFace Space** | https://huggingface.co/spaces/OpenBMB/VoxCPM-Demo |

## 6. 最新动态

| 日期 | 更新内容 |
|------|----------|
| 2025.09.16 | 开源 VoxCPM-0.5B 权重 |
| 2025.09.16 | 提供 Gradio Playground |
| 2026 | VoxCPM2 (2B参数，30语言) 发布 |

## 7. 许可证

- **代码和模型权重**：Apache-2.0
- **商用**：允许，但建议进行严格的安全评估
- **限制**：严禁用于冒充、欺诈或传播虚假信息

## 8. 引用

```bibtex
@article{voxcpm2025,
    title={VoxCPM: Tokenizer-Free TTS for Context-Aware Speech Generation and True-to-Life Voice Cloning},
    author={Zhou, Yixuan and Zeng, Guoyang and Liu, Xin and Li, Xiang and Yu, Renjie and Wang, Ziyang and Ye, Runchuan and Sun, Weiyue and Gui, Jiancheng and Li, Kehan and Wu, Zhiyong and Liu, Zhiyuan},
    journal={arXiv preprint arXiv:2509.24650},
    year={2025},
}

@article{voxcpm2_2026,
    title={VoxCPM2: Tokenizer-Free TTS for Multilingual Speech Generation, Creative Voice Design, and True-to-Life Cloning},
    author={VoxCPM Team},
    journal={GitHub},
    year={2026},
}
```
