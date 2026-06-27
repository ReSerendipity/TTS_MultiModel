# TTS MultiModel

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C.svg?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

基于 VoxCPM2 和 IndexTTS 2.0 的多模型语音合成平台。支持声音设计、声音克隆、LoRA 微调训练与多角色剧本配音。内置 9 种预置音色，支持中英日韩多语言界面。

A powerful multi-model Text-to-Speech (TTS) web application with a modern FastAPI-based web interface, supporting voice cloning, model training, and high-quality speech synthesis.

## Features

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

## Quick Start

### Prerequisites

- **Operating System**: Windows 10/11 (64-bit) or Linux
- **Python**: 3.12+ (bundled WinPython included for Windows, or install your own)
- **GPU**: NVIDIA GPU (CUDA) recommended for optimal performance
  - Apple Silicon (MPS) is supported
  - Minimum 6.5GB VRAM required for VoxCPM2 model
  - CPU mode is available but slower
- **VC Redistributable** (Windows only): Visual C++ Redistributable (included in `VC运行库/` folder)

### Windows

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

3. **Download required models** (see [Model Download](#model-download) section)

4. **Start the application**:
   ```bash
   python bin\clean_launch.py
   ```

### Linux

1. **Install Python 3.12+** and dependencies:
   ```bash
   git clone https://github.com/ReSerendipity/TTS_MultiModel.git
   cd TTS_MultiModel
   chmod +x install.sh
   ./install.sh
   ```

2. **Download required models** (see [Model Download](#model-download) section)

3. **Start the application**:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

### Docker

1. **Build and run with Docker Compose**:
   ```bash
   docker compose up -d
   ```

2. **Or build manually**:
   ```bash
   docker build -t tts-multimodel .
   docker run -d --gpus all -p 7869:7869 \
     -v ./pretrained_models:/app/pretrained_models \
     -v ./outputs:/app/outputs \
     -v ./personas:/app/personas \
     tts-multimodel
   ```

3. Access the application at `http://localhost:7869`

> **Note**: Docker deployment requires NVIDIA GPU with nvidia-docker runtime installed. See [Dockerfile](Dockerfile) and [docker-compose.yml](docker-compose.yml) for details.

## Model Download

The following models need to be downloaded separately and placed in the `pretrained_models/` directory:

### Required Models (VoxCPM2 Engine)

| Model | Description | Directory |
|-------|-------------|-----------|
| VoxCPM2 | Main TTS model | `pretrained_models/VoxCPM2/` |
| SenseVoiceSmall | ASR (Automatic Speech Recognition) model | `pretrained_models/SenseVoiceSmall/` |
| speech_zipenhancer | Audio denoiser model | `pretrained_models/speech_zipenhancer/` |

### Required Models (IndexTTS 2.0 Engine)

| Model | Description | Directory |
|-------|-------------|-----------|
| IndexTTS2 | IndexTTS 2.0 TTS model | `pretrained_models/IndexTTS2/` |

Download from [HuggingFace](https://huggingface.co/) or [ModelScope](https://modelscope.cn/).

### Model Download Script (Optional)

Use the provided script to download IndexTTS 2.0 model:
```bash
python scripts/download_indextts2.py
```

For detailed download instructions, see [Model Download Guide](docs/MODEL_DOWNLOAD_GUIDE.md).

## Project Structure

```
TTS_MultiModel/
├── bin/                          # Application binaries and scripts
│   ├── integrated_app/          # Main application code
│   │   ├── routes/             # API route handlers
│   │   │   ├── generate/       # TTS generation routes (VoxCPM2, IndexTTS2)
│   │   │   └── system/         # System routes (health, GPU, settings)
│   │   ├── engines/            # TTS model engines
│   │   │   ├── voxcpm2/       # VoxCPM2 engine implementation
│   │   │   └── indextts2_engine.py  # IndexTTS 2.0 engine
│   │   ├── training/           # Model training modules
│   │   ├── middleware/         # HTTP middleware (CSRF, request ID)
│   │   ├── templates/          # Jinja2 HTML templates
│   │   ├── locales/            # i18n translation files (zh, en, ja, ko)
│   │   └── ui/                 # UI components
│   ├── clean_launch.py         # Clean startup script
│   ├── start_app.bat           # Windows startup batch file
│   └── ffmpeg.exe / ffplay.exe / ffprobe.exe  # Audio tools
├── data/                        # Runtime data files
├── docs/                        # Project documentation
│   ├── screenshots/            # Application screenshots
│   └── research/               # Research and analysis reports
├── examples/                    # Example data for training
├── personas/                    # Custom voice persona files
├── scripts/                     # Utility and debug scripts
├── tests/                       # Test suite
│   └── benchmarks/             # Performance benchmark tests
├── VC运行库/                    # Windows VC++ Redistributable installers
├── config.yaml                  # Application configuration
├── pyproject.toml               # Python project metadata
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker build configuration
├── docker-compose.yml           # Docker Compose configuration
├── install.bat / install.sh     # Installation scripts
├── start.bat / start.sh         # Startup scripts
└── LICENSE                      # MIT License
```

## Usage

### Starting the Application

1. **Quick Start** (Windows):
   ```bash
   start.bat
   ```

2. **Quick Start** (Linux):
   ```bash
   ./start.sh
   ```

3. **Clean Launch** (clears cache):
   ```bash
   python bin/clean_launch.py
   ```

4. **Docker**:
   ```bash
   docker compose up -d
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

#### Voice Design
- Describe the desired voice characteristics in text
- Generate speech matching the description

#### Script Studio
- Write multi-character dialogue scripts
- Assign speakers to dialogue lines
- Generate audio for the entire script

#### Model Training
- Prepare training dataset (audio + text pairs)
- Configure training parameters
- Start fine-tuning process
- Monitor training progress in real-time

## Configuration

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

For detailed parameter descriptions, see [Adjustable Parameters Guide](docs/ADJUSTABLE_PARAMETERS.md).

## Official Speakers

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

## Tech Stack

| Layer | Technology |
|-------|------------|
| Web Framework | FastAPI + Uvicorn |
| Frontend | HTMX + Jinja2 + Bootstrap |
| TTS Engine | VoxCPM2 + IndexTTS 2.0 |
| ASR Engine | SenseVoiceSmall |
| Audio Processing | speech_zipenhancer + FFmpeg + SoX |
| Deep Learning | PyTorch + Transformers + FunASR |
| Database | SQLite (history) |
| Language | Python 3.12+ |
| Containerization | Docker + Docker Compose |

## API Endpoints

The application provides REST API endpoints for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system/health` | GET | Health check |
| `/api/system/gpu` | GET | GPU utilization info |
| `/api/generate/voxcpm2/clone` | POST | Voice cloning (VoxCPM2) |
| `/api/generate/voxcpm2/design` | POST | Voice design (VoxCPM2) |
| `/api/generate/voxcpm2/script` | POST | Script generation (VoxCPM2) |
| `/api/generate/voxcpm2/streaming_sse` | POST | Streaming generation (SSE) |
| `/api/generate/indextts2/synthesize` | POST | TTS synthesis (IndexTTS 2.0) |
| `/api/model/load` | POST | Load TTS model |
| `/api/model/unload` | POST | Unload TTS model |
| `/api/history` | GET | Generation history |

> **Note**: Enable API authentication in `config.yaml` under `api_auth` section for production use.

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
   - Install `VC运行库\VC_redist.x64.exe`

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
4. **Improve Documentation** - Fix typos, add examples, translate content

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Doro2047

## Documentation

- [Model Download Guide](docs/MODEL_DOWNLOAD_GUIDE.md) - How to download and configure models
- [Model Extension Guide](docs/MODEL_EXTENSION_GUIDE.md) - How to add new TTS engines
- [IndexTTS2 Integration Guide](docs/INDEXTTS2_INTEGRATION_GUIDE.md) - IndexTTS 2.0 integration details
- [Project Architecture](docs/PROJECT_ARCHITECTURE.md) - System architecture overview
- [Adjustable Parameters](docs/ADJUSTABLE_PARAMETERS.md) - Configuration parameter reference
- [UI Development Guide](docs/UI开发指南_README.md) - Web UI development guide
- [Improvement Guidebook](docs/IMPROVEMENT_GUIDEBOOK.md) - Optimization and improvement suggestions

## Acknowledgments

- [VoxCPM2](https://github.com/OpenBMB/VoxCPM2) model by OpenBMB
- [IndexTTS2](https://github.com/IndexTeam/IndexTTS2) model by IndexTeam
- [FastAPI](https://fastapi.tiangolo.com/) and [HTMX](https://htmx.org/) for the web interface framework
- All open-source contributors

---

**Note**: This project uses offline model loading by default. Ensure all required models are downloaded before first use.
