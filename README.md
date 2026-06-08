# 🎙️ TTS MultiModel

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C.svg?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

基于 VoxCPM2 的多模型语音合成平台。支持声音设计、声音克隆、LoRA 微调训练与多角色剧本配音。内置 9 种预置音色，支持中英日韩多语言界面。

A powerful multi-model Text-to-Speech (TTS) web application with a modern FastAPI-based web interface, supporting voice cloning, model training, and high-quality speech synthesis.

## ✨ Features

- 🎤 **Multiple TTS Models** - Support for VoxCPM2 and IndexTTS 2.0 dual-engine architecture
- 🎭 **Voice Cloning** - Create custom voice personas with minimal audio samples (controllable clone + ultimate clone)
- 🎨 **Voice Design** - Generate speech from voice description text
- 🎬 **Script Studio** - Multi-character dialogue generation with speaker mapping
- 📡 **Streaming Generation** - Real-time audio streaming for long text
- 🏋️ **LoRA Fine-tuning** - Fine-tune models with your own datasets via LoRA
- 🌐 **Web Interface** - Responsive and modern web UI built with FastAPI + HTMX + Jinja2
- 📦 **Batch Processing** - Support for batch audio generation
- 📜 **History Management** - SQLite-based history tracking with search, filter, and pagination
- 🌍 **Multi-language** - Internationalization support (i18n) for Chinese, English, Japanese, Korean
- ⚡ **Multi-GPU Backend** - Support for NVIDIA CUDA, AMD ROCM, Intel XPU, Apple MPS, and CPU
- 🔥 **GPU Acceleration** - Optimized for GPU-based inference with adaptive VRAM management
- 🔊 **9 Official Speakers** - Pre-configured voice personas covering various voice types

## 🚀 Quick Start (Windows)

### Prerequisites

- **Operating System**: Windows 10/11 (64-bit)
- **Python**: 3.12+ (bundled WinPython included, or install your own)
- **GPU**: NVIDIA GPU (CUDA) / AMD GPU (ROCM) / Intel GPU (XPU) (recommended for optimal performance)
  - Both integrated and discrete GPUs are supported
  - Minimum 6.5GB VRAM required for VoxCPM2 model
- **VC Redistributable**: Visual C++ Redistributable (included in `VC运行库/` folder)

### Installation Steps

#### Method 1: Use Bundled WinPython (Recommended)

1. **Download or clone this repository**:
   ```bash
   git clone https://github.com/ReSerendipity/TTS_MultiModel.git
   cd TTS_MultiModel
   ```

2. **Install VC Redistributable** (if not already installed):
   - Run `VC运行库\VC_redist.x64.exe`

3. **Install dependencies and setup**:
   ```bash
   install.bat
   ```

