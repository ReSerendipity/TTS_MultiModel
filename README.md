# TTS MultiModel

A powerful multi-model Text-to-Speech (TTS) web application with Gradio interface, supporting voice cloning, model training, and high-quality speech synthesis.

## Features

- **Multiple TTS Models**: Support for VoxCPM2 and other advanced TTS models
- **Voice Cloning**: Create custom voice personas with minimal audio samples
- **Model Training**: Fine-tune models with your own datasets
- **Web Interface**: User-friendly Gradio-based web UI
- **Batch Processing**: Support for batch audio generation
- **History Management**: Track and manage your generation history
- **Multi-language**: Internationalization support (i18n)
- **GPU Acceleration**: Optimized for GPU-based inference and training

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
├── LICENSE                      # MIT License
└── start.bat                    # Windows startup script
```

## Prerequisites

- **Operating System**: Windows 10/11 (64-bit)
- **Python**: 3.12+ (bundled WinPython included)
- **GPU**: NVIDIA GPU with CUDA support (recommended for optimal performance)
- **VC Redistributable**: Visual C++ Redistributable (included in `VC运行库/` folder)
- **FFmpeg**: Required for audio processing

## Installation

### Option 1: Use Bundled Python (Recommended for Windows)

1. Download or clone this repository:
   ```bash
   git clone https://github.com/Doro2047/TTS_MultiModel.git
   cd TTS_MultiModel
   ```

2. Install VC Redistributable (if not already installed):
   - Run `VC运行库/VC_redist.x64.exe`

3. Download required pre-trained models (see [Model Download](#model-download) section)

4. Launch the application:
   ```bash
   start.bat
   ```

### Option 2: Use Your Own Python Environment

1. Install Python 3.12+ from [python.org](https://www.python.org/downloads/)

2. Clone and install dependencies:
   ```bash
   git clone https://github.com/Doro2047/TTS_MultiModel.git
   cd TTS_MultiModel
   pip install -r requirements.txt
   ```

3. Download required pre-trained models

4. Launch:
   ```bash
   python bin/integrated_app/app_server.py
   ```

## Model Download

The following models need to be downloaded separately and placed in the `pretrained_models/` directory:

### Required Models

1. **VoxCPM2** - Main TTS model
   - Place in: `pretrained_models/VoxCPM2/`

2. **SenseVoiceSmall** - ASR (Automatic Speech Recognition) model
   - Place in: `pretrained_models/SenseVoiceSmall/`

3. **speech_zipenhancer** - Audio denoiser model
   - Place in: `pretrained_models/speech_zipenhancer/`

### Download Instructions

Models can be downloaded from:
- HuggingFace Hub
- ModelScope
- Official model repositories

Refer to each model's documentation for specific download instructions.

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

3. **Direct Launch**:
   ```bash
   python bin/integrated_app/app_server.py
   ```

### Web Interface

After starting the application, open your browser and navigate to:
```
http://localhost:7860
```

The port may vary depending on your configuration. Check the console output for the actual URL.

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
  - Port number
  - Host address
  - GPU settings

## Official Speakers

The application comes with 9 pre-configured official speakers:

| Speaker | Description | Voice Type |
|---------|-------------|------------|
| Vivian | 薇薇安 - Sweet and youthful voice | 少女音 |
| 阿知 | 阿知 - Clean and bright youthful voice | 少年音 |
| 若彤 | 若彤 - Soft and cute loli voice | 萝莉音 |
| 成杰 | 成杰 - Calm and powerful young male voice | 青年男音 |
| 沐晴 | 沐晴 | 知性优雅，温柔而有力量 | 少御音 |
| 御姐 | 御姐 - Mature and charismatic voice | 御姐音 |
| 旁白 | 旁白 - Standard broadcasting voice | 播音腔 |
| 老伯 | 老伯 - Experienced and deep elderly voice | 老年男音 |
| 少女 | 少女 - Sweet and lovely young girl voice | 少女音 |

## Troubleshooting

### Common Issues

1. **VC Redistributable Error**:
   - Install `VC运行库/VC_redist.x64.exe`

2. **Model Not Found**:
   - Ensure models are downloaded and placed in `pretrained_models/`
   - Check directory structure matches expected layout

3. **GPU Not Detected**:
   - Install CUDA-compatible PyTorch version
   - Verify NVIDIA drivers are up to date

4. **Port Already in Use**:
   - Change port in configuration
   - Or kill existing process using the port

### Logs

Check console output for detailed error messages. Log files are generated in the root directory if errors occur.

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

## Acknowledgments

- VoxCPM2 model and related technologies
- Gradio for the web interface framework
- All open-source contributors

## Contact

For issues, feature requests, or questions, please open an issue on GitHub.

---

**Note**: This project uses offline model loading by default. Ensure all required models are downloaded before first use.
