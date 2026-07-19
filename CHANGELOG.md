# Changelog

All notable changes to TTS MultiModel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
