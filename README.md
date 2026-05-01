# TTS MultiModel

A complete TTS (Text-to-Speech) project integrating multiple models including Qwen3-TTS, SenseVoice, VoxCPM2, and speech enhancement, with a portable Python environment (WinPython) and custom voice personas.

## Project Structure

```
TTS_MultiModel/
├── bin/                          # Application binaries, configs, and tools
│   ├── integrated_app/           # Main application
│   ├── sox-14.4.2-win32/         # Audio processing tool
│   ├── ffmpeg.exe                # FFmpeg for audio/video processing
│   └── config.yaml               # Application configuration
├── docs/                         # Documentation
├── personas/                     # Custom voice profiles (audio + config)
├── faster-qwen3-tts-main/        # Faster Qwen3-TTS source code
├── WPy64-312101/                 # Portable Python 3.12 environment
│   └── python/                   # Python installation with all dependencies
├── VC运行库/                     # Visual C++ Redistributables (Windows)
└── setup.bat                     # One-click setup script (auto-generated)
```

## Prerequisites

Before using this project, you need to download the required model files. The code, Python environment, and tools are all included in this repository.

### Step 1: Download Model Files

The following directories must be populated with model files before running the application:

```
models/              # Main TTS models
pretrained_models/   # Pretrained models (SenseVoice, VoxCPM2, speech enhancer)
```

#### Required Models

| Directory | Model Name | Download Source | Description |
|-----------|-----------|-----------------|-------------|
| `models/Qwen3-TTS-12Hz-0.6B-Base` | Qwen3-TTS 0.6B Base | [HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) / [ModelScope](https://modelscope.cn/models/qwen/Qwen3-TTS-12Hz-0.6B-Base) | Base TTS model (0.6B parameters) |
| `models/Qwen3-TTS-12Hz-0.6B-CustomVoice` | Qwen3-TTS 0.6B CustomVoice | [HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice) / [ModelScope](https://modelscope.cn/models/qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice) | Custom voice TTS model |
| `models/Qwen3-TTS-12Hz-1.7B-Base` | Qwen3-TTS 1.7B Base | [HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) / [ModelScope](https://modelscope.cn/models/qwen/Qwen3-TTS-12Hz-1.7B-Base) | Base TTS model (1.7B parameters) |
| `models/Qwen3-TTS-12Hz-1.7B-CustomVoice` | Qwen3-TTS 1.7B CustomVoice | [HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) / [ModelScope](https://modelscope.cn/models/qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) | Custom voice TTS model (1.7B) |
| `models/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | Qwen3-TTS 1.7B VoiceDesign | [HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign) / [ModelScope](https://modelscope.cn/models/qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign) | Voice design model |
| `pretrained_models/SenseVoiceSmall` | SenseVoice Small | [HuggingFace](https://huggingface.co/FunAudioLLM/SenseVoiceSmall) / [ModelScope](https://modelscope.cn/models/iic/SenseVoiceSmall) | Speech recognition model |
| `pretrained_models/VoxCPM2` | VoxCPM2 | [HuggingFace](https://huggingface.co/openbmb/VoxCPM2) / [ModelScope](https://modelscope.cn/models/openbmb/VoxCPM2) | Voice processing model |
| `pretrained_models/speech_zipenhancer` | Speech ZipEnhancer | [HuggingFace](https://huggingface.co/modelscope/speech_zipenhancer_ans_multiloss_16k_base) | Speech enhancement model |

### Step 2: Quick Download Script

Create a `download_models.py` file in the project root with the following content to download all models automatically:

```python
"""
Model download script. Run with: python download_models.py
Requires: pip install modelscope huggingface_hub
"""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent

MODEL_LIST = [
    # (model_id, target_dir, source)
    ("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "models/Qwen3-TTS-12Hz-0.6B-Base"),
    ("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "models/Qwen3-TTS-12Hz-0.6B-CustomVoice"),
    ("Qwen/Qwen3-TTS-12Hz-1.7B-Base", "models/Qwen3-TTS-12Hz-1.7B-Base"),
    ("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "models/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    ("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"),
    ("FunAudioLLM/SenseVoiceSmall", "pretrained_models/SenseVoiceSmall"),
    ("openbmb/VoxCPM2", "pretrained_models/VoxCPM2"),
]

def download_model(model_id, target_dir):
    full_path = PROJECT_DIR / target_dir
    if full_path.exists() and list(full_path.glob("*.safetensors")):
        print(f"[OK] {model_id} already exists, skipping")
        return
    
    print(f"[Downloading] {model_id} -> {target_dir}")
    try:
        from modelscope import snapshot_download
        snapshot_download(model_id, local_dir=str(full_path))
        print(f"[Done] {model_id}")
    except Exception as e:
        print(f"[Error] Failed to download {model_id}: {e}")
        print("  Try: huggingface-cli download {model_id} --local-dir {target_dir}")

if __name__ == "__main__":
    print("Downloading required models...")
    for model_id, target_dir in MODEL_LIST:
        download_model(model_id, target_dir)
    print("\nAll downloads complete (or already existed).")
```

Run the script:
```bash
# Using the bundled Python environment
WPy64-312101\python\python.exe download_models.py

# Or with system Python (if modelscope is installed)
python download_models.py
```

### Step 3: Manual Download (Alternative)

If you prefer to download manually, use one of these commands:

```bash
# Using ModelScope (recommended for China users)
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3-TTS-12Hz-0.6B-Base', local_dir='models/Qwen3-TTS-12Hz-0.6B-Base')"

# Using HuggingFace
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-Base --local-dir models/Qwen3-TTS-12Hz-0.6B-Base
```

## Usage

### Launch the Application

```bash
# Using the bundled portable Python
WPy64-312101\python\python.exe bin\integrated_app\main.py

# Or double-click the batch file (if created)
```

### Available Personas

The `personas/` directory includes pre-configured voice profiles:
- gf1, 小林，御姐，旁白，李老师，南宫婉，韩立

Each persona includes:
- `.txt` - Voice description
- `.wav` - Reference audio
- `.pt` - Speaker embedding

### Using VC Redistributable

If you encounter missing DLL errors on first run, install the VC redistributable:

```
VC运行库\VC_redist.x64.exe
```

## Technical Details

- **Python Version**: 3.12.10 (WinPython portable distribution)
- **Main Framework**: PyTorch with CUDA support
- **TTS Models**: Qwen3-TTS (0.6B / 1.7B), VoxCPM2
- **ASR Model**: SenseVoiceSmall
- **Speech Enhancement**: ZipEnhancer
- **Audio Tools**: FFmpeg, SoX

## Notes

- Model files are **not** included in this repository due to their large size
- All model files must be downloaded separately before first use
- The bundled Python environment (`WPy64-312101/`) includes all required dependencies
- CUDA-compatible GPU recommended for real-time performance

## License

This project is provided for personal/educational use. All model weights are subject to their respective licenses:
- Qwen3-TTS: [Qwen License](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base)
- SenseVoice: [FunAudioLLM License](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)
- VoxCPM2: [OpenBMB License](https://huggingface.co/openbmb/VoxCPM2)