4. **Download required models** (see [Model Download](#model-download) section)

5. **Start the application**:
   ```bash
   start.bat
   ```

#### Method 2: Use Your Own Python Environment

1. **Install Python 3.12+** from [python.org](https://www.python.org/downloads/)

2. **Clone and install dependencies**:
   ```bash
   git clone https://github.com/ReSerendipity/TTS_MultiModel.git
   cd TTS_MultiModel
   pip install -r requirements.txt
   ```

3. **Download required models**

4. **Start the application**:
   ```bash
   python bin\clean_launch.py
   ```

## 🤖 Model Download

The following models need to be downloaded separately and placed in the `pretrained_models/` directory:

### Required Models

| Model | Description | Directory |
|-------|-------------|-----------|
| VoxCPM2 | Main TTS model | `pretrained_models/VoxCPM2/` |
| SenseVoiceSmall | ASR (Automatic Speech Recognition) model | `pretrained_models/SenseVoiceSmall/` |
| speech_zipenhancer | Audio denoiser model | `pretrained_models/speech_zipenhancer/` |

Download from [HuggingFace](https://huggingface.co/) or [ModelScope](https://modelscope.cn/).

### Model Download Script (Optional)

If a `download_models.py` script is included, you can use it to automate the download:
```bash
python download_models.py
```

## 📁 Project Structure

```
TTS_MultiModel/
├── bin/                          # Application binaries and scripts
│   ├── integrated_app/          # Main application code
│   │   ├── routes/             # API route handlers
│   │   ├── engines/            # TTS model engines
│   │   ├── training/           # Model training modules
│   │   ├── ui/                 # UI components
│   │   └── ...
│   ├── clean_launch.py         # Clean startup script
│   └── test_integration.py     # Integration tests
├── pretrained_models/           # Pre-trained model files (download separately)
├── personas/                    # Custom voice persona files
├── outputs/                     # Generated audio outputs
├── lora/                        # LoRA fine-tuned models
├── cache/                       # Cache directory
├── config.yaml                  # Application configuration
├── requirements.txt             # Python dependencies
├── docs/                        # Documentation
│   ├── MODEL_DOWNLOAD_GUIDE.md      # Model download and configuration guide
│   ├── MODEL_EXTENSION_GUIDE.md     # How to add new TTS engines
│   └── UI开发指南_README.md         # UI development guide
├── install.bat                  # Windows installation script
├── start.bat                    # Windows startup script
└── LICENSE                      # MIT License
```

## 🎯 Usage

### Starting the Application

1. **Quick Start** (Windows):
   ```bash
   start.bat
   ```

2. **Clean Launch** (clears cache):
   ```bash
   python bin/clean_launch.py
   ```

### Web Interface

After starting the application, open your browser and navigate to:
```
http://127.0.0.1:7869
```

The application will auto-open your browser when ready.

### Features Overview

#### Text-to-Speech
- Enter text in the input field
- Select voice persona or adjust parameters
- Click "Generate" to synthesize speech
- Download or play the generated audio

#### Voice Cloning
- Upload reference audio files (5-30 seconds recommended)
- Provide persona name and description
- Generate custom voice persona

#### Model Training
- Prepare training dataset (audio + text pairs)
- Configure training parameters
- Start fine-tuning process
- Monitor training progress in real-time

## ⚙️ Configuration

Edit `config.yaml` to customize:

- **Generation Parameters**:
  - `cfg_value`: Classifier-free guidance scale (default: 2.0)
  - `inference_timesteps`: Number of inference steps (default: 10)
  - `normalize`: Text normalization (default: True)
  - `denoise`: Audio denoising (default: True)
  - `retry_badcase`: Auto-retry on bad cases (default: True)

- **Server Settings**:
  - Port number (default: 7869)
  - Host address
  - GPU settings

## 🎙️ Official Speakers

The application comes with 9 pre-configured official speakers:

| Speaker | Description | Voice Type |
|---------|-------------|------------|
| Vivian | Sweet and youthful voice | 少女音 |
| 阿知 | Clean and bright youthful voice | 少年音 |
| 若彤 | Soft and cute loli voice | 萝莉音 |
| 成杰 | Calm and powerful young male voice | 青年男音 |
| 沐晴 | Intellectual and elegant voice | 少御音 |
| 御姐 | Mature and charismatic voice | 御姐音 |
| 旁白 | Standard broadcasting voice | 播音腔 |
| 老伯 | Experienced and deep elderly voice | 老年男音 |
| 少女 | Sweet and lovely young girl voice | 少女音 |

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Web Framework | FastAPI |
| Frontend | HTMX + Jinja2 |
| TTS Engine | VoxCPM2 |
| ASR Engine | SenseVoiceSmall |
| Audio Processing | speech_zipenhancer |
| Deep Learning | PyTorch + Transformers + FunASR |
| Language | Python 3.12+ |

## 🔧 Troubleshooting

### Common Issues

1. **VC Redistributable Error**:
   - Install `VC运行库\VC_redist.x64.exe`

2. **Model Not Found**:
   - Ensure models are downloaded and placed in `pretrained_models/`
   - Check directory structure matches expected layout

3. **GPU Not Detected**:
   - Install GPU-compatible PyTorch version (CUDA for NVIDIA, ROCM for AMD, XPU for Intel)
   - Verify GPU drivers are up to date
   - For integrated GPUs (iGPU), ensure system memory is sufficient (VoxCPM2 requires ~6.5GB VRAM)
   - Check `python -c "import torch; print(torch.cuda.is_available())"` or equivalent for your backend

4. **Port Already in Use**:
   - The app will auto-select an available port
   - Check console output for the actual URL

### Logs

Check `logs/app.log` for detailed error messages.

## 🧪 Development

### Running Tests

```bash
python bin/test_integration.py
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

## Recent Optimizations (v2.0)

### Architecture Improvements
- **Generation Template Pattern**: Extracted common generation logic into `generate_with_template()` in `_base.py`, eliminating ~176 lines of duplicate code across clone/design/ultimate modules
- **TTSEngine Protocol Enforcement**: Route layer now calls engines through `registry.get_current_engine()` protocol interface instead of direct module imports, enabling transparent engine switching
- **Unified Model Loading**: Merged `load_voxcpm2()` and `_load_voxcpm2_engine()` into shared `_do_load_voxcpm2_internal()`, eliminating ~60 lines of duplicate loading code

### Concurrency & Reliability
- **Semaphore Race Condition Fix**: Replaced TOCTOU-vulnerable `locked()` check with `asyncio.wait_for()` + proper `finally` release, ensuring no deadlocks
- **OOM Retry with Degraded Parameters**: OOM retries now automatically reduce inference steps and disable denoising instead of retrying with identical parameters (max 2 retries)
- **Unified Error Handling**: All engine exceptions now convert to TTSError subclasses with Chinese user-facing messages; added specialized handling for InsufficientVRAMError and EngineSwitchError

### Performance
- **Tiered GPU Memory Cleanup**: 3-tier cleanup strategy (lightweight → medium → heavy) with timing monitoring, replacing unconditional heavy cleanup
- **Smart Engine Switching**: Replaced `time.sleep(2)` with VRAM polling (0.5s intervals, max 5s), reducing switch latency
- **Adaptive Cache Enhancement**: Added memory footprint estimation, eviction tracking, and memory-based capacity limits to AdaptiveLRUCache

### Data & Text Processing
- **History Database Robustness**: Added corruption detection with auto-rebuild, orphan record cleanup, integrity validation, and file-missing tracking
- **Smart Text Splitting**: Improved `_find_best_split_point()` to avoid splitting inside quoted content, English abbreviations (Dr., U.S.A.), and decimal numbers (3.14)

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Report Bugs** - Open an issue with detailed reproduction steps
2. **Suggest Features** - Open an issue with the `enhancement` label
3. **Submit Code** - Fork → Branch → Commit → Push → Pull Request
4. **Improve Documentation** - Fix typos, add examples, translate content

## 📄 License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2025 Doro

## 📚 Documentation

- [Model Download Guide](docs/MODEL_DOWNLOAD_GUIDE.md) - How to download and configure models
- [Model Extension Guide](docs/MODEL_EXTENSION_GUIDE.md) - How to add new TTS engines
- [UI Development Guide](docs/UI开发指南_README.md) - Web UI development guide

## 🙏 Acknowledgments

- VoxCPM2 model and related technologies
- FastAPI and HTMX for the web interface framework
- All open-source contributors

---

**Note**: This project uses offline model loading by default. Ensure all required models are downloaded before first use.
