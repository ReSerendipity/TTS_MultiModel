<div align="center">

# TTS MultiModel

**多模型语音合成平台 | Multi-Model Text-to-Speech Platform**

基于 VoxCPM2 和 IndexTTS 2.0 的开源语音合成平台，支持声音克隆、声音设计、LoRA 微调与多角色剧本配音

A powerful open-source multi-model Text-to-Speech platform with voice cloning, voice design, LoRA fine-tuning, and multi-character script dubbing

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C.svg?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![CI](https://github.com/ReSerendipity/TTS_MultiModel/actions/workflows/ci.yml/badge.svg)](https://github.com/ReSerendipity/TTS_MultiModel/actions/workflows/ci.yml)

[English](#english) · [中文](#中文) · [Features](#-features) · [Quick Start](#-quick-start) · [Documentation](#-documentation) · [API](#-api-endpoints) · [Contributing](#-contributing)

</div>

---

<a id="中文"></a>

## 功能亮点

| 功能 | 描述 |
|------|------|
| **双引擎架构** | VoxCPM2 + IndexTTS 2.0 双 TTS 引擎，灵活切换 |
| **声音克隆** | 仅需少量音频样本即可克隆声音（可控克隆 + 极致克隆） |
| **声音设计** | 通过文字描述生成目标音色的语音 |
| **剧本配音** | 多角色对话剧本自动分配说话人，批量生成配音 |
| **流式生成** | 长文本实时流式音频输出（SSE） |
| **LoRA 微调** | 自定义数据集 LoRA 微调训练 |
| **Web 界面** | FastAPI + HTMX + Jinja2 现代化响应式 Web UI |
| **批量处理** | 支持批量音频生成 |
| **历史管理** | SQLite 历史记录，支持搜索、筛选、分页 |
| **多语言界面** | 支持中文、英文、日文、韩文界面切换 |
| **多 GPU 后端** | NVIDIA CUDA / Apple MPS / CPU |
| **自定义音色库** | 支持用户保存和管理自定义音色 |

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 (64-bit) 或 Linux |
| Python | 3.12+（Windows 内置 WinPython，也可自行安装） |
| GPU | NVIDIA (CUDA) / Apple Silicon (MPS)，推荐 6.5GB+ VRAM |
| VC 运行库 | Windows 需安装 Visual C++ Redistributable（项目内含） |

## 快速开始

### Windows 安装

**方式一：使用内置 WinPython（推荐）**

```bash
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel

# 安装 VC 运行库（首次运行）
# 双击 VC 运行库\VC_redist.x64.exe

# 安装依赖
install.bat

# 下载模型（见下方"模型下载"章节）

# 启动应用
start.bat
```

**方式二：使用自己的 Python 环境**

```bash
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel
pip install -r requirements.txt

# 下载模型后启动
python bin\clean_launch.py
```

### Linux 安装

```bash
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel
chmod +x install.sh && ./install.sh

# 下载模型后启动
chmod +x start.sh && ./start.sh
```

### Docker 部署

```bash
# Docker Compose 一键启动
docker compose up -d

# 或手动构建
docker build -t tts-multimodel .
docker run -d --gpus all -p 7869:7869 \
  -v ./pretrained_models:/app/pretrained_models \
  -v ./outputs:/app/outputs \
  -v ./personas:/app/personas \
  tts-multimodel
```

访问 `http://localhost:7869` 即可使用。Docker 部署需要 nvidia-docker runtime。

## 模型下载

模型需单独下载并放入 `pretrained_models/` 目录：

### VoxCPM2 引擎所需模型

| 模型 | 说明 | 存放目录 |
|------|------|----------|
| VoxCPM2 | 主 TTS 模型 | `pretrained_models/VoxCPM2/` |
| SenseVoiceSmall | ASR 语音识别模型 | `pretrained_models/SenseVoiceSmall/` |
| speech_zipenhancer | 音频降噪模型 | `pretrained_models/speech_zipenhancer/` |

### IndexTTS 2.0 引擎所需模型

| 模型 | 说明 | 存放目录 |
|------|------|----------|
| IndexTTS2 | IndexTTS 2.0 TTS 模型 | `pretrained_models/IndexTTS2/` |

从 [HuggingFace](https://huggingface.co/) 或 [ModelScope](https://modelscope.cn/) 下载。

快捷下载脚本：
```bash
python scripts/download_indextts2.py
```

详细说明见 [模型下载指南](docs/MODEL_DOWNLOAD_GUIDE.md)。

## 配置

编辑 `config.yaml` 自定义参数：

- **生成参数**: `cfg_value`（引导系数）、`inference_timesteps`（推理步数）、`normalize`（文本归一化）、`denoise`（降噪）
- **服务设置**: 端口（默认 7869）、主机地址、GPU 设置
- **API 认证**: `api_auth` 区域配置 token 认证

详见 [参数调整指南](docs/ADJUSTABLE_PARAMETERS.md)。

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 前端 | HTMX + Jinja2 + Bootstrap |
| TTS 引擎 | VoxCPM2 + IndexTTS 2.0 |
| ASR 引擎 | SenseVoiceSmall |
| 音频处理 | speech_zipenhancer + FFmpeg + SoX |
| 深度学习 | PyTorch + Transformers + FunASR |
| 数据库 | SQLite |
| 容器化 | Docker + Docker Compose |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/system/health` | GET | 健康检查 |
| `/api/system/gpu` | GET | GPU 利用率信息 |
| `/api/generate/voxcpm2/clone` | POST | 声音克隆 (VoxCPM2) |
| `/api/generate/voxcpm2/design` | POST | 声音设计 (VoxCPM2) |
| `/api/generate/voxcpm2/script` | POST | 剧本配音 (VoxCPM2) |
| `/api/generate/voxcpm2/streaming_sse` | POST | 流式生成 (SSE) |
| `/api/generate/indextts2/synthesize` | POST | TTS 合成 (IndexTTS 2.0) |
| `/api/model/load` | POST | 加载模型 |
| `/api/model/unload` | POST | 卸载模型 |
| `/api/history` | GET | 生成历史 |

> 生产环境建议在 `config.yaml` 的 `api_auth` 区域启用 API 认证。

## 项目结构

```
TTS_MultiModel/
├── bin/                          # 应用程序代码
│   ├── integrated_app/          # 主应用模块
│   │   ├── routes/             # API 路由处理
│   │   │   ├── generate/       # TTS 生成路由 (VoxCPM2, IndexTTS2)
│   │   │   └── system/         # 系统路由 (健康检查，GPU, 设置)
│   │   ├── engines/            # TTS 模型引擎
│   │   │   ├── voxcpm2/       # VoxCPM2 引擎实现
│   │   │   └── indextts2_engine.py  # IndexTTS 2.0 引擎
│   │   ├── training/           # 模型训练模块
│   │   ├── middleware/         # HTTP 中间件 (CSRF, 请求 ID)
│   │   ├── templates/          # Jinja2 HTML 模板
│   │   ├── locales/            # i18n 翻译文件 (zh, en, ja, ko)
│   │   └── ui/                 # UI 组件
│   ├── clean_launch.py         # 清理启动脚本
│   └── ffmpeg.exe / ffplay.exe # 音频工具
├── data/                        # 运行时数据
├── docs/                        # 项目文档
├── examples/                    # 训练示例数据
├── personas/                    # 自定义音色文件
├── scripts/                     # 工具和调试脚本
├── tests/                       # 测试套件
├── config.yaml                  # 应用配置
├── pyproject.toml               # Python 项目元数据
├── Dockerfile                   # Docker 构建配置
├── docker-compose.yml           # Docker Compose 配置
└── LICENSE                      # Apache 2.0 许可证
```

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| VC 运行库错误 (Windows) | 安装 `VC 运行库\VC_redist.x64.exe` |
| 模型未找到 | 确保模型下载到 `pretrained_models/` 且目录结构正确 |
| GPU 未检测到 | 安装对应 PyTorch 版本 (CUDA/MPS)，更新驱动 |
| 端口被占用 | 应用会自动选择可用端口，查看控制台输出 |
| Docker GPU 访问 | 确保安装 nvidia-docker runtime |

详细日志查看 `logs/app.log`。

## 参与贡献

欢迎贡献！参与方式：

1. **报告 Bug** - 提交 Issue 并附上复现步骤
2. **功能建议** - 提交带 `enhancement` 标签的 Issue
3. **提交代码** - Fork → Branch → Commit → Push → Pull Request
4. **改进文档** - 修复错别字、添加示例、翻译内容

详见 [贡献指南](CONTRIBUTING.md)。

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 开源。

Copyright (c) 2026 ReSerendipity

## 文档

- [模型下载指南](docs/MODEL_DOWNLOAD_GUIDE.md) - 模型下载与配置
- [模型扩展指南](docs/MODEL_EXTENSION_GUIDE.md) - 添加新 TTS 引擎
- [IndexTTS2 集成指南](docs/INDEXTTS2_INTEGRATION_GUIDE.md) - IndexTTS 2.0 集成详情
- [项目架构](docs/PROJECT_ARCHITECTURE.md) - 系统架构概览
- [参数调整](docs/ADJUSTABLE_PARAMETERS.md) - 配置参数参考
- [UI 开发指南](docs/UI 开发指南_README.md) - Web UI 开发指南
- [改进手册](docs/IMPROVEMENT_GUIDEBOOK.md) - 优化和改进建议

## 致谢

- [VoxCPM2](https://github.com/OpenBMB/VoxCPM2) - OpenBMB 开源 TTS 模型
- [IndexTTS2](https://github.com/IndexTeam/IndexTTS2) - IndexTeam 开源 TTS 模型
- [FastAPI](https://fastapi.tiangolo.com/) 和 [HTMX](https://htmx.org/) - Web 框架
- 所有开源贡献者

---

<div align="center">

**如果这个项目对你有帮助，请给个 Star 支持一下！**

</div>

---

<a id="english"></a>

## Features

<<<<<<< HEAD
| Feature | Description |
|---------|-------------|
| **Dual Engine** | VoxCPM2 + IndexTTS 2.0 dual TTS engine architecture |
| **Voice Cloning** | Clone voices with minimal audio samples (controllable + ultimate clone) |
| **Voice Design** | Generate speech from voice description text |
| **Script Studio** | Multi-character dialogue generation with speaker mapping |
| **Streaming** | Real-time audio streaming for long text (SSE) |
| **LoRA Fine-tuning** | Fine-tune models with custom datasets |
| **Web UI** | Modern responsive interface (FastAPI + HTMX + Jinja2) |
| **Batch Processing** | Batch audio generation support |
| **History** | SQLite-based history with search, filter, pagination |
| **i18n** | UI in Chinese, English, Japanese, Korean |
| **Multi-GPU** | NVIDIA CUDA / Apple MPS / CPU |
| **Custom Voice Library** | Save and manage custom voice personas |
=======
- **Multiple TTS Models** - Support for VoxCPM2 and IndexTTS 2.0 dual-engine architecture
- **Voice Cloning** - Create custom voice personas with minimal audio samples (controllable clone + ultimate clone)
- **Voice Design** - Generate speech from voice description text
- **Script Studio** - Multi-character dialogue generation with speaker mapping
- **Streaming Generation** - Real-time audio streaming for long text
- **LoRA Fine-tuning** - Fine-tune models with your own datasets via LoRA
- **Web Interface** - Responsive and modern web UI built with FastAPI + HTMX + Jinja2
- **Batch Processing** - Support for batch audio generation
- **History Management** - SQLite-based history tracking with search, filter, and pagination
- **Multi-language** - Internationalization support (i18n) for Chinese, English, Japanese, Korean
- **Multi-GPU Backend** - Support for NVIDIA CUDA, Apple MPS, and CPU
- **GPU Acceleration** - Optimized for GPU-based inference with adaptive VRAM management
- **9 Official Speakers** - Pre-configured voice personas covering various voice types
>>>>>>> c8bfcbd8f75e4e4fd69abff1f6aaf9a1b95e8018

## Quick Start

### Prerequisites

<<<<<<< HEAD
- **OS**: Windows 10/11 (64-bit) or Linux
- **Python**: 3.12+ (bundled WinPython for Windows)
- **GPU**: NVIDIA (CUDA) / Apple Silicon (MPS), 6.5GB+ VRAM recommended
- **VC Redistributable** (Windows): Included in `VC 运行库/` folder
=======
- **Operating System**: Windows 10/11 (64-bit) or Linux
- **Python**: 3.12+ (bundled WinPython included for Windows, or install your own)
- **GPU**: NVIDIA GPU (CUDA) recommended for optimal performance
  - Apple Silicon (MPS) is supported
  - Minimum 6.5GB VRAM required for VoxCPM2 model
  - CPU mode is available but slower
- **VC Redistributable** (Windows only): Visual C++ Redistributable (included in `VC运行库/` folder)
>>>>>>> c8bfcbd8f75e4e4fd69abff1f6aaf9a1b95e8018

### Windows

```bash
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel
install.bat    # Install dependencies
# Download models (see Model Download section)
start.bat      # Start the application
```

### Linux

```bash
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel
chmod +x install.sh && ./install.sh
# Download models (see Model Download section)
chmod +x start.sh && ./start.sh
```

### Docker

```bash
docker compose up -d
# Access at http://localhost:7869
```

## Model Download

Download models from [HuggingFace](https://huggingface.co/) or [ModelScope](https://modelscope.cn/) and place in `pretrained_models/`:

| Model | Description | Directory |
|-------|-------------|-----------|
| VoxCPM2 | Main TTS model | `pretrained_models/VoxCPM2/` |
| SenseVoiceSmall | ASR model | `pretrained_models/SenseVoiceSmall/` |
| speech_zipenhancer | Audio denoiser | `pretrained_models/speech_zipenhancer/` |
| IndexTTS2 | IndexTTS 2.0 model | `pretrained_models/IndexTTS2/` |

Quick download: `python scripts/download_indextts2.py`

See [Model Download Guide](docs/MODEL_DOWNLOAD_GUIDE.md) for details.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Web Framework | FastAPI + Uvicorn |
| Frontend | HTMX + Jinja2 + Bootstrap |
| TTS Engine | VoxCPM2 + IndexTTS 2.0 |
| ASR Engine | SenseVoiceSmall |
| Audio Processing | speech_zipenhancer + FFmpeg + SoX |
| Deep Learning | PyTorch + Transformers + FunASR |
| Database | SQLite |
| Containerization | Docker + Docker Compose |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system/health` | GET | Health check |
| `/api/system/gpu` | GET | GPU utilization |
| `/api/generate/voxcpm2/clone` | POST | Voice cloning (VoxCPM2) |
| `/api/generate/voxcpm2/design` | POST | Voice design (VoxCPM2) |
| `/api/generate/voxcpm2/script` | POST | Script generation (VoxCPM2) |
| `/api/generate/voxcpm2/streaming_sse` | POST | Streaming generation (SSE) |
| `/api/generate/indextts2/synthesize` | POST | TTS synthesis (IndexTTS 2.0) |
| `/api/model/load` | POST | Load model |
| `/api/model/unload` | POST | Unload model |
| `/api/history` | GET | Generation history |

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run unit tests only (skip GPU/integration tests)
pytest tests/ -v -k "not gpu and not cuda and not vram" -m "not integration"

# Run with coverage
pytest tests/ -v --cov=bin/integrated_app --cov-report=term-missing
```

### Code Quality

```bash
# Lint
ruff check bin/integrated_app/ scripts/

# Format
ruff format bin/integrated_app/ scripts/
```

### Code Structure

- **bin/integrated_app/**: Main application
  - `app_server.py`: Server entry point with background model loading
  - `config.py` / `config_models.py`: Pydantic-validated configuration management
  - `model_manager.py`: Model loading, unloading, engine switching with rollback
  - `model_registry.py`: Centralized model state management with engine protocol
  - `engine_interface.py`: TTSEngine Protocol definition for type-safe duck typing
  - `routes/`: HTTP route handlers (auto-discovered)
  - `engines/`: TTS engine implementations (VoxCPM2, IndexTTS 2.0)
  - `training/`: LoRA fine-tuning functionality
  - `cache.py`: Adaptive LRU cache with GPU-aware capacity management
  - `history_db.py`: SQLite-based generation history with full-text search
  - `gpu_backend.py`: Multi-backend GPU abstraction layer
  - `gpu_utils.py`: GPU memory management and OOM detection

For architecture details, see [Project Architecture](docs/PROJECT_ARCHITECTURE.md).

## Troubleshooting

### Common Issues

1. **VC Redistributable Error** (Windows):
   - Install `VC 运行库\VC_redist.x64.exe`

2. **Model Not Found**:
   - Ensure models are downloaded and placed in `pretrained_models/`
   - Check directory structure matches expected layout

3. **GPU Not Detected**:
   - Install GPU-compatible PyTorch version (CUDA for NVIDIA)
   - Verify GPU drivers are up to date
   - Check `python -c "import torch; print(torch.cuda.is_available())"`

4. **Port Already in Use**:
   - The app will auto-select an available port
   - Check console output for the actual URL

5. **Docker GPU Access**:
   - Ensure nvidia-docker runtime is installed
   - Verify with `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`

### Logs

Check `logs/app.log` for detailed error messages.

## Contributing

Contributions are welcome! Here's how you can help:

1. **Report Bugs** - Open an issue with detailed reproduction steps
2. **Suggest Features** - Open an issue with the `enhancement` label
3. **Submit Code** - Fork → Branch → Commit → Push → Pull Request
4. **Improve Docs** - Fix typos, add examples, translate

See [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the [Apache License 2.0](LICENSE).

Copyright (c) 2026 ReSerendipity

## Acknowledgments

- [VoxCPM2](https://github.com/OpenBMB/VoxCPM2) by OpenBMB
- [IndexTTS2](https://github.com/IndexTeam/IndexTTS2) by IndexTeam
- [FastAPI](https://fastapi.tiangolo.com/) and [HTMX](https://htmx.org/)
- All open-source contributors

---

<div align="center">

**If you find this project helpful, please consider giving it a Star!**

</div>
