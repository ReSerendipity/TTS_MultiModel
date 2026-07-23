# Examples

This directory contains example scripts demonstrating how to use TTS MultiModel's API and features.

## Prerequisites

1. Start the TTS MultiModel server:
   ```bash
   start.bat          # Windows
   ./start.sh         # Linux
   # or
   python bin/clean_launch.py
   ```

2. Install Python dependencies:
   ```bash
   pip install httpx
   ```

## Available Examples

| Script | Description |
|--------|-------------|
| `clone_example.py` | Voice cloning with reference audio |
| `api_example.py` | API usage (health check, GPU info, voice design, history) |
| `batch_example.py` | Batch text-to-speech generation |

## Quick Start

```bash
# Voice cloning example
python examples/clone_example.py

# API usage examples
python examples/api_example.py

# Batch generation example
python examples/batch_example.py
```

## Reference Audio

The `reference_speaker.wav` file is a sample reference audio for voice cloning experiments. You can replace it with your own `.wav` file (recommended: 5-15 seconds, clear speech, 16kHz+ sample rate).

## Training Data

The `train_data_example.jsonl` file shows the expected format for LoRA fine-tuning datasets. Each line is a JSON object with `text` and `audio_path` fields.
