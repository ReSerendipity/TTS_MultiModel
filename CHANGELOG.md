# Changelog

All notable changes to TTS MultiModel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-07-23

### Added
- GitHub reference repos analysis report (GITHUB_REFERENCE_REPOS_ANALYSIS.md)
- Cloned 5 new reference repos to `reference_repos/`:
  - Fish Speech (fishaudio/fish-speech) - SOTA multilingual TTS with 4B params
  - Chatterbox (resemble-ai/chatterbox) - Low-latency TTS family (Turbo/Nano/Multilingual)
  - OpenVoice (myshell-ai/OpenVoice) - Instant voice cloning with style control
  - VoxCPM (OpenBMB/VoxCPM) - VoxCPM2 upstream with tokenizer-free TTS
  - ChatTTS (2noise/ChatTTS) - Dialogue-optimized TTS with fine-grained control

### Added (Short-term Improvements)
- **CLI Batch Enhancement** (`cli.py`): JSON/CSV input support, output format (WAV/MP3), engine selection, progress reporting with ETA
- **Emotion Tag System** (`emotion_tags.py`): 30+ emotion/style tags inspired by Fish Speech, bracket/parenthetical/Chinese tag formats, tag validation, control instruction generation
- **Neural Watermarking** (`watermark.py`): Spread-spectrum audio watermarking inspired by Chatterbox Perth, invisible watermark with payload encoding, detection and verification
- **vLLM Acceleration Backend** (`vllm_backend.py`): Optional vLLM integration for high-throughput LLM inference, automatic fallback to PyTorch, model compatibility checker
- **v2.0.2 Config**: Emotion tags, watermark, and vLLM configuration options in `config.yaml`
- **Optional Dependencies**: Added `vllm` and `watermark` optional dependency groups in `pyproject.toml`

### Added (Medium-term Design Documents)
- `docs/MODEL_TIERING_PLAN.md`: Turbo/Nano/Standard tiered deployment (inspired by Chatterbox)
- `docs/TRAINING_TOOLCHAIN_PLAN.md`: Complete training pipeline: VAD splitting, ASR annotation, quality filtering, data packing
- `docs/RL_ALIGNMENT_PLAN.md`: GRPO reinforcement learning alignment with multi-dimension rewards (inspired by Fish Speech)
- `docs/TENSORRT_INTEGRATION_PLAN.md`: TensorRT-LLM integration for 2-4x inference acceleration (inspired by CosyVoice)

### Added (Long-term Design Documents)
- `docs/DIALECT_SUPPORT_PLAN.md`: Chinese dialect expansion via LoRA adapters (inspired by CosyVoice 18+ dialects)
- `docs/MULTI_SPEAKER_PLAN.md`: Multi-speaker token generation for script dubbing (inspired by Fish Speech)
- `docs/EDGE_DEPLOYMENT_PLAN.md`: Edge device deployment via ONNX Runtime / llama.cpp / GGUF quantization
- `docs/OPENAI_COMPATIBLE_API.md`: OpenAI-compatible `/v1/audio/speech` API endpoint design

### Key Findings
- Fish Speech represents current SOTA with 80+ languages and RL alignment
- Chatterbox's model tiering strategy (Turbo/Nano/Multilingual) is worth adopting
- VoxCPM's deployment ecosystem (Nano-vLLM, vLLM-Omni) provides acceleration options
- GPT-SoVITS offers the most complete training toolchain
- CosyVoice's TensorRT-LLM integration achieves 4x inference speedup

## [2.0.0] - 2026-06-04

### Added
- Dual-engine architecture: VoxCPM2 + IndexTTS 2.0 support
- IndexTTS 2.0 engine integration with synthesize API
- Docker support (Dockerfile + docker-compose.yml)
- Internationalization (i18n) for Chinese, English, Japanese, Korean
- Settings page for runtime configuration
- Test suite with unit, integration, and benchmark tests
- CI/CD pipeline with GitHub Actions (lint, test, build)
- Model download script for IndexTTS 2.0
- Multi-GPU backend support (CUDA, ROCM, XPU, MPS, CPU)

### Changed
- Refactored VoxCPM2 engine architecture
- Reorganized project root directory structure
- Extracted shared components to reduce frontend/backend coupling
- Improved GPU memory management and OOM detection
- Enhanced configuration with Pydantic validation

### Fixed
- Settings page toggle button visibility issue
- Cleaned up deprecated modules and test files
- Updated .gitignore for runtime and test artifacts

## [1.0.0] - 2026-05-01

### Added
- Initial release with VoxCPM2 engine
- Voice cloning (controllable + ultimate clone)
- Voice design from text description
- Script Studio for multi-character dialogue
- Streaming generation (SSE)
- LoRA fine-tuning training
- 9 official speaker personas
- Web interface with FastAPI + HTMX + Jinja2
- SQLite history management
- Windows WinPython bundled environment
- Installation scripts for Windows and Linux
