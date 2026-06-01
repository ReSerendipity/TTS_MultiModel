# TTS MultiModel

A powerful multi-model Text-to-Speech (TTS) web application with a modern FastAPI-based web interface, supporting voice cloning, model training, and high-quality speech synthesis.

## Features

- **Multiple TTS Models**: Support for VoxCPM2 and other advanced TTS models
- **Voice Cloning**: Create custom voice personas with minimal audio samples
- **Model Training**: Fine-tune models with your own datasets
- **Web Interface**: Responsive and modern web UI built with FastAPI + HTMX + Jinja2
- **Batch Processing**: Support for batch audio generation
- **History Management**: Track and manage your generation history
- **Multi-language**: Internationalization support (i18n)
- **GPU Acceleration**: Optimized for GPU-based inference and training

## Quick Start (Windows)

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
   git clone <your-repo-url>
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
   git clone <your-repo-url>
   cd TTS_MultiModel
   pip install -r requirements.txt
   ```

3. **Download required models**

4. **Start the application**:
   ```bash
   python bin\clean_launch.py
   ```

## Model Download

The following models need to be downloaded separately and placed in the `pretrained_models/` directory:

### Required Models

1. **VoxCPM2** - Main TTS model
   - Place in: `pretrained_models\VoxCPM2\`
   - Download from HuggingFace or ModelScope

2. **SenseVoiceSmall** - ASR (Automatic Speech Recognition) model
   - Place in: `pretrained_models\SenseVoiceSmall\`
   - Download from HuggingFace or ModelScope

3. **speech_zipenhancer** - Audio denoiser model
   - Place in: `pretrained_models\speech_zipenhancer\`
   - Download from HuggingFace or ModelScope

### Model Download Script (Optional)

If a `download_models.py` script is included, you can use it to automate the download:
```bash
python download_models.py
```

## Project Structure

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

## Usage

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

## Troubleshooting

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

## Development

### Running Tests

```bash
python bin/test_integration.py
```

### Code Structure

- **bin/integrated_app/**: Main application
  - `app_server.py`: Server entry point
  - `config.py`: Path and model configuration
  - `model_manager.py`: Model loading and management
  - `routes/`: HTTP route handlers
  - `engines/`: TTS model implementations
  - `training/`: Model training functionality

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Documentation

- [Model Download Guide](docs/MODEL_DOWNLOAD_GUIDE.md) - How to download and configure models
- [Model Extension Guide](docs/MODEL_EXTENSION_GUIDE.md) - How to add new TTS engines
- [UI Development Guide](docs/UI开发指南_README.md) - Web UI development guide

## Acknowledgments

- VoxCPM2 model and related technologies
- FastAPI and HTMX for the web interface framework
- All open-source contributors

## Contact

For issues, feature requests, or questions, please open an issue on GitHub.

---

**Note**: This project uses offline model loading by default. Ensure all required models are downloaded before first use.
